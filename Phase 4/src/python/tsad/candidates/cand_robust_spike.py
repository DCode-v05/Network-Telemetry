"""Robust-spike unified streaming detector (shared-state, normalized-excess max-fusion).

ONE budget-fit unit covering spike, drift, periodicity AND transient. Three heads SHARE a
single short ring buffer (of FIRST DIFFERENCES) plus a tiny EWMV-hold baseline:

  * SPIKE / TRANSIENT head -- robust z of the first difference d = x - x_prev against the
    rolling median + MAD of recent first differences::

        score = |d - med_d| / (1.4826 * MAD_d)

    Differencing detrends the signal, so the head is robust to BOTH a curved periodic base
    and a sloped trend base (where a level-based median straddles the curve and inflates the
    scale). The median + MAD have a ~50% breakdown point, so an isolated spike / transient --
    or a single legitimate level-shift step on a bursty base -- barely perturbs the scale it
    is judged against (predict-then-update: d is scored BEFORE it joins the buffer). This is
    what keeps spike precision high on the noisy bursty / periodic bases.

  * DRIFT head -- an EWMV control statistic with an anomaly-aware "hold" baseline: the slow
    mean / variance freeze while the standardized deviation is over threshold, so a gradual
    ramp drives the residual up instead of being chased into the baseline. Two float scalars.

  * PERIODICITY head -- lag-k autocorrelation DROP, computed ON THE SHARED first-difference
    ring buffer. Differencing a sinusoid yields a (phase-shifted) sinusoid of the SAME
    period, so the dominant lag is preserved; the positive part of (r_ref - r_now) scores
    loss of periodic structure. No second buffer.

Fusion -- the heads are fused by the MAX of their NORMALIZED EXCESS over each head's own
nominal threshold::

    f_h    = max(0, score_h - thr_h) / scale_h
    output = max(f_spike, f_drift, f_acf)

Taking the excess (not the raw score) means a head contributes ZERO while it sits at its own
in-control noise level, so an out-of-type head cannot pollute the single per-stream threshold
the harness picks -- the fused output stays near the strongest in-type head (close to an
oracle per-type router) instead of being diluted by a mean. Higher == more anomalous.

State (mirrors the C twin ``struct``):
  * RingBuffer(window) of first differences -- shared by the spike & periodicity heads
  * x_prev, mu, sigma                       -- diff seed + EWMV-hold baseline (3 floats)
  * period (int slot), r_ref                -- periodicity reference (2 floats)
Total = window + 5 floats; for window <= 17 the float32 footprint is < 100 bytes.

Pure scalar arithmetic only inside ``update``; cost O(window). Warm-up returns 0.0.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad, MAD_TO_SIGMA

_EPS = 1e-9

# Per-head nominal thresholds (the in-control noise ceiling) and post-excess scales.
_SPIKE_THR = 3.0      # robust sigmas on the first difference before a spike/transient counts
_SPIKE_SCALE = 1.0
_DRIFT_THR = 3.0      # EWMV control sigmas before sustained drift counts
_DRIFT_SCALE = 1.0
_ACF_THR = 0.20       # autocorrelation drop before loss-of-periodicity counts
_ACF_SCALE = 0.10


class RobustSpikeUnified(Detector):
    """Shared-state robust-diff spike/transient + ewmv-hold drift + acf-drop periodicity."""

    name = "robust_spike"

    def __init__(self, window: int = 16, threshold: float = 1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.window)   # ring buffer of FIRST DIFFERENCES (shared)
        self.x_prev = 0.0
        # drift (ewmv-hold) baseline
        self.lam = 2.0 / (self.window + 1)
        self.alpha_s = self.lam / 4.0
        self.mu = 0.0
        self.sigma = 1.0
        # periodicity (acf-drop) reference, over the differenced buffer
        self.period = 0
        self.r_ref = 0.0

    # ------------------------------------------------------------- head helpers
    def _drift_score(self, x: float) -> float:
        """EWMV control statistic with anomaly-aware hold baseline."""
        control_sigma = self.sigma * sqrt(self.lam / (2.0 - self.lam))
        score = abs(x - self.mu) / (control_sigma + _EPS)
        if score < _DRIFT_THR:                       # freeze baseline on suspected anomaly
            d = x - self.mu
            self.mu += self.alpha_s * d
            self.sigma = sqrt((1.0 - self.alpha_s) * (self.sigma * self.sigma
                                                      + self.alpha_s * d * d))
            if self.sigma < 1e-6:
                self.sigma = 1e-6
        return score

    def _acf(self, vals, lag):
        N = len(vals)
        if N <= lag + 2:
            return 0.0
        mean = sum(vals) / N
        num = 0.0
        for i in range(lag, N):
            num += (vals[i] - mean) * (vals[i - lag] - mean)
        den = 0.0
        for v in vals:
            dd = v - mean
            den += dd * dd
        den += _EPS
        return num / den

    def _periodicity_score(self, vals) -> float:
        if len(self.buf) < self.window:
            return 0.0
        if self.period == 0:
            best_lag, best_r = 0, -2.0
            for lag in range(2, max(3, self.window // 2) + 1):
                r = self._acf(vals, lag)
                if r > best_r:
                    best_r, best_lag = r, lag
            if best_r < 0.2:                         # not really periodic -> stay quiet
                self.period = max(2, self.window // 4)
                self.r_ref = 0.05
            else:
                self.period = best_lag
                self.r_ref = best_r
            return 0.0
        r_now = self._acf(vals, self.period)
        drop = self.r_ref - r_now
        return drop if drop > 0.0 else 0.0

    # ------------------------------------------------------------------- streaming
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)

        if self.n == 1:
            self.x_prev = x
            self.mu = x
            self.sigma = 1.0
            self.buf.push(0.0)
            self.last_score = 0.0
            return 0.0

        # ---- SPIKE / TRANSIENT head: robust z of the first difference (predict-then-update)
        d = x - self.x_prev
        if len(self.buf) >= 3:
            sv = self.buf.sorted_values()
            med = median_sorted(sv)
            m = mad(self.buf.values(), med)
            sd = MAD_TO_SIGMA * m
            s_spike = abs(d - med) / (sd + _EPS)
        else:
            s_spike = 0.0

        # ---- DRIFT head: scored against (and updating) its own hold baseline on x
        s_drift = self._drift_score(x)

        # ---- fold the first difference into the shared buffer, then PERIODICITY head
        self.buf.push(d)
        self.x_prev = x
        s_acf = self._periodicity_score(self.buf.values())

        # ---- max-fusion of NORMALIZED EXCESS over each head's in-control noise ceiling ----
        f_spike = (s_spike - _SPIKE_THR) / _SPIKE_SCALE
        if f_spike < 0.0:
            f_spike = 0.0
        f_drift = (s_drift - _DRIFT_THR) / _DRIFT_SCALE
        if f_drift < 0.0:
            f_drift = 0.0
        f_acf = (s_acf - _ACF_THR) / _ACF_SCALE
        if f_acf < 0.0:
            f_acf = 0.0

        score = f_spike
        if f_drift > score:
            score = f_drift
        if f_acf > score:
            score = f_acf

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # x_prev, mu, sigma (drift) + period(int slot), r_ref (periodicity)
        return 5

    def state_buffer_len(self) -> int:
        return self.window
