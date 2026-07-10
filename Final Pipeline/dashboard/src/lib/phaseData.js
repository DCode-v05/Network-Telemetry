// phaseData.js -- deterministic synthetic streams for the Phase 2 & 3 labs.
// A flat baseline with ONE injected anomaly of a chosen type -- the four types
// Phase 2/3 benchmarked (burst, rate shift, gradual drift, transient). Seeded so
// runs are reproducible and re-rollable (matches the research injectors' shapes).

function mulberry32(seed) {
  let a = seed >>> 0
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
function gaussian(rng) {
  let u = 0, v = 0
  while (u === 0) u = rng()
  while (v === 0) v = rng()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}


// which single detectors "should" win each type (from Phase 2 detection-rate results)
export const EXPECTED = {
  burst: ['MAD', 'ZScore'],
  transient: ['MAD', 'ZScore'],
  rate_shift: ['MAD', 'EWMA', 'CUSUM'],
  gradual_drift: ['CUSUM', 'PageHinkley', 'MAD'],
}

export function makeStream(atype, { n = 320, sigma = 1.0, level = 50, seed = 7 } = {}) {
  const rng = mulberry32(seed)
  const v = new Array(n)
  const labels = new Array(n).fill(0)
  for (let i = 0; i < n; i++) v[i] = level + gaussian(rng) * sigma
  const start = Math.floor(n * 0.45)
  let event = [start, start]
  if (atype === 'burst') {
    const L = 5
    for (let i = start; i < start + L; i++) { v[i] += 5 * sigma; labels[i] = 1 }
    event = [start, start + L - 1]
  } else if (atype === 'transient') {
    // a brief 5-sigma blip: the spike detectors catch it instantly, but the
    // smoothing / accumulating detectors (EWMA, Page-Hinkley) average it away
    v[start] += 5 * sigma; labels[start] = 1
    event = [start, start]
  } else if (atype === 'rate_shift') {
    // a modest 2-sigma step: the change detectors accumulate it and lock on, but
    // the window spike detectors adapt to the new level and miss it
    for (let i = start; i < n; i++) { v[i] += 2 * sigma; labels[i] = 1 }
    event = [start, Math.min(n - 1, start + 20)]   // onset window is what must be caught
  } else if (atype === 'gradual_drift') {
    // a slow 0.12-sigma/sample ramp: the change detectors accumulate it and catch,
    // but the window spike detectors (Z-Score, MAD) adapt to it and miss
    const ramp = 30
    for (let i = start; i < n; i++) {
      const d = 0.12 * sigma * Math.min(i - start + 1, ramp)
      v[i] += d; labels[i] = 1
    }
    event = [start, Math.min(n - 1, start + ramp)]
  }
  for (let i = 0; i < n; i++) v[i] = Math.round(v[i] * 1000) / 1000
  return { values: v, labels, event, atype }
}

// Score one detector's alert stream against the labelled event + label array.
// caught  = alerted at least once inside [event.start, event.end + tol] (onset)
// latency = samples from event start to first in-window alert
// fp      = alerts on NORMAL samples (labels[i] === 0) -- true false positives
// tp      = alerts on anomalous samples (labels[i] === 1)
export function scoreAlerts(alerts, event, labels, tol = 3) {
  const [a, b] = event
  let caught = false, latency = null, fp = 0, tp = 0
  for (let i = 0; i < alerts.length; i++) {
    if (!alerts[i]) continue
    if (labels[i]) tp += 1; else fp += 1
    if (!caught && i >= a && i <= b + tol) { caught = true; latency = Math.max(0, i - a) }
  }
  return { caught, latency, fp, tp }
}
