"""Export the cross-phase evaluation catalogue for the dashboard.

Combines the REAL committed results from all three empirical phases into one
`evaluation.json` (read-only from the research repo):

  * Phase 2 -- 6 single detectors on CESNET traffic (TPR / FPR / F1)
  * Phase 3 -- 14 detectors: 6 single + 4 confirmation-gated + 4 ensemble (FPR reduction)
  * Phase 4 -- 20 detectors scored on a two-axis intelligence-vs-cost basis with a
              hard < 100 us / < 100 byte budget gate; this is the decisive selection.

  6 + 14 + 20 = 40 detectors. `unified` and the Pareto-winner `deriv` are flagged.

Run:  python export_eval.py     (from Final Pipeline/python)
"""

from __future__ import annotations

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.normpath(os.path.join(HERE, "..", "dashboard", "public", "data", "evaluation.json"))

P2_CSV = os.path.join(CODE, "Phase 2", "results", "csv", "aggregated_results.csv")
P3_CSV = os.path.join(CODE, "Phase 3", "results", "csv", "aggregated_results.csv")
P4_SEL = os.path.join(CODE, "Phase 4", "results", "selection.json")

# design targets per Phase 4 detector (from tsad/registry.py SPECS)
TARGETS = {
    "ewma_z": ["spike", "drift", "transient"], "robust_z": ["spike", "transient"],
    "hampel": ["spike", "transient"], "cusum": ["drift"], "page_hinkley": ["drift"],
    "ewmv_adaptive": ["spike", "drift"], "deriv": ["transient", "spike"],
    "acf_periodicity": ["periodicity"], "heavy_baseline": ["spike", "drift"],
    "layered": ["spike", "drift", "transient"], "voting": ["spike", "drift", "transient", "periodicity"],
    "cascade": ["spike", "drift", "transient"], "ewma_z_hold": ["spike", "drift"],
    "ewmv_hold": ["drift"], "cusum_gated": ["drift"], "page_hinkley_gated": ["drift"],
    "ewmv_gated": ["drift"], "ewmv_hold_gated": ["drift"], "acf_gated": ["periodicity"],
    "unified": ["spike", "drift", "periodicity", "transient"],
}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _agg_phase_csv(path):
    """Aggregate an aggregated_results.csv down to one row per base detector.

    NOTE on the primary metric: these are RARE POINT anomalies, so sample-level
    precision floors near ~0.001 (a handful of positive samples vs. thousands of
    negatives) and sample-F1 collapses to ~0.01 for *every* detector -- a
    misleading number that makes strong detectors look broken. The metric that
    actually carries signal here is the EVENT-level DETECTION RATE (did we flag
    the anomaly window at all) paired with the false-positive rate. So we surface
    detection_rate per type as the headline and keep F1/TPR/FPR alongside.
    """
    if not os.path.exists(path):
        return []
    rows = list(csv.DictReader(open(path, newline="")))
    by_base = {}
    for r in rows:
        base = r["detector"].split("(")[0].strip().strip('"')
        d = by_base.setdefault(base, {"f1": [], "tpr": [], "fpr": [], "det": [],
                                       "by_type": {}, "by_type_det": {}})
        f1, tpr, fpr = _num(r["f1_mean"]), _num(r["tpr_mean"]), _num(r["fpr_mean"])
        det = _num(r.get("detection_rate"))
        if f1 is not None:
            d["f1"].append(f1)
        if tpr is not None:
            d["tpr"].append(tpr)
        if fpr is not None:
            d["fpr"].append(fpr)
        if det is not None:
            d["det"].append(det)
        at = r["anomaly_type"]
        bt = d["by_type"].setdefault(at, [])
        if f1 is not None:
            bt.append(f1)
        btd = d["by_type_det"].setdefault(at, [])
        if det is not None:
            btd.append(det)
    out = []
    for base, d in by_base.items():
        out.append({
            "detector": base,
            "f1_best": round(max(d["f1"]), 4) if d["f1"] else 0,
            "f1_mean": round(sum(d["f1"]) / len(d["f1"]), 4) if d["f1"] else 0,
            "tpr_mean": round(sum(d["tpr"]) / len(d["tpr"]), 4) if d["tpr"] else 0,
            "fpr_mean": round(sum(d["fpr"]) / len(d["fpr"]), 4) if d["fpr"] else 0,
            "det_best": round(max(d["det"]), 4) if d["det"] else 0,
            "by_type": {t: round(max(v), 4) for t, v in d["by_type"].items() if v},
            # event-level detection rate per anomaly type (the headline metric)
            "by_type_det": {t: round(max(v), 4) for t, v in d["by_type_det"].items() if v},
        })
    out.sort(key=lambda x: -x["det_best"])
    return out


def _kind(name):
    if name.startswith("Gated"):
        return "gated"
    if any(k in name for k in ("Spike_", "Sustained_", "Ensemble", "TwoLayer")):
        return "ensemble"
    return "single"


def main():
    phase2 = _agg_phase_csv(P2_CSV)
    phase3 = _agg_phase_csv(P3_CSV)
    for d in phase3:
        d["kind"] = _kind(d["detector"])

    sel = json.load(open(P4_SEL))
    phase4 = []
    for r in sel["per_detector_best"]:
        name = r["detector"]
        phase4.append({
            "detector": name, "window": r["window"], "family": r["family"],
            "intel": round(r["intel"], 4), "vus_pr": round(r["vus_pr"], 4),
            "f1": round(r["f1"], 4), "mcc": round(r["mcc"], 4),
            "latency": round(r["latency"], 2), "us_per_sample": r["us_per_sample"],
            "state_bytes": r["state_bytes"], "budget_ok": r["budget_ok"],
            "cost_source": r.get("cost_source", "py"),
            "targets": TARGETS.get(name, []),
            "is_unified": name == "unified",
            "is_ensemble": r["family"] == "ensemble",
        })

    doc = {
        "budget": sel["budget"],
        "recommended": sel["recommended"],
        "condition_to_algorithm": sel.get("condition_to_algorithm", {}),
        "pareto_front": sel.get("pareto_front", []),
        "phase2": phase2,
        "phase3": phase3,
        "phase4": phase4,
        "counts": {"phase2": len(phase2), "phase3": len(phase3),
                   "phase4": len(phase4), "total": len(phase2) + len(phase3) + len(phase4)},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w"), indent=1)
    c = doc["counts"]
    print(f"wrote {OUT}")
    print(f"  Phase 2: {c['phase2']}  Phase 3: {c['phase3']}  Phase 4: {c['phase4']}  = {c['total']} detectors")
    print(f"  recommended overall={sel['recommended']['overall']['detector']}  "
          f"best_combined={sel['recommended']['best_combined']['detector']}")


if __name__ == "__main__":
    main()
