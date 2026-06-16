"""Seasonal-residual (STL-lite) all-in-one streaming detector.

ONE shared-state unit that covers all four anomaly types (spike, drift,
periodicity, transient) inside the <100 byte budget by SHARING a single small ring
buffer across every head -- there is no per-head sub-detector and no second buffer.

Why "seasonal-residual" is realised with period-free surrogates
---------------------------------------------------------------
A stored per-phase seasonal profile cannot fit the budget: the telemetry bases used
here have a dominant period ~24, far larger than any profile affordable in <100
bytes. So the STL "trend + seasonal" decomposition is approximated LOCALLY, and the
loss-of-periodicity is detected from the buffer's autocorrelation instead of from a
stored profile:

  trend / drift  -> an anomaly-aware EWMA control-chart (the ewmv_hold statistic):
                    a fast smoother ``z`` is compared to a slow HELD mean ``mu``;
                    a sustained ramp accumulates in ``z`` while ``mu`` (frozen during
                    an anomaly) does not chase it. The drift score is CLIPPED so a
                    one-off legitimate level step (the bursty base) cannot out-shout
                    a genuine point anomaly -- a sustained drift stays at the cap for
                    many samples (recall) while a step touches it only briefly.

  spike / transient -> a derivative z-score with an anomaly-aware HOLD. The de-trended
                    surrogate for the "season" is the previous sample (the buffer's
                    second-newest entry, no extra storage), so the head reacts to the
                    one-step jump of a spike / fast transient and is the only head that
                    works on the periodic base, where a level baseline lags the season.

  loss of periodicity -> the classic ACF-DROP. The dominant lag is found once when the
                    buffer fills; the head ARMS only if the buffer is genuinely
                    periodic (peak ACF >= GATE), so it is completely SILENT on
                    flat/trend/bursty bases (no false positives there) and fires only
                    when an established periodicity collapses.

Fusion: MAX of NORMALISED head scores (score / own-alarm-scale). Max-fusion keeps the
sharp spike/transient evidence from being averaged away by the quieter drift /
periodicity heads; the drift CLIP and the periodicity GATE keep those two heads from
polluting the spike/transient operating point.

State (fixed, allocated once; mirrors the C twin) -- 6 float slots + one buffer:
  * RingBuffer(BUF)  the lone buffer. Its windowed mean/variance feed the ACF head
                     AND the drift control sigma; its second-newest entry is the
                     derivative head's previous sample. Nothing else is buffered.
  * scalars: mu_d, var_d (derivative baseline), z, mu (drift fast/slow),
             period, r_ref (periodicity)

Pure scalar arithmetic in ``update``; O(BUF) per step (windowed stats + one fixed-lag
ACF), with a one-time O(BUF^2/2) lag scan when the buffer first fills.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer

_EPS = 1e-9


class SeasonalResidual(Detector):
    name = "seasonal_residual"

    BUF_LEN = 16          # lone ring buffer; must span the season well enough to ARM ACF
    GATE = 0.45           # min peak ACF to ARM the periodicity head (rejects aperiodic)
    TH_DRV = 2.8          # derivative alarm scale (spike / transient)
    TH_EWMV = 2.5         # drift control-chart alarm scale
    DR_CAP = 0.9          # cap on the drift head's normalised output (anti-pollution)
    TH_PER = 0.4          # ACF-drop alarm scale
    HOLD = 2.5            # derivative-baseline freeze threshold (anomaly-aware)

    def __init__(self, window: int = 30, threshold: float = 1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.BUF_LEN)

        # periodicity
        self.period = 0            # 0 == dominant lag not yet established
        self.r_ref = 0.0           # reference ACF at that lag
        self.armed = 0             # 1 once a genuine periodicity is locked

        # derivative (spike / transient) baseline
        self.mu_d = 0.0
        self.var_d = 1.0

        # drift control-chart (ewmv_hold) state
        self.z = 0.0               # fast smoother
        self.mu = 0.0              # slow HELD mean

        self.alpha = 2.0 / (self.window + 1)
        self.lam = 2.0 / (self.window + 1)
        self.alpha_s = self.lam / 4.0

    # ------------------------------------------------------------------- helpers
    def _acf(self, vals, lag, mean, den):
        N = len(vals)
        if N <= lag + 2 or den < _EPS:
            return 0.0
        num = 0.0
        for i in range(lag, N):
            num += (vals[i] - mean) * (vals[i - lag] - mean)
        return num / den

    # ------------------------------------------------------------------- streaming
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)
        self.buf.push(x)
        warm = self.warm()

        vals = self.buf.values()
        m = len(vals)

        if m == 1:                 # need a previous sample for any difference
            self.z = x
            self.mu = x
            self.last_score = 0.0
            return 0.0

        # ---- shared windowed mean / variance (feeds ACF + drift scale) ----
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

        # ---- DERIVATIVE head (spike / transient), prev = buffer's 2nd-newest ----
        dx = x - vals[m - 2]
        sdd = sqrt(self.var_d)
        z_deriv = abs(dx - self.mu_d) / (sdd + _EPS)
        if z_deriv < self.HOLD:                       # anomaly-aware HOLD
            diff = dx - self.mu_d
            self.mu_d += self.alpha * diff
            self.var_d = (1.0 - self.alpha) * (self.var_d + self.alpha * diff * diff)
            if self.var_d < 1e-6:
                self.var_d = 1e-6
        s_drv = z_deriv / self.TH_DRV

        # ---- DRIFT head: ewmv_hold control chart, scale from the shared sd ----
        control_sigma = sd * sqrt(self.lam / (2.0 - self.lam))
        s_ewmv = abs(self.z - self.mu) / (control_sigma + _EPS)
        self.z = self.lam * x + (1.0 - self.lam) * self.z   # fast smoother always tracks
        if s_ewmv < self.TH_EWMV:                            # freeze slow mean on anomaly
            self.mu += self.alpha_s * (x - self.mu)
        s_drift = s_ewmv / self.TH_EWMV
        if s_drift > self.DR_CAP:                            # clip: a step can't out-shout a spike
            s_drift = self.DR_CAP

        # ---- PERIODICITY head: gated ACF-drop ----
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
                r_now = self._acf(vals, self.period, mean, den)
                drop = self.r_ref - r_now
                if drop > 0.0:
                    s_per = drop / self.TH_PER

        # ---- MAX-fuse normalised heads ----
        score = s_drv
        if s_drift > score:
            score = s_drift
        if s_per > score:
            score = s_per

        if not warm:
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # mu_d, var_d, z, mu, period, r_ref  (alpha/lam/alpha_s are derived constants;
        # armed is a 1-bit flag folded into the +8 counter allowance)
        return 6

    def state_buffer_len(self) -> int:
        return self.BUF_LEN
