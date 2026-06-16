"""Voting ensemble over four complementary detectors with an agreement bonus.

Members: robust-z (spike), CUSUM (drift), Hampel (transient), ACF (periodicity). Each
member's score is normalized by its own threshold; the ensemble score is the strongest
normalized signal boosted when several members agree:

    score = max(norm_i) * (1 + 0.15 * (votes - 1)),  votes = #{ norm_i >= 1 }

so a single very strong member can still fire, while agreement among members is rewarded.
This is the broadest-coverage candidate (all four anomaly types) for Q5.
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.detectors.robust_z import RobustZ
from tsad.detectors.cusum import Cusum
from tsad.detectors.hampel import Hampel
from tsad.detectors.acf_periodicity import AcfPeriodicity


class Voting(Detector):
    name = "voting"

    def __init__(self, window=30, threshold=1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self):
        super().reset()
        self.members = [
            RobustZ(window=self.window),
            Cusum(window=self.window),
            Hampel(window=self.window),
            AcfPeriodicity(window=self.window),
        ]

    def update(self, x):
        self.n += 1
        norms = [m.update(x) / (m.threshold + 1e-9) for m in self.members]
        mx = max(norms)
        votes = sum(1 for v in norms if v >= 1.0)
        score = mx * (1.0 + 0.15 * max(0, votes - 1))
        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_bytes(self):
        return sum(m.state_bytes() for m in self.members) + 8
