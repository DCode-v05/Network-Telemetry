"""Heavy classical baseline detector (sliding linear detrend + robust scale).

This detector is DELIBERATELY heavy. It exists as a research baseline to
demonstrate the compute cost and short-window degradation of "classical" methods
when ported to constrained on-device budgets -- so it must NOT be optimized away.

Algorithm (predict-then-update, window of the last ``window`` samples):
  Over the buffered values ``vals = [y_0 .. y_{N-1}]`` at integer times
  ``t = 0 .. N-1`` it fits a least-squares line ``y = a + b*t`` (closed form),
  extrapolates one step to predict ``pred = a + b*N`` for the incoming sample
  ``x``, and divides the absolute residual by a robust scale. The scale is the
  max of the plain standard deviation and a MAD-based robust sigma
  (``MAD_TO_SIGMA * MAD``); the extra full sort for the MAD is intentionally
  "heavy". With fewer than 4 buffered points the line is underdetermined, so the
  score is 0.0. ``x`` is folded into the buffer only AFTER scoring, so a spike
  cannot contaminate its own prediction.

Score: ``|x - pred| / (scale + eps)`` -- a residual expressed in robust-sigma
units, so it is on a z-score-like scale (default threshold 3.0). Non-negative;
0.0 during warm-up.

State: ONE RingBuffer(window); no extra float scalars. ``update`` is O(window)
(several full passes plus a sort over the window), by design.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad

_EPS = 1e-9
_MAD_TO_SIGMA = 1.4826


class HeavyBaseline(Detector):
    """Sliding least-squares detrend + robust-scale residual detector (heavy)."""

    name = "heavy_baseline"

    def __init__(self, window: int = 30, threshold: float = 3.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.window)

    def update(self, x: float) -> float:
        self.n += 1

        vals = self.buf.values()
        N = len(vals)

        if N >= 4:
            st = N * (N - 1) / 2.0
            stt = sum(t * t for t in range(N))
            sy = sum(vals)
            sty = sum(t * vals[t] for t in range(N))
            denom = (N * stt - st * st) + _EPS
            b = (N * sty - st * sy) / denom
            a = (sy - b * st) / N
            pred = a + b * N

            mean = sy / N
            var = sum((v - mean) ** 2 for v in vals) / N
            std = sqrt(var)

            sv = sorted(vals)
            med = median_sorted(sv)
            m = mad(vals, med)
            rob = _MAD_TO_SIGMA * m

            scale = max(std, rob)
            score = abs(x - pred) / (scale + _EPS)
        else:
            score = 0.0

        self.buf.push(x)

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_floats(self) -> int:
        return 0

    def state_buffer_len(self) -> int:
        return self.window
