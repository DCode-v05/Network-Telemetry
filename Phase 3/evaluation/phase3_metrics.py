"""
Phase 3 metric aggregations.

Pure functions that consume the same CSVs Phase 2 emits
(`raw_trial_results.csv`, `aggregated_results.csv`) plus the new ensemble rows
Phase 3 produces. They answer the three Phase 3 headline questions:

1. Which detector wins on each anomaly type?            → per_anomaly_winner
2. Does the ensemble beat the best single detector?      → ensemble_vs_best_single
3. How many FPs does the confirmation gate eliminate?    → gate_fp_reduction
"""
import csv
from collections import defaultdict
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_aggregated_csv(path: str) -> List[Dict[str, Any]]:
    """Load aggregated_results.csv with numeric columns coerced to float/int."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "detector":                str(r["detector"]),
                "anomaly_type":            str(r["anomaly_type"]),
                "window_size":             int(r["window_size"]),
                "n_trials":                int(r["n_trials"]),
                "tpr_mean":                float(r["tpr_mean"]),
                "tpr_std":                 float(r["tpr_std"]),
                "fpr_mean":                float(r["fpr_mean"]),
                "fpr_std":                 float(r["fpr_std"]),
                "precision_mean":          float(r["precision_mean"]),
                "precision_std":           float(r["precision_std"]),
                "f1_mean":                 float(r["f1_mean"]),
                "f1_std":                  float(r["f1_std"]),
                "detection_rate":          float(r["detection_rate"]),
                "avg_detection_latency":   float(r["avg_detection_latency"]),
                "stdev_detection_latency": float(r["stdev_detection_latency"]),
            })
    return rows


def load_raw_csv(path: str) -> List[Dict[str, Any]]:
    """Load raw_trial_results.csv with int FP/TP/etc. coerced."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "detector":          str(r["detector"]),
                "anomaly_type":      str(r["anomaly_type"]),
                "window_size":       int(r["window_size"]),
                "trial":             int(r["trial"]),
                "tpr":               float(r["tpr"]),
                "fpr":               float(r["fpr"]),
                "precision":         float(r["precision"]),
                "f1":                float(r["f1"]),
                "detection_latency": int(r["detection_latency"]),
                "tp": int(r["tp"]),
                "fp": int(r["fp"]),
                "tn": int(r["tn"]),
                "fn": int(r["fn"]),
            })
    return rows


