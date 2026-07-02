"""Standalone `unified` streaming anomaly detector.

Extracted verbatim from the Phase 4 research repo
(`Phase 4/src/python/tsad/ensembles/unified.py`, class `Unified`) into a single
self-contained module with NO third-party dependencies (Python stdlib only).

ONE < 100-byte streaming unit that covers all four telemetry anomaly types
(spike, drift, periodicity loss, transient) using three internal heads that share
a single state block and are MAX-fused on normalised scores:

  1. derivative head  (first-difference z-score, anomaly-aware HOLD baseline)  -> spike / transient
  2. EWMA control-chart head (control-sigma from shared windowed sd, CLIPPED output) -> drift
  3. gated lag-k ACF-drop head (armed only when the base signal is periodic)   -> periodicity loss

  final score = max(head1, head2, head3)

Footprint model (float32, per-metric persistent state): 5 float scalars
(mu_d, var_d, z, mu, r_ref) + a 17-deep ring buffer + int counters
= 5*4 + 17*4 + 8 = 96 bytes.  `state_bytes()` returns this; it is the number the
C twin's `unified_state_bytes()` mirrors and the < 100-byte budget is checked against.

Contract (shared with the C twin so the two can be parity-checked):
  * pure scalar arithmetic in update() -- no numpy, no history reprocessing
  * update(x) -> continuous score >= 0 (higher == more anomalous)
  * binary decision is `score >= threshold`
  * returns 0.0 during warm-up
"""

from __future__ import annotations

from math import sqrt

_EPS = 1e-9


class RingBuffer:
    """Fixed-capacity circular float buffer. Mirrors a C `float buf[N]; int head, count;`."""

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self.buf = [0.0] * self.capacity
        self.head = 0
        self.count = 0

    def push(self, x: float) -> None:
        self.buf[self.head] = float(x)
        self.head = (self.head + 1) % self.capacity
        if self.count < self.capacity:
            self.count += 1

    def is_full(self) -> bool:
        return self.count == self.capacity

    def values(self) -> list:
        """Valid values oldest -> newest. O(count)."""
        if self.count < self.capacity:
            return self.buf[:self.count]
        return self.buf[self.head:] + self.buf[:self.head]

    def __len__(self) -> int:
        return self.count


class UnifiedDetector:
    """The `unified` detector as a standalone class.

    Same math and constants as the Phase 4 `Unified` class; the only structural
    difference is that the minimal base-class + ring-buffer machinery is inlined
    here so the file has no repo dependencies.
    """

    name = "unified"

    # tuning constants (identical to Phase 4 Unified)
    BUF_LEN = 17
    GATE = 0.45      # min autocorrelation to "arm" the periodicity head
    TH_DRV = 2.8     # derivative-head normaliser
    TH_EWMV = 2.5    # drift-head normaliser
    DR_CAP = 0.9     # drift-head output clip (< 1.0 so a step can't out-shout a spike)
    TH_PER = 0.4     # periodicity-head normaliser
    HOLD = 2.5       # freeze derivative baseline while |z_deriv| exceeds this

    def __init__(self, window: int = 24, threshold: float = 1.0, warmup=None, **params):
        self.window = int(window)
        self.threshold = float(threshold)
        self.warmup = int(warmup) if warmup is not None else max(3, self.window // 3)
        self.params = dict(params)
        self.reset()

    # ---- lifecycle -------------------------------------------------------
    def reset(self) -> None:
        """Allocate/zero all streaming state (call once; also called by __init__)."""
        self.n = 0
        self.last_score = 0.0
        self.s_drv = 0.0      # last per-head normalised scores (for introspection / VU display)
        self.s_drift = 0.0
        self.s_per = 0.0
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

    # `init` alias to match the init()/update()/state_bytes() contract naming
    def init(self) -> None:
        self.reset()

    def warm(self) -> bool:
        return self.n > self.warmup

    # ---- helpers ---------------------------------------------------------
    def _acf(self, vals, lag, mean, den):
        """Lag-`lag` autocorrelation of `vals` (mean/den precomputed). O(window)."""
        N = len(vals)
        if N <= lag + 2 or den < _EPS:
            return 0.0
        num = 0.0
        for i in range(lag, N):
            num += (vals[i] - mean) * (vals[i - lag] - mean)
        return num / den

    # ---- core ------------------------------------------------------------
    def update(self, x: float) -> float:
        """Process one sample, return a non-negative anomaly score."""
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
            self.s_drv = self.s_drift = self.s_per = 0.0
            return 0.0

        # shared windowed mean / variance (used by drift + periodicity heads)
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

        # -- head 1: derivative z-score with anomaly-aware HOLD baseline
        dx = x - vals[m - 2]
        z_deriv = abs(dx - self.mu_d) / (sqrt(self.var_d) + _EPS)
        if z_deriv < self.HOLD:
            diff = dx - self.mu_d
            self.mu_d += self.alpha * diff
            self.var_d = (1.0 - self.alpha) * (self.var_d + self.alpha * diff * diff)
            if self.var_d < 1e-6:
                self.var_d = 1e-6
        s_drv = z_deriv / self.TH_DRV

        # -- head 2: held EWMA control-chart, output CLIPPED at DR_CAP
        control_sigma = sd * sqrt(self.lam / (2.0 - self.lam))
        s_ewmv = abs(self.z - self.mu) / (control_sigma + _EPS)
        self.z = self.lam * x + (1.0 - self.lam) * self.z
        if s_ewmv < self.TH_EWMV:
            self.mu += self.alpha_s * (x - self.mu)
        s_drift = s_ewmv / self.TH_EWMV
        if s_drift > self.DR_CAP:
            s_drift = self.DR_CAP

        # -- head 3: gated ACF-drop (arms once, only if the base is periodic)
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

        # -- MAX fusion
        score = s_drv
        if s_drift > score:
            score = s_drift
        if s_per > score:
            score = s_per
        if not warm:
            score = 0.0
        self.s_drv, self.s_drift, self.s_per = s_drv, s_drift, s_per
        self.last_score = score
        return score

    def flag(self, x: float) -> int:
        """update(x) then return the binary decision at the current threshold."""
        return 1 if self.update(x) >= self.threshold else 0

    def score_stream(self, xs) -> list:
        """Run over an iterable, returning the per-sample score list (eval helper)."""
        out = []
        for x in xs:
            out.append(self.update(float(x)))
        return out

    # ---- footprint accounting -------------------------------------------
    def state_floats(self) -> int:
        return 5  # mu_d, var_d, z, mu, r_ref

    def state_buffer_len(self) -> int:
        return self.BUF_LEN  # 17

    def state_bytes(self) -> int:
        """float32 per-metric footprint model: scalars*4 + buffer*4 + 8 (int counters)."""
        return self.state_floats() * 4 + self.state_buffer_len() * 4 + 8


if __name__ == "__main__":
    # quick smoke test
    d = UnifiedDetector()
    print("name        :", d.name)
    print("window      :", d.window, " warmup:", d.warmup, " threshold:", d.threshold)
    print("state_bytes :", d.state_bytes(), "(budget < 100)")
    # feed a flat stream with one big spike; the spike sample should score highest
    import random
    random.seed(1)
    scores = []
    spike_at = 120
    for i in range(200):
        x = 50.0 + random.gauss(0.0, 1.0)
        if i == spike_at:
            x += 12.0
        scores.append(d.update(x))
    peak = max(range(len(scores)), key=lambda i: scores[i])
    print(f"peak score at i={peak} (spike injected at {spike_at}) "
          f"score={scores[peak]:.3f}  alert={'YES' if scores[peak] >= d.threshold else 'no'}")
