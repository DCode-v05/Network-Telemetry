"""Learned logistic fusion of cheap shared-state anomaly features (ONE unit).

A single streaming detector that fuses a few normalized per-sample features through a
logistic-regression head whose weights were FIT OFFLINE (see
``scripts/fit_logistic_fusion.py``) and hard-coded below. All features come from ONE shared
anomaly-aware ("hold") baseline plus ONE small (capped) ring buffer, so the on-device
footprint stays under the 100-byte budget while covering all four anomaly types.

Two design choices do the heavy lifting on the hard SPIKE type:

  1. CENTERED curvature (1-sample latency).  The strongest causal-ish point-anomaly signal
     is how far a sample sits from the straight line through its two TIME neighbours:
     ``c = x[t-1] - 0.5*(x[t] + x[t-2])``. This annihilates any locally-linear trend AND a
     smooth sine's slope, so a spike on a high-amplitude periodic base (where a level
     z-score is swamped by the sine swing) still stands out. We therefore emit the score for
     sample ``t-1`` when ``x[t]`` arrives -- a 1-sample detection latency, well inside the
     event metric's tolerance. The curvature scale is an EWMA-of-|c| (lighter tails than an
     EWMV), held while a spike is present so the spike cannot inflate its own normaliser.

  2. SCALE-CORRECT level + conjunction.  A level z-score against the (held) slow baseline
     catches flat/bursty spikes and drift onset; multiplying curvature by the local level
     gives a conjunctive feature that fires only when BOTH are high, suppressing the
     single-channel noise that otherwise sets the false-positive floor for 4-sigma spikes.

Features (all "higher == more anomalous", standardized then fused):
  f0  level_z    |x - mu| / sigma                         level spikes, drift onset
  f1  curv_z     |c| / scale_c                            spike/transient, sine-/trend-immune
  f2  ewmv_div   |z_fast - mu| / control_sigma             gradual drift / change-point
  f3  acf_drop   max(0, r1_ref - r1_now) lag-1 ACF         loss of periodicity (scramble)
  f4  var_drop   max(0, 1 - win_std/ref_std)              loss of periodicity (dropout)
  f5  conj       sqrt(curv_z * level_z)                    conjunctive spike (noise-robust)

Score = ``sigmoid(w . standardize(f) + b)`` with pure scalar arithmetic (no numpy). The slow
baseline mean/sigma is FROZEN while the ewmv divergence is over a hold gate (drift / level
robustness). The ring buffer capacity is CAPPED independent of ``window`` so every evaluated
window stays in budget. ``update`` is O(cap); everything else O(1).
"""

from __future__ import annotations

from math import sqrt, exp

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer
from tsad.core.stats import median_sorted, mad, MAD_TO_SIGMA  # noqa: F401 (contract import)

_EPS = 1e-9
_SD_FLOOR = 1e-6
_HOLD_GATE = 3.0          # freeze the slow baseline while ewmv divergence exceeds this
_CURV_GATE = 3.0          # freeze the curvature scale while a spike is present
_ABS_TO_SD = 1.2533141373155003   # 1 / sqrt(2/pi): mean|N(0,s)| = s * sqrt(2/pi)
_BUFCAP = 12              # capped window for ACF / robust-z / local-std (budget-bounded)
_NFEAT = 6


