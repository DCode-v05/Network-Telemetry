"""Build per-detector scorecards and the composite ranking with a hard cost gate.

Intelligence score (per detector x window), all components in [0,1]:
    intel = 0.45*VUS-PR + 0.30*F1 + 0.15*MCC01 + 0.10*latency_score
  where MCC01 = (MCC+1)/2 and latency_score rewards fast detection.

Cost gate (the lightweight budget is a HARD constraint, not a trade-off):
    pass if  state_bytes < 100  AND  us_per_sample < 100
  C measurements are used when available (merged from the C bench); otherwise the Python
  reference figures are used and the gate on time is reported as provisional.
"""

from __future__ import annotations

import math

W_VUS, W_F1, W_MCC, W_LAT = 0.45, 0.30, 0.15, 0.10
BUDGET_US = 100.0
BUDGET_BYTES = 100


def _latency_score(latency):
    """Map mean detection latency (samples) to [0,1]; ~1 for instant, decays with delay."""
    if latency is None or (isinstance(latency, float) and math.isnan(latency)):
        return 0.0
    return 1.0 / (1.0 + max(0.0, latency) / 5.0)


def intelligence_score(row):
    vus = row.get("vus_pr") or 0.0
    f1 = row.get("f1") or 0.0
    mcc01 = ((row.get("mcc") or 0.0) + 1.0) / 2.0
    lat = _latency_score(row.get("latency"))
    return W_VUS * vus + W_F1 * f1 + W_MCC * mcc01 + W_LAT * lat


def cost_for(detector, window, cost_index):
    """Return (us_per_sample, state_bytes, source) using C if present else Python."""
    c = cost_index.get((detector, window), {})
    us = c.get("c_us_per_sample")
    src = "C"
    if us is None:
        us = c.get("py_us_per_sample")
        src = "py"
    by = c.get("c_state_bytes")
    if by is None:
        by = c.get("state_bytes")
    return us, by, src


def passes_budget(us, by):
    ok_bytes = (by is not None) and (0 <= by < BUDGET_BYTES)
    ok_time = (us is not None) and (us < BUDGET_US)
    return bool(ok_bytes and ok_time), ok_bytes, ok_time


def build_scorecards(agg_dw, cost_index):
    """agg_dw: list of dicts (detector,window,family,metrics). Returns ranked scorecards."""
    cards = []
    for row in agg_dw:
        det, win = row["detector"], row["window"]
        intel = intelligence_score(row)
        us, by, src = cost_for(det, win, cost_index)
        ok, ok_b, ok_t = passes_budget(us, by)
        cards.append({
            "detector": det, "window": win, "family": row.get("family"),
            "intel": round(intel, 4),
            "vus_pr": row.get("vus_pr"), "f1": row.get("f1"), "mcc": row.get("mcc"),
            "latency": row.get("latency"), "fp_per_1k": row.get("fp_per_1k"),
            "us_per_sample": us, "state_bytes": by, "cost_source": src,
            "budget_ok": ok, "bytes_ok": ok_b, "time_ok": ok_t,
        })
    cards.sort(key=lambda c: (c["budget_ok"], c["intel"]), reverse=True)
    return cards
