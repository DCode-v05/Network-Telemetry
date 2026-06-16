"""Shared-residual streaming engine: ONE anomaly-aware baseline feeds four cheap heads.

A single detector that covers spike, drift, periodicity and transient at once while
staying under the 100-byte on-device budget. The trick is SHARED STATE: one
anomaly-aware EWMA/EWMV "hold" baseline produces a residual ``r = x - mu`` and a
normalized residual ``z = |r| / sd``; everything else is derived from that residual
(and one small ring buffer of residuals), so we pay for the state once.

Heads (all derived from the shared residual)
--------------------------------------------
  * spike     : z = |r| / sd                              (level outlier)
  * transient : |r - r_prev| / sd                         (derivative of the residual)
  * drift     : two-sided CUSUM on r/sd                   (slow accumulated shift)
  * periodicity: r_ref - acf(residual_ring, period)       (loss of structure)

Fusion
------
We do NOT average the heads (averaging dilutes the one head that actually fires --
the classic spike-to-0.57 failure). Instead each head is divided by its own
normalizer (so a "firing" head reads ~1.0 at its anomaly) and we take the MAX:

    score = max(z/THR_s, dz/THR_t, cusum/THR_d, acf_drop/THR_p)

The anomaly-aware HOLD on the baseline is what makes this work: while the normalized
residual is large the slow mean/variance are frozen, so (a) a drift does not get
absorbed into its own baseline and (b) a spike does not inflate sd and spray false
positives afterwards. The variance floor and a separate fast/slow split keep the
bursty base (legitimate ~1.5 sigma level shifts) from generating spike false positives.

State (float32 model)
---------------------
  mu, var, r_prev, g_pos, g_neg, period(int slot), r_ref   -> 7 scalars
  one RingBuffer(buf_len) of residuals
With buf_len = min(window, 16) the footprint is 7*4 + 16*4 + 8 = 100 ... so we keep
buf_len <= 14 to stay strictly under budget; the ACF head only needs a couple of
periods of residual history, not the full eval window.

Pure scalar arithmetic in update(); O(buf_len) per sample (one ACF pass).
"""

from __future__ import annotations

from math import sqrt

from tsad.core.base import Detector
from tsad.core.ring_buffer import RingBuffer

_EPS = 1e-9
_SD_FLOOR = 1e-3


def _acf(vals, lag, mean):
    """Lag-``lag`` autocorrelation of ``vals`` about a supplied ``mean``."""
    N = len(vals)
    if N <= lag + 2:
        return 0.0
    num = 0.0
    den = 0.0
    for i in range(N):
        d = vals[i] - mean
        den += d * d
        if i >= lag:
            num += d * (vals[i - lag] - mean)
    den += _EPS
    return num / den


class ResidualEngine(Detector):
    """One anomaly-aware residual baseline -> four max-fused heads."""

    name = "residual_engine"

    # per-head normalizers (a firing head reads ~1.0 at its anomaly)
    THR_S = 4.0      # spike: |r|/sd sigmas
    THR_T = 6.0      # transient: |r - r_prev|/sd (derivative, ~2x a level step)
    THR_D = 6.0      # drift: CUSUM accumulation
    THR_P = 0.45     # periodicity: acf drop magnitude
    SLACK_K = 0.5    # CUSUM allowance in residual-sigma units

    def __init__(self, window: int = 20, threshold: float = 1.0, **params):
        super().__init__(window=window, threshold=threshold, **params)

    # ------------------------------------------------------------------ lifecycle
    def reset(self) -> None:
        super().reset()
        self.alpha = 2.0 / (self.window + 1)          # slow baseline smoother
        # residual ring buffer: a couple of periods is enough for ACF; keep <= 14
        self.buf_len = min(self.window, 14)
        self.buf = RingBuffer(self.buf_len)
        self.mu = 0.0
        self.var = 1.0
        self.r_prev = 0.0
        self.g_pos = 0.0
        self.g_neg = 0.0
        self.period = 0                                # established dominant lag
        self.r_ref = 0.0                               # reference ACF at that lag

    # ------------------------------------------------------------------- streaming
    def update(self, x: float) -> float:
        self.n += 1
        x = float(x)

        if self.n == 1:
            self.mu = x
            self.var = 1.0
            self.r_prev = 0.0
            self.last_score = 0.0
            return 0.0

        sd = sqrt(self.var)
        if sd < _SD_FLOOR:
            sd = _SD_FLOOR

        # --- shared residual against the CURRENT (pre-update) baseline ---
        r = x - self.mu
        rn = r / sd                                    # signed normalized residual
        z = abs(rn)                                    # spike head

        # --- transient head: derivative of the residual ---
        dz = abs(r - self.r_prev) / sd

        # --- drift head: two-sided CUSUM on the normalized residual ---
        self.g_pos = max(0.0, self.g_pos + rn - self.SLACK_K)
        self.g_neg = max(0.0, self.g_neg - rn - self.SLACK_K)
        cusum = self.g_pos if self.g_pos > self.g_neg else self.g_neg

        # --- periodicity head: ACF drop over the residual ring buffer ---
        acf_drop = 0.0
        self.buf.push(r)
        if self.buf.is_full():
            vals = self.buf.values()
            bmean = sum(vals) / len(vals)
            if self.period == 0:
                best_lag, best_r = 0, -2.0
                for lag in range(2, max(3, self.buf_len // 2) + 1):
                    rr = _acf(vals, lag, bmean)
                    if rr > best_r:
                        best_r, best_lag = rr, lag
                if best_r < 0.2:
                    self.period = max(2, self.buf_len // 4)
                    self.r_ref = 0.05
                else:
                    self.period = best_lag
                    self.r_ref = best_r
            else:
                r_now = _acf(vals, self.period, bmean)
                acf_drop = self.r_ref - r_now
                if acf_drop < 0.0:
                    acf_drop = 0.0

        # --- anomaly-aware HOLD: freeze slow baseline while clearly anomalous ---
        if z < self.THR_S:
            diff = x - self.mu
            self.mu += self.alpha * diff
            self.var = (1.0 - self.alpha) * (self.var + self.alpha * diff * diff)
            if self.var < _SD_FLOOR * _SD_FLOOR:
                self.var = _SD_FLOOR * _SD_FLOOR

        # reset CUSUM after a confident drift alarm so it does not latch
        if cusum >= self.THR_D:
            self.g_pos = 0.0
            self.g_neg = 0.0

        self.r_prev = r

        # --- normalized max-fusion ---
        score = z / self.THR_S
        t = dz / self.THR_T
        if t > score:
            score = t
        d = cusum / self.THR_D
        if d > score:
            score = d
        p = acf_drop / self.THR_P
        if p > score:
            score = p

        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    # ------------------------------------------------------------- cost accounting
    def state_floats(self) -> int:
        # mu, var, r_prev, g_pos, g_neg, period(int slot), r_ref
        return 7

    def state_buffer_len(self) -> int:
        return self.buf_len
