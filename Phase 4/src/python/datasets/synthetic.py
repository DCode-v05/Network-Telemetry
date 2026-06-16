"""Synthetic network-telemetry signal generators + labelled-anomaly suite builder.

Base signals approximate common telemetry shapes (utilisation %, packet rate, queue
depth, periodic keepalive). Anomalies are injected by ``injectors`` with ground-truth
labels, so accuracy and detection latency can be measured exactly. Difficulty is varied
through magnitude (in sigma units) and multiple random seeds ("multiple tries").
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .injectors import INJECTORS, ANOMALY_TYPES

# Base signal kinds compatible with each anomaly type. Periodicity loss needs a
# genuinely periodic base; the other anomaly types use the broader set.
BASE_KINDS = ("flat", "periodic", "trend", "bursty")
PERIODIC_BASES = ("periodic",)


@dataclass
class Stream:
    values: np.ndarray
    labels: np.ndarray
    events: list                      # list[(start, end)] inclusive
    meta: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        m = self.meta
        return f"{m.get('source','syn')}|{m.get('anomaly_type','?')}|{m.get('base','?')}|s{m.get('seed','?')}|m{m.get('mag','?')}"


def base_signal(kind, n, sigma, rng, period=24, amp=6.0, slope=None):
    """Generate a clean base signal of length n with additive Gaussian noise ~ sigma."""
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
        # piecewise-constant levels with occasional legitimate level changes (NOT anomalies)
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


def make_suite(seeds=range(10), mags=(4.0, 6.0, 9.0), n=600):
    """Build the full synthetic evaluation suite.

    For each anomaly type, each compatible base signal, each magnitude and each seed we
    emit one stream. Periodicity-loss is generated only on periodic bases.
    """
    streams = []
    for atype in ANOMALY_TYPES:
        bases = PERIODIC_BASES if atype == "periodicity" else BASE_KINDS
        mag_grid = (0.0,) if atype == "periodicity" else mags  # periodicity ignores mag
        for base in bases:
            for mag in mag_grid:
                for seed in seeds:
                    streams.append(make_stream(atype, base, n=n, seed=int(seed), mag=mag))
    return streams


if __name__ == "__main__":  # tiny smoke test
    suite = make_suite(seeds=range(2))
    print(f"generated {len(suite)} synthetic streams")
    for s in suite[:4]:
        print(f"  {s.name:55s} len={len(s.values)} anomalies={int(s.labels.sum())} events={len(s.events)}")
