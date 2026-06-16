"""
Phase 3 dashboard data export.

Reads the Phase 3 evaluation CSVs (and, when available, the Phase 2 aggregated
CSV for the cross-phase comparison), computes every figure's data via the same
pure functions the legacy report used, and writes a single JSON snapshot for the
React (Vite + ECharts) app in `dashboard/web/`.

Run standalone:   python dashboard/export_data.py
"""
import json
import os
import sys
from datetime import datetime

import pandas as pd

_HERE   = os.path.dirname(os.path.abspath(__file__))
_PHASE3 = os.path.dirname(_HERE)
if _PHASE3 not in sys.path:
    sys.path.insert(0, _PHASE3)

from evaluation.phase3_metrics import (
    load_aggregated_csv, load_raw_csv,
    ensemble_vs_best_single, gate_fp_reduction, per_anomaly_winner,
    _is_ensemble_name, _is_gated_name,
)

AGG_CSV     = os.path.join(_PHASE3, "results", "csv", "aggregated_results.csv")
RAW_CSV     = os.path.join(_PHASE3, "results", "csv", "raw_trial_results.csv")
P2_AGG_CSV  = os.path.join(_PHASE3, "..", "Phase 2", "results", "csv", "aggregated_results.csv")
OUTPUT_JSON = os.path.join(_HERE, "web", "src", "data.json")

ANOMALY_TYPES = ["burst", "rate_shift", "gradual_drift", "transient"]

DET_ORDER = [
    "ZScore", "MAD", "EWMA", "CUSUM", "PageHinkley", "SlidingWindow",
    "GatedZScore", "GatedMAD", "GatedEWMA", "GatedCUSUM",
    "Spike_AND", "Spike_OR", "Sustained_OR", "TwoLayerEnsemble",
]
DET_COLORS = {
    "ZScore": "#1D9E75", "MAD": "#7F77DD", "EWMA": "#D85A30", "CUSUM": "#378ADD",
    "PageHinkley": "#BA7517", "SlidingWindow": "#888780",
    "GatedZScore": "#A8D5C2", "GatedMAD": "#BBB6E8", "GatedEWMA": "#EBB7A2", "GatedCUSUM": "#A2C4E8",
    "Spike_AND": "#E0457B", "Spike_OR": "#F09EBC", "Sustained_OR": "#7BC8B7",
    "TwoLayerEnsemble": "#F4C152",
}
DET_LABELS = {
    "ZScore": "Z-Score", "MAD": "MAD", "EWMA": "EWMA", "CUSUM": "CUSUM",
    "PageHinkley": "Page-Hinkley", "SlidingWindow": "Sliding Window",
    "GatedZScore": "Gated Z-Score", "GatedMAD": "Gated MAD",
    "GatedEWMA": "Gated EWMA", "GatedCUSUM": "Gated CUSUM",
    "Spike_AND": "Spike · AND", "Spike_OR": "Spike · OR",
    "Sustained_OR": "Sustained · OR", "TwoLayerEnsemble": "Two-Layer Ensemble",
}
DET_GROUP = {
    **{d: "individual" for d in ["ZScore", "MAD", "EWMA", "CUSUM", "PageHinkley", "SlidingWindow"]},
    **{d: "gated" for d in ["GatedZScore", "GatedMAD", "GatedEWMA", "GatedCUSUM"]},
    **{d: "ensemble" for d in ["Spike_AND", "Spike_OR", "Sustained_OR", "TwoLayerEnsemble"]},
}
ANOMALY_LABELS = {
    "burst": "Burst", "rate_shift": "Rate Shift",
    "gradual_drift": "Gradual Drift", "transient": "Transient",
}


def short_name(full_name: str) -> str:
    base = str(full_name).split("(", 1)[0]
    return base.split("[", 1)[0]


def _round(v, n=4):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def load_df() -> pd.DataFrame:
    if not os.path.exists(AGG_CSV):
        print(f"[export] ERROR: aggregated CSV not found: {AGG_CSV}")
        print("Run the evaluation first:  python main.py")
        sys.exit(1)
    df = pd.read_csv(AGG_CSV)
    df["detector_short"] = df["detector"].apply(short_name)
    return df


