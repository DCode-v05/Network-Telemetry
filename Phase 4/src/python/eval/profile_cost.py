"""Lightweight-cost profiling for the Python reference detectors.

Measures the on-device-relevant costs as faithfully as Python allows. The authoritative
numbers come from the C twin (WF-C: real cycles + sizeof); these Python figures give an
early, consistent ranking and feed the Pareto analysis.

Reported per detector:
  * py_ns_per_sample  -- median wall-time of one update() call (ns), warm cache, many reps
  * py_ns_p99         -- 99th-percentile per-batch update time (tail behaviour)
  * state_bytes       -- declared steady-state footprint (float32 model; matches C struct)
  * tracemalloc_bytes -- peak Python heap during a run (sanity check on allocation)
"""

from __future__ import annotations

import time
import tracemalloc

import numpy as np


def time_per_sample(factory, values, reps=30, inner=None):
    """Median ns per update() over `reps` passes; also returns p99 of per-pass means."""
    xs = [float(v) for v in values]
    n = len(xs)
    if inner is None:
        inner = max(1, 4000 // max(1, n))
    d = factory()
    for x in xs:
        d.update(x)

    per_pass = []
    for _ in range(reps):
        d = factory()
        t0 = time.perf_counter_ns()
        for _ in range(inner):
            for x in xs:
                d.update(x)
        t1 = time.perf_counter_ns()
        per_pass.append((t1 - t0) / (inner * n))
    per_pass.sort()
    median = per_pass[len(per_pass) // 2]
    p99 = per_pass[min(len(per_pass) - 1, int(0.99 * len(per_pass)))]
    return float(median), float(p99)


def mem_bytes(factory, values):
    """Peak Python heap (bytes) attributable to constructing + running one detector."""
    xs = [float(v) for v in values[:200]]
    tracemalloc.start()
    tracemalloc.clear_traces()
    base = tracemalloc.take_snapshot()
    d = factory()
    for x in xs:
        d.update(x)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return int(peak)


def profile_detector(factory, values, reps=25):
    """Full cost bundle for one detector configuration."""
    d = factory()
    ns_med, ns_p99 = time_per_sample(factory, values, reps=reps)
    return {
        "py_ns_per_sample": ns_med,
        "py_ns_p99": ns_p99,
        "state_bytes": int(d.state_bytes()),
        "tracemalloc_bytes": mem_bytes(factory, values),
    }
