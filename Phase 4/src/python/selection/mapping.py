"""Condition -> algorithm mapping (Problem-Statement Q4).

For each anomaly type, pick the empirically best detector+window (by VUS-PR, then F1),
preferring budget-passing configurations. The design intent (registry ``targets``) is
attached for comparison against what actually wins.
"""

from __future__ import annotations

import tsad.registry as registry


def best_per_type(agg_dwt, cost_index, budget_fn, prefer_single=False):
    """agg_dwt: rows with (detector, window, anomaly_type, metrics). -> {type: choice}."""
    by_type = {}
    for row in agg_dwt:
        by_type.setdefault(row["anomaly_type"], []).append(row)

    out = {}
    for atype, rows in by_type.items():
        def key(r):
            det, win = r["detector"], r["window"]
            c = cost_index.get((det, win), {})
            us = c.get("c_us_per_sample") or c.get("py_us_per_sample")
            by = c.get("c_state_bytes")
            if by is None:
                by = c.get("state_bytes")
            ok = budget_fn(us, by)[0]
            is_single = registry.family(det) != "ensemble"
            # sort key: budget first, (single if requested), then quality
            return (ok, (is_single if prefer_single else True),
                    r.get("vus_pr") or 0.0, r.get("f1") or 0.0)

        best = max(rows, key=key)
        det = best["detector"]
        out[atype] = {
            "detector": det, "window": best["window"],
            "vus_pr": best.get("vus_pr"), "f1": best.get("f1"),
            "mcc": best.get("mcc"), "latency": best.get("latency"),
            "design_targets": list(registry.targets(det)) if det in registry.SPECS else [],
            "family": registry.family(det) if det in registry.SPECS else None,
        }
    return out
