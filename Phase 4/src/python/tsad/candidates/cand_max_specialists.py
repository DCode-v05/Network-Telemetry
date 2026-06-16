"""Max-fusion of tuned specialists -- ONE budget-fit unit covering all four types.

Strategy (max_specialists)
--------------------------
A single streaming detector that internally runs three lightweight, anomaly-family
specialist "heads" and fuses them by the MAX of their NORMALISED scores
(raw_score / per-head-threshold) -- never the mean, which would dilute the sharp
single-type signals into the noise of the silent heads::

    score = max( deriv  / THR_D,     # spike + transient  (first-difference z-score)
                 ewmv   / THR_E,      # gradual drift      (anomaly-aware "hold" baseline)
                 acf    / THR_A )     # loss of periodicity (lag-k autocorrelation drop)

Because every head is divided by its own threshold *before* the max, a non-firing head
sits well below 1.0 and the firing head dominates; the harness's single per-stream
threshold (picked near 1.0) then separates each type with minimal cross-talk.

What it took to stop the heads fighting each other (the "naive fusion" failure mode)
------------------------------------------------------------------------------------
  1. ewmv lives on a much noisier scale than deriv (its control-chart sigma sees a
     spike as a transient baseline jump). Its NORMALISER THR_E is therefore set high
     (~9) so ewmv's noise floor on spike/periodicity streams stays < 1.0 while a real
     drift (huge, sustained) still clears it. The HOLD/freeze trigger is kept separate
     at ~3 sigma so the drift baseline still freezes correctly.
  2. The acf head is GATED: it only activates on genuinely periodic streams (the
     reference autocorrelation r_ref >= ACF_GATE). On flat/bursty/trend bases r_ref is
     small, so acf emits 0 and cannot raise spurious periodicity alarms there.
  3. A spike that enters the ring buffer corrupts the autocorrelation for the whole
     window as it travels through, faking a periodicity collapse. A short REFRACTORY
     cooldown (triggered for free by the deriv head firing) silences acf for `refrac`
     samples after any sharp spike, so spike/transient streams on a periodic base no
     longer leak into the periodicity head.

Shared state to fit < 100 bytes
-------------------------------
There is exactly ONE ring buffer (window W) and it is needed ONLY by the acf head;
the spike (deriv) and drift (ewmv) heads are pure O(1) scalar recursions, so the only
buffer cost in the budget is paid once. The deriv and ewmv smoothing spans are
DECOUPLED from the buffer window (they are O(1), so a longer effective span costs no
memory) -- this is what lets the buffer stay at the minimum W=16 that periodicity needs
(period detection collapses below 16) while spike/drift still use their preferred
longer spans.

Float scalars (6): deriv {x_prev, var_d}; ewmv {z, mu, sigma}; acf {r_ref}.
  state_bytes = 4*W (buffer) + 4*6 (floats) + 8 (n + period/cool/flag) = 4*16+24+8 = 96 < 100.

Contract: pure scalar arithmetic in update(); O(window) (the acf pass); warm-up -> 0.0.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer

_EPS = 1e-9


class MaxSpecialists(Detector):
    """Max-fusion of three shared-state specialist heads (spike/transient, drift, periodicity)."""

    name = "max_specialists"

    def __init__(self, window: int = 16, threshold: float = 1.0, **params):
        # ---- per-head NORMALISERS (raw head score is divided by these; decision ~1.0)
        self.thr_d = float(params.pop("thr_d", 3.3))    # deriv: spike/transient z-score
        self.thr_e = float(params.pop("thr_e", 11.0))   # ewmv: drift control-chart sigma
        self.thr_a = float(params.pop("thr_a", 0.40))   # acf: periodicity drop

        # ---- effective smoothing spans, DECOUPLED from the buffer window (O(1) heads)
        self.dspan = int(params.pop("dspan", 40))       # deriv first-diff EWMV span
        self.espan = int(params.pop("espan", 20))       # ewmv slow/fast baseline span

        # ---- behavioural knobs
        self.freeze = float(params.pop("freeze", 3.0))  # ewmv HOLD trigger (sigma)
        self.slowdiv = float(params.pop("slowdiv", 6.0))  # ewmv slow-baseline = lam / slowdiv
        # acf_gate kept conservative-low so ALL genuinely periodic seeds (r_ref ~0.38..0.55)
        # activate the periodicity head; non-periodic bases sit below it and stay silent.
        self.acf_gate = float(params.pop("acf_gate", 0.36))  # min r_ref to call a stream periodic
        self.refrac = int(params.pop("refrac", 16))     # acf cooldown after a spike (samples)
        self.refrac_trig = float(params.pop("refrac_trig", 3.0))  # raw deriv level that arms cooldown

        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        # ONE ring buffer, used only by the acf periodicity head.
        self.buf = RingBuffer(self.window)

        # deriv head (spike + transient): 2 floats
        self.x_prev = 0.0
        self.var_d = 1.0
        self._ad = 2.0 / (self.dspan + 1)

        # ewmv_hold head (drift): 3 floats
        self._lam = 2.0 / (self.espan + 1)
        self._alpha_s = self._lam / self.slowdiv
        self.z = 0.0
        self.mu = 0.0
        self.sigma = 1.0

        # acf head (periodicity): 1 float + small int/flag state
        self.r_ref = 0.0
        self.period = 0
        self.periodic = False
        self.cool = 0          # refractory countdown

        # warm-up driven by the longest effective span (not the tiny buffer window)
        self.warmup = max(3, max(self.dspan, self.espan) // 3)

    # ------------------------------------------------------------------ acf helper
    def _acf(self, vals, lag):
        N = len(vals)
        if N <= lag + 2:
            return 0.0
        mean = sum(vals) / N
        num = 0.0
        for i in range(lag, N):
            num += (vals[i] - mean) * (vals[i - lag] - mean)
        den = _EPS
        for v in vals:
            dv = v - mean
            den += dv * dv
        return num / den

    # ------------------------------------------------------------------ update
    def update(self, x: float) -> float:
        self.n += 1

        # ---- first sample: seed every baseline, emit nothing
        if self.n == 1:
            self.buf.push(x)
            self.x_prev = x
            self.z = x
            self.mu = x
            self.last_score = 0.0
            return 0.0

        # ================= HEAD 1: deriv (spike + transient), O(1) =================
        d = x - self.x_prev
        sd = sqrt(self.var_d)
        s_deriv = abs(d) / (sd + _EPS)                  # mean-diff ~ 0, omitted (saves a float)
        self.var_d = (1.0 - self._ad) * (self.var_d + self._ad * d * d)
        self.x_prev = x

        # ================= HEAD 2: ewmv_hold (drift), O(1) =========================
        control_sigma = self.sigma * sqrt(self._lam / (2.0 - self._lam))
        s_ewmv = abs(self.z - self.mu) / (control_sigma + _EPS)
        self.z = self._lam * x + (1.0 - self._lam) * self.z      # fast smoother always tracks
        if s_ewmv < self.freeze:                                  # freeze slow baseline on anomaly
            dd = x - self.mu
            self.mu += self._alpha_s * dd
            self.sigma = sqrt((1.0 - self._alpha_s)
                              * (self.sigma * self.sigma + self._alpha_s * dd * dd))
            if self.sigma < 1e-6:
                self.sigma = 1e-6

        self.buf.push(x)

        # normalised deriv; a sharp first-difference arms the acf refractory cooldown
        # (a spike/transient travelling through the buffer fakes a periodicity collapse).
        f_d = s_deriv / self.thr_d
        if s_deriv > self.refrac_trig:
            self.cool = self.refrac

        # ================= HEAD 3: acf drop (periodicity), O(window) ===============
        s_acf = 0.0
        if self.buf.is_full():
            vals = self.buf.values()
            if self.period == 0:
                # establish the dominant lag + reference autocorrelation ONCE
                best_lag, best_r = 0, -2.0
                for lag in range(2, max(3, self.window // 2) + 1):
                    r = self._acf(vals, lag)
                    if r > best_r:
                        best_r, best_lag = r, lag
                self.period = best_lag if best_lag >= 2 else max(2, self.window // 4)
                self.r_ref = best_r
                self.periodic = best_r >= self.acf_gate     # gate: only periodic streams use acf
            elif self.periodic and self.cool == 0:
                r_now = self._acf(vals, self.period)
                drop = self.r_ref - r_now
                if drop > 0.0:
                    s_acf = drop
        if self.cool > 0:
            self.cool -= 1

        # ================= MAX-FUSION of normalised heads ==========================
        score = f_d
        f_e = s_ewmv / self.thr_e
        if f_e > score:
            score = f_e
        f_a = s_acf / self.thr_a
        if f_a > score:
            score = f_a

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # deriv {x_prev, var_d} = 2 ; ewmv {z, mu, sigma} = 3 ; acf {r_ref} = 1  -> 6
        return 6

    def state_buffer_len(self) -> int:
        return self.window
