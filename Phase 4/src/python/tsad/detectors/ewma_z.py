"""EWMA-mean + EWMA-variance residual z-score detector.

Streaming detector that maintains an exponentially weighted moving average of the
signal (``mu``) and an exponentially weighted moving variance (``var``). For each new
sample it scores the standardized residual of ``x`` against the *pre-update* baseline:

    z = |x - mu| / (sqrt(var) + eps)

then folds ``x`` into the baseline (predict-then-update, so a spike does not mask
itself by inflating its own baseline before being scored). The smoothing factor is
``alpha = 2 / (window + 1)``, the standard EWMA span->alpha conversion, so ``window``
behaves like an effective averaging length.

This catches both abrupt spikes (large instantaneous residual) and slower shifts
(the residual stays elevated for several samples until ``mu`` drifts to the new level).
It mirrors a C twin holding two float scalars plus the int sample counter -- well under
the < 100 byte state budget.

State: 2 float scalars (``mu``, ``var``); no ring buffer. Score is a non-negative
z-score; default decision threshold is 3.0 (~3 sigma).
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer  # noqa: F401  (kept for contract parity)
from tsad.core.stats import median_sorted, mad  # noqa: F401  (kept for contract parity)

EPS = 1e-9


class EwmaZ(Detector):
    """EWMA mean + EWMA variance residual z-score (spikes and shifts)."""

    name = "ewma_z"

    def __init__(self, window: int = 30, threshold: float = 3.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()                       # sets self.n = 0, self.last_score = 0.0
        # Smoothing factor from the EWMA span -> alpha convention.
        self.alpha = 2.0 / (self.window + 1.0)
        self.mu = 0.0                          # EWMA mean
        self.var = 1.0                         # EWMA variance (seeded to 1.0)

    # ------------------------------------------------------------------ streaming
    def update(self, x: float) -> float:
        self.n += 1

        # First sample: initialize the baseline; nothing to score against yet.
        if self.n == 1:
            self.mu = x
            self.var = 1.0
            self.last_score = 0.0
            return 0.0

        # Score against the PRE-update baseline (predict-then-update).
        sd = sqrt(self.var)
        z = abs(x - self.mu) / (sd + EPS)

        # Fold x into the EWMA mean and EWMA variance.
        diff = x - self.mu
        self.mu += self.alpha * diff
        self.var = (1.0 - self.alpha) * (self.var + self.alpha * diff * diff)

        score = z
        if not self.warm():                    # self.n <= self.warmup
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # mu, var (alpha is a fixed config constant derived from window, not state).
        return 2
