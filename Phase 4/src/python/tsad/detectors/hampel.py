"""Hampel-identifier streaming anomaly detector.

The Hampel identifier flags a sample as anomalous when it lies many (robust)
standard deviations away from the *local* median, where the spread is estimated
by the Median Absolute Deviation (MAD) scaled to a Gaussian sigma:

    sigma_hat = 1.4826 * MAD

Score for the current sample ``x`` over a trailing window that **includes** ``x``::

    score = |x - median| / (1.4826 * MAD + eps)

This is the classic robust z-score, but -- unlike ``robust_z`` -- the current
sample is folded into the window *before* the median/MAD are computed. Including
the point under test is what makes this the textbook Hampel identifier: the
median and MAD are highly robust (breakdown point 50%), so a single outlier
barely shifts them, yet the outlier's own large ``|x - median|`` still yields a
big score. This makes Hampel a strong, low-state spike / transient detector.

State (mirrors the C twin ``struct { float buf[W]; int head; int count; }``):
  * one ``RingBuffer`` of capacity ``window`` -- the only state besides counters.
  * no extra float scalars are retained between calls.

Cost: ``update`` is O(window) (one sort for the median/MAD), bounded state.
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad
from math import sqrt

EPS = 1e-9
MAD_TO_SIGMA = 1.4826


class Hampel(Detector):
    """Trailing median + MAD robust z-score, current sample inside the window."""

    name = "hampel"


    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.window)

    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)
        self.buf.push(x)

        if len(self.buf) >= 3:
            sv = self.buf.sorted_values()
            med = median_sorted(sv)
            m = mad(self.buf.values(), med)
            sd = MAD_TO_SIGMA * m
            score = abs(x - med) / (sd + EPS)
        else:
            score = 0.0

        if not self.warm():
            score = 0.0
            self.last_score = score
            return score

        self.last_score = score
        return score

    def state_floats(self) -> int:
        """No retained float scalars beyond the ring buffer."""
        return 0

    def state_buffer_len(self) -> int:
        """The trailing window is the only buffer."""
        return self.window
