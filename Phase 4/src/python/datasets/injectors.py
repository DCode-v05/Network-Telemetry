"""Anomaly injectors for the four telemetry anomaly types.

Each injector takes a clean base signal plus the noise scale ``sigma`` and returns
``(values, labels, events)``:

  * ``values``  -- np.ndarray float, the signal WITH the anomaly added
  * ``labels``  -- np.ndarray int {0,1}, per-sample ground truth (1 == anomalous)
  * ``events``  -- list[(start, end)] inclusive index ranges, one per injected anomaly,
                   used for event/range metrics and detection-latency measurement.

Anomaly magnitudes are expressed in units of the noise ``sigma`` so difficulty is
comparable across base signals. A ``margin`` keeps anomalies away from the warm-up
region at the start of the stream.
"""

from __future__ import annotations

import numpy as np

ANOMALY_TYPES = ("spike", "drift", "periodicity", "transient")


def _pick_locations(n, k, margin, min_gap, rng):
    """Pick k well-separated indices in [margin, n-margin)."""
    lo, hi = margin, n - margin
    chosen = []
    attempts = 0
    while len(chosen) < k and attempts < 200:
        attempts += 1
        c = int(rng.integers(lo, hi))
        if all(abs(c - p) >= min_gap for p in chosen):
            chosen.append(c)
    return sorted(chosen)


def inject_spike(values, sigma, rng, n_events=3, mag=6.0, burst_len=1, margin=40):
    """Additive spikes / short bursts (point + short-subsequence anomalies)."""
    v = values.astype(float).copy()
    n = len(v)
    labels = np.zeros(n, dtype=int)
    events = []
    locs = _pick_locations(n, n_events, margin, max(8, burst_len * 3), rng)
    for c in locs:
        sign = 1.0 if rng.random() < 0.5 else -1.0
        L = int(burst_len)
        end = min(n - 1, c + L - 1)
        for i in range(c, end + 1):
            v[i] += sign * mag * sigma
            labels[i] = 1
        events.append((c, end))
    return v, labels, events


def inject_transient(values, sigma, rng, n_events=4, mag=9.0, margin=40):
    """Very brief 1-2 sample microbursts / drop spikes (fast transients)."""
    v = values.astype(float).copy()
    n = len(v)
    labels = np.zeros(n, dtype=int)
    events = []
    locs = _pick_locations(n, n_events, margin, 6, rng)
    for c in locs:
        sign = 1.0 if rng.random() < 0.5 else -1.0
        L = 1 if rng.random() < 0.7 else 2
        end = min(n - 1, c + L - 1)
        for i in range(c, end + 1):
            v[i] += sign * mag * sigma
            labels[i] = 1
        events.append((c, end))
    return v, labels, events


def inject_drift(values, sigma, rng, mag=5.0, ramp=None, margin=40):
    """A single gradual rate shift: a linear ramp to a sustained offset of mag*sigma.

    The event is labelled from the ramp start onward (the regime is anomalous once the
    drift begins). Detection latency is measured from the ramp start.
    """
    v = values.astype(float).copy()
    n = len(v)
    labels = np.zeros(n, dtype=int)
    if ramp is None:
        ramp = max(10, n // 12)
    cp = int(rng.integers(margin, n - margin - ramp))
    shift = mag * sigma
    for i in range(cp, n):
        frac = min(1.0, (i - cp + 1) / ramp)
        v[i] += shift * frac
        labels[i] = 1
    events = [(cp, n - 1)]
    return v, labels, events


def inject_periodicity(values, sigma, rng, seg_len=None, mode=None, margin=40):
    """Disrupt a periodic signal over a segment (loss of periodicity).

    The base signal must be periodic. The disruption either flattens the segment to its
    local mean plus noise ('dropout') or scrambles its phase ('scramble'). Detection
    latency is measured from the segment start.
    """
    v = values.astype(float).copy()
    n = len(v)
    labels = np.zeros(n, dtype=int)
    if seg_len is None:
        seg_len = max(15, n // 8)
    start = int(rng.integers(margin, n - margin - seg_len))
    end = start + seg_len - 1
    if mode is None:
        mode = "dropout" if rng.random() < 0.5 else "scramble"
    seg = v[start:end + 1]
    local_mean = float(np.mean(seg))
    if mode == "dropout":
        v[start:end + 1] = local_mean + rng.normal(0.0, sigma, size=seg.shape)
    else:  # scramble: destroy phase by permuting the segment samples
        perm = rng.permutation(seg.shape[0])
        v[start:end + 1] = seg[perm]
    labels[start:end + 1] = 1
    events = [(start, end)]
    return v, labels, events


INJECTORS = {
    "spike": inject_spike,
    "transient": inject_transient,
    "drift": inject_drift,
    "periodicity": inject_periodicity,
}
