"""Merge the C benchmark (results/c_cost.csv) into results/cost.csv and metrics.json.

After the C bench runs, selection/scorecard use the real C per-sample time and float32
footprint when present. Safe to run before the C bench exists (no-op + notice).
Stdlib only (no pandas).
"""

from __future__ import annotations

import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))
C_COLS = ["c_ns_per_sample", "c_us_per_sample", "c_state_bytes", "sizeof_struct_bytes"]


def _num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if math.isnan(f):
        return None
    return int(f) if f.is_integer() and "." not in str(v) and "e" not in str(v).lower() else f


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    cost_path = os.path.join(RESULTS, "cost.csv")
    c_path = os.path.join(RESULTS, "c_cost.csv")
    if not os.path.exists(cost_path):
        print("cost.csv not found; run the sweep first.")
        return 1

    cost = _read(cost_path)
    base_cols = [c for c in (cost[0].keys() if cost else []) if c not in C_COLS]

    if os.path.exists(c_path):
        cidx = {(r["detector"], str(r["window"])): r for r in _read(c_path)}
        for r in cost:
            m = cidx.get((r["detector"], str(r["window"])))
            for col in C_COLS:
                r[col] = (m or {}).get(col, "")
        print(f"merged C cost for {len({k[0] for k in cidx})} detectors")
        out_cols = base_cols + C_COLS
    else:
        print("c_cost.csv not found; leaving Python-only cost (C merge skipped).")
        out_cols = base_cols

    with open(cost_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_cols, extrasaction="ignore")
        w.writeheader()
        for r in cost:
            w.writerow({k: r.get(k, "") for k in out_cols})

    # refresh metrics.json cost block (numeric, NaN -> None)
    mj = os.path.join(RESULTS, "metrics.json")
    if os.path.exists(mj):
        with open(mj) as f:
            payload = json.load(f)
        payload["cost"] = [{k: _num(v) for k, v in r.items()} for r in cost]
        with open(mj, "w") as f:
            json.dump(payload, f, indent=2)
        print("updated metrics.json cost block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
