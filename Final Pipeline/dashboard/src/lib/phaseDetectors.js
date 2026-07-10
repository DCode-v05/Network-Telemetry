// phaseDetectors.js -- browser ports of the Phase 2 single detectors and the
// Phase 3 confirmation-gate + two-layer ensemble, faithful to the exact configs
// used in the research repo (ZScore thr 3.0, MAD thr 3.5, EWMA lambda 0.2/L 3.5,
// CUSUM k 0.5/h 3.5, PageHinkley delta 0.5/lambda 12, SlidingWindow mean thr 3.0;
// ConfirmationGate n=2; Spike_AND / Sustained_OR / TwoLayerEnsemble).
//
// Each detector exposes update(x) -> { alert: bool, score: number }. The change
// detectors (EWMA/CUSUM/PageHinkley) freeze a baseline (mu0, sigma) over a short
// warmup and then work in sigma units, mirroring Phase 2's per-series
// z-normalisation. Window detectors adapt to their local window. Pure scalar
// arithmetic, deterministic -- safe to run live in the browser.

function median(a) {
  const b = [...a].sort((x, y) => x - y)
  const n = b.length
  if (!n) return 0
  return n % 2 ? b[(n - 1) / 2] : (b[n / 2 - 1] + b[n / 2]) / 2
}
function meanOf(a) { let s = 0; for (const v of a) s += v; return a.length ? s / a.length : 0 }
function stdOf(a, m) { if (a.length < 2) return 0; let s = 0; for (const v of a) { const d = v - m; s += d * d } return Math.sqrt(s / (a.length - 1)) }

// frozen baseline (mu0, sigma) estimated over the first `warmup` samples
class Baseline {
  constructor(warmup = 40) { this.warmup = warmup; this.n = 0; this.sum = 0; this.sumsq = 0; this.mu0 = 0; this.sigma = 1; this.ready = false }
  observe(x) {
    this.n += 1
    if (!this.ready) {
      this.sum += x; this.sumsq += x * x
      if (this.n >= this.warmup) {
        this.mu0 = this.sum / this.n
        const v = this.sumsq / this.n - this.mu0 * this.mu0
        this.sigma = Math.sqrt(Math.max(v, 1e-9))
        this.ready = true
      }
    }
    return this.ready
  }
}

// ----- Phase 2 single detectors --------------------------------------------

export class ZScore {
  constructor(w = 20, thr = 3.0) { this.w = w; this.thr = thr; this.name = 'ZScore'; this.reset() }
  reset() { this.buf = [] }
  update(x) {
    let z = 0, alert = false
    if (this.buf.length >= Math.min(8, this.w)) {
      const m = meanOf(this.buf), s = stdOf(this.buf, m)
      z = s > 1e-9 ? Math.abs(x - m) / s : 0
      alert = z > this.thr
    }
    this.buf.push(x); if (this.buf.length > this.w) this.buf.shift()   // decision-then-push (no masking)
    return { alert, score: z }
  }
}

export class MAD {
  constructor(w = 20, thr = 3.5) { this.w = w; this.thr = thr; this.name = 'MAD'; this.reset() }
  reset() { this.buf = [] }
  update(x) {
    let z = 0, alert = false
    if (this.buf.length >= Math.min(8, this.w)) {
      const med = median(this.buf)
      const mad = median(this.buf.map((v) => Math.abs(v - med)))
      z = mad > 1e-9 ? 0.6745 * Math.abs(x - med) / mad : 0
      alert = z > this.thr
    }
    this.buf.push(x); if (this.buf.length > this.w) this.buf.shift()
    return { alert, score: z }
  }
}

export class SlidingWindow {
  // window-mean deviation with a slower (2x window) baseline -- the Phase 2 weakest
  constructor(w = 20, thr = 3.0) { this.w = w; this.thr = thr; this.name = 'SlidingWindow'; this.reset() }
  reset() { this.buf = [] }
  update(x) {
    let z = 0, alert = false
    const eff = this.w * 2
    if (this.buf.length >= Math.min(16, eff)) {
      const m = meanOf(this.buf), s = stdOf(this.buf, m)
      z = s > 1e-9 ? Math.abs(x - m) / s : 0
      alert = z > this.thr
    }
    this.buf.push(x); if (this.buf.length > eff) this.buf.shift()
    return { alert, score: z }
  }
}

export class EWMA {
  // Roberts control chart: alarm when the smoothed statistic leaves L*sigma_ewma
  constructor(lambda = 0.2, L = 3.5, warmup = 40) { this.lam = lambda; this.L = L; this.warmup = warmup; this.name = 'EWMA'; this.reset() }
  reset() { this.base = new Baseline(this.warmup); this.S = null }
  update(x) {
    const ready = this.base.observe(x)
    if (this.S === null) this.S = x
    this.S = this.lam * x + (1 - this.lam) * this.S
    if (!ready) return { alert: false, score: 0 }
    const cl = this.L * this.base.sigma * Math.sqrt(this.lam / (2 - this.lam))
    const dev = Math.abs(this.S - this.base.mu0)
    return { alert: dev > cl, score: cl > 1e-9 ? dev / cl : 0 }
  }
}

