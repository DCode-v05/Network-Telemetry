"""Page-Hinkley change detector (two-sided) on EWMA-normalized deviations.

The Page-Hinkley (PH) test is a sequential change-point test that accumulates the
running sum of deviations of a signal from its mean, minus a small tolerance
``delta`` (slack). The cumulative sum is tracked against its running minimum; once
the gap (sum - running_min) exceeds a threshold the process is declared to have
drifted. It is tuned to catch *gradual drift* rather than sharp spikes -- a single
isolated spike produces only a modest, transient bump.

This implementation normalizes each sample by an EWMA estimate of the running mean
and standard deviation, so the PH statistic operates on roughly unit-variance
deviations ``e`` and is therefore scale-free across heterogeneous telemetry streams.
We run two one-sided PH tests (upward and downward drift) and report the larger of
the two gaps, giving a two-sided detector. When the score crosses ``threshold`` the
accumulators are reset, so the test re-arms for the next change-point.

State (6 float scalars, no ring buffer):
  xbar   -- running mean (cumulative)
  sd     -- EWMA standard-deviation estimate
  m_up   -- upward cumulative sum
  min_up -- running minimum of m_up
  m_dn   -- downward cumulative sum
  min_dn -- running minimum of m_dn

Footprint: 6 floats + counters, well under the 100-byte budget. Mirrors the C twin's
``struct { float xbar, sd, m_up, min_up, m_dn, min_dn; int n; }`` 1:1.

Score scale: a cumulative-statistic gap. Default ``threshold = 5.0`` is the decision
boundary; ensembles combine via ``score / threshold``.
"""

from __future__ import annotations

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer  # noqa: F401  (contract import; unused)
from tsad.core.stats import median_sorted, mad  # noqa: F401  (contract import; unused)
from math import sqrt


class PageHinkley(Detector):
    """Two-sided Page-Hinkley drift detector on EWMA-normalized deviations."""

    name = "page_hinkley"

    def __init__(self, window: int = 30, threshold: float = 5.0, **params):
        # Default threshold 5.0 (a cumulative-gap boundary); window only sets the
        # EWMA smoothing factor alpha = 2/(window+1) and the inherited warm-up.
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()  # sets self.n = 0, self.last_score = 0.0
        # EWMA smoothing factor and PH slack (allocated once).
        self._alpha = 2.0 / (self.window + 1)
        self._delta = 0.005
        # Fixed scalar state.
        self.xbar = 0.0    # running (cumulative) mean
        self.sd = 1.0      # EWMA std-dev estimate
        self.m_up = 0.0     # upward cumulative sum
        self.min_up = 0.0   # running min of m_up
        self.m_dn = 0.0     # downward cumulative sum
        self.min_dn = 0.0   # running min of m_dn

    # -------------------------------------------------------------------- update
    def update(self, x: float) -> float:
        self.n += 1
        alpha = self._alpha
        delta = self._delta

        # Update running mean, then an EWMA estimate of the deviation variance.
        self.xbar += (x - self.xbar) / self.n
        d = x - self.xbar
        self.sd = sqrt((1.0 - alpha) * (self.sd * self.sd + alpha * d * d))
        if self.sd < 1e-6:
            self.sd = 1e-6

        # Normalized deviation (roughly unit-variance).
        e = (x - self.xbar) / (self.sd + 1e-9)

        # Two one-sided Page-Hinkley statistics.
        self.m_up += (e - delta)
        self.min_up = min(self.min_up, self.m_up)
        ph_up = self.m_up - self.min_up

        self.m_dn += (-e - delta)
        self.min_dn = min(self.min_dn, self.m_dn)
        ph_dn = self.m_dn - self.min_dn

        score = max(ph_up, ph_dn)

        # Re-arm after firing so the test is ready for the next change-point.
        if score >= self.threshold:
            self.m_up = 0.0
            self.min_up = 0.0
            self.m_dn = 0.0
            self.min_dn = 0.0

        if not self.warm():
            score = 0.0
            self.last_score = score
            return score

        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        return 6  # xbar, sd, m_up, min_up, m_dn, min_dn
