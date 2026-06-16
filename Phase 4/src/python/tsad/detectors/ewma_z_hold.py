"""EWMA z-score with an anomaly-aware ("hold") baseline.

Identical to ewma_z except the baseline mean/variance is FROZEN while the residual is over
threshold. This stops a real anomaly from (a) being absorbed into its own baseline (which
would mask it / shorten detection) and (b) inflating the variance, which otherwise causes a
burst of false positives right after the event. Pure O(1), 2 float scalars.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector


class EwmaZHold(Detector):
    name = "ewma_z_hold"

    def __init__(self, window=30, threshold=3.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self):
        super().reset()
        self.alpha = 2.0 / (self.window + 1)
        self.mu = 0.0
        self.var = 1.0

    def update(self, x):
        self.n += 1
        if self.n == 1:
            self.mu = x
            self.var = 1.0
            self.last_score = 0.0
            return 0.0
        sd = sqrt(self.var)
        z = abs(x - self.mu) / (sd + 1e-9)
        if z < self.threshold:
            diff = x - self.mu
            self.mu += self.alpha * diff
            self.var = (1 - self.alpha) * (self.var + self.alpha * diff * diff)
        score = z if self.warm() else 0.0
        self.last_score = score
        return score

    def state_floats(self):
        return 2
