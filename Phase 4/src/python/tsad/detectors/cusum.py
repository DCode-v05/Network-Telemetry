"""Two-sided tabular CUSUM on EWMA-normalized residuals (change-point / drift).

This detector targets *gradual drift* and *change-points* -- the kind of slow
mean shift that point-anomaly detectors (robust-z, Hampel) tend to miss because
each individual sample still looks plausible. It works by accumulating the signed,
normalized residual of each sample against a slowly-tracking baseline; once that
running sum drifts far enough in either direction the CUSUM statistic crosses the
threshold and an alarm fires.

Algorithm
---------
Maintain an EWMA mean ``mu`` and an EWMA standard deviation ``sd`` of the stream
(smoothing factor ``alpha = 2/(window+1)``, the standard EWMA span convention).
For each new sample ``x`` form the normalized residual ``r = (x - mu) / sd`` and
feed it into the classic two-sided tabular CUSUM with allowance (slack) ``k``::

    g_pos = max(0, g_pos + r - k)      # accumulates upward shifts
    g_neg = max(0, g_neg - r - k)      # accumulates downward shifts
    score = max(g_pos, g_neg)

The slack ``k`` (in residual-sigma units) absorbs small, in-control fluctuations so
the statistic only grows when the mean is genuinely off. After an alarm
(``score >= threshold``) both accumulators are reset to zero so the detector is
immediately ready for the next change rather than latching high.

Because the baseline ``mu``/``sd`` keeps tracking, a *sustained* shift drives the
score up sharply at the change point and then -- as the EWMA catches up to the new
level -- the residuals shrink and the statistic relaxes. A single isolated spike
produces only a modest bump (one over-threshold residual), which is by design: this
is a drift detector, not a spike detector.

State
-----
Four float scalars (``mu``, ``sd``, ``g_pos``, ``g_neg``); no ring buffer. ``update``
is O(1) and uses pure scalar arithmetic so it maps 1:1 onto the C twin and fits the
<100 byte state budget.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad

_EPS = 1e-9
_SLACK_K = 0.5
_SD_FLOOR = 1e-6


class Cusum(Detector):
    """Two-sided tabular CUSUM over EWMA-normalized residuals."""

    name = "cusum"

    def __init__(self, window: int = 30, threshold: float = 5.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self) -> None:
        super().reset()
        self.alpha = 2.0 / (self.window + 1)
        self.mu = 0.0
        self.sd = 1.0
        self.g_pos = 0.0
        self.g_neg = 0.0

    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)

        if self.n == 1:
            self.mu = x
            self.sd = 1.0
            self.last_score = 0.0
            return 0.0

        alpha = self.alpha
        k = _SLACK_K

        r = (x - self.mu) / (self.sd + _EPS)
        self.g_pos = max(0.0, self.g_pos + r - k)
        self.g_neg = max(0.0, self.g_neg - r - k)
        score = self.g_pos if self.g_pos > self.g_neg else self.g_neg

        diff = x - self.mu
        self.mu += alpha * diff
        self.sd = sqrt((1.0 - alpha) * (self.sd * self.sd + alpha * diff * diff))
        if self.sd < _SD_FLOOR:
            self.sd = _SD_FLOOR

        if score >= self.threshold:
            self.g_pos = 0.0
            self.g_neg = 0.0

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_floats(self) -> int:
        return 4
