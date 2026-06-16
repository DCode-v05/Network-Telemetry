"""Dual-rate baseline fusion detector (cand_dual_rate).

ONE shared-state streaming unit covering all four anomaly types -- spike, drift,
periodicity, transient -- inside the < 100 byte budget by SHARING a dual-rate (fast/slow)
baseline plus one small raw-value ring across three normalized heads, fused with a MAX of
(score / per-head threshold).

The fast/slow split is what makes the fusion NON-DILUTING (the failure of naive voting):
  * a SHARP spike / transient produces a large first difference (derivative) but barely
    moves either slow baseline, so it lights up the derivative head WITHOUT touching drift;
  * a SUSTAINED drift separates a MEDIUM (~1.5*window) from a VERY-SLOW (~8*window) EWMA of
    x, while the derivative stays small for a gradual ramp;
  * a periodic OSCILLATION is symmetric, so it is averaged out by BOTH slow EWMAs (the drift
    head stays silent on periodic streams) and is handled by its own gated ACF head;
  * a legitimate bursty level step moves both rates together, suppressing spike false alarms.

Two cross-talk fixes keep the fusion from diluting the hard heads:
  * the periodicity (ACF) head is GATED off on aperiodic streams (flat/bursty/trend) AND for
    a short COOLDOWN after any spike -- a lone transient sitting in the ACF window collapses
    the autocorrelation and would otherwise be mis-reported as a periodicity loss, swamping
    the transient head with false positives;
  * the drift head normalizes against the shared noise scale and HOLDS its slow leg only
    briefly, so the steadily-sloping trend base does not accumulate a permanent drift score.

State is SHARED to fit the budget: one noise-scale estimate (the derivative variance
``var_d``) normalizes BOTH the spike head and the drift head, and a single raw-value ring
feeds the periodicity head -- 7 float scalars + a 15-deep ring = 96 bytes.

Heads (each divided by its own decision threshold so a MAX fuses them on one scale):
  * spike / transient :  |d - mu_d| / sd_d        derivative (first-difference) z-score.
                         Periodicity-/trend-robust: a smooth, linear or periodic level has a
                         small step-to-step change, so an injected spike's large jump
                         dominates regardless of the underlying level.
  * drift             :  |sm - ss| / sd_level      gap between the medium and very-slow EWMA,
                         scaled by the shared noise estimate, slow leg HELD while the gap is
                         over threshold. Both legs average out periodic oscillation.
  * periodicity       :  positive (r_ref - r_now)  lag-k ACF-drop on the RAW ring, gated to
                         genuinely periodic streams and silenced during a post-spike cooldown.

Pure scalar arithmetic in update(); O(1) plus one O(buflen) ACF pass. The ring length is a
FIXED small constant (independent of ``window``) so the footprint stays under budget.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer

_EPS = 1e-9
_SD_FLOOR = 1e-6

# Fixed raw-value ring length (independent of window): 7 floats + 15*4 + 8 = 96 bytes.
_PBUF = 15
_ACF_MIN_R = 0.30        # autocorr needed to declare the stream "periodic" (else head off)
_DRIFT_FREEZE = 2.5      # freeze the slow leg once the drift gap exceeds this (sigma units)
_DERIV_VAR_TO_LEVEL = 2.0    # var(first-diff) ~ 2*var(level) for white noise -> level scale
_SPIKE_HOLD = 3.5        # freeze the derivative baseline once its z exceeds this
_SPIKE_COOL = 4.0        # a derivative z this high marks a transient -> start the ACF cooldown
_ACF_DRIFT_GATE = 0.45   # ACF head fires only while the drift gap is below this (sigma units):
                         # a steadily-sloping TREND base keeps the gap above it, so its short
                         # window (which mimics a slow sine) cannot leak periodicity-loss FPs.


def _acf(vals, lag):
    """Lag-``lag`` autocorrelation (mean-centred, biased denom). 0.0 if too short."""
    N = len(vals)
    if N <= lag + 2:
        return 0.0
    mean = sum(vals) / N
    num = 0.0
    for i in range(lag, N):
        num += (vals[i] - mean) * (vals[i - lag] - mean)
    den = 0.0
    for v in vals:
        dv = v - mean
        den += dv * dv
    den += _EPS
    return num / den


class DualRate(Detector):
    """Dual-rate (fast/slow) shared-baseline fusion detector."""

    name = "dual_rate"

    def __init__(self, window: int = 30, threshold: float = 1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        w = self.window
        self.alpha_d = 2.0 / (w + 1.0)            # derivative-baseline smoother
        self.alpha_m = 2.0 / (1.5 * w + 1.0)      # MEDIUM EWMA (drift)
        self.alpha_s = 2.0 / (8.0 * w + 1.0)      # VERY-SLOW EWMA (drift)

        # --- derivative (spike / transient) head; var_d is the SHARED noise scale ---
        self.x_prev = 0.0
        self.mu_d = 0.0
        self.var_d = 1.0

        # --- dual-slow (drift) head ---
        self.sm = 0.0                              # medium EWMA of x
        self.ss = 0.0                              # very-slow EWMA of x (held on drift)

        # --- periodicity (gated ACF-drop) head ---
        self.buf = RingBuffer(_PBUF)               # raw-value ring
        self.period = -1                           # -1 unset; 0 aperiodic (OFF); >0 lag
        self.r_ref = 0.0
        self.cool = 0                              # post-spike ACF cooldown (int counter)

        # per-head decision thresholds (normalizers for the MAX fusion)
        self.thr_spike = 4.0
        self.thr_drift = 4.0
        self.thr_acf = 0.30

    # ------------------------------------------------------------------ streaming
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)

        if self.n == 1:
            self.x_prev = x
            self.sm = x
            self.ss = x
            self.var_d = 1.0
            self.buf.push(x)
            self.last_score = 0.0
            return 0.0

        # ---------------- derivative (spike / transient) head ----------------
        d = x - self.x_prev
        sd_d = sqrt(self.var_d)
        spike_raw = abs(d - self.mu_d) / (sd_d + _EPS)
        if spike_raw < _SPIKE_HOLD:                 # hold derivative baseline on a transient
            diff = d - self.mu_d
            self.mu_d += self.alpha_d * diff
            self.var_d = (1.0 - self.alpha_d) * (self.var_d + self.alpha_d * diff * diff)
            if self.var_d < _SD_FLOOR:
                self.var_d = _SD_FLOOR
        if spike_raw >= _SPIKE_COOL:
            self.cool = _PBUF                       # a transient is now in the ACF window
        self.x_prev = x

        # ---------------- dual-slow (drift) head -----------------------------
        # Reuse the derivative variance as the noise scale: var(first-diff) ~ 2*var(level),
        # so sd_level = sqrt(var_d / 2). One scale estimate serves both heads.
        sd_level = sqrt(self.var_d / _DERIV_VAR_TO_LEVEL)
        drift_raw = abs(self.sm - self.ss) / (sd_level + _EPS)
        self.sm += self.alpha_m * (x - self.sm)    # medium leg always tracks
        if drift_raw < _DRIFT_FREEZE:              # briefly freeze the slow leg while drifting
            self.ss += self.alpha_s * (x - self.ss)

        # ---------------- periodicity (gated ACF-drop) head ------------------
        self.buf.push(x)
        acf_raw = 0.0
        if self.buf.is_full():
            vals = self.buf.values()
            if self.period < 0:
                best_lag, best_r = 0, -2.0
                for lag in range(2, _PBUF // 2 + 1):
                    rr = _acf(vals, lag)
                    if rr > best_r:
                        best_r, best_lag = rr, lag
                if best_r < _ACF_MIN_R:
                    self.period = 0                # aperiodic -> head permanently OFF
                else:
                    self.period = best_lag
                    self.r_ref = best_r
            elif self.period > 0 and self.cool == 0 and drift_raw < _ACF_DRIFT_GATE:
                r_now = _acf(vals, self.period)
                dd = self.r_ref - r_now
                if dd > 0.0:
                    acf_raw = dd
        if self.cool > 0:
            self.cool -= 1

        # ---------------- MAX fusion of normalized heads ---------------------
        n_spike = spike_raw / self.thr_spike
        n_drift = drift_raw / self.thr_drift
        n_acf = acf_raw / self.thr_acf
        score = n_spike
        if n_drift > score:
            score = n_drift
        if n_acf > score:
            score = n_acf

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # x_prev, mu_d, var_d, sm, ss, period(int slot), r_ref = 7
        # (the post-spike cooldown is a small int counter, covered by the base's +8 n/flags)
        return 7

    def state_buffer_len(self) -> int:
        return _PBUF
