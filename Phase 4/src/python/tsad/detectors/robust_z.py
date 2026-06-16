"""Robust rolling-median + MAD z-score spike detector.

A contamination-resistant cousin of the classic z-score. Instead of a mean and
standard deviation -- both of which are dragged around by the very outliers we are
trying to catch -- this detector scores each sample against the **median** and the
**median absolute deviation (MAD)** of a trailing window:

    score = |x - median| / (1.4826 * MAD + eps)

The 1.4826 factor (``MAD_TO_SIGMA``) rescales the MAD so that, for Gaussian noise,
``1.4826 * MAD`` is a consistent estimate of sigma; the resulting score is therefore
on the same "number of sigmas" scale as an ordinary z-score and the default threshold
of 3.5 reads as "3.5 robust sigmas from the local center".

Because the median and MAD have a ~50% breakdown point, a single large spike (or even
a modest cluster of them) barely perturbs the baseline, so the spike itself lights up
strongly instead of inflating the scale and hiding. We additionally compute the score
from the window **before** folding ``x`` in (predict-then-update), so a spike can never
contaminate the baseline it is being judged against.

State: one ``RingBuffer(window)`` of recent samples and the inherited counters -- no
extra float scalars -- which keeps the on-device footprint well under the 100-byte
budget for modest windows.
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad
from math import sqrt  # noqa: F401  (kept for parity with the C twin's includes)

MAD_TO_SIGMA = 1.4826  # rescale raw MAD to a Gaussian-sigma estimate
_EPS = 1e-9


class RobustZ(Detector):
    """Rolling median + MAD robust z-score over a trailing window (spike detector)."""

    name = "robust_z"

    def __init__(self, window: int = 30, threshold: float = 3.5, **params):
        # Override only to supply the sensible default threshold (3.5 robust sigmas);
        # everything else defers to the base contract (warmup, reset()).
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()                       # sets self.n = 0, self.last_score = 0.0
        self.buf = RingBuffer(self.window)    # one fixed-capacity window buffer

    def update(self, x: float) -> float:
        self.n += 1

        # Need at least 3 points for a meaningful median/MAD; otherwise no judgment.
        if len(self.buf) >= 3:
            sv = self.buf.sorted_values()           # O(window log window)
            med = median_sorted(sv)
            m = mad(self.buf.values(), med)         # raw MAD about the median
            sd = MAD_TO_SIGMA * m                    # robust sigma estimate
            score = abs(x - med) / (sd + _EPS)
        else:
            score = 0.0

        # Predict-then-update: judge x against the window BEFORE it joins the baseline.
        self.buf.push(x)

        if not self.warm():                          # self.n <= self.warmup
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # No standalone float scalars -- all numeric state lives in the ring buffer.
        return 0

    def state_buffer_len(self) -> int:
        return self.window