def build_aggregated(df: pd.DataFrame) -> list:
    cols = ["tpr_mean", "tpr_std", "fpr_mean", "fpr_std", "precision_mean",
            "precision_std", "f1_mean", "f1_std", "detection_rate",
            "avg_detection_latency", "stdev_detection_latency"]
    out = []
    for _, r in df.iterrows():
        row = {"detector": r["detector_short"], "detector_full": r["detector"],
               "anomaly_type": r["anomaly_type"], "window_size": int(r["window_size"]),
               "n_trials": int(r["n_trials"])}
        for c in cols:
            row[c] = _round(r[c])
        out.append(row)
    return out


def build_gate_fp(raw_rows) -> list:
    red = gate_fp_reduction(raw_rows)
    out = []
    for fam, m in red.items():
        out.append({
            "family": fam,
            "fp_reduction_pct": _round(m["fp_reduction_pct"]),
            "tp_retention_pct": _round(m["tp_retention_pct"]),
            "baseline_fp": int(m["baseline_fp"]),
            "gated_fp": int(m["gated_fp"]),
            "baseline_tp": int(m["baseline_tp"]),
            "gated_tp": int(m["gated_tp"]),
        })
    out.sort(key=lambda x: (x["fp_reduction_pct"] or 0), reverse=True)
    return out


def build_ensemble_vs_best(agg_rows) -> list:
    deltas = ensemble_vs_best_single(agg_rows, ensemble_name="TwoLayerEnsemble")
    if not deltas:
        return []
    df = pd.DataFrame(deltas)
    g = df.groupby("anomaly_type").agg(
        ensemble_f1=("ensemble_f1", "mean"), best_f1=("best_single_f1", "mean"),
        ensemble_tpr=("ensemble_tpr", "mean"), ensemble_fpr=("ensemble_fpr", "mean"),
        best_tpr=("best_single_tpr", "mean"), best_fpr=("best_single_fpr", "mean"),
        best_name=("best_single", lambda s: s.value_counts().index[0]),
    ).reindex(ANOMALY_TYPES)
    out = []
    for at in ANOMALY_TYPES:
        if at not in g.index or pd.isna(g.loc[at, "ensemble_f1"]):
            continue
        out.append({
            "anomaly_type": at,
            "best_name": short_name(g.loc[at, "best_name"]),
            "best_f1": _round(g.loc[at, "best_f1"]),
            "best_tpr": _round(g.loc[at, "best_tpr"]),
            "best_fpr": _round(g.loc[at, "best_fpr"]),
            "ensemble_f1": _round(g.loc[at, "ensemble_f1"]),
            "ensemble_tpr": _round(g.loc[at, "ensemble_tpr"]),
            "ensemble_fpr": _round(g.loc[at, "ensemble_fpr"]),
        })
    return out


def build_phase_compare(agg_rows) -> list:
    if not os.path.isfile(P2_AGG_CSV):
        return []
    try:
        p2_rows = load_aggregated_csv(P2_AGG_CSV)
    except Exception as e:
        print(f"[export] Phase 2 comparison skipped: {e}")
        return []
    p2_winner = per_anomaly_winner(p2_rows)
    deltas = ensemble_vs_best_single(agg_rows, ensemble_name="TwoLayerEnsemble")
    if not deltas:
        return []
    p3 = pd.DataFrame(deltas).groupby("anomaly_type")["ensemble_f1"].mean()
    out = []
    for at in ANOMALY_TYPES:
        if at in p2_winner and at in p3.index:
            out.append({
                "anomaly_type": at,
                "phase2_winner": short_name(p2_winner[at]["detector"]),
                "phase2_f1": _round(p2_winner[at]["f1_mean"]),
                "phase3_ensemble_f1": _round(float(p3[at])),
            })
    return out


