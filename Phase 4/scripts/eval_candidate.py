"""Evaluate ONE candidate detector class per anomaly type -- the shared measurement tool
for the >0.90 architecture search.

Usage:
  python scripts/eval_candidate.py <module> <ClassName> [--seeds 4] [--windows 16,20,24,30]

Builds <ClassName>(window=w) for each window, runs it over the synthetic suite (the four
controlled anomaly types), and reports per-type mean point-F1 and event-F1, the min across
the four types (the bottleneck for "all four >= 0.90"), and the float32 state footprint.
Prints a single JSON object to stdout.

The class must subclass tsad.core.base.Detector (i.e. expose update(x)->score, score_stream,
state_bytes). All four anomaly types are scored: spike, drift, periodicity, transient.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src", "python"))

from datasets.synthetic import make_suite          # noqa: E402
from eval.metrics_intel import evaluate             # noqa: E402

TYPES = ["spike", "drift", "periodicity", "transient"]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def evaluate_class(cls, windows, seeds, seed_start=0):
    suite = make_suite(seeds=range(seed_start, seed_start + seeds))
    result = {}
    for w in windows:
        buckets = {t: {"point": [], "event": [], "opt": []} for t in TYPES}
        for s in suite:
            t = s.meta["anomaly_type"]
            if t not in buckets:
                continue
            det = cls(window=w)
            scores = det.score_stream(s.values)
            m = evaluate(s.labels, scores, s.events, n=len(s.values))
            buckets[t]["point"].append(m["f1"])
            buckets[t]["event"].append(m["event_f1"])
            buckets[t]["opt"].append(m["event_f1_opt"])
        try:
            sb = int(cls(window=w).state_bytes())
        except Exception:
            sb = -1
        types = {t: {"point_f1": round(_mean(b["point"]), 4),
                     "event_f1": round(_mean(b["event"]), 4),
                     "event_f1_opt": round(_mean(b["opt"]), 4)}
                 for t, b in buckets.items()}
        result[str(w)] = {
            "types": types,
            "min_point_f1": round(min(types[t]["point_f1"] for t in TYPES), 4),
            "min_event_f1": round(min(types[t]["event_f1"] for t in TYPES), 4),
            "min_event_f1_opt": round(min(types[t]["event_f1_opt"] for t in TYPES), 4),
            "state_bytes": sb,
            "within_budget": 0 <= sb < 100,
        }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("cls")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--seed-start", type=int, default=0, dest="seed_start",
                    help="first seed (use a held-out value to check generalization)")
    ap.add_argument("--windows", default="16,20,24,30")
    args = ap.parse_args()

    windows = [int(x) for x in args.windows.split(",")]
    mod = importlib.import_module(args.module)
    cls = getattr(mod, args.cls)
    res = evaluate_class(cls, windows, args.seeds, seed_start=args.seed_start)

    # pick the best window: maximise min_event_f1 among within-budget windows
    budget_windows = {w: r for w, r in res.items() if r["within_budget"]}
    pool = budget_windows or res
    best_w = max(pool, key=lambda w: pool[w]["min_event_f1_opt"])
    summary = {
        "module": args.module, "class": args.cls,
        "best_window": int(best_w),
        "best": res[best_w],
        "all_windows": res,
        "all4_event_opt_ge_090": res[best_w]["min_event_f1_opt"] >= 0.90,
        "all4_event_ge_090": res[best_w]["min_event_f1"] >= 0.90,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
