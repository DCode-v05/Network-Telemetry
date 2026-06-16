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
        # Override only to supply the derivative-detector default threshold (4 sigma
        # on the first difference). All other lifecycle behaviour is inherited.
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()                     # self.n = 0, self.last_score = 0.0
        self.x_prev = 0.0                   # previous sample value
        self.mu_d = 0.0                     # EWMA mean of the first difference
        self.var_d = 1.0                    # EWMV variance of the first difference

    def update(self, x: float) -> float:
        self.n += 1
        # Smoothing factor matched to the window (span -> alpha conversion).
        alpha = 2.0 / (self.window + 1)

        # First sample: no difference available yet -- seed state, emit 0.0.
        if self.n == 1:
            self.x_prev = x
            self.mu_d = 0.0
            self.var_d = 1.0
            self.last_score = 0.0
            return 0.0

        # Score the latest first-difference against the current baseline BEFORE
        # folding it in, so a transient does not mask itself.
        d = x - self.x_prev
        sd = sqrt(self.var_d)
        score = abs(d - self.mu_d) / (sd + _EPS)

        # EWMA / EWMV update of the difference baseline (Welford-style EWMV).
        diff = d - self.mu_d
        self.mu_d += alpha * diff
        self.var_d = (1.0 - alpha) * (self.var_d + alpha * diff * diff)

        self.x_prev = x

        if not self.warm():                 # self.n <= self.warmup
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        return 3                            # x_prev, mu_d, var_d
