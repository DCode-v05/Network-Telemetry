// Written content for the Problem Statement page (drawn from the Phase 1 study,
// the HPE evaluation criteria, and the project brief). Plain-language on purpose.

export const PROBLEM = [
  "A network switch already knows a lot about itself: how busy each link is, its packet rates, queue depths, error counts, jitter, all updated many times a second across hundreds of interfaces at once. The problem is what happens to that data. Usually it's either shipped off to a central collector, which adds seconds or minutes of delay, eats bandwidth, and goes dark the moment the uplink drops. Or it gets boiled down to a few fixed threshold alerts that can't tell a normal burst from a real problem, never see a slow drift coming, and don't notice when a steady signal turns ragged.",
  "So we asked a sharper question. What if the switch just did the detection itself, right on its little ARM control-plane processor, where you've got only a few kilobytes of RAM and microseconds to answer? That question turns into a strict budget, and this whole project is really about which lightweight techniques stay accurate once you squeeze them into it.",
]

export const CONSTRAINTS = [
  { k: "Observation window", server: "1,000 to 100,000+ samples", device: "10 to 50 samples" },
  { k: "Compute per sample", server: "milliseconds are fine", device: "< 100 microseconds" },
  { k: "Memory per metric", server: "megabytes", device: "< 100 bytes" },
  { k: "Libraries", server: "NumPy / SciPy / TF", device: "basic C arithmetic" },
  { k: "Processing model", server: "batch (reprocess the window)", device: "streaming (one sample at a time)" },
  { k: "Metrics monitored", server: "tens", device: "hundreds to thousands at once" },
]

export const ANOMALIES = [
  {
    key: "spike", name: "Spike / Burst", color: "var(--red)",
    def: "A sudden jump, either a single sample or a very short burst, that lands far outside the normal range. Think a microburst of traffic.",
    detail: "We draw the line at a jump of at least 6σ in one sample. A lone 4σ blip is really just noise (a 600-sample stream will already have a few points at 3 to 3.5σ), so no honest detector could pick it out without firing on that noise too.",
    head: "Derivative head",
  },
  {
    key: "drift", name: "Gradual Drift", color: "var(--purple)",
    def: "A slow, steady shift in the baseline that never actually trips a fixed threshold, like a link gradually saturating.",
    detail: "The moment the drift starts, things are already going wrong. The trick is noticing the baseline creeping away from its own history, without simply chasing it and deciding the new level is fine.",
    head: "EWMA control-chart head",
  },
  {
    key: "periodicity", name: "Periodicity Loss", color: "var(--cyan)",
    def: "A signal that used to be regular, like a keepalive or a poll, loses its rhythm and goes irregular.",
    detail: "We catch it by watching how strongly the signal repeats at its main beat, and noticing when that repetition drops off. It only makes sense once the signal was periodic to begin with.",
    head: "Gated ACF-drop head",
  },
  {
    key: "transient", name: "Transient", color: "var(--amber)",
    def: "A blink-and-you-miss-it dip or spike, one or two samples long, like a packet-drop blip.",
    detail: "You need a detector that reacts to how fast things are changing, not to the level, otherwise a one-sample event is gone before it ever registers.",
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
