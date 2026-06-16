"""EWMA control-chart detector on the smoothed signal with adaptive limits.

``ewmv_adaptive`` watches a fast EWMA (``z``) of the signal against a slowly
drifting baseline (``mu``), normalising the gap by an EWMA-style standard
deviation (``sigma``). This combines a classic EWMA control chart (sensitive to
small *sustained* shifts) with the spike sensitivity of a fast smoother:

  * ``z``     -- fast exponential mean of ``x`` (responds quickly to spikes/shifts).
  * ``mu``    -- slow baseline (a quarter of the fast rate) that the gap is measured
                 against, so a small persistent shift opens a visible gap before the
                 baseline catches up.
  * ``sigma`` -- EWMA estimate of the local scale, giving *adaptive* control limits:
                 in a quiet stream the limits tighten, in a noisy one they widen.

The reported score is the standardised deviation of the smoothed value from the
baseline, ``|z - mu| / control_sigma`` where ``control_sigma`` is the EWMA-chart
steady-state limit ``sigma * sqrt(lam / (2 - lam))``. A score ``>= threshold``
(default 3.0, i.e. a "3-sigma" control limit) flags an anomaly.

Predict-then-update: the score is computed from state *before* folding ``x`` in,
so a spike is judged against the pre-spike baseline rather than masking itself.

State: three float scalars (``z``, ``mu``, ``sigma``); no ring buffer. Pure scalar
arithmetic only, mirroring the on-device C twin. Footprint is well under the
< 100 byte budget (3 floats + counters).
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad

_EPS = 1e-9
_SIGMA_FLOOR = 1e-6


class EwmvAdaptive(Detector):
    """EWMA control chart on the smoothed signal with adaptive (EWMA-std) limits."""

    name = "ewmv_adaptive"

    def __init__(self, window: int = 30, threshold: float = 3.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self) -> None:
        super().reset()
        self.lam = 2.0 / (self.window + 1)
        self.alpha_s = self.lam / 4.0
        self.z = 0.0
        self.mu = 0.0
        self.sigma = 1.0

    def update(self, x: float) -> float:
        self.n += 1

        if self.n == 1:
            self.z = x
            self.mu = x
            self.sigma = 1.0
            self.last_score = 0.0
            return 0.0

        control_sigma = self.sigma * sqrt(self.lam / (2.0 - self.lam))
        score = abs(self.z - self.mu) / (control_sigma + _EPS)

        self.z = self.lam * x + (1.0 - self.lam) * self.z
        d = x - self.mu
        self.mu += self.alpha_s * d
        self.sigma = sqrt((1.0 - self.alpha_s) * (self.sigma * self.sigma
                                                  + self.alpha_s * d * d))
        if self.sigma < _SIGMA_FLOOR:
            self.sigma = _SIGMA_FLOOR

        if not self.warm():
            score = 0.0

        self.last_score = score
        return score

    def state_floats(self) -> int:
        return 3
