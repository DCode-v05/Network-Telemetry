"""EWMA control-chart (ewmv_adaptive) with an anomaly-aware ("hold") slow baseline.

Same smoothed-deviation statistic as ewmv_adaptive, but the slow baseline mean/sigma is
frozen while the deviation is over threshold (the fast smoother z keeps tracking). Best
suited to gradual drift, where freezing prevents the baseline from chasing the drift and
suppressing the very signal it should report. Pure O(1), 3 float scalars.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector


class EwmvHold(Detector):
    name = "ewmv_hold"

    def __init__(self, window=30, threshold=3.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self):
        super().reset()
        self.lam = 2.0 / (self.window + 1)
        self.alpha_s = self.lam / 4.0
        self.z = 0.0
        self.mu = 0.0
        self.sigma = 1.0

    def update(self, x):
        self.n += 1
        if self.n == 1:
            self.z = x
            self.mu = x
            self.sigma = 1.0
            self.last_score = 0.0
            return 0.0
        control_sigma = self.sigma * sqrt(self.lam / (2.0 - self.lam))
        score = abs(self.z - self.mu) / (control_sigma + 1e-9)
        self.z = self.lam * x + (1 - self.lam) * self.z
        if score < self.threshold:
            d = x - self.mu
            self.mu += self.alpha_s * d
            self.sigma = sqrt((1 - self.alpha_s) * (self.sigma * self.sigma + self.alpha_s * d * d))
            if self.sigma < 1e-6:
                self.sigma = 1e-6
        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_floats(self):
        return 3
