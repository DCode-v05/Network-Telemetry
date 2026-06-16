"""Tiered cascade: a cheap EWMA-z pre-filter gates an expensive robust confirmation.

Every sample pays only the cheap cost: an O(1) EWMA-z update plus an O(1) ring-buffer
push. The expensive O(window) median/MAD confirmation runs ONLY when the cheap stage
raises a candidate (its normalized score exceeds ``GATE``). This is how on-device
analytics scale to thousands of metrics: the heavy path executes rarely.

``expensive_runs / n`` is tracked so the average-cost saving can be reported.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad, MAD_TO_SIGMA
from tsad.detectors.ewma_z import EwmaZ

GATE = 0.5            # fraction of the cheap detector's threshold that opens the heavy path
ROBUST_THR = 3.5      # robust-z threshold used to normalize the confirmation score


class Cascade(Detector):
    name = "cascade"

    def __init__(self, window=30, threshold=1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self):
        super().reset()
        self.ewma = EwmaZ(window=self.window)
        self.buf = RingBuffer(self.window)
        self.expensive_runs = 0

    def update(self, x):
        self.n += 1
        n_cheap = self.ewma.update(x) / (self.ewma.threshold + 1e-9)   # cheap, O(1)
        self.buf.push(x)                                              # cheap, O(1)
        score = n_cheap
        if n_cheap >= GATE and len(self.buf) >= 3:                    # candidate -> confirm
            self.expensive_runs += 1
            sv = self.buf.sorted_values()
            med = median_sorted(sv)
            sd = MAD_TO_SIGMA * mad(self.buf.values(), med)
            rz = abs(x - med) / (sd + 1e-9)
            n_rz = rz / ROBUST_THR
            if n_rz > score:
                score = n_rz
        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    @property
    def expensive_fraction(self):
        return self.expensive_runs / self.n if self.n else 0.0

    def state_bytes(self):
        return self.ewma.state_bytes() + self.window * 4 + 12
