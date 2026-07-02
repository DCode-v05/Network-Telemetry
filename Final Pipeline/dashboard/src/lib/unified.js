// unified.js -- browser port of the `unified` streaming anomaly detector.
//
// Line-for-line port of Phase 4/src/python/tsad/ensembles/unified.py (and the C
// twin unified.c). JS Numbers are IEEE-754 double, same as Python float, so the
// scores match the Python/C reference bit-for-bit (verified by _parity_check.mjs).
//
// update(x) returns { score, sDrv, sDrift, sPer, warm } so the UI can show not
// just the fused score but each head's live contribution (the VU meters).

const BUF_LEN = 17
const GATE = 0.45
const TH_DRV = 2.8
const TH_EWMV = 2.5
const DR_CAP = 0.9
const TH_PER = 0.4
const HOLD = 2.5
const EPS = 1e-9

export class UnifiedDetector {
  constructor(window = 24, threshold = 1.0) {
    this.window = window
    this.threshold = threshold
    this.warmup = Math.max(3, Math.floor(window / 3))
    this.reset()
  }

  reset() {
    this.n = 0
    this.last = 0
    this.buf = new Array(BUF_LEN).fill(0)
    this.head = 0
    this.count = 0
    this.period = 0
    this.rRef = 0
    this.armed = 0
    this.muD = 0
    this.varD = 1
    this.z = 0
    this.mu = 0
    this.alpha = 2 / (this.window + 1)
    this.lam = 2 / (this.window + 1)
    this.alphaS = this.lam / 4
  }

  stateBytes() {
    return 5 * 4 + BUF_LEN * 4 + 8 // = 96
  }

  _acf(vals, lag, mean, den) {
    const N = vals.length
    if (N <= lag + 2 || den < EPS) return 0
    let num = 0
    for (let i = lag; i < N; i++) num += (vals[i] - mean) * (vals[i - lag] - mean)
    return num / den
  }

  update(x) {
    this.n += 1
    x = +x

    // ring push
    this.buf[this.head] = x
    this.head = (this.head + 1) % BUF_LEN
    if (this.count < BUF_LEN) this.count += 1

    const warm = this.n > this.warmup

    // values oldest -> newest
    const m = this.count
    let vals
    if (this.count < BUF_LEN) vals = this.buf.slice(0, this.count)
    else vals = this.buf.slice(this.head).concat(this.buf.slice(0, this.head))

    if (m === 1) {
      this.z = x
      this.mu = x
      this.last = 0
      return { score: 0, sDrv: 0, sDrift: 0, sPer: 0, warm: false }
    }

    // shared windowed mean / variance
    let mean = 0
    for (const v of vals) mean += v
    mean /= m
    let den = 0
    for (const v of vals) {
      const d = v - mean
      den += d * d
    }
    const varr = den / m
    const sd = varr > 1e-12 ? Math.sqrt(varr) : 1e-6

    // head 1 -- derivative z-score with HOLD baseline
    const dx = x - vals[m - 2]
    const zDeriv = Math.abs(dx - this.muD) / (Math.sqrt(this.varD) + EPS)
    if (zDeriv < HOLD) {
      const diff = dx - this.muD
      this.muD += this.alpha * diff
      this.varD = (1 - this.alpha) * (this.varD + this.alpha * diff * diff)
      if (this.varD < 1e-6) this.varD = 1e-6
    }
    const sDrv = zDeriv / TH_DRV

    // head 2 -- held EWMA control-chart, output clipped
    const controlSigma = sd * Math.sqrt(this.lam / (2 - this.lam))
    const sEwmv = Math.abs(this.z - this.mu) / (controlSigma + EPS)
    this.z = this.lam * x + (1 - this.lam) * this.z
    if (sEwmv < TH_EWMV) this.mu += this.alphaS * (x - this.mu)
    let sDrift = sEwmv / TH_EWMV
    if (sDrift > DR_CAP) sDrift = DR_CAP

    // head 3 -- gated ACF-drop
    let sPer = 0
    if (this.count === BUF_LEN) {
      if (this.period === 0) {
        let bestLag = 0
        let bestR = -2
        const hi = Math.max(3, Math.floor(BUF_LEN / 2))
        for (let lag = 2; lag <= hi; lag++) {
          const rr = this._acf(vals, lag, mean, den)
          if (rr > bestR) {
            bestR = rr
            bestLag = lag
          }
        }
        this.period = bestLag > 0 ? bestLag : 2
        this.rRef = bestR
        this.armed = bestR >= GATE ? 1 : 0
      } else if (this.armed) {
        const drop = this.rRef - this._acf(vals, this.period, mean, den)
        if (drop > 0) sPer = drop / TH_PER
      }
    }

    // MAX fusion
    let score = sDrv
    if (sDrift > score) score = sDrift
    if (sPer > score) score = sPer
    if (!warm) score = 0
    this.last = score
    return { score, sDrv, sDrift, sPer, warm }
  }
}

// causal one-sample-at-a-time z-score (running Welford) -- for raw real streams
export class CausalStandardizer {
  constructor() {
    this.n = 0
    this.mean = 0
    this.M2 = 0
  }
  push(x) {
    this.n += 1
    const d = x - this.mean
    this.mean += d / this.n
    this.M2 += d * (x - this.mean)
    if (this.n < 2) return 0
    const sd = Math.sqrt(this.M2 / (this.n - 1))
    return sd > 1e-9 ? (x - this.mean) / sd : 0
  }
}
