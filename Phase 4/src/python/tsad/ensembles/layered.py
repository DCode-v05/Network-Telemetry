"""Layered detector: EWMA baseline/spike  ->  CUSUM drift, OR-fused on normalized scores.

A single sample feeds two cheap streaming detectors that cover complementary anomaly
types (EWMA-z for spikes/level breaks, CUSUM for gradual drift). Their scores are put on
a common scale by dividing by each one's threshold, then OR-fused with ``max`` (Q5: does a
layered pipeline beat any single detector?). Decision boundary is the normalized 1.0.
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.detectors.ewma_z import EwmaZ
from tsad.detectors.cusum import Cusum


class Layered(Detector):
    name = "layered"

    def __init__(self, window=30, threshold=1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self):
        super().reset()
        self.ewma = EwmaZ(window=self.window)
        self.cusum = Cusum(window=self.window)

    def update(self, x):
        self.n += 1
        s1 = self.ewma.update(x) / (self.ewma.threshold + 1e-9)
        s2 = self.cusum.update(x) / (self.cusum.threshold + 1e-9)
        score = s1 if s1 >= s2 else s2
        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_bytes(self):
        return self.ewma.state_bytes() + self.cusum.state_bytes() + 8
