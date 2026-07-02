"""Labelled data sources for the unified-detector demo.

Read-only extraction (verbatim) of the Phase 4 data code so the standalone
package reuses the *exact* injectors / synthetic generators / NAB loader rather
than re-deriving them:

  * injectors  <- Phase 4/src/python/datasets/injectors.py
  * synthetic  <- Phase 4/src/python/datasets/synthetic.py
  * load_nab   <- Phase 4/src/python/datasets/real_loaders.py

Dependency: numpy (+ stdlib). Nothing here imports the sweep harness / registry.

Each source returns a `Stream(values, labels, events, meta)`:
  * values -- np.ndarray float, signal WITH the anomaly
  * labels -- np.ndarray int {0,1}, per-sample ground truth (1 == anomalous)
  * events -- list[(start, end)] inclusive index ranges, one per injected anomaly
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

# ---------------------------------------------------------------------------
# Stream container
# ---------------------------------------------------------------------------

ANOMALY_TYPES = ("spike", "drift", "periodicity", "transient")
BASE_KINDS = ("flat", "periodic", "trend", "bursty")
PERIODIC_BASES = ("periodic",)


@dataclass
class Stream:
    values: np.ndarray
    labels: np.ndarray
    events: list
    meta: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        m = self.meta
        return (f"{m.get('source','syn')}|{m.get('anomaly_type','?')}|{m.get('base','?')}"
                f"|s{m.get('seed','?')}|m{m.get('mag','?')}")


# ---------------------------------------------------------------------------
# Anomaly injectors (verbatim from Phase 4 injectors.py)
# ---------------------------------------------------------------------------

def _pick_locations(n, k, margin, min_gap, rng):
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
    """Additive spikes / short bursts (>= 6 sigma point excursions)."""
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
    """Very brief 1-2 sample microbursts / drop spikes."""
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
    """A single gradual rate shift: linear ramp to a sustained offset of mag*sigma."""
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
    """Disrupt a periodic signal over a segment (loss of periodicity)."""
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
    else:
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


# ---------------------------------------------------------------------------
# Synthetic base signals + stream builder (verbatim from Phase 4 synthetic.py)
# ---------------------------------------------------------------------------

def base_signal(kind, n, sigma, rng, period=24, amp=6.0, slope=None):
    """Clean base signal of length n with additive Gaussian noise ~ sigma."""
    t = np.arange(n)
    noise = rng.normal(0.0, sigma, size=n)
    if kind == "flat":
        base = np.full(n, 50.0)
    elif kind == "periodic":
        base = 50.0 + amp * np.sin(2.0 * np.pi * t / period)
    elif kind == "trend":
        if slope is None:
            slope = amp / n
        base = 40.0 + slope * t + 0.3 * amp * np.sin(2.0 * np.pi * t / period)
    elif kind == "bursty":
        base = np.full(n, 45.0)
        level = 45.0
        for i in range(n):
            if rng.random() < 0.02:
                level = 45.0 + rng.normal(0.0, 1.5 * sigma)
            base[i] = level
    else:
        raise ValueError(f"unknown base kind: {kind}")
    return base + noise


def make_stream(anomaly_type, base_kind, n=600, seed=0, sigma=1.0, mag=6.0,
                period=24, amp=6.0):
    """Build one labelled stream of the requested anomaly type on the requested base."""
    rng = np.random.default_rng(seed)
    vals = base_signal(base_kind, n, sigma, rng, period=period, amp=amp)
    injector = INJECTORS[anomaly_type]
    if anomaly_type == "spike":
        vals, labels, events = injector(vals, sigma, rng, n_events=3, mag=mag)
    elif anomaly_type == "transient":
        vals, labels, events = injector(vals, sigma, rng, n_events=4, mag=mag + 3.0)
    elif anomaly_type == "drift":
        vals, labels, events = injector(vals, sigma, rng, mag=max(4.0, mag - 1.0))
    elif anomaly_type == "periodicity":
        vals, labels, events = injector(vals, sigma, rng)
    else:
        raise ValueError(anomaly_type)
    meta = dict(source="syn", anomaly_type=anomaly_type, base=base_kind, n=n,
                seed=seed, sigma=sigma, mag=mag, period=period,
                anomaly_ratio=float(labels.mean()))
    return Stream(vals, labels, events, meta)


# ---------------------------------------------------------------------------
# NAB loader (verbatim from Phase 4 real_loaders.py)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
# In the standalone package the staged NAB data lives under ../data/nab_streams
NAB_DIR = os.path.normpath(os.path.join(_HERE, "..", "data", "nab_streams"))

_TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
               "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d")


def _parse_ts(s):
    s = (s or "").strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _read_nab_csv(path):
    timestamps, values = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "value" not in reader.fieldnames:
            return None, None
        for row in reader:
            try:
                values.append(float(row["value"]))
            except (ValueError, TypeError, KeyError):
                continue
            timestamps.append(_parse_ts(row.get("timestamp", "")))
    return timestamps, np.asarray(values, dtype=float)


def _windows_to_events(timestamps, windows):
    events = []
    for win in windows:
        a, b = _parse_ts(win[0]), _parse_ts(win[1])
        if a is None or b is None:
            continue
        idx = [i for i, t in enumerate(timestamps) if t is not None and a <= t <= b]
        if idx:
            events.append((idx[0], idx[-1]))
    return events


def load_nab(nab_dir=NAB_DIR):
    """Return list[Stream] for every labelled NAB file staged under `nab_dir`."""
    labels_path = os.path.join(nab_dir, "combined_windows.json")
    if not os.path.exists(labels_path):
        return []
    with open(labels_path) as f:
        all_windows = json.load(f)

    streams = []
    for rel, windows in all_windows.items():
        path = os.path.join(nab_dir, rel.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        timestamps, values = _read_nab_csv(path)
        if values is None or len(values) == 0:
            continue
        n = len(values)
        labels = np.zeros(n, dtype=int)
        events = _windows_to_events(timestamps, windows)
        for (s, e) in events:
            labels[s:e + 1] = 1
        family = rel.split("/")[0]
        meta = dict(source="nab", anomaly_type="real", base=family,
                    name=rel, n=n, seed=0, mag="real",
                    anomaly_ratio=float(labels.mean()))
        if labels.sum() > 0:
            streams.append(Stream(values, labels, events, meta))
    return streams


if __name__ == "__main__":
    s = make_stream("spike", "flat", seed=1)
    print(f"synthetic: {s.name}  len={len(s.values)}  anomalies={int(s.labels.sum())}  events={s.events}")
    nab = load_nab()
    print(f"NAB staged: {len(nab)} stream(s)")
    for st in nab:
        print(f"  {st.meta['name']:55s} len={len(st.values)} anomalies={int(st.labels.sum())} events={len(st.events)}")
