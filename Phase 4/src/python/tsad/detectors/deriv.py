"""First-difference (derivative) z-score detector for fast transients / edges.

This detector scores the *rate of change* of the signal rather than its level. It
maintains an EWMA mean and EWMV variance of the first difference ``d = x - x_prev``
and reports the standardized surprise of the latest difference::

    score = |d - mu_d| / (sqrt(var_d) + eps)

Because it looks at the derivative, it reacts sharply to abrupt edges / transients
(a sudden step or spike produces a large one-step difference) while ignoring slow
level changes, which is the complement to the level-based EWMA / robust-z detectors.

State is three float scalars (``x_prev``, ``mu_d``, ``var_d``) plus the inherited
counters -- no ring buffer -- so the on-device footprint is tiny and the C twin maps
1:1 onto a ``struct { float x_prev, mu_d, var_d; int n; }``.

Contract notes:
  * Pure scalar arithmetic only (no numpy); ``update`` is O(1).
  * Non-negative score, higher == more anomalous; returns 0.0 during warm-up.
  * Default decision threshold 4.0 (a 4-sigma jump in the first difference).
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad
from math import sqrt

_EPS = 1e-9


class Deriv(Detector):
    """Derivative (first-difference) EWMA/EWMV z-score detector."""

    name = "deriv"

    def __init__(self, window: int = 30, threshold: float = 4.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self) -> None:
        super().reset()
        self.x_prev = 0.0
        self.mu_d = 0.0
        self.var_d = 1.0

    def update(self, x: float) -> float:
        self.n += 1
        alpha = 2.0 / (self.window + 1)

        if self.n == 1:
            self.x_prev = x
            self.mu_d = 0.0
            self.var_d = 1.0
            self.last_score = 0.0
            return 0.0

        d = x - self.x_prev
        sd = sqrt(self.var_d)
        score = abs(d - self.mu_d) / (sd + _EPS)

        diff = d - self.mu_d
        self.mu_d += alpha * diff
        self.var_d = (1.0 - alpha) * (self.var_d + alpha * diff * diff)

        self.x_prev = x

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_floats(self) -> int:
        return 3
