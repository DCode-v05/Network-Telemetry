"""
Phase 3 metrics report — Accuracy, F1 Score, and TPR vs FPR per detector.

Phase 2's metric module (and therefore the Phase 3 harness) records per-trial
TPR, FPR, precision, F1, and the raw confusion-matrix counts (tp, fp, tn, fn)
but never an *accuracy* column. This module adds accuracy on top of the existing
`raw_trial_results.csv` without re-running the 6,720-trial sweep:

    accuracy = (TP + TN) / (TP + TN + FP + FN)      per trial, then averaged.

It produces three views, each aggregated per detector across every anomaly type,
window size, and trial present in the CSV (sorted best-first):

    1. ACCURACY PER DETECTOR     — mirrors the reference screenshot
    2. F1 SCORE PER DETECTOR
    3. TPR vs FPR PER DETECTOR

Usage
-----
    python evaluation/metrics_report.py
    python evaluation/metrics_report.py --raw results/csv/raw_trial_results.csv
    python evaluation/metrics_report.py --per_anomaly        # add per-anomaly breakdown
    python evaluation/metrics_report.py --csv_out results/csv/metrics_report.csv

Notes
-----
- Accuracy is reported for completeness because it was requested, but on this
  class-imbalanced task (5-20 anomalous samples in a ~2,000-sample series) it is
  dominated by true negatives and flatters detectors that rarely fire. F1 and
  the TPR/FPR pair remain the honest headline metrics — see PHASE_3_DOCUMENTATION
  section 14.
"""
import argparse
import csv
import os
from collections import defaultdict
from typing import Any, Dict, List


_FAMILY_ORDER = [
    "ZScore", "MAD", "EWMA", "CUSUM", "PageHinkley", "SlidingWindow",
    "GatedCUSUM", "GatedEWMA", "GatedMAD", "GatedZScore",
    "Spike_AND", "Sustained_OR", "Spike_OR", "TwoLayerEnsemble",
]


def _family(name: str) -> str:
    """'MAD(w=20, thr=3.5)' -> 'MAD'; 'Spike_AND(GatedMAD+GatedZScore)' -> 'Spike_AND'."""
    return name.split("(", 1)[0]


def load_raw(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "detector":     str(r["detector"]),
                "anomaly_type": str(r["anomaly_type"]),
                "window_size":  int(r["window_size"]),
                "trial":        int(r["trial"]),
                "tpr":          float(r["tpr"]),
                "fpr":          float(r["fpr"]),
                "precision":    float(r["precision"]),
                "f1":           float(r["f1"]),
                "tp":           int(r["tp"]),
                "fp":           int(r["fp"]),
                "tn":           int(r["tn"]),
                "fn":           int(r["fn"]),
            })
    return rows


def _accuracy(row: Dict[str, Any]) -> float:
    denom = row["tp"] + row["tn"] + row["fp"] + row["fn"]
    return (row["tp"] + row["tn"]) / denom if denom else 0.0


