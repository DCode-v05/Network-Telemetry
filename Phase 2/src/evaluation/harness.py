# src/evaluation/harness.py
import os
import csv
import logging
import numpy as np
from tqdm import tqdm
from typing import List, Dict, Any

import config as cfg
from src.pipeline.loader import load_cesnet_sample
from src.injector.anomaly_injector import AnomalyInjector
from src.evaluation.metrics import compute_metrics, aggregate_metrics, EvalMetrics
from src.detectors.base import DetectorBase

logger = logging.getLogger(__name__)


def _sanitise(text: str) -> str:
    """
    Replace all non-ASCII characters in detector names with ASCII equivalents.
    Prevents UnicodeEncodeError when writing CSV on Windows (cp1252 encoding).
    """
    replacements = {
        "\u03bb": "lambda",   # λ
        "\u03b4": "delta",    # δ
        "\u03bc": "mu",       # μ
        "\u03c3": "sigma",    # σ
        "\u03b1": "alpha",    # α
        "\u2019": "'",
        "\u2014": "-",
        "\u2013": "-",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final safety net: encode to ASCII, replacing anything still non-ASCII
    return text.encode("ascii", errors="replace").decode("ascii")


def build_detectors(window_size: int) -> List[DetectorBase]:
    from src.detectors.zscore               import ZScoreDetector
    from src.detectors.mad                  import MADDetector
    from src.detectors.ewma                 import EWMADetector
    from src.detectors.cusum                import CUSUMDetector
    from src.detectors.page_hinkley         import PageHinkleyDetector
    from src.detectors.sliding_window_stats import SlidingWindowStatsDetector

    p = cfg.DETECTORS
    # Warmup must be at least 20 regardless of window_size to get a stable baseline
    warmup = max(window_size, 20)

    return [
        ZScoreDetector(
            window_size = window_size,
            threshold   = p["zscore"]["threshold"],
        ),
        MADDetector(
            window_size = window_size,
            threshold   = p["mad"]["threshold"],
        ),
        EWMADetector(
            lambda_  = p["ewma"]["lambda_"],
            L        = p["ewma"]["L"],
            warmup   = warmup,
        ),
        CUSUMDetector(
            k       = p["cusum"]["k"],
            h       = p["cusum"]["h"],
            warmup  = warmup,
        ),
        PageHinkleyDetector(
            delta   = p["page_hinkley"]["delta"],
            lambda_ = p["page_hinkley"]["lambda_"],
            alpha   = p["page_hinkley"]["alpha"],
            warmup  = warmup,
        ),
        SlidingWindowStatsDetector(
            window_size = window_size,
            stat        = p["sliding_window"]["stat"],
            threshold   = p["sliding_window"]["threshold"],
            warmup      = max(window_size * 2, 40),
        ),
    ]


def run_evaluation() -> List[Dict[str, Any]]:
    os.makedirs(cfg.RESULTS_CSV_DIR, exist_ok=True)
    os.makedirs(cfg.RESULTS_PLT_DIR, exist_ok=True)

    logger.info("Loading CESNET dataset...")
    series_list = load_cesnet_sample(
        data_dir   = cfg.DATA_DIR,
        signal_col = cfg.PRIMARY_SIGNAL,
        max_ips    = cfg.MAX_IPS,
    )
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
    # Sanitise all string values to ASCII — prevents Windows cp1252 crash
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
    # Sanitise strings
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
