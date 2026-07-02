"""Streaming input pipeline for the unified detector.

Simulates a real-time telemetry feed: samples are consumed and scored ONE AT A
TIME via Python generators. There is deliberately NO vectorised / whole-array
numpy operation here -- each sample is pushed into the detector exactly as an
on-device implementation would receive it, with no look-ahead.

Public API:
  csv_row_stream(path)            -> yields (timestamp, value) parsed row-by-row
  values_stream(values, ts=None)  -> yields (timestamp, value) from an in-memory array
  stream_detect(detector, source, threshold=None) -> yields Sample(...) per input

A `Sample` is: (i, timestamp, value, score, is_alert).
"""

from __future__ import annotations

import csv
from math import sqrt
from typing import Iterable, Iterator, NamedTuple, Optional


class Sample(NamedTuple):
    i: int
    timestamp: Optional[str]
    value: float
    score: float
    is_alert: int


class CausalStandardizer:
    """Online z-score via running Welford mean/variance -- NO look-ahead.

    Real telemetry arrives on arbitrary scales (packet counts in the thousands,
    temperatures near 80, ...). The unified detector's head normalisers assume a
    roughly standardised input, so raw streams are z-scored causally before
    detection -- the same idea as the Phase 2 CESNET loader, but computed one
    sample at a time so it stays a true streaming feed. Returns 0.0 until it has
    seen 2 samples.
    """

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.M2 = 0.0

    def push(self, x: float) -> float:
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.M2 += d * (x - self.mean)
        if self.n < 2:
            return 0.0
        sd = sqrt(self.M2 / (self.n - 1))
        return (x - self.mean) / sd if sd > 1e-9 else 0.0


def csv_row_stream(path: str) -> Iterator[tuple]:
    """Yield (timestamp, value) one row at a time from a CSV.

    Reads incrementally (csv.reader over the open file handle) -- the whole file
    is never materialised in memory. Uses the 'value' column if present, else the
    last column; 'timestamp' column if present, else None. Non-numeric rows are
    skipped.
    """
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return
        cols = [c.strip() for c in header]
        try:
            vcol = cols.index("value")
        except ValueError:
            vcol = len(cols) - 1
        tcol = cols.index("timestamp") if "timestamp" in cols else None
        for row in reader:
            if not row or len(row) <= vcol:
                continue
            try:
                value = float(row[vcol])
            except (ValueError, IndexError):
                continue
            ts = row[tcol] if (tcol is not None and tcol < len(row)) else None
            yield ts, value


def values_stream(values: Iterable[float], timestamps: Optional[Iterable] = None) -> Iterator[tuple]:
    """Yield (timestamp, value) from an in-memory sequence, one at a time."""
    if timestamps is None:
        for v in values:
            yield None, float(v)
    else:
        for ts, v in zip(timestamps, values):
            yield ts, float(v)


def stream_detect(detector, source: Iterable[tuple], threshold: Optional[float] = None,
                  standardize: bool = False) -> Iterator[Sample]:
    """Feed a (timestamp, value) stream through `detector` one sample at a time.

    Yields a Sample(i, timestamp, value, score, is_alert) for every input sample.
    `threshold` defaults to the detector's own decision threshold.
    If `standardize` is True the raw value is z-scored causally (CausalStandardizer)
    before being handed to the detector; the Sample still reports the ORIGINAL value.
    """
    thr = detector.threshold if threshold is None else float(threshold)
    std = CausalStandardizer() if standardize else None
    for i, (ts, value) in enumerate(source):
        x = float(value)
        fed = std.push(x) if std is not None else x
        score = detector.update(fed)
        is_alert = 1 if score >= thr else 0
        yield Sample(i, ts, x, float(score), is_alert)


if __name__ == "__main__":
    # smoke: stream a synthetic spike stream through the detector one sample at a time
    from unified_detector import UnifiedDetector
    from datasets import make_stream

    s = make_stream("spike", "flat", seed=7)
    det = UnifiedDetector(window=24)
    n_alert = 0
    peak = (-1, 0.0)
    for smp in stream_detect(det, values_stream(s.values)):
        n_alert += smp.is_alert
        if smp.score > peak[1]:
            peak = (smp.i, smp.score)
    print(f"streamed {len(s.values)} samples one-at-a-time  alerts={n_alert}")
    print(f"peak score {peak[1]:.3f} at i={peak[0]}  (injected events={s.events})")
