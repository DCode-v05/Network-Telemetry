# dashboard/export_data.py
#
# Exports the Phase 2 evaluation CSVs into a single JSON snapshot consumed by the
# React (Vite + ECharts) dashboard in `dashboard/web/`.
#
# Run standalone:   python dashboard/export_data.py
# The React app imports the emitted file directly, so `npm run build` bakes the
# data into the static bundle (no server required to view the result).

import json
import os
import sys
from datetime import datetime

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG_CSV     = os.path.join(BASE_DIR, "results", "csv", "aggregated_results.csv")
RAW_CSV     = os.path.join(BASE_DIR, "results", "csv", "raw_trial_results.csv")
OUTPUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "web", "src", "data.json")

# ── Config (mirrors generate_report.py) ───────────────────────────────────────
ANOMALY_TYPES = ["burst", "rate_shift", "gradual_drift", "transient"]
WINDOW_SIZES  = [10, 20, 30, 50]
DET_ORDER     = ["ZScore", "MAD", "EWMA", "CUSUM", "PageHinkley", "SlidingWindow"]

DET_COLORS = {
    "ZScore":        "#1D9E75",
    "MAD":           "#7F77DD",
    "EWMA":          "#D85A30",
    "CUSUM":         "#378ADD",
    "PageHinkley":   "#BA7517",
    "SlidingWindow": "#888780",
}

# Human-friendly metadata used by the UI ---------------------------------------
DET_LABELS = {
    "ZScore":        "Z-Score",
    "MAD":           "MAD",
    "EWMA":          "EWMA",
    "CUSUM":         "CUSUM",
    "PageHinkley":   "Page-Hinkley",
    "SlidingWindow": "Sliding Window",
}
DET_BLURB = {
    "ZScore":        "Standard-deviation deviation from the rolling mean.",
    "MAD":           "Median absolute deviation — robust to outliers.",
    "EWMA":          "Exponentially weighted moving average control chart.",
    "CUSUM":         "Cumulative sum change-point detector.",
    "PageHinkley":   "Sequential drift / mean-shift detector.",
    "SlidingWindow": "Windowed mean ± k·σ threshold.",
}
ANOMALY_LABELS = {
    "burst":         "Burst",
    "rate_shift":    "Rate Shift",
    "gradual_drift": "Gradual Drift",
    "transient":     "Transient",
}


def short_name(full_name: str) -> str:
    """'ZScore(w=10, thr=3.0)' -> 'ZScore'."""
    return str(full_name).split("(")[0]


def _round(v, n=4):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def load() -> pd.DataFrame:
    if not os.path.exists(AGG_CSV):
        print(f"[export] ERROR: aggregated CSV not found: {AGG_CSV}")
        print("Run the evaluation first:  python main.py")
        sys.exit(1)
    df = pd.read_csv(AGG_CSV)
    df["detector_short"] = df["detector"].apply(short_name)
    return df


def build_aggregated(df: pd.DataFrame) -> list:
    cols = [
        "tpr_mean", "tpr_std", "fpr_mean", "fpr_std",
        "precision_mean", "precision_std", "f1_mean", "f1_std",
        "detection_rate", "avg_detection_latency", "stdev_detection_latency",
    ]
    out = []
    for _, r in df.iterrows():
        row = {
            "detector":      r["detector_short"],
            "detector_full": r["detector"],
            "anomaly_type":  r["anomaly_type"],
            "window_size":   int(r["window_size"]),
            "n_trials":      int(r["n_trials"]),
        }
        for c in cols:
            row[c] = _round(r[c])
        out.append(row)
    return out


def build_winners(df: pd.DataFrame) -> dict:
    """Best detector (by mean F1 across windows) per anomaly type."""
    winners = {}
    grouped = (df.groupby(["detector_short", "anomaly_type"])
                 .agg(f1=("f1_mean", "mean"), tpr=("tpr_mean", "mean"),
                      fpr=("fpr_mean", "mean"))
                 .reset_index())
    for at in ANOMALY_TYPES:
        sub = grouped[grouped["anomaly_type"] == at]
        if sub.empty:
            continue
        best = sub.loc[sub["f1"].idxmax()]
        winners[at] = {
            "detector": best["detector_short"],
            "f1":  _round(best["f1"]),
            "tpr": _round(best["tpr"]),
            "fpr": _round(best["fpr"]),
        }
    return winners


def build_kpis(df: pd.DataFrame) -> dict:
    best_row = df.loc[df["f1_mean"].idxmax()]
    # Most reliable = highest detection_rate averaged across grid
    det_rate = (df.groupby("detector_short")["detection_rate"].mean())
    cleanest = (df.groupby("detector_short")["fpr_mean"].mean())
    return {
        "n_detectors":   int(df["detector_short"].nunique()),
        "n_anomalies":   int(df["anomaly_type"].nunique()),
        "n_windows":     int(df["window_size"].nunique()),
        "n_trials":      int(df["n_trials"].max()),
        "total_runs":    int(len(df) * int(df["n_trials"].max())),
        "best_f1": {
            "value":    _round(best_row["f1_mean"]),
            "detector": short_name(best_row["detector"]),
            "anomaly":  best_row["anomaly_type"],
            "window":   int(best_row["window_size"]),
        },
        "top_detection_rate": {
            "value":    _round(det_rate.max()),
            "detector": det_rate.idxmax(),
        },
        "cleanest": {
            "value":    _round(cleanest.min()),
            "detector": cleanest.idxmin(),
        },
    }


def main():
    df = load()

    payload = {
        "meta": {
            "phase":        2,
            "title":        "Network Anomaly Detection",
            "subtitle":     "Single-detector benchmark on CESNET ISP telemetry",
            "generated":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dataset":      "CESNET-TimeSeries24",
            "anomaly_types": ANOMALY_TYPES,
            "window_sizes":  WINDOW_SIZES,
            "detector_order": DET_ORDER,
            "colors":        DET_COLORS,
            "det_labels":    DET_LABELS,
            "det_blurb":     DET_BLURB,
            "anomaly_labels": ANOMALY_LABELS,
        },
        "kpis":       build_kpis(df),
        "winners":    build_winners(df),
        "aggregated": build_aggregated(df),
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[export] Wrote {len(payload['aggregated'])} rows -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
