"""Generate the demo datasets for the standalone package.

1. data/synthetic_demo.csv  -- ONE labelled stream covering all four anomaly
   types (spike, transient, periodicity loss, drift) at known, non-overlapping
   positions. Built by REUSING the Phase 4 injectors (delta-merge onto a shared
   periodic base), not by re-deriving anomaly maths.

2. data/nab_streams/        -- three real labelled NAB streams copied read-only
   from the Phase 4 data tree, plus a trimmed combined_windows.json so the
   vendored load_nab() finds exactly those three.

Run:  python make_demo_data.py
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta

import numpy as np

from datasets import base_signal, inject_spike, inject_transient, inject_drift, inject_periodicity

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
NAB_OUT = os.path.join(DATA, "nab_streams")
PHASE4_NAB = os.path.normpath(os.path.join(HERE, "..", "..", "Phase 4", "data", "real", "nab"))

# Which NAB streams to stage (present in the Phase 4 repo), one per demo purpose.
# Chosen empirically: streams where the unified detector cleanly flags every
# labelled window at a low false-positive rate (PR-AUC lift >= 1.4x).
NAB_PICKS = [
    "realTraffic/speed_7578.csv",                             # traffic-speed sensor, 4 clear anomaly windows -> spike/level
    "realKnownCause/machine_temperature_system_failure.csv",  # drift + faults -> drift/spike heads
    "realKnownCause/ec2_request_latency_system_failure.csv",  # latency bursts -> transient/spike heads
]


# ---------------------------------------------------------------------------
# 1. composite synthetic stream (all four anomaly types, known positions)
# ---------------------------------------------------------------------------

def _inject_in_band(fn, base, sigma, band, **kw):
    """Run injector `fn` (reused verbatim) retrying seeds until ALL its events
    fall inside [band[0], band[1]); return (delta, labels, events).

    delta = injected_signal - base isolates just this injector's contribution,
    so several injectors can be merged onto one shared base without interfering.
    """
    lo, hi = band
    for seed in range(2000):
        rng = np.random.default_rng(seed)
        v, labels, events = fn(base.copy(), sigma, rng, **kw)
        if events and all(lo <= s and e < hi for (s, e) in events):
            return (v - base), labels, events
    raise RuntimeError(f"could not place {fn.__name__} in band {band}")


def build_composite(n=960, sigma=1.0, period=24, amp=6.0, seed=11):
    """Build one periodic stream with all four anomaly types in disjoint regions."""
    rng = np.random.default_rng(seed)
    base = base_signal("periodic", n, sigma, rng, period=period, amp=amp)

    composite = base.copy()
    labels = np.zeros(n, dtype=int)
    atype = [""] * n
    events_by_type = {}

    # Regions are separated so labels never overlap. Order along the stream:
    #   spike (~200) -> transient (~360) -> periodicity (~500-560) -> drift (700..end)
    plan = [
        ("spike",       inject_spike,       (150, 250), dict(n_events=1, mag=8.0)),
        ("transient",   inject_transient,   (320, 430), dict(n_events=2, mag=10.0)),
        ("periodicity", inject_periodicity, (480, 600), dict(seg_len=60, mode="scramble")),
        ("drift",       inject_drift,       (680, n),   dict(mag=6.0, ramp=40)),
    ]
    for name, fn, band, kw in plan:
        delta, lab, events = _inject_in_band(fn, base, sigma, band, **kw)
        composite += delta
        for (s, e) in events:
            labels[s:e + 1] = 1
            for i in range(s, e + 1):
                atype[i] = name
        events_by_type[name] = events

    return composite, labels, atype, events_by_type


def write_synthetic_csv(path, values, labels, atype, start="2024-01-01 00:00:00"):
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    with open(path, "w", newline="") as f:
        f.write("timestamp,value,label,anomaly_type\n")
        for i, (v, l, a) in enumerate(zip(values, labels, atype)):
            ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ts},{v:.6f},{int(l)},{a}\n")


# ---------------------------------------------------------------------------
# 2. stage NAB streams (read-only copy)
# ---------------------------------------------------------------------------

def stage_nab():
    src_labels = os.path.join(PHASE4_NAB, "combined_windows.json")
    if not os.path.exists(src_labels):
        print(f"  !! Phase 4 NAB not found at {PHASE4_NAB} -- skipping NAB staging")
        return 0
    with open(src_labels) as f:
        all_windows = json.load(f)

    # start clean so a changed NAB_PICKS list never leaves stale streams behind
    if os.path.isdir(NAB_OUT):
        shutil.rmtree(NAB_OUT)
    os.makedirs(NAB_OUT, exist_ok=True)

    trimmed = {}
    staged = 0
    for rel in NAB_PICKS:
        src = os.path.join(PHASE4_NAB, rel.replace("/", os.sep))
        if not os.path.exists(src):
            print(f"  !! missing NAB source: {rel}")
            continue
        dst = os.path.join(NAB_OUT, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)                 # read-only copy; originals untouched
        trimmed[rel] = all_windows.get(rel, [])
        staged += 1
        print(f"  staged {rel}  ({len(trimmed[rel])} label window(s))")

    with open(os.path.join(NAB_OUT, "combined_windows.json"), "w") as f:
        json.dump(trimmed, f, indent=2)
    return staged


def main():
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(NAB_OUT, exist_ok=True)

    print("building synthetic_demo.csv (all four anomaly types) ...")
    values, labels, atype, events = build_composite()
    out_csv = os.path.join(DATA, "synthetic_demo.csv")
    write_synthetic_csv(out_csv, values, labels, atype)
    print(f"  wrote {out_csv}  ({len(values)} samples, {int(labels.sum())} anomalous)")
    for name, evs in events.items():
        print(f"    {name:12s} events={evs}")

    print("staging NAB streams (read-only) ...")
    n = stage_nab()
    print(f"done. staged {n} NAB stream(s).")


if __name__ == "__main__":
    main()
