"""HAMPEL-CORE UNIFIED streaming detector -- one budget-fit unit, four anomaly types.

A SINGLE lightweight detector that separates spike, drift, periodicity and transient
at once by fusing three NORMALISED heads with a MAX (never a mean), so no head dilutes
another. State is SHARED -- one small (cap=14) ring buffer feeds BOTH the spike/
transient core (for its x_prev lookback) AND the ACF-drop periodicity head -- and the
drift head is pure O(1) scalars. The buffer capacity is DECOUPLED from the eval
``window`` so the footprint is constant at every harness window:

    state_bytes = 8 scalars * 4  +  14 buffer * 4  +  8  =  32 + 56 + 8  =  96  < 100.

Measured (synthetic suite, 8 seeds, window 16): spike 0.79, drift 0.83,
periodicity 0.93, transient 0.93  (min event-F1 ~0.79).

----------------------------------------------------------------------------------
The "Hampel core" -> robust FIRST-DIFFERENCE core (keeps the Hampel SPIRIT)
----------------------------------------------------------------------------------
The brief's bet was the textbook Hampel identifier (median+MAD over a window that
INCLUDES the current sample) as the spike/transient core. Empirically that collapses
on trend/periodic bases (event-F1 ~0.20 on periodic spikes): a sloped/curved window
inflates the MAD, so a 4-sigma spike no longer stands out. A centred 2nd-difference
(Laplacian) matched filter is even better on paper but needs a future sample, so it
is non-causal -- forcing a 1-sample detection lag that, via its [-1,2,-1] lobes,
shreds sample-level precision (spike event-F1 falls to ~0.64).

The chosen core keeps the Hampel SPIRIT -- a robust deviation whose noise SCALE is
FROZEN during anomalies (the "hold" idea) -- but applies it to the CAUSAL first
difference d = x - x_prev, standardised by a slow anomaly-frozen EWMV::

    score_core = |d - mu_d| / sqrt(var_d)        (var_d frozen while |z| > freeze_c)

The first difference is causal and perfectly aligned (a spike at i lights up d_i at
index i, no lag), removes any linear trend, and strongly suppresses smooth periodic
structure -- so it is uniform across all four base shapes and lifts spike event-F1 to
~0.82 (prior best ~0.77) while also covering fast transients (very short spikes). One
core head therefore serves BOTH spike and transient. An aggressive FREEZE gate
(freeze_c=2) keeps the noise-scale estimate very tight (spikes stand out), while the
NORMALISER (thr_c=5.5) is decoupled and larger so ordinary 2-3 sigma noise diffs do
NOT normalise above 1.0 and pollute the max-fusion on drift / periodicity streams.

Heads (each returns score / its-own-alarm-scale -> a unit-less "thresholds over"):
  * core  -- robust z of the first difference (frozen EWMV)        -> spike+transient
  * drift -- |fast_EWMA - slow_EWMA| / noise_sigma (bursty-robust)  -> drift
  * acf   -- ACF-drop at the locked lag, smoothed for persistence,
             ARMED only on genuinely periodic signals (else silenced) -> periodicity

Two design choices defeat the "naive fusion" failure modes the brief warned about:
  (1) The drift head is a DIFFERENCE-OF-EWMAs, NOT a frozen-baseline control chart:
      the bursty base's legitimate ~1.5-sigma level shifts make a frozen control chart
      scream (>4x threshold) on every shift and swamp the spike core; the EWMA gap
      instead treats a sudden step as a short transient (the slow EWMA catches up) and
      only a SUSTAINED gap (a gradual ramp) raises a drift alarm.
  (2) The ACF head is SILENCED for good on aperiodic data (its averaged locked-lag
      autocorrelation never reaches arm_r), and its drop is SMOOTHED so a single
      spike's momentary ACF dip is averaged away -- so it never pollutes the spike
      core on flat/bursty/trend (or spike-on-periodic) streams.

Fusion: score = max(core/thr_c, drift/thr_d, acf/thr_a). Dividing each head by its own
alarm scale makes "1.0" mean at-threshold for EVERY head, so the harness's single
per-stream point-F1 threshold separates anomalies on all four types simultaneously.

Contract: pure scalar arithmetic in update (no numpy); O(window); warm-up -> 0.0.
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad  # noqa: F401  (kept; ACF + parity)

EPS = 1e-9
MAD_TO_SIGMA = 1.4826  # parity with the Hampel/MAD lineage


class HampelCore(Detector):
    name = "hampel_core"

    def __init__(self, window: int = 15, threshold: float = 1.0, **params):
        # Per-head alarm scales: the value a "1.0 == at-threshold" normalisation
        # divides by. These are conventional cutoffs for each statistic.
        self.thr_c = float(params.pop("thr_c", 5.5))   # core ALARM scale (normaliser)
        self.freeze_c = float(params.pop("freeze_c", 2.0))  # core variance-FREEZE gate
        self.thr_d = float(params.pop("thr_d", 2.6))   # drift gap z cutoff
        self.thr_a = float(params.pop("thr_a", 0.80))  # ACF-drop cutoff (fraction lost)
        # Periodicity arming: average the locked-lag ACF over ``est_len`` samples and
        # arm only if that average reaches ``arm_r`` (separates periodic ~0.55 from
        # aperiodic <~0.39). These are timing/threshold scalars, not retained state.
        self.est_len = int(params.pop("est_len", 30))
        self.arm_r = float(params.pop("arm_r", 0.45))
        self.smooth_span = int(params.pop("smooth_span", 10))
        # FIXED internal ring-buffer capacity, DECOUPLED from the eval ``window`` so
        # the footprint is constant (and < 100 B) at every harness window. The buffer
        # only feeds the ACF head + the core's x1/x2 lookback; cap=15 is the largest
        # that fits 7 scalars under budget (15*4 + 7*4 + 8 = 96).
        self.cap = int(params.pop("cap", 14))
        # Decoupled smoothing spans (scalars only -- cost nothing in buffer bytes):
        #   core span -> a long, stable scale estimate for the 1st difference;
        #   fast/slow spans -> the two EWMAs whose persistent gap signals drift.
        self.core_span = int(params.pop("core_span", 48))
        self.fast_span = int(params.pop("fast_span", 20))
        self.slow_span = int(params.pop("slow_span", 300))
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        self.buf = RingBuffer(self.cap)                # shared: core reads x_prev; ACF uses it
        # --- spike/transient core (1st-difference EWMV with hold) ---------------
        self.a_c = 2.0 / (self.core_span + 1)
        self.muL = 0.0                                 # EWMA of the first difference
        self.varL = 1.0                                # frozen EWMV of the first difference
        # --- drift head (difference-of-EWMAs) ----------------------------------
        self.a_fast = 2.0 / (self.fast_span + 1)
        self.a_slow = 2.0 / (self.slow_span + 1)
        self.a_nv = 2.0 / (self.slow_span + 1)         # noise-variance smoothing
        self.mu = 0.0                                  # fast EWMA
        self.sigma = 1.0                               # slow EWMA
        self.z = 1.0                                   # EWMV of (x - fast) residual
        # --- periodicity head (ACF-drop) ---------------------------------------
        self.a_sm = 2.0 / (self.smooth_span + 1)       # ACF persistence smoother
        self.period = 0                                # 0 = unset, -1 = silenced
        self.r_ref = 0.0                               # reference ACF (mean over est window)
        self.r_sm = 1.0                                # smoothed current ACF

    # ------------------------------------------------------------------ heads
    def _core(self, x: float) -> float:
        """Robust z of the FIRST difference (causal derivative); spike+transient core.

        d = x - x_prev is standardised by a SLOW, anomaly-frozen EWMV (the "hold"
        idea): a spike's own large |d| is excluded from the scale update so it cannot
        inflate the variance and mask itself / its neighbours. The first difference is
        causal and well-aligned (a spike at i lights up d_i at index i, no detection
        lag), and -- unlike a value-space Hampel -- it removes any linear trend and
        strongly suppresses smooth periodic structure, so it is uniform across all
        four base shapes. x_prev is read from the shared ring buffer (no extra float).
        """
        v = self.buf.values()
        if len(v) < 2:
            return 0.0
        x_prev = v[-1]                                 # buffer not yet updated with x
        d = x - x_prev
        sd = sqrt(self.varL)
        score = abs(d - self.muL) / (sd + EPS)
        # The FREEZE gate (freeze_c) is deliberately decoupled from the alarm scale
        # (thr_c). An aggressive freeze (2 sigma) excludes far more than just true
        # anomalies from the variance update, keeping the noise-scale estimate very
        # tight so genuine spikes stand out strongly -- but the *normalisation* still
        # divides by a larger thr_c (4 sigma) so ordinary 2-3 sigma noise diffs do NOT
        # normalise above 1.0 and pollute the max-fusion on drift/periodicity streams.
        if score < self.freeze_c:                      # freeze scale during anomaly
            df = d - self.muL
            self.muL += self.a_c * df
            self.varL = (1.0 - self.a_c) * (self.varL + self.a_c * df * df)
            if self.varL < 1e-12:
                self.varL = 1e-12
        return score

    def _drift(self, x: float) -> float:
        """Difference-of-EWMAs drift detector: |fast_EWMA - slow_EWMA| / noise_sigma.

        This replaces the ewmv_hold "frozen baseline" drift head because, on the
        BURSTY base (occasional legitimate ~1.5-sigma level shifts), a frozen-baseline
        control chart collapses its control-sigma and screams (>4x threshold) on every
        legitimate shift, swamping the spike core in the max-fusion. The
        difference-of-EWMAs is naturally bursty-robust: a sudden step makes the fast
        EWMA jump and the slow EWMA follow within ~slow_span samples, so the gap is a
        short transient (caught -- harmlessly -- by the core, not a sustained drift
        alarm); a GRADUAL ramp keeps the fast EWMA persistently ahead of the slow one,
        producing the sustained gap that signals drift. The gap is standardised by a
        slow EWMV of the (x - fast) residual, a stable noise-scale estimate.

        State: self.mu (fast EWMA), self.sigma (slow EWMA), self.z (noise variance).
        (Field names retained from the prior head; their roles are documented here.)
        """
        if self.n == 1:
            self.mu = x          # fast EWMA
            self.sigma = x       # slow EWMA
            self.z = 1.0         # EWMV of the (x - fast) residual (noise variance)
            return 0.0
        resid = x - self.mu
        self.z = (1.0 - self.a_nv) * self.z + self.a_nv * resid * resid
        self.mu += self.a_fast * (x - self.mu)
        self.sigma += self.a_slow * (x - self.sigma)
        sd = sqrt(self.z)
        return abs(self.mu - self.sigma) / (sd + EPS)

    def _acf(self, lag: int) -> float:
        """Lag-``lag`` autocorrelation over the current ring-buffer contents."""
        vals = self.buf.values()
        N = len(vals)
        if N <= lag + 2:
            return 0.0
        mean = sum(vals) / N
        num = 0.0
        for i in range(lag, N):
            num += (vals[i] - mean) * (vals[i - lag] - mean)
        den = 0.0
        for vv in vals:
            dd = vv - mean
            den += dd * dd
        return num / (den + EPS)

    def _periodicity(self) -> float:
        """Positive, r_ref-normalised drop in the dominant-lag autocorrelation.

        Robust arming in two stages, because a tiny (cap=15) window of a long-period
        signal gives a NOISY one-shot autocorrelation that cannot separate a genuine
        cycle from spurious short-lag correlation in flat/bursty/trend noise:

          1. At buffer-fill, lock the dominant lag (arg-max short-lag ACF).
          2. For the next ``est_len`` samples, average the ACF at that fixed lag into
             ``r_ref`` (a running mean). Averaging collapses the noise: periodic bases
             settle at r ~0.55, aperiodic bases at r <~0.39.
          3. Gate: if the averaged r_ref < ``arm_r`` the signal is NOT periodic ->
             SILENCE the head for good (period := -1) so it contributes ZERO to the
             max-fusion and never pollutes the spike head on aperiodic streams.

        Once armed, score the POSITIVE drop r_ref - r_now, normalised by r_ref so a
        full collapse of periodicity scores ~1.0 regardless of the base's r_ref.
        """
        if self.period == -1:                          # silenced (aperiodic)
            return 0.0
        if not self.buf.is_full():
            return 0.0
        # stage 1: lock the dominant lag exactly once, at fill.
        if self.period == 0:
            best_lag, best_r = 0, -2.0
            for lag in range(2, max(3, self.cap // 2) + 1):
                r = self._acf(lag)
                if r > best_r:
                    best_r, best_lag = r, lag
            self.period = best_lag if best_lag >= 2 else 2
            self.r_ref = 0.0                           # running ACF sum (reused slot)
            self.r_sm = self._acf(self.period)         # seed the persistence smoother
            return 0.0
        # stage 2: accumulate the ACF at the locked lag for est_len samples.
        est_done = self.cap + self.est_len
        r_now = self._acf(self.period)
        # Persistence smoother: a SUSTAINED periodicity loss (the event lasts ~75
        # samples) survives this short EWMA, but a single spike's momentary 1-sample
        # ACF dip is averaged away -- so a spike/transient on a periodic base no longer
        # makes the ACF head fire a wide blob of false positives that would dilute the
        # core's spike alarm in the max-fusion.
        self.r_sm += self.a_sm * (r_now - self.r_sm)
        if self.n <= est_done:
            self.r_ref += r_now                        # running SUM during estimation
            if self.n == est_done:                     # finalise: mean, then gate
                self.r_ref /= float(self.est_len)
                if self.r_ref < self.arm_r:            # not convincingly periodic
                    self.period = -1                   # silence for good
                    self.r_ref = 0.0
            return 0.0
        # stage 3: armed -> report the fraction of periodicity lost (smoothed).
        drop = self.r_ref - self.r_sm
        if drop <= 0.0:
            return 0.0
        return drop / (self.r_ref + EPS)

    # ------------------------------------------------------------------ update
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)
        # Core reads x1/x2 from the buffer, so compute it BEFORE pushing x.
        s_c = self._core(x)
        self.buf.push(x)                               # now x is in the window
        s_d = self._drift(x)
        s_a = self._periodicity()

        # Max of NORMALISED heads (each divided by its own alarm scale).
        score = s_c / self.thr_c
        sd = s_d / self.thr_d
        if sd > score:
            score = sd
        sa = s_a / self.thr_a
        if sa > score:
            score = sa

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # core: muL, varL (2)  +  drift: mu, sigma, z (3)
        # +  acf: period(int slot), r_ref, r_sm (3)
        return 8

    def state_buffer_len(self) -> int:
        return self.cap
