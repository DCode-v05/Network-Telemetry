// Unified detector architecture content (authored from unified.py / unified.c),
// written to be read like an explanation rather than a datasheet.

export const HEADS = [
  {
    n: 1, name: "Derivative head", color: "var(--red)",
    stat: "first-difference z-score",
    anomalies: ["spike", "transient"],
    formula: "z = |Δx − μ_Δ| / σ_Δ",
    trick: "Anomaly-aware HOLD",
    trickDesc: "When it sees a big jump (|z| ≥ 2.5), it freezes its own running stats. Otherwise the spike would quietly fold into the baseline, hide itself, and set off a burst of false alarms right afterward.",
    why: "It watches how fast the signal is moving, not where it sits, so a sharp edge or a one-sample blip lights up while a slow drift slides right past it.",
  },
  {
    n: 2, name: "EWMA control-chart head", color: "var(--purple)",
    stat: "held EWMA vs windowed σ",
    anomalies: ["drift"],
    formula: "s = |z − μ| / (σ·√(λ/(2−λ)))",
    trick: "Output CLIPPED at 0.9",
    trickDesc: "Its score is capped just below the alert line, so a slow step, even a perfectly legitimate one, can never drown out a real spike when the scores are combined. And it holds its baseline while the signal drifts, so it doesn't just chase the drift and pretend nothing's wrong.",
    why: "A quick EWMA follows the signal while a slower, held baseline lags behind, and the gap between the two opens up the moment there's a sustained shift.",
  },
  {
    n: 3, name: "Gated ACF-drop head", color: "var(--cyan)",
    stat: "lag-k autocorrelation drop",
    anomalies: ["periodicity"],
    formula: "s = max(0, r_ref − ACF(lag))",
    trick: "GATE, arms only if periodic",
    trickDesc: "The first time its buffer fills, it looks for the signal's strongest repeating beat (lags 2 to 8) and only switches on if that beat is clear enough, above 0.45. On signals that aren't periodic it just stays quiet and adds nothing to the score.",
    why: "A healthy periodic signal correlates strongly with itself one beat back; when the rhythm breaks, that correlation falls, and that drop is the whole signal.",
  },
]

export const STATE = {
  total: 96,
  items: [
    { k: "5 float32 scalars", bytes: 20, detail: "μ_Δ, σ²_Δ, z, μ, r_ref" },
    { k: "17-deep ring buffer", bytes: 68, detail: "float32 × 17, long enough to span the dominant period" },
    { k: "integer counters", bytes: 8, detail: "n, period, armed" },
  ],
  note: "Five scalars, a 17-slot buffer, a couple of counters: 5×4 + 17×4 + 8 = 96 bytes, just under the 100-byte line. That 17th slot (instead of 16) is the one deliberate splurge. It pushed periodicity detection from about 0.84 up to nearly 1.00, and we stayed in budget by storing the period as an integer instead of a float.",
}

export const FUSION = "score = max( derivative , drift , periodicity )   →   alert when score ≥ threshold"

export const NODILUTION = [
  { t: "HOLD the baselines", d: "an anomaly never gets to corrupt the very stats that are supposed to catch it" },
  { t: "CLIP the drift head", d: "a slow step can't drown out a spike happening at the same moment" },
  { t: "GATE the periodicity head", d: "it stays silent on non-periodic data, so it never adds a false signal" },
  { t: "Share one state block", d: "all three heads reuse the same 96 bytes instead of ~424 for a naive four-detector vote" },
]