def build_leaderboard(df: pd.DataFrame) -> list:
    """Mean metrics across anomaly types per detector (matches metrics_report)."""
    g = (df.groupby("detector_short")
           .agg(f1=("f1_mean", "mean"), tpr=("tpr_mean", "mean"),
                fpr=("fpr_mean", "mean"), precision=("precision_mean", "mean"),
                det_rate=("detection_rate", "mean"))
           .reset_index())
    out = []
    for _, r in g.iterrows():
        out.append({
            "detector": r["detector_short"],
            "group": DET_GROUP.get(r["detector_short"], "individual"),
            "f1": _round(r["f1"]), "tpr": _round(r["tpr"]), "fpr": _round(r["fpr"]),
            "precision": _round(r["precision"]), "det_rate": _round(r["det_rate"]),
        })
    out.sort(key=lambda x: (x["fpr"] if x["fpr"] is not None else 1))
    return out


def build_winners(df: pd.DataFrame) -> dict:
    """Best *individual* detector per anomaly (by mean F1), for the headline."""
    indiv = df[df["detector_short"].apply(
        lambda d: not _is_ensemble_name(d) and not _is_gated_name(d))]
    grouped = (indiv.groupby(["detector_short", "anomaly_type"])
                    .agg(f1=("f1_mean", "mean"), tpr=("tpr_mean", "mean"),
                         fpr=("fpr_mean", "mean")).reset_index())
    winners = {}
    for at in ANOMALY_TYPES:
        sub = grouped[grouped["anomaly_type"] == at]
        if sub.empty:
            continue
        best = sub.loc[sub["f1"].idxmax()]
        winners[at] = {"detector": best["detector_short"], "f1": _round(best["f1"]),
                       "tpr": _round(best["tpr"]), "fpr": _round(best["fpr"])}
    return winners


def build_kpis(df: pd.DataFrame, gate_fp: list, evb: list) -> dict:
    ens = df[df["detector_short"] == "TwoLayerEnsemble"]
    ens_fpr = float(ens["fpr_mean"].mean()) if len(ens) else None
    ens_tpr = float(ens["tpr_mean"].mean()) if len(ens) else None
    reds = [g["fp_reduction_pct"] for g in gate_fp if g["fp_reduction_pct"] is not None]
    mean_red = sum(reds) / len(reds) if reds else 0.0
    best_gate = gate_fp[0] if gate_fp else None
    wins = sum(1 for e in evb if e["ensemble_fpr"] is not None
               and e["best_fpr"] is not None and e["ensemble_fpr"] <= e["best_fpr"])
    return {
        "n_detectors": int(df["detector_short"].nunique()),
        "n_anomalies": int(df["anomaly_type"].nunique()),
        "n_windows": int(df["window_size"].nunique()),
        "n_trials": int(df["n_trials"].max()),
        "total_runs": int(len(df) * int(df["n_trials"].max())),
        "mean_gate_fp_reduction": _round(mean_red),
        "best_gate": {"family": best_gate["family"], "value": best_gate["fp_reduction_pct"]} if best_gate else None,
        "ensemble_fpr": _round(ens_fpr),
        "ensemble_tpr": _round(ens_tpr),
        "fpr_wins": {"count": wins, "total": len(evb)},
    }


def main():
    df = load_df()
    agg_rows = load_aggregated_csv(AGG_CSV)
    raw_rows = load_raw_csv(RAW_CSV)

    gate_fp = build_gate_fp(raw_rows)
    evb = build_ensemble_vs_best(agg_rows)

    payload = {
        "meta": {
            "phase": 3,
            "title": "Two-Layer Ensemble",
            "subtitle": "Confirmation-gated ensemble of the Phase 2 finalists",
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dataset": "CESNET-TimeSeries24",
            "anomaly_types": ANOMALY_TYPES,
            "window_sizes": sorted(df["window_size"].unique().tolist()),
            "detector_order": DET_ORDER,
            "colors": DET_COLORS,
            "det_labels": DET_LABELS,
            "det_group": DET_GROUP,
            "anomaly_labels": ANOMALY_LABELS,
            "confirmation_n": 2,
        },
        "kpis": build_kpis(df, gate_fp, evb),
        "winners": build_winners(df),
        "leaderboard": build_leaderboard(df),
        "gate_fp": gate_fp,
        "ensemble_vs_best": evb,
        "phase_compare": build_phase_compare(agg_rows),
        "aggregated": build_aggregated(df),
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[export] Wrote {len(payload['aggregated'])} agg rows, "
          f"{len(gate_fp)} gate families, {len(evb)} ensemble cells "
          f"-> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
