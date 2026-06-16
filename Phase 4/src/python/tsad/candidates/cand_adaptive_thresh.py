"""Adaptive-threshold hybrid: ONE shared-state fusion detector for all four types.

Design philosophy
-----------------
A single budget-fit unit must separate spike, drift, periodicity AND transient at
once. We share ONE ring buffer (recent samples) plus a handful of O(1) scalars and run
four cheap "heads" off that shared state. Each head emits a score normalized by its own
decision threshold (raw / thr) and we FUSE BY MAX of the normalized heads -- never the
mean, which dilutes a strong single-head signal (the failure mode of the old voting
ensemble that crushed spike to 0.57). Because every head is on the same "fraction of its
own threshold" scale, a max-fusion ranks an anomalous sample of ANY type above normal
samples, which is what the harness' per-stream best-F1 threshold sweep needs.

The bet that makes the fusion work (instead of every head's noise floor polluting every
other type) is CHARACTER-AWARE GATING using only shared state:
  * the periodicity (ACF) head is SILENT unless the stream is genuinely periodic;
  * the drift head is SILENT on periodic streams (it would track the sine) and SILENT
    when the latest change is ABRUPT (a step/spike, not a gradual ramp) -- this is what
    stops a bursty base's legitimate level shifts from masquerading as drift;
  * the spike scale ADAPTS: the robust scale is lifted by the (held) baseline sigma, so a
    volatile bursty stretch raises the bar and the false spikes there disappear.

Heads (all off ONE shared ring buffer + ONE shared anomaly-aware "hold" baseline)
---------------------------------------------------------------------------------
* spike     : robust z |x - median| over the most-recent few buffer samples, normalized
              by max(window robust-sigma, hold sigma). The hold sigma rises in bursty
              stretches and freezes during an event -> adaptive, false-spike-resistant.
* transient : derivative z |x - x_prev| / sd_d (EWMV of the first difference). Catches
              1-2 sample microbursts and lights up spikes/transients on a periodic base,
              where a window median (which spans the sine) cannot.
* drift     : EWMV-hold control-chart z. A fast EWMA smoother z lags a sustained ramp;
              |z - mu| in CONTROL-sigma units stays large for the whole drift. mu/sigma
              is the SHARED hold baseline, frozen on anomaly so it never chases the ramp.
* periodicity: |autocorrelation| collapse on the shared buffer at the locked dominant lag
              (allowing the strong ANTI-correlation at the half-period, visible in a
              sub-period window). Score = |r_ref| - |r_now|, with r_ref a fixed reference.

Budget (float32 model)
----------------------
5 scalars: z, mu, sigma (drift + shared hold baseline), var_d (deriv scale), period(int
slot). x_prev is read from the ring buffer (no extra slot) and the deriv mean is taken as
0. ONE ring buffer length `window`. At window=16: 5*4 + 16*4 + 8 = 92 bytes < 100. Pure
scalar arithmetic; update is O(window) only for the small median / ACF passes.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad, MAD_TO_SIGMA

_EPS = 1e-9

# Per-head decision thresholds (the normalizer for max-fusion). The fused score is the
# max over heads of (head_raw / head_thr); 1.0 == "one head at its own threshold".
_THR_SPIKE = 4.5      # robust sigmas from the local median
_THR_DERIV = 4.5      # sigmas on the first difference
_THR_DRIFT = 4.5      # control-chart sigmas for the EWMV-hold drift z
_THR_ACF = 0.55       # absolute autocorrelation collapse that signals lost periodicity

_ACF_PERIODIC_MIN = 0.35   # min |peak autocorr| to treat a stream as periodic at all
_ACF_REF = 0.60            # fixed reference |autocorr| of a healthy periodic stream
_K_SPIKE = 5               # spike median uses only the most-recent K buffer samples
_DRIFT_GATE = 2.0          # drift head fires only if the change is GRADUAL (deriv z < this)
_FREEZE = 1.0              # fused level at/above which the hold baseline freezes
_SD_FLOOR = 1e-6


def _acf_lag(vals, lag, mean):
    """Lag-`lag` autocorrelation of `vals` given its precomputed mean (biased denom)."""
    N = len(vals)
    if N <= lag + 2:
        return 0.0
    num = 0.0
    for i in range(lag, N):
        num += (vals[i] - mean) * (vals[i - lag] - mean)
    den = 0.0
    for v in vals:
        d = v - mean
        den += d * d
    den += _EPS
    return num / den


class AdaptiveThresh(Detector):
    """Adaptive-threshold shared-state fusion detector (spike/drift/periodicity/transient)."""

    name = "adaptive_thresh"

    def __init__(self, window: int = 16, threshold: float = 1.0, **params):
        # Fused score is in "fraction of a head threshold" units; 1.0 == a head at its own
        # decision level. Window 16 is the largest that keeps state < 100 bytes (5 scalars)
        # and is big enough to see the half-period anti-correlation for periodicity.
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()                      # self.n = 0, self.last_score = 0.0
        self.buf = RingBuffer(self.window)   # ONE shared ring buffer

        # smoothing factors derived from the window (constants, not part of the C struct)
        self.lam = 2.0 / (self.window + 1)       # fast EWMA smoother (drift + deriv var)
        self.alpha_s = self.lam / 4.0            # slow hold-baseline smoother

        # --- drift head (EWMV-hold) + SHARED anomaly-aware hold baseline ---
        self.z = 0.0                         # fast EWMA smoother of the level
        self.mu = 0.0                        # slow baseline mean (frozen on anomaly)
        self.sigma = 1.0                     # slow baseline sigma (spike-scale guard too)

        # --- transient head: EWMV of the first difference (mean taken as 0) ---
        self.var_d = 1.0

        # --- periodicity head: locked dominant lag (sign of value is the state) ---
        self.period = 0                      # int slot; 0 == not set, -1 == aperiodic

    # ------------------------------------------------------------------- streaming
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)

        # ---- seed all baselines on the very first sample; no judgement yet ----
        if self.n == 1:
            self.buf.push(x)
            self.z = x
            self.mu = x
            self.sigma = 1.0
            self.last_score = 0.0
            return 0.0

        # x_prev is the most recent buffered value (no dedicated scalar slot).
        x_prev = self.buf.newest()
        vals = self.buf.values()

        # =============================================================== HEADS ===
        # Predict from CURRENT state, then fold x in, so an anomaly is never judged
        # against a baseline it has already contaminated.

        # ---- spike head: robust z over the most-recent K samples, adaptive scale ----
        spike_norm = 0.0
        if len(vals) >= 3:
            w = vals[-_K_SPIKE:] if len(vals) > _K_SPIKE else vals
            med = median_sorted(sorted(w))
            m = mad(w, med)                              # raw MAD about the local median
            robust_sigma = MAD_TO_SIGMA * m
            # Adaptive scale: the LARGER of the local robust sigma and the (held) baseline
            # sigma. A bursty region inflates the baseline sigma -> raises the bar; a quiet
            # region keeps it at the local noise floor.
            eff_scale = robust_sigma if robust_sigma > self.sigma else self.sigma
            if eff_scale < _EPS:
                eff_scale = _EPS
            spike_norm = (abs(x - med) / eff_scale) / _THR_SPIKE

        # ---- transient head: derivative z-score on the first difference ----
        d = x - x_prev
        sd_d = sqrt(self.var_d)
        deriv_z = abs(d) / (sd_d + _EPS)
        deriv_norm = deriv_z / _THR_DERIV

        # ---- drift head: EWMV-hold control-chart z (fast smoother vs slow baseline) ----
        # Gated OFF (a) on a genuinely periodic stream (period > 0) -- there the fast
        # smoother swings with the sine and would mistake the oscillation for drift -- and
        # (b) when the latest change is ABRUPT (deriv z large), which is a step / spike, not
        # a gradual ramp. (b) is what stops a bursty base's legitimate level shifts (sharp
        # jumps that then hold) from masquerading as drift, the classic bursty-base trap.
        if self.period > 0 or deriv_z > _DRIFT_GATE:
            drift_norm = 0.0
        else:
            control_sigma = self.sigma * sqrt(self.lam / (2.0 - self.lam))
            drift_z = abs(self.z - self.mu) / (control_sigma + _EPS)
            drift_norm = drift_z / _THR_DRIFT

        # ---- periodicity head: |autocorrelation| collapse on the shared buffer ----
        acf_norm = 0.0
        if self.buf.is_full():
            mean = sum(vals) / len(vals)
            if self.period == 0:
                # establish the dominant lag ONCE; rank on |acf| so the strong ANTI-
                # correlation at the half-period (visible in a sub-period window) qualifies.
                best_lag, best_abs = 0, 0.0
                hi = self.window - 3
                for lag in range(2, hi + 1):
                    rr = _acf_lag(vals, lag, mean)
                    if abs(rr) > best_abs:
                        best_abs, best_lag = abs(rr), lag
                # period < 0 flags "aperiodic": the ACF head stays SILENT for the whole
                # stream so its noisy swings never pollute the max-fusion.
                self.period = -1 if best_abs < _ACF_PERIODIC_MIN else best_lag
            elif self.period > 0:               # only score a genuinely periodic stream
                r_now = _acf_lag(vals, self.period, mean)
                drop = _ACF_REF - abs(r_now)    # |acf| collapse toward 0
                if drop > 0.0:
                    acf_norm = drop / _THR_ACF

        # ============================================================ FUSE (MAX) ==
        score = spike_norm
        if deriv_norm > score:
            score = deriv_norm
        if drift_norm > score:
            score = drift_norm
        if acf_norm > score:
            score = acf_norm

        # ================================================= STATE UPDATES (fold x) ==
        # Fast smoother always tracks (it is the drift detector's leading edge).
        self.z = self.lam * x + (1.0 - self.lam) * self.z

        # Anomaly-aware HOLD baseline: freeze mu/sigma while the FUSED score says
        # "anomaly". This keeps the drift residual scale and the spike scale-guard from
        # being dragged by the event, yet the lagging fast smoother z still drifts so a
        # sustained ramp keeps the drift head lit.
        if score < _FREEZE:
            dm = x - self.mu
            self.mu += self.alpha_s * dm
            self.sigma = sqrt((1.0 - self.alpha_s) * (self.sigma * self.sigma
                                                      + self.alpha_s * dm * dm))
            if self.sigma < _SD_FLOOR:
                self.sigma = _SD_FLOOR

        # derivative scale always tracks (a transient is a single large d that relaxes)
        self.var_d = (1.0 - self.lam) * (self.var_d + self.lam * d * d)

        # finally, fold x into the shared ring buffer (predict-then-update for spike/ACF)
        self.buf.push(x)

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # z, mu, sigma, var_d, period(int slot)  (x_prev lives in the ring buffer)
        return 5

    def state_buffer_len(self) -> int:
        return self.window
