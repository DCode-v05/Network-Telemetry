// Unified detector architecture content (authored from unified.py / unified.c).

export const HEADS = [
  {
    n: 1, name: "Derivative head", color: "var(--red)",
    stat: "first-difference z-score",
    anomalies: ["spike", "transient"],
    formula: "z = |Δx − μ_Δ| / σ_Δ",
    trick: "Anomaly-aware HOLD",
    trickDesc: "Freezes its running mean/variance while |z| ≥ 2.5, so a spike can't be absorbed into its own baseline (which would mask it and cause a burst of false positives right after).",
    why: "Scores the rate of change, not the level — so an abrupt edge or a 1-sample transient lights up sharply while slow drift is ignored.",
  },
  {
    n: 2, name: "EWMA control-chart head", color: "var(--purple)",
    stat: "held EWMA vs windowed σ",
    anomalies: ["drift"],
    formula: "s = |z − μ| / (σ·√(λ/(2−λ)))",
    trick: "Output CLIPPED at 0.9",
    trickDesc: "The drift score is capped below the 1.0 decision boundary so a slow, legitimate step can never out-shout a genuine spike under MAX-fusion. Baseline is held while deviating so it doesn't chase the drift.",
    why: "A fast EWMA tracks the signal while a slow held baseline lags — the gap between them opens on a sustained shift.",
  },
  {
    n: 3, name: "Gated ACF-drop head", color: "var(--cyan)",
    stat: "lag-k autocorrelation drop",
    anomalies: ["periodicity"],
    formula: "s = max(0, r_ref − ACF(lag))",
    trick: "GATE — arms only if periodic",
    trickDesc: "On the first full buffer it scans lags 2–8 for the strongest autocorrelation; it only arms if that exceeds 0.45. On aperiodic signals it stays silent, contributing zero dilution to the fused score.",
    why: "A healthy periodic signal has strong autocorrelation at its dominant lag; when the rhythm breaks, that correlation drops.",
  },
]

export const STATE = {
  total: 96,
  items: [
    { k: "5 float32 scalars", bytes: 20, detail: "μ_Δ, σ²_Δ, z, μ, r_ref" },
    { k: "17-deep ring buffer", bytes: 68, detail: "float32 × 17 — spans the dominant period" },
    { k: "integer counters", bytes: 8, detail: "n, period, armed" },
  ],
  note: "5×4 + 17×4 + 8 = 96 bytes < 100-byte budget. The 17-deep buffer (vs 16) is the one budget-precise change that lifted periodicity detection from ~0.84 to ~1.00 — and it stays under budget because `period` is an int, not a float.",
}

export const FUSION = "score = max( derivative , drift , periodicity )   →   alert when score ≥ threshold"

export const NODILUTION = [
  { t: "HOLD baselines", d: "anomalies never corrupt the stats that are supposed to catch them" },
  { t: "CLIP the drift head", d: "a gradual step can't dominate a simultaneous spike under max-fusion" },
  { t: "GATE the periodicity head", d: "silent on non-periodic data — no false contribution" },
  { t: "Share one state block", d: "3 heads reuse the same 96 bytes instead of ~424 for a naive 4-detector vote" },
]