export class CUSUM {
  // bidirectional cumulative sum in sigma units; resets after an alarm
  constructor(k = 0.5, h = 3.5, warmup = 40) { this.k = k; this.h = h; this.warmup = warmup; this.name = 'CUSUM'; this.reset() }
  reset() { this.base = new Baseline(this.warmup); this.cp = 0; this.cm = 0 }
  update(x) {
    const ready = this.base.observe(x)
    if (!ready) return { alert: false, score: 0 }
    const z = (x - this.base.mu0) / (this.base.sigma || 1)
    this.cp = Math.max(0, this.cp + z - this.k)
    this.cm = Math.max(0, this.cm - z - this.k)
    const stat = Math.max(this.cp, this.cm)
    const alert = stat > this.h
    if (alert) { this.cp = 0; this.cm = 0 }
    return { alert, score: stat }
  }
}

export class PageHinkley {
  // adaptive-mean change test; alarms when the cumulative deviation exceeds lambda
  constructor(delta = 0.5, lambda = 12.0, alpha = 0.9999, warmup = 40) {
    this.delta = delta; this.lambda = lambda; this.alpha = alpha; this.warmup = warmup; this.name = 'PageHinkley'; this.reset()
  }
  reset() { this.base = new Baseline(this.warmup); this.mean = 0; this.k = 0; this.mPos = 0; this.minPos = 0; this.mNeg = 0; this.maxNeg = 0 }
  update(x) {
    const ready = this.base.observe(x)
    const z = ready ? (x - this.base.mu0) / (this.base.sigma || 1) : 0
    this.k += 1
    this.mean += (z - this.mean) / this.k
    // two-sided Page-Hinkley
    this.mPos += z - this.mean - this.delta
    if (this.mPos < this.minPos) this.minPos = this.mPos
    this.mNeg += z - this.mean + this.delta
    if (this.mNeg > this.maxNeg) this.maxNeg = this.mNeg
    const ph = Math.max(this.mPos - this.minPos, this.maxNeg - this.mNeg)
    return { alert: ready && ph > this.lambda, score: ph }
  }
}

export const SINGLE_DEFS = [
  { key: 'ZScore', make: (w) => new ZScore(w, 3.0), family: 'spike', color: 'var(--red)', blurb: 'rolling z-score (thr 3.0)' },
  { key: 'MAD', make: (w) => new MAD(w, 3.5), family: 'spike', color: 'var(--amber)', blurb: 'robust median-abs-dev (thr 3.5)' },
  { key: 'SlidingWindow', make: (w) => new SlidingWindow(w, 3.0), family: 'spike', color: 'var(--fg-subtle)', blurb: 'window-mean deviation (thr 3.0)' },
  { key: 'EWMA', make: () => new EWMA(0.2, 3.5), family: 'sustained', color: 'var(--purple)', blurb: 'EWMA control chart (λ 0.2, L 3.5)' },
  { key: 'CUSUM', make: () => new CUSUM(0.5, 3.5), family: 'sustained', color: 'var(--cyan)', blurb: 'cumulative-sum (k 0.5, h 3.5)' },
  { key: 'PageHinkley', make: () => new PageHinkley(0.5, 12.0), family: 'sustained', color: 'var(--green)', blurb: 'Page-Hinkley (δ 0.5, λ 12)' },
]

// ----- Phase 3 confirmation gate + ensembles -------------------------------

export class ConfirmationGate {
  // requires n consecutive child alarms before firing (kills singleton FPs)
  constructor(child, n = 2) { this.child = child; this.n = n; this.streak = 0; this.name = 'Gated' + (child.name || '') }
  reset() { this.child.reset && this.child.reset(); this.streak = 0 }
  update(x) {
    const r = this.child.update(x)
    this.streak = r.alert ? this.streak + 1 : 0
    return { alert: this.streak >= this.n, score: r.score }
  }
}

export class VotingLayer {
  // AND = every child alarms this sample; OR = any child alarms
  constructor(children, mode = 'OR', name = 'Vote') { this.children = children; this.mode = mode; this.name = name }
  reset() { this.children.forEach((c) => c.reset && c.reset()) }
  update(x) {
    let votes = 0, score = 0
    for (const c of this.children) { const r = c.update(x); if (r.alert) votes += 1; if (r.score > score) score = r.score }
    const alert = this.mode === 'AND' ? votes === this.children.length : votes > 0
    return { alert, score, votes }
  }
}

// the Phase 3 main product: Spike_AND(GatedMAD, GatedZScore) OR Sustained_OR(GatedEWMA, GatedCUSUM)
export class TwoLayerEnsemble {
  constructor(w = 20) {
    this.spike = new VotingLayer([new ConfirmationGate(new MAD(w, 3.5)), new ConfirmationGate(new ZScore(w, 3.0))], 'AND', 'Spike_AND')
    this.sustained = new VotingLayer([new ConfirmationGate(new EWMA(0.2, 3.5)), new ConfirmationGate(new CUSUM(0.5, 3.5))], 'OR', 'Sustained_OR')
    this.name = 'TwoLayerEnsemble'
  }
  reset() { this.spike.reset(); this.sustained.reset() }
  update(x) {
    const s = this.spike.update(x)
    const u = this.sustained.update(x)
    // attribution: 1 = spike layer, 2 = sustained layer only
    const layer = s.alert ? 1 : u.alert ? 2 : 0
    return { alert: s.alert || u.alert, score: Math.max(s.score, u.score), layer }
  }
}
