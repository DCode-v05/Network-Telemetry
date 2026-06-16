"""Selection runner: read sweep results, choose the best, write results/selection.json.

Reads:  results/agg_detector_window.csv, results/agg_detector_window_type.csv,
        results/cost.csv  (cost.csv may already include merged C measurements)
Writes: results/selection.json  (scorecards, Pareto front, condition->algorithm map,
        and the recommended best-single / best-combined / overall configurations)

Run:    python -m selection.select
"""

from __future__ import annotations

import json
import os

import tsad.registry as registry
from eval.tabio import read_csv, jsonsafe
from selection.pareto import pareto_front
from selection.scorecard import (build_scorecards, passes_budget, intelligence_score,
                                 cost_for, BUDGET_US, BUDGET_BYTES)
from selection.mapping import best_per_type

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "results"))


def _cost_index(cost_rows):
    return {(r["detector"], r["window"]): r for r in cost_rows}


def main():
    agg_dw = read_csv(os.path.join(RESULTS, "agg_detector_window.csv"))
    agg_dwt = read_csv(os.path.join(RESULTS, "agg_detector_window_type.csv"))
    cost_rows = read_csv(os.path.join(RESULTS, "cost.csv"))
    cost_index = _cost_index(cost_rows)

    cards = build_scorecards(agg_dw, cost_index)

    # best window per detector (by intelligence), for a clean per-detector summary
    best_card = {}
    for c in cards:
        d = c["detector"]
        if d not in best_card or c["intel"] > best_card[d]["intel"]:
            best_card[d] = c
    per_detector = sorted(best_card.values(), key=lambda c: c["intel"], reverse=True)

    # Pareto frontier over (cost us, intelligence) using each detector's best-intel window
    pareto_pts = [{"detector": c["detector"], "window": c["window"],
                   "us": c["us_per_sample"], "intel": c["intel"],
                   "budget_ok": c["budget_ok"]}
                  for c in per_detector if c["us_per_sample"] is not None]
    front = pareto_front(pareto_pts, "us", "intel", minimize_x=True, maximize_y=True)

    # condition -> algorithm map
    cond_map = best_per_type(agg_dwt, cost_index, passes_budget)
    cond_map_single = best_per_type(agg_dwt, cost_index, passes_budget, prefer_single=True)

    # recommendations (must pass budget)
    gated = [c for c in per_detector if c["budget_ok"]]
    pool = gated if gated else per_detector
    singles = [c for c in pool if registry.family(c["detector"]) != "ensemble"]
    ensembles = [c for c in pool if registry.family(c["detector"]) == "ensemble"]
    best_single = singles[0] if singles else None
    best_combined = ensembles[0] if ensembles else None
    overall = pool[0] if pool else None

    out = {
        "budget": {"max_us": BUDGET_US, "max_bytes": BUDGET_BYTES},
        "scorecards": cards,
        "per_detector_best": per_detector,
        "pareto_front": front,
        "condition_to_algorithm": cond_map,
        "condition_to_algorithm_single": cond_map_single,
        "recommended": {
            "overall": overall,
            "best_single": best_single,
            "best_combined": best_combined,
        },
        "cost_source": ("C" if any(r.get("c_us_per_sample") is not None
                                    for r in cost_rows) else "python"),
    }
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "selection.json"), "w") as f:
        json.dump(jsonsafe(out), f, indent=2, default=lambda o: None)

    # console summary
    print("=== Recommended configurations (budget-gated) ===")
    for label, c in [("OVERALL", overall), ("BEST SINGLE", best_single),
                     ("BEST COMBINED", best_combined)]:
        if c:
            print(f"  {label:14s}: {c['detector']:16s} w={c['window']:<3} "
                  f"intel={c['intel']:.3f} VUS={c['vus_pr']:.3f} F1={c['f1']:.3f} "
                  f"us={c['us_per_sample']} bytes={c['state_bytes']} ok={c['budget_ok']}")
    print("\n=== Condition -> algorithm (budget-gated, any family) ===")
    for atype, ch in cond_map.items():
        print(f"  {atype:12s}-> {ch['detector']:16s} w={ch['window']:<3} "
              f"VUS={ch['vus_pr']:.3f} F1={ch['f1']:.3f}")
    print(f"\nwrote {os.path.join(RESULTS, 'selection.json')}")


if __name__ == "__main__":
    main()
