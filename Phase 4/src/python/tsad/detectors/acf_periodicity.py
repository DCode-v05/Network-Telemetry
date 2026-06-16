"""Lag-k autocorrelation DROP detector (loss of periodicity).

Many network-telemetry signals are quasi-periodic (e.g. a polling cadence, a
diurnal traffic cycle, a heartbeat). A healthy periodic signal has a strong
autocorrelation at its dominant lag ``period``; when the periodic structure
collapses -- the loop stalls, the cadence jitters, the heartbeat dies -- that
autocorrelation drops sharply. This detector watches exactly that drop.

Algorithm
---------
Once the ring buffer is full we estimate the dominant period ONCE by scanning
candidate lags and keeping the one with the largest autocorrelation ``r``
(its value is cached as the reference ``r_ref``). If the signal does not look
periodic at all we fall back to a nominal period and a tiny reference so the
detector stays quiet on aperiodic data. Thereafter every sample re-measures the
autocorrelation at the fixed ``period`` and the score is the POSITIVE part of
``r_ref - r_now`` -- large when periodicity collapses, zero while it holds.

State (mirrors the C twin)
--------------------------
  * one ``RingBuffer(window)`` of floats (the observation window)
  * ``period``  -- int, the established dominant lag (counts as one scalar slot)
  * ``r_ref``   -- float, the reference autocorrelation at that lag

Pure scalar arithmetic only inside ``update``; ``update`` is O(window).
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad
from math import sqrt

EPS = 1e-9


def acf(vals, lag):
    """Lag-``lag`` autocorrelation of ``vals`` (mean-centred, biased denom).

    Returns 0.0 when there are too few samples to form the lagged products.
    """
    N = len(vals)
    if N <= lag + 2:
        return 0.0
    mean = sum(vals) / N
    num = 0.0
    for i in range(lag, N):
        num += (vals[i] - mean) * (vals[i - lag] - mean)
    den = 0.0
    for v in vals:
        d = v - mean
        den += d * d
    den += EPS
    return num / den


class AcfPeriodicity(Detector):
    """Detect loss of periodicity via a drop in lag-k autocorrelation."""

    name = "acf_periodicity"

    def __init__(self, window: int = 30, threshold: float = 0.3, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.window)
        self.period = 0
        self.r_ref = 0.0

    def update(self, x: float) -> float:
        self.n += 1
        self.buf.push(x)

        if not self.buf.is_full():
            return 0.0

        vals = self.buf.values()

        if self.period == 0:
            best_lag, best_r = 0, -2.0
            for lag in range(2, max(3, self.window // 2) + 1):
                r = acf(vals, lag)
                if r > best_r:
                    best_r, best_lag = r, lag
            if best_r < 0.2:
                self.period = max(2, self.window // 4)
                self.r_ref = 0.05
            else:
                self.period = best_lag
                self.r_ref = best_r
            return 0.0

        r_now = acf(vals, self.period)
        score = self.r_ref - r_now
        if score < 0.0:
            score = 0.0
        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_floats(self) -> int:
        return 2

    def state_buffer_len(self) -> int:
        return self.window
