// Explanatory content for the Problem & Theory page (authored from the repo docs:
// Phase 1 Algorithm Study + HPE Evaluation Criteria + CPP problem statement).

export const PROBLEM = [
  "Network switches already emit rich telemetry — link utilisation, packet rate, queue depth, error counters, jitter — at sub-second granularity. Today that data is either shipped to a central collector (seconds-to-minutes of latency, bandwidth cost, a single point of failure) or reduced to static threshold alerts that can't tell a legitimate burst from an anomaly, can't see gradual drift, and can't notice a periodic signal going irregular.",
  "This project asks a narrower question: can useful anomaly detection run directly on the switch's ARM-class control-plane processor — where you get a few kilobytes of RAM and must answer in microseconds? That turns into a hard resource budget, and the whole study is about which lightweight time-series techniques stay accurate inside it.",
]

export const CONSTRAINTS = [
  { k: "Observation window", server: "1,000 – 100,000+ samples", device: "10 – 50 samples" },
  { k: "Compute per sample", server: "milliseconds OK", device: "< 100 microseconds" },
  { k: "Memory per metric", server: "megabytes", device: "< 100 bytes" },
  { k: "Libraries", server: "NumPy / SciPy / TF", device: "basic C arithmetic" },
  { k: "Processing model", server: "batch (reprocess window)", device: "streaming (one sample at a time)" },
  { k: "Metrics monitored", server: "tens", device: "hundreds – thousands at once" },
]

export const ANOMALIES = [
  {
    key: "spike", name: "Spike / Burst", color: "var(--red)",
    def: "A sudden, large single-sample (or very short) excursion far outside normal range — e.g. a microburst of traffic.",
    detail: "Defined here as a ≥ 6σ single-sample excursion. A lone 4σ sample is within normal noise (a 600-sample stream already has several 3–3.5σ points), so no causal detector can separate it without firing on noise.",
    head: "Derivative head",
  },
  {
    key: "drift", name: "Gradual Drift", color: "var(--purple)",
    def: "A slow, sustained shift of the baseline that never crosses a fixed threshold — e.g. a link slowly saturating.",
    detail: "The regime is anomalous once the drift begins; a level detector must notice the baseline moving away from its history without chasing it.",
    head: "EWMA control-chart head",
  },
  {
    key: "periodicity", name: "Periodicity Loss", color: "var(--cyan)",
    def: "A previously regular / periodic signal (keepalive, poll) becomes irregular — the rhythm breaks.",
    detail: "Detected by watching the autocorrelation at the dominant short lag drop. Only meaningful when the signal was periodic to begin with.",
    head: "Gated ACF-drop head",
  },
  {
    key: "transient", name: "Transient", color: "var(--amber)",
    def: "A brief 1–2 sample drop or spike that lasts only a moment — a packet-drop blip.",
    detail: "Needs a detector that reacts to the rate of change, not the level, so a one-sample event still registers before it's gone.",
    head: "Derivative head",
  },
]

// tiny illustrative sample shapes for the sparkline (unit-ish scale)
export function shapeFor(key, n = 60) {
  const out = []
  for (let i = 0; i < n; i++) {
    let v = 0
    const noise = Math.sin(i * 12.9898) * 0.35 // deterministic pseudo-noise
    if (key === "spike") v = (i === 30 ? 6 : 0) + noise
    else if (key === "drift") v = (i > 24 ? (i - 24) * 0.28 : 0) + noise
    else if (key === "periodicity") v = (i < 30 || i > 44 ? 2.4 * Math.sin(i * 0.9) : noise) + noise * 0.3
    else if (key === "transient") v = (i === 28 ? 5 : i === 40 ? -4 : 0) + noise
    out.push(v)
  }
  return out
}