# ---------------------------------------------------------------------------
# 1. Per-anomaly winner
# ---------------------------------------------------------------------------
def per_anomaly_winner(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """For each anomaly_type, return the row with the highest f1_mean across all
    detectors and window sizes. Useful for the headline "best individual" table.
    """
    best: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        a = r["anomaly_type"]
        if a not in best or r["f1_mean"] > best[a]["f1_mean"]:
            best[a] = r
    return best


# ---------------------------------------------------------------------------
# 2. Ensemble vs best single
# ---------------------------------------------------------------------------
def _is_ensemble_name(name: str) -> bool:
    """Detector names produced by Phase 3 ensemble layer."""
    return name.startswith(("Spike_", "Sustained_", "TwoLayerEnsemble"))


def _is_gated_name(name: str) -> bool:
    return name.startswith("Gated")


def ensemble_vs_best_single(
    rows: List[Dict[str, Any]],
    ensemble_name: str = "TwoLayerEnsemble",
) -> List[Dict[str, Any]]:
    """For each (anomaly_type, window_size), compute deltas:

        Δ_TPR = ensemble.tpr_mean − best_single.tpr_mean
        Δ_FPR = ensemble.fpr_mean − best_single.fpr_mean   (negative is good)
        Δ_F1  = ensemble.f1_mean  − best_single.f1_mean
        Δ_lat = ensemble.avg_detection_latency − best_single.avg_detection_latency

    "best_single" = the non-ensemble, non-gated detector with the highest F1
    for that (anomaly, window) cell. Ties broken by lowest FPR.
    """
    by_cell: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cell[(r["anomaly_type"], r["window_size"])].append(r)

    deltas = []
    for (anomaly, window), cell_rows in sorted(by_cell.items()):
        ensemble_row = next(
            (r for r in cell_rows if r["detector"].startswith(ensemble_name)),
            None,
        )
        if ensemble_row is None:
            continue

        singles = [
            r for r in cell_rows
            if not _is_ensemble_name(r["detector"]) and not _is_gated_name(r["detector"])
        ]
        if not singles:
            continue
        best = max(singles, key=lambda r: (r["f1_mean"], -r["fpr_mean"]))

        deltas.append({
            "anomaly_type":      anomaly,
            "window_size":       window,
            "best_single":       best["detector"],
            "best_single_f1":    best["f1_mean"],
            "best_single_tpr":   best["tpr_mean"],
            "best_single_fpr":   best["fpr_mean"],
            "best_single_lat":   best["avg_detection_latency"],
            "ensemble_f1":       ensemble_row["f1_mean"],
            "ensemble_tpr":      ensemble_row["tpr_mean"],
            "ensemble_fpr":      ensemble_row["fpr_mean"],
            "ensemble_lat":      ensemble_row["avg_detection_latency"],
            "delta_f1":          ensemble_row["f1_mean"]  - best["f1_mean"],
            "delta_tpr":         ensemble_row["tpr_mean"] - best["tpr_mean"],
            "delta_fpr":         ensemble_row["fpr_mean"] - best["fpr_mean"],
            "delta_latency":     ensemble_row["avg_detection_latency"] - best["avg_detection_latency"],
        })
    return deltas


# ---------------------------------------------------------------------------
# 3. Confirmation gate FP reduction
# ---------------------------------------------------------------------------
_GATED_TO_BASE = {
    "GatedMAD":     "MAD",
    "GatedZScore":  "ZScore",
    "GatedEWMA":    "EWMA",
    "GatedCUSUM":   "CUSUM",
    "GatedPageHinkley":   "PageHinkley",
    "GatedSlidingWindow": "SlidingWindow",
}


def _detector_family(name: str) -> str:
    """Strip parameter suffix: 'MAD(w=20, thr=3.5)' -> 'MAD'."""
    return name.split("(", 1)[0]


def gate_fp_reduction(raw_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Per base detector, compute the FP reduction achieved by its gated variant.

    Sums TP, FP, TN, FN over all trials/cells per detector family. Compares the
    base family (e.g. "MAD") with its gated counterpart ("GatedMAD").

    Returns
    -------
    dict keyed by base family name with:
        baseline_fp        — total FPs across all trials for base detector
        gated_fp           — total FPs across all trials for gated detector
        fp_reduction_pct   — (baseline_fp - gated_fp) / baseline_fp  (0..1)
        baseline_tp        — total TPs for base
        gated_tp           — total TPs for gated
        tp_retention_pct   — gated_tp / baseline_tp (≤1: how much detection survived)
    """
    totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    for r in raw_rows:
        fam = _detector_family(r["detector"])
        totals[fam]["tp"] += r["tp"]
        totals[fam]["fp"] += r["fp"]
        totals[fam]["tn"] += r["tn"]
        totals[fam]["fn"] += r["fn"]

    out: Dict[str, Dict[str, float]] = {}
    for gated_fam, base_fam in _GATED_TO_BASE.items():
        if base_fam not in totals or gated_fam not in totals:
            continue
        bfp = totals[base_fam]["fp"]
        gfp = totals[gated_fam]["fp"]
        btp = totals[base_fam]["tp"]
        gtp = totals[gated_fam]["tp"]
        out[base_fam] = {
            "baseline_fp":      float(bfp),
            "gated_fp":         float(gfp),
            "fp_reduction_pct": (bfp - gfp) / bfp if bfp > 0 else 0.0,
            "baseline_tp":      float(btp),
            "gated_tp":         float(gtp),
            "tp_retention_pct": gtp / btp if btp > 0 else 0.0,
        }
    return out