def aggregate_per_detector(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record per detector: mean accuracy / f1 / tpr / fpr / precision over all trials."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[r["detector"]].append(r)

    out: List[Dict[str, Any]] = []
    for detector, group in groups.items():
        n = len(group)
        out.append({
            "detector":  detector,
            "n_trials":  n,
            "accuracy":  sum(_accuracy(r) for r in group) / n,
            "f1":        sum(r["f1"]  for r in group) / n,
            "tpr":       sum(r["tpr"] for r in group) / n,
            "fpr":       sum(r["fpr"] for r in group) / n,
            "precision": sum(r["precision"] for r in group) / n,
        })
    return out


def _order_key(detector: str):
    fam = _family(detector)
    idx = _FAMILY_ORDER.index(fam) if fam in _FAMILY_ORDER else len(_FAMILY_ORDER)
    return (idx, detector)


def _print_table(title: str, records: List[Dict[str, Any]], columns: List[str]) -> None:
    name_w = max(len("detector"), max(len(r["detector"]) for r in records))
    header = f"  {'detector':>{name_w}}"
    for c in columns:
        header += f"  {c:>10}"
    print(f"\n=== {title} ===")
    print(header)
    print("  " + "-" * (name_w + len(columns) * 12))
    for r in records:
        line = f"  {r['detector']:>{name_w}}"
        for c in columns:
            line += f"  {r[c]:>10.6f}"
        print(line)


def report(rows: List[Dict[str, Any]], per_anomaly: bool = False) -> List[Dict[str, Any]]:
    per_det = aggregate_per_detector(rows)

    windows = sorted({r["window_size"] for r in rows})
    anomalies = sorted({r["anomaly_type"] for r in rows})
    n_trials = sorted({r["trial"] for r in rows})
    print("=" * 72)
    print("  PHASE 3 METRICS REPORT")
    print(f"  rows={len(rows)}  detectors={len(per_det)}  "
          f"windows={windows}  anomalies={anomalies}  trials/cell={len(n_trials)}")
    print("=" * 72)

    by_acc = sorted(per_det, key=lambda r: r["accuracy"], reverse=True)
    _print_table("ACCURACY PER DETECTOR", by_acc, ["accuracy"])

    by_f1 = sorted(per_det, key=lambda r: r["f1"], reverse=True)
    _print_table("F1 SCORE PER DETECTOR", by_f1, ["f1"])

    by_roster = sorted(per_det, key=lambda r: _order_key(r["detector"]))
    _print_table("TPR vs FPR PER DETECTOR", by_roster, ["tpr", "fpr"])

    if per_anomaly:
        _print_per_anomaly(rows)

    return per_det


def _print_per_anomaly(rows: List[Dict[str, Any]]) -> None:
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["anomaly_type"], r["detector"])].append(r)

    by_anomaly: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for (anomaly, detector), group in groups.items():
        n = len(group)
        by_anomaly[anomaly].append({
            "detector": detector,
            "accuracy": sum(_accuracy(r) for r in group) / n,
            "f1":       sum(r["f1"]  for r in group) / n,
            "tpr":      sum(r["tpr"] for r in group) / n,
            "fpr":      sum(r["fpr"] for r in group) / n,
        })

    for anomaly in sorted(by_anomaly):
        recs = sorted(by_anomaly[anomaly], key=lambda r: r["f1"], reverse=True)
        _print_table(f"{anomaly.upper()} — per detector (sorted by F1)",
                     recs, ["accuracy", "f1", "tpr", "fpr"])


def _write_csv(per_det: List[Dict[str, Any]], path: str) -> None:
    recs = sorted(per_det, key=lambda r: r["accuracy"], reverse=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["detector", "n_trials", "accuracy",
                                          "f1", "tpr", "fpr", "precision"])
        w.writeheader()
        for r in recs:
            w.writerow({k: r[k] for k in w.fieldnames})
    print(f"\nWrote per-detector metrics -> {path}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_raw = os.path.join(here, "..", "results", "csv", "raw_trial_results.csv")

    ap = argparse.ArgumentParser(description="Phase 3 Accuracy / F1 / TPR-vs-FPR report")
    ap.add_argument("--raw", default=os.path.normpath(default_raw),
                    help="Path to raw_trial_results.csv")
    ap.add_argument("--per_anomaly", action="store_true",
                    help="Also print a per-anomaly-type breakdown")
    ap.add_argument("--csv_out", default=None,
                    help="Optional path to write the per-detector summary CSV")
    args = ap.parse_args()

    if not os.path.isfile(args.raw):
        raise SystemExit(f"raw CSV not found: {args.raw}\nRun `python main.py` first.")

    rows = load_raw(args.raw)
    per_det = report(rows, per_anomaly=args.per_anomaly)

    if args.csv_out:
        _write_csv(per_det, args.csv_out)


if __name__ == "__main__":
    main()
