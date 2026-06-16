"""
Phase 3 detection demo — show WHICH anomaly is detected and by WHICH layer.

The benchmark harness only reports aggregate metrics (TPR/FPR/F1). This tool
answers the operational question instead:

    "For a given signal, where did the TwoLayerEnsemble fire, and which layer
     (spike L1 / sustained L2) caught it?"

It uses the real Phase 3 architecture (`TwoLayerEnsemble` built exactly like the
harness builds it), plus standalone copies of the spike and sustained layers so
attribution can distinguish spike-only / sustained-only / both.

How detection is read:
  - ensemble.update(x).is_anomaly  -> alarm on this sample (Layer1 OR Layer2)
  - ensemble.update(x).alarm_value -> 1.0 = spike fired, 2.0 = sustained only, 0 = none
  - compare alarm positions against the injector's ground-truth window
    [inject_start, inject_end):
        alarm inside  the window -> true positive (correctly caught the anomaly)
        alarm outside the window -> false positive (false alarm)
  - "detected" = at least one alarm within DETECTION_WINDOW samples of inject_start
    (same rule the harness uses for detection latency).

Usage
-----
    python evaluation/detect_demo.py                       # all 4 anomaly types
    python evaluation/detect_demo.py --anomaly burst       # one type, with timeline
    python evaluation/detect_demo.py --window 20 --max_ips 5
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from _phase2_bridge import (
    ZScoreDetector, MADDetector, EWMADetector, CUSUMDetector,
    AnomalyInjector, load_cesnet_sample,
)
from ensemble.confirmation_gate  import ConfirmationGate
from ensemble.voting_layer       import VotingLayer
from ensemble.two_layer_ensemble import TwoLayerEnsemble


# ---------------------------------------------------------------------------
# Build the architecture exactly like evaluation/harness.py does
# ---------------------------------------------------------------------------
def _make_base(key: str, window_size: int):
    p      = cfg.DETECTORS
    warmup = max(window_size, 20)
    if key == "zscore":
        return ZScoreDetector(window_size=window_size, threshold=p["zscore"]["threshold"])
    if key == "mad":
        return MADDetector(window_size=window_size, threshold=p["mad"]["threshold"])
    if key == "ewma":
        return EWMADetector(lambda_=p["ewma"]["lambda_"], L=p["ewma"]["L"], warmup=warmup)
    if key == "cusum":
        return CUSUMDetector(k=p["cusum"]["k"], h=p["cusum"]["h"], warmup=warmup)
    raise KeyError(f"detector key not used by the ensemble: {key}")


def _build_layer(layer_cfg, layer_name, window_size, n):
    children = [
        ConfirmationGate(_make_base(k, window_size), n_consecutive=n)
        for k in layer_cfg["members"]
    ]
    return VotingLayer(children=children, mode=layer_cfg["voting_mode"], layer_name=layer_name)


def build_parts(window_size: int):
    """Return (ensemble, standalone_spike, standalone_sustained).

    The ensemble has its own fresh layer instances; the two standalone layers
    are independent copies used only to attribute spike-vs-sustained per sample.
    All three are deterministic, so on the same signal the standalone layers'
    OR equals the ensemble's alarm.
    """
    n        = cfg.ENSEMBLE["confirmation_n"]
    spike_c  = cfg.ENSEMBLE["spike_layer"]
    sustain_c = cfg.ENSEMBLE["sustained_layer"]

    ensemble = TwoLayerEnsemble(
        spike_layer     = _build_layer(spike_c,   "Spike",     window_size, n),
        sustained_layer = _build_layer(sustain_c, "Sustained", window_size, n),
    )
    standalone_spike     = _build_layer(spike_c,   "Spike",     window_size, n)
    standalone_sustained = _build_layer(sustain_c, "Sustained", window_size, n)
    return ensemble, standalone_spike, standalone_sustained


# ---------------------------------------------------------------------------
# Run the ensemble on one injected series and attribute every alarm
# ---------------------------------------------------------------------------
def analyse(series, anomaly_type, window_size, seed, position=None):
    injector = AnomalyInjector(random_seed=seed)
    params   = cfg.INJECTION[anomaly_type].copy()
    if position is not None:
        params["position"] = position
    inj = injector.inject(signal=series, anomaly_type=anomaly_type, params=params)

    ensemble, spike, sustained = build_parts(window_size)
    ens_res   = ensemble.run_on_series(inj.signal)
    spike_res = spike.run_on_series(inj.signal)
    sust_res  = sustained.run_on_series(inj.signal)

    ens_alarm  = np.array([1 if r.is_anomaly else 0 for r in ens_res], dtype=np.int8)
    spike_fire = np.array([1 if r.is_anomaly else 0 for r in spike_res], dtype=np.int8)
    sust_fire  = np.array([1 if r.is_anomaly else 0 for r in sust_res], dtype=np.int8)

    # Sanity: the ensemble alarm IS the OR of the two layers (the architecture rule).
    assert np.array_equal(ens_alarm, (spike_fire | sust_fire)), \
        "ensemble alarm != spike OR sustained (architecture mismatch)"

    start, end = inj.inject_start, inj.inject_end
    labels     = inj.labels
    dwin       = cfg.DETECTION_WINDOW
    n_normal   = int((labels == 0).sum())

    in_mask  = np.zeros(len(labels), dtype=bool)
    in_mask[start:end] = True

    alarm_idx     = np.flatnonzero(ens_alarm == 1)
    in_window     = [i for i in alarm_idx if start <= i < end]
    near_window   = [i for i in alarm_idx if start <= i < start + dwin]   # "timely"
    out_window    = [i for i in alarm_idx if not (start <= i < end)]

    detected = len(near_window) > 0
    first_in = near_window[0] if near_window else (in_window[0] if in_window else None)
    latency  = (first_in - start) if first_in is not None else -1

    def layer_of(i):
        if spike_fire[i] and sust_fire[i]: return "BOTH"
        if spike_fire[i]:                  return "Spike(L1)"
        if sust_fire[i]:                   return "Sustained(L2)"
        return "-"

    caught_by = layer_of(first_in) if first_in is not None else "-"

    # Per-layer behaviour: hits inside the anomaly vs false alarms outside it.
    l1_in  = int(spike_fire[in_mask].sum());  l1_out = int(spike_fire[~in_mask].sum())
    l2_in  = int(sust_fire[in_mask].sum());   l2_out = int(sust_fire[~in_mask].sum())

    return {
        "anomaly":      anomaly_type,
        "start":        start,
        "end":          end,
        "n_anom":       int(labels.sum()),
        "n_normal":     n_normal,
        "detected":     detected,
        "latency":      latency,
        "caught_by":    caught_by,
        "tp_alarms":    len(in_window),
        "fp_alarms":    len(out_window),
        "l1_in": l1_in, "l1_out": l1_out, "l1_fpr": l1_out / n_normal if n_normal else 0.0,
        "l2_in": l2_in, "l2_out": l2_out, "l2_fpr": l2_out / n_normal if n_normal else 0.0,
        "ens_alarm":    ens_alarm,
        "spike_fire":   spike_fire,
        "sust_fire":    sust_fire,
        "labels":       labels,
        "layer_of":     layer_of,
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------
def print_summary(rows):
    print("\n" + "=" * 78)
    print("  WHICH ANOMALY IS DETECTED  (TwoLayerEnsemble, Phase 3 architecture)")
    print("=" * 78)
    print(f"  {'anomaly':<14} {'window':>13}  {'detected':>8}  {'latency':>7}  "
          f"{'caught_by':>14}  {'TP':>3} {'FP':>4}")
    print("  " + "-" * 74)
    for r in rows:
        win = f"[{r['start']},{r['end']})"
        det = "YES" if r["detected"] else "no"
        lat = f"{r['latency']}" if r["latency"] >= 0 else "-"
        print(f"  {r['anomaly']:<14} {win:>13}  {det:>8}  {lat:>7}  "
              f"{r['caught_by']:>14}  {r['tp_alarms']:>3} {r['fp_alarms']:>4}")
    print("  " + "-" * 74)
    print("  detected = alarm within DETECTION_WINDOW samples of the injection start")
    print("  caught_by: which layer fired first  |  TP = alarms inside the anomaly,"
          "  FP = alarms outside")


def print_layers(rows):
    print("\n  PER-LAYER BEHAVIOUR  (in = fires inside anomaly, out = false alarms, fpr = out/normal)")
    print(f"  {'anomaly':<14}  {'L1 Spike(AND)':>22}  {'L2 Sustained(OR)':>24}")
    print(f"  {'':<14}  {'in':>5} {'out':>7} {'fpr':>7}  {'in':>5} {'out':>7} {'fpr':>7}")
    print("  " + "-" * 66)
    for r in rows:
        print(f"  {r['anomaly']:<14}  "
              f"{r['l1_in']:>5} {r['l1_out']:>7} {r['l1_fpr']:>7.3f}  "
              f"{r['l2_in']:>5} {r['l2_out']:>7} {r['l2_fpr']:>7.3f}")
    print("  " + "-" * 66)
    print("  Healthy: L1 catches burst/transient at near-zero FPR; L2 catches rate_shift/")
    print("  drift. A saturated L2 (fpr -> ~0.8) means EWMA/CUSUM are tripping on this")
    print("  series's own structure, not the injected anomaly.")


def print_timeline(r, pad_before=3, pad_after=None):
    dwin = cfg.DETECTION_WINDOW
    if pad_after is None:
        pad_after = dwin + 2
    lo = max(0, r["start"] - pad_before)
    hi = min(len(r["ens_alarm"]), r["end"] + pad_after)
    print(f"\n  --- timeline for '{r['anomaly']}'  (sample: truth | ensemble | layer) ---")
    print(f"  {'idx':>6}  {'truth':>5}  {'alarm':>5}  layer")
    for i in range(lo, hi):
        truth = "ANOM" if r["labels"][i] else "."
        alarm = "FIRE" if r["ens_alarm"][i] else "."
        layer = r["layer_of"](i) if r["ens_alarm"][i] else ""
        marker = "  <-- inside anomaly" if (r["start"] <= i < r["end"]) else ""
        print(f"  {i:>6}  {truth:>5}  {alarm:>5}  {layer:<14}{marker}")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Phase 3 — which anomaly is detected, by which layer")
    ap.add_argument("--anomaly", default=None,
                    help="one of burst|rate_shift|gradual_drift|transient (default: all)")
    ap.add_argument("--window",  type=int, default=20)
    ap.add_argument("--max_ips", type=int, default=5)
    ap.add_argument("--seed",    type=int, default=None, help="injection seed (default cfg.RANDOM_SEED)")
    ap.add_argument("--position", type=int, default=None, help="fixed injection index (default: random)")
    ap.add_argument("--timeline", action="store_true",
                    help="also print a per-sample timeline around each injection")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else cfg.RANDOM_SEED

    series_list = load_cesnet_sample(
        data_dir=cfg.DATA_DIR, signal_col=cfg.PRIMARY_SIGNAL, max_ips=args.max_ips,
    )
    if not series_list:
        raise SystemExit("No CESNET series loaded — check cfg.DATA_DIR.")
    # pick the first series long enough for any injection
    ip_id, series = next(((i, s) for i, s in series_list if len(s) >= 200), series_list[0])
    print(f"Using IP series '{ip_id}' ({len(series)} samples), window={args.window}, seed={seed}")

    anomalies = [args.anomaly] if args.anomaly else list(cfg.ANOMALY_TYPES)
    rows = [analyse(series, a, args.window, seed, args.position) for a in anomalies]

    print_summary(rows)
    print_layers(rows)
    if args.timeline or args.anomaly:
        for r in rows:
            print_timeline(r)


if __name__ == "__main__":
    main()
