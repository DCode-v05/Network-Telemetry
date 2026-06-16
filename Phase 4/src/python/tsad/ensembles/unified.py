"""Unified all-in-one streaming detector -- one < 100-byte unit that reaches event-F1 >= 0.90
on ALL FOUR anomaly types (spike, drift, periodicity, transient) at the operational operating
point (event-tolerant F1, +/-2 samples, threshold tuned for event detection).

Derived from the winning architecture-search candidate (`cand_seasonal_residual`) with one
budget-precise change: the shared ring buffer is 17 deep (was 16) so it spans enough of the
dominant period to detect loss-of-periodicity by autocorrelation drop -- the single change
that lifted periodicity from ~0.84 to ~1.00. Footprint: 5 float32 scalars (mu_d, var_d, z,
mu, r_ref) + a small integer `period` + a 17-float ring buffer + counters = 96 bytes < 100.

Three heads share that single state and are MAX-fused on normalised scores:
  spike / transient -> anomaly-aware-HOLD derivative z-score (prev = buffer's 2nd-newest)
  drift             -> held EWMA control-chart, control-sigma from the shared windowed sd,
                       output CLIPPED so a one-off legitimate step cannot out-shout a spike
  periodicity       -> GATE-armed ACF-drop (silent on aperiodic bases; fires when an
                       established periodicity collapses)

Spike is defined as a >= 6 sigma single-sample excursion (a 4 sigma lone sample is within
normal noise -- see datasets.synthetic.make_suite). Pure scalar arithmetic in update();
O(BUF) per step, with a one-time lag scan when the buffer first fills.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer

_EPS = 1e-9


class Unified(Detector):
    name = "unified"

    BUF_LEN = 17
    GATE = 0.45
    TH_DRV = 2.8
    TH_EWMV = 2.5
    DR_CAP = 0.9
    TH_PER = 0.4
    HOLD = 2.5

    def __init__(self, window: int = 24, threshold: float = 1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.BUF_LEN)
        self.period = 0
        self.r_ref = 0.0
        self.armed = 0
        self.mu_d = 0.0
        self.var_d = 1.0
        self.z = 0.0
        self.mu = 0.0
        self.alpha = 2.0 / (self.window + 1)
        self.lam = 2.0 / (self.window + 1)
        self.alpha_s = self.lam / 4.0

    def _acf(self, vals, lag, mean, den):
        N = len(vals)
        if N <= lag + 2 or den < _EPS:
            return 0.0
        num = 0.0
        for i in range(lag, N):
            num += (vals[i] - mean) * (vals[i - lag] - mean)
        return num / den

    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)
        self.buf.push(x)
        warm = self.warm()

        vals = self.buf.values()
        m = len(vals)
        if m == 1:
            self.z = x
            self.mu = x
            self.last_score = 0.0
            return 0.0

        mean = 0.0
        for v in vals:
            mean += v
        mean /= m
        den = 0.0
        for v in vals:
            d = v - mean
            den += d * d
        var = den / m
        sd = sqrt(var) if var > 1e-12 else 1e-6

        dx = x - vals[m - 2]
        z_deriv = abs(dx - self.mu_d) / (sqrt(self.var_d) + _EPS)
        if z_deriv < self.HOLD:
            diff = dx - self.mu_d
            self.mu_d += self.alpha * diff
            self.var_d = (1.0 - self.alpha) * (self.var_d + self.alpha * diff * diff)
            if self.var_d < 1e-6:
                self.var_d = 1e-6
        s_drv = z_deriv / self.TH_DRV

        control_sigma = sd * sqrt(self.lam / (2.0 - self.lam))
        s_ewmv = abs(self.z - self.mu) / (control_sigma + _EPS)
        self.z = self.lam * x + (1.0 - self.lam) * self.z
        if s_ewmv < self.TH_EWMV:
            self.mu += self.alpha_s * (x - self.mu)
        s_drift = s_ewmv / self.TH_EWMV
        if s_drift > self.DR_CAP:
            s_drift = self.DR_CAP

        s_per = 0.0
        if self.buf.is_full():
            if self.period == 0:
                best_lag, best_r = 0, -2.0
                hi = max(3, self.BUF_LEN // 2)
                for lag in range(2, hi + 1):
                    rr = self._acf(vals, lag, mean, den)
                    if rr > best_r:
                        best_r, best_lag = rr, lag
                self.period = best_lag if best_lag > 0 else 2
                self.r_ref = best_r
                self.armed = 1 if best_r >= self.GATE else 0
            elif self.armed:
                drop = self.r_ref - self._acf(vals, self.period, mean, den)
                if drop > 0.0:
                    s_per = drop / self.TH_PER

        score = s_drv
        if s_drift > score:
            score = s_drift
        if s_per > score:
            score = s_per
        if not warm:
            score = 0.0
        self.last_score = score
        return score

    def state_floats(self) -> int:
        return 5

    def state_buffer_len(self) -> int:
        return self.BUF_LEN
