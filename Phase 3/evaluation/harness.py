"""
Phase 3 evaluation harness.

Adapted from `Phase 2/src/evaluation/harness.py`. Trial loop and CSV writer
are unchanged so output schemas remain comparable. The detector roster in
`build_detectors()` is rewritten to include the Phase 3 ensemble variants:

    individual baselines  : 6  (ZScore, MAD, EWMA, CUSUM, PageHinkley, SlidingWindow)
    gated baselines       : 4  (GatedMAD, GatedZScore, GatedEWMA, GatedCUSUM)
    voting layers         : 3  (Spike_AND, Sustained_OR, Spike_OR ablation)
    top-level ensemble    : 1  (TwoLayerEnsemble)
                          ----
                            14 detectors per window-size sweep
"""
import csv
import logging
import os
import sys
from typing import Any, Dict, List

import numpy as np
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg                                      # Phase 3 config
from _phase2_bridge import (                              # Phase 2 imports via bridge
    DetectorBase,
    ZScoreDetector, MADDetector, EWMADetector,
    CUSUMDetector, PageHinkleyDetector, SlidingWindowStatsDetector,
    AnomalyInjector,
    load_cesnet_sample,
    compute_metrics, aggregate_metrics, EvalMetrics,
)
from ensemble.confirmation_gate  import ConfirmationGate
from ensemble.voting_layer       import VotingLayer
from ensemble.two_layer_ensemble import TwoLayerEnsemble

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sanitisation — verbatim from Phase 2 harness so CSV stays Windows-cp1252-safe
# ---------------------------------------------------------------------------
def _sanitise(text: str) -> str:
    replacements = {
        "λ": "lambda",
        "δ": "delta",
        "μ": "mu",
        "σ": "sigma",
        "α": "alpha",
        "’": "'",
        "—": "-",
        "–": "-",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("ascii", errors="replace").decode("ascii")


# ---------------------------------------------------------------------------
# Detector factory — Phase 3 expanded roster
# ---------------------------------------------------------------------------
def _make_individuals(window_size: int) -> Dict[str, DetectorBase]:
    """Return the six Phase 2 detectors keyed by config short-name."""
    p      = cfg.DETECTORS
    warmup = max(window_size, 20)
    return {
        "zscore":          ZScoreDetector(window_size=window_size,
                                          threshold=p["zscore"]["threshold"]),
        "mad":             MADDetector(window_size=window_size,
                                       threshold=p["mad"]["threshold"]),
        "ewma":            EWMADetector(lambda_=p["ewma"]["lambda_"],
                                        L=p["ewma"]["L"], warmup=warmup),
        "cusum":           CUSUMDetector(k=p["cusum"]["k"],
                                         h=p["cusum"]["h"], warmup=warmup),
        "page_hinkley":    PageHinkleyDetector(delta=p["page_hinkley"]["delta"],
                                               lambda_=p["page_hinkley"]["lambda_"],
                                               alpha=p["page_hinkley"]["alpha"],
                                               warmup=warmup),
        "sliding_window":  SlidingWindowStatsDetector(window_size=window_size,
                                                      stat=p["sliding_window"]["stat"],
                                                      threshold=p["sliding_window"]["threshold"],
                                                      warmup=max(window_size * 2, 40)),
    }


def build_detectors(window_size: int) -> List[DetectorBase]:
    """
    Return ~14 detectors per window-size sweep.

    Ordering: individuals → gated singles → voting layers → top-level ensemble.
    Output is exactly the order shown in the Phase 3 dashboard so detectors
    appear left-to-right by complexity.
    """
    n          = cfg.ENSEMBLE["confirmation_n"]
    spike_cfg  = cfg.ENSEMBLE["spike_layer"]
    sustain_cfg = cfg.ENSEMBLE["sustained_layer"]

    detectors: List[DetectorBase] = []

    # 1. Individual baselines (re-benchmarked for parity)
    individuals = _make_individuals(window_size)
    if cfg.ENSEMBLE.get("include_individual_baselines", True):
        # Stable ordering matching Phase 2's harness
        for key in ("zscore", "mad", "ewma", "cusum", "page_hinkley", "sliding_window"):
            detectors.append(individuals[key])

    # 2. Gated baselines (only for the four detectors used in either layer)
    if cfg.ENSEMBLE.get("include_gated_baselines", True):
        gated_keys = sorted(set(spike_cfg["members"]) | set(sustain_cfg["members"]))
        for key in gated_keys:
            child = _make_individuals(window_size)[key]   # fresh instance per gate
            detectors.append(ConfirmationGate(child, n_consecutive=n))

    # 3. Voting layers
    spike_children = [
        ConfirmationGate(_make_individuals(window_size)[k], n_consecutive=n)
        for k in spike_cfg["members"]
    ]
    spike_layer_AND = VotingLayer(
        children   = spike_children,
        mode       = spike_cfg["voting_mode"],
        layer_name = "Spike",
    )
    detectors.append(spike_layer_AND)

    sustained_children = [
        ConfirmationGate(_make_individuals(window_size)[k], n_consecutive=n)
        for k in sustain_cfg["members"]
    ]
    sustained_layer = VotingLayer(
        children   = sustained_children,
        mode       = sustain_cfg["voting_mode"],
        layer_name = "Sustained",
    )
    detectors.append(sustained_layer)

    if cfg.ENSEMBLE.get("include_or_variant", True):
        spike_or_children = [
            ConfirmationGate(_make_individuals(window_size)[k], n_consecutive=n)
            for k in spike_cfg["members"]
        ]
        detectors.append(VotingLayer(
            children   = spike_or_children,
            mode       = "OR",
            layer_name = "Spike",
        ))

    # 4. Top-level ensemble — uses FRESH spike/sustained instances so children
    #    aren't shared with steps 3 (which would couple state across detectors).
    top_spike_children = [
        ConfirmationGate(_make_individuals(window_size)[k], n_consecutive=n)
        for k in spike_cfg["members"]
    ]
    top_sustained_children = [
        ConfirmationGate(_make_individuals(window_size)[k], n_consecutive=n)
        for k in sustain_cfg["members"]
    ]
    detectors.append(TwoLayerEnsemble(
        spike_layer = VotingLayer(
            children   = top_spike_children,
            mode       = spike_cfg["voting_mode"],
            layer_name = "Spike",
        ),
        sustained_layer = VotingLayer(
            children   = top_sustained_children,
            mode       = sustain_cfg["voting_mode"],
            layer_name = "Sustained",
        ),
    ))

    return detectors


# ---------------------------------------------------------------------------
# Trial loop — unchanged from Phase 2 except for output paths
# ---------------------------------------------------------------------------
def run_evaluation() -> List[Dict[str, Any]]:
    os.makedirs(cfg.RESULTS_CSV_DIR, exist_ok=True)
    os.makedirs(cfg.RESULTS_PLT_DIR, exist_ok=True)

    logger.info("Loading CESNET dataset...")
    series_list = load_cesnet_sample(
        data_dir   = cfg.DATA_DIR,
        signal_col = cfg.PRIMARY_SIGNAL,
        max_ips    = cfg.MAX_IPS,
    )
    cap = getattr(cfg, "MAX_SAMPLES_PER_SERIES", None)
    if cap is not None and cap > 0:
        cropped = []
        for ip_id, s in series_list:
            cropped.append((ip_id, s[:cap] if len(s) > cap else s))
        series_list = cropped
        logger.info(f"Cropped each series to {cap} samples for runtime control.")
    logger.info(f"Loaded {len(series_list)} IP series.")

    injector = AnomalyInjector(random_seed=cfg.RANDOM_SEED)
    rng      = np.random.default_rng(cfg.RANDOM_SEED + 1)

    all_trial_results: List[EvalMetrics] = []

    total = (
        len(cfg.WINDOW_SIZES)
        * len(cfg.ANOMALY_TYPES)
        * len(build_detectors(10))
        * cfg.N_TRIALS
    )

    with tqdm(total=total, desc="Evaluating") as pbar:
        for window_size in cfg.WINDOW_SIZES:
            detectors = build_detectors(window_size)

            for anomaly_type in cfg.ANOMALY_TYPES:
                inj_params = cfg.INJECTION[anomaly_type].copy()

                for trial in range(cfg.N_TRIALS):
                    ip_id, series = series_list[
                        int(rng.integers(0, len(series_list)))
                    ]

                    try:
                        result = injector.inject(
                            signal       = series,
                            anomaly_type = anomaly_type,
                            params       = inj_params,
                        )
                    except ValueError as e:
                        logger.warning(f"Injection failed for {ip_id}: {e}")
                        pbar.update(len(detectors))
                        continue

                    for detector in detectors:
                        detector.reset()
                        raw_results = detector.run_on_series(result.signal)
                        predictions = np.array(
                            [1 if r.is_anomaly else 0 for r in raw_results],
                            dtype=np.int8,
                        )

                        metrics = compute_metrics(
                            labels           = result.labels,
                            predictions      = predictions,
                            inject_start     = result.inject_start,
                            detector_name    = detector.name,
                            anomaly_type     = anomaly_type,
                            window_size      = window_size,
                            trial            = trial,
                            detection_window = cfg.DETECTION_WINDOW,
                        )
                        all_trial_results.append(metrics)
                        pbar.update(1)

    _save_raw_results(all_trial_results)
    aggregated = _aggregate_all(all_trial_results)
    _save_aggregated_results(aggregated)

    logger.info(f"Evaluation complete. Results saved to {cfg.RESULTS_CSV_DIR}")
    return aggregated


def _save_raw_results(results: List[EvalMetrics]) -> None:
    path = os.path.join(cfg.RESULTS_CSV_DIR, "raw_trial_results.csv")
    if not results:
        return
    rows = [r.to_dict() for r in results]
    rows = [
        {k: (_sanitise(v) if isinstance(v, str) else v) for k, v in row.items()}
        for row in rows
    ]
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Raw results -> {path}")


def _aggregate_all(results: List[EvalMetrics]) -> List[Dict[str, Any]]:
    groups: Dict[tuple, List[EvalMetrics]] = {}
    for m in results:
        key = (m.detector_name, m.anomaly_type, m.window_size)
        groups.setdefault(key, []).append(m)

    aggregated = []
    for key, group in sorted(groups.items()):
        aggregated.append(aggregate_metrics(group))
    return aggregated


def _save_aggregated_results(aggregated: List[Dict[str, Any]]) -> None:
    path = os.path.join(cfg.RESULTS_CSV_DIR, "aggregated_results.csv")
    if not aggregated:
        return
    clean = [
        {k: (_sanitise(v) if isinstance(v, str) else v) for k, v in row.items()}
        for row in aggregated
    ]
    keys = list(clean[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(clean)
    logger.info(f"Aggregated results -> {path}")