class LogisticFusion(Detector):
    """Offline-fit logistic fusion of scale-correct, centered shared-state features."""

    name = "logistic_fusion"

    # --- OFFLINE-FIT logistic head (filled by scripts/fit_logistic_fusion.py) ---
    FEAT_MU = (0.888646, 0.88523, 1.22152, 0.165108, 0.189181, 0.786506)
    FEAT_SD = (0.710172, 0.834027, 1.27677, 0.207573, 0.202173, 0.638582)
    W = (0.0822944, 0.544453, 0, 0.408708, 0.0737432, 0)
    B = -0.364783

    def __init__(self, window: int = 16, threshold: float = 0.5, **params):
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        self.lam = 2.0 / (self.window + 1)            # fast smoother
        self.alpha = self.lam / 4.0                   # slow baseline (anomaly-aware hold)
        self.alpha_c = self.lam                       # curvature-scale smoother
        self.cap = _BUFCAP if self.window > _BUFCAP else self.window
        self.csig = sqrt(self.lam / (2.0 - self.lam)) # control-chart sigma factor
        # shared level baseline (anomaly-aware hold)
        self.mu = 0.0
        self.sigma = 1.0
        self.z_fast = 0.0       # fast EWMA (diverges from mu during drift)
        # centered-curvature state (1-sample lag)
        self.x_prev = 0.0       # x[t-1]
        self.x_prev2 = 0.0      # x[t-2]
        self.abs_c = 1.0        # EWMA of |centered curvature| -> robust scale
        self.f0_prev = 0.0      # level_z of the sample we score this step (x[t-1])
        # periodicity heads
        self.buf = RingBuffer(self.cap)
        self.r1_ref = 0.0       # reference lag-1 autocorrelation
        self.ref_std = 0.0      # reference rolling std (periodic amplitude scale)

    # ------------------------------------------------------------- helpers
    def _win_stats(self, vals):
        """(std, lag1_acf) of the window. O(cap)."""
        N = len(vals)
        mean = 0.0
        for v in vals:
            mean += v
        mean /= N
        den = 0.0
        num1 = 0.0
        prev_dev = None
        for v in vals:
            dv = v - mean
            den += dv * dv
            if prev_dev is not None:
                num1 += prev_dev * dv
            prev_dev = dv
        std = sqrt(den / N)
        r1 = num1 / (den + _EPS)
        return std, r1

    def _logit(self, feats):
        z = self.B
        W = self.W
        mu_s = self.FEAT_MU
        sd_s = self.FEAT_SD
        for k in range(_NFEAT):
            z += W[k] * ((feats[k] - mu_s[k]) / (sd_s[k] + _EPS))
        return z

    @staticmethod
    def _sigmoid(z):
        if z >= 0.0:
            return 1.0 / (1.0 + exp(-z))
        ez = exp(z)
        return ez / (1.0 + ez)

    # ------------------------------------------------------------------- streaming
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)

        if self.n == 1:
            self.mu = x
            self.sigma = 1.0
            self.z_fast = x
            self.x_prev = x
            self.x_prev2 = x
            self.buf.push(x)
            self.last_features = (0.0,) * _NFEAT
            self.last_score = 0.0
            return 0.0

        sd = self.sigma if self.sigma > _SD_FLOOR else _SD_FLOOR

        # ---- CENTERED curvature for the PREVIOUS sample x[t-1] ------------------
        # c = x[t-1] - 0.5*(x[t] + x[t-2]); scored against an EWMA-of-|c| scale.
        c = self.x_prev - 0.5 * (x + self.x_prev2)
        scale_c = _ABS_TO_SD * self.abs_c
        if scale_c < _SD_FLOOR:
            scale_c = _SD_FLOOR
        f1 = abs(c) / scale_c
        if f1 < _CURV_GATE:                       # hold scale: a spike must not inflate it
            self.abs_c += self.alpha_c * (abs(c) - self.abs_c)
            if self.abs_c < _SD_FLOOR:
                self.abs_c = _SD_FLOOR

        # the level feature we fuse with this curvature is x[t-1]'s level (computed last step)
        f0 = self.f0_prev
        f5 = sqrt((f1 if f1 > 0.0 else 0.0) * (f0 if f0 > 0.0 else 0.0))

        # ---- f2 fast/slow EWMA divergence (drift), evaluated on x[t] ------------
        control_sigma = sd * self.csig
        f2 = abs(self.z_fast - self.mu) / (control_sigma + _EPS)

        # ---- f3 acf-drop / f4 var-drop from the shared window (on x[t]) ---------
        f3 = 0.0
        f4 = 0.0
        self.buf.push(x)
        if self.buf.is_full():
            vals = self.buf.values()
            std_w, r1 = self._win_stats(vals)
            if self.ref_std == 0.0:
                self.ref_std = std_w if std_w > _SD_FLOOR else _SD_FLOOR
                self.r1_ref = r1
            else:
                drop_acf = self.r1_ref - r1
                if drop_acf < 0.0:
                    drop_acf = 0.0
                f3 = drop_acf
                vd = 1.0 - (std_w / (self.ref_std + _EPS))
                if vd < 0.0:
                    vd = 0.0
                f4 = vd
                if vd < 0.25 and drop_acf < 0.25:    # adapt refs only on intact structure
                    self.ref_std += 0.02 * (std_w - self.ref_std)
                    self.r1_ref += 0.02 * (r1 - self.r1_ref)

        feats = (f0, f1, f2, f3, f4, f5)
        self.last_features = feats

        # ---- advance level baseline (anomaly-aware hold) on x[t] ---------------
        resid = x - self.mu
        f0_cur = abs(resid) / sd                  # level_z of x[t] (scored next step)
        self.z_fast = self.lam * x + (1.0 - self.lam) * self.z_fast
        if f2 < _HOLD_GATE:
            self.mu += self.alpha * resid
            self.sigma = sqrt((1.0 - self.alpha) * (self.sigma * self.sigma
                                                    + self.alpha * resid * resid))
            if self.sigma < _SD_FLOOR:
                self.sigma = _SD_FLOOR
        self.f0_prev = f0_cur
        self.x_prev2 = self.x_prev
        self.x_prev = x

        if not self.warm():
            self.last_score = 0.0
            return 0.0

        score = self._sigmoid(self._logit(feats))
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # mu, sigma, z_fast, x_prev, x_prev2, abs_c, f0_prev, r1_ref, ref_std
        return 9

    def state_buffer_len(self) -> int:
        return self.cap
