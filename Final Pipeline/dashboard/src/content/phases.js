// phases.js -- the written content for the phase-by-phase walkthrough. The facts
// and numbers come from the repo docs (Phase 1 study, Phase 2 benchmark, Phase 3
// ensemble docs, Phase 4 report/selection); the wording is meant to read like a
// person explaining it. Quantitative tables come from evaluation.json.

// ---------------------------------------------------------------- Phase 1 ----
export const PHASE1 = {
  goal: 'Before running a single experiment, we asked a simple question of 15 classic anomaly-detection algorithms: could this one even work in our budget of 10 to 50 samples, under 100 bytes, and under 100 microseconds? Only the ones that passed on paper moved on.',
  studied: [
    { name: 'Z-Score', cat: 'statistical', verdict: 'kept', note: 'Kept because it is O(1) and streaming (Welford’s method): a cheap, reliable spike baseline.' },
    { name: 'MAD', cat: 'statistical', verdict: 'kept', note: 'Kept because it stays robust on heavy-tailed, bursty traffic where a plain average gets fooled.' },
    { name: 'EWMA', cat: 'smoothing', verdict: 'kept', note: 'Kept because one running average both smooths the signal and flags level shifts, all in O(1).' },
    { name: 'CUSUM', cat: 'change-point', verdict: 'kept', note: 'Kept because it adds up small deviations to catch a sustained shift, with almost no state.' },
    { name: 'Page-Hinkley', cat: 'change-point', verdict: 'kept', note: 'Kept as the specialist for slow, gradual drift, and it is still O(1).' },
    { name: 'Sliding-Window', cat: 'statistical', verdict: 'kept', note: 'Kept as a simple window-stats primitive the other detectors build features from.' },
    { name: 'ADWIN', cat: 'change-point', verdict: 'cut', note: 'Cut: its change test needs hundreds to thousands of samples to mean anything, useless at 50.' },
    { name: 'DDM', cat: 'change-point', verdict: 'cut', note: 'Cut: it watches a classifier’s error rate, but we have raw telemetry and no classifier.' },
    { name: 'Kalman Filter', cat: 'state-space', verdict: 'cut', note: 'Cut: it needs noise parameters we simply cannot pin down on ever-changing traffic.' },
    { name: 'Matrix Profile', cat: 'pattern', verdict: 'cut', note: 'Cut: a batch method that wants the whole series and O(N²) work.' },
    { name: 'Spectral Residual', cat: 'pattern', verdict: 'cut', note: 'Cut: an FFT on 10 samples gives almost no usable frequency detail.' },
    { name: 'SAX / HOT-SAX', cat: 'pattern', verdict: 'cut', note: 'Cut: its normalisation breaks on tiny windows, and it is batch anyway.' },
    { name: 'ARIMA', cat: 'forecasting', verdict: 'cut', note: 'Cut: fitting its coefficients needs hundreds of samples and a steady signal.' },
    { name: 'PELT', cat: 'segmentation', verdict: 'cut', note: 'Cut: it optimises over the entire series at once, which is fundamentally batch.' },
    { name: 'Binary Segmentation', cat: 'segmentation', verdict: 'cut', note: 'Cut: recursive splitting falls apart on short, noisy windows.' },
  ],
  selectedRoles: [
    { name: 'Z-Score', role: 'Kept as the cheapest spike baseline: O(1) and streaming via Welford’s method, so it always fits the budget.' },
    { name: 'MAD', role: 'Kept for heavy-tailed, bursty traffic where a plain average gets fooled: robust, and still cheap.' },
    { name: 'EWMA', role: 'Kept because one running average smooths the signal and flags level shifts at the same time, in O(1).' },
    { name: 'CUSUM', role: 'Kept because it catches sustained rate shifts by accumulating small deviations, with tiny state.' },
    { name: 'Page-Hinkley', role: 'Kept as the specialist for slow, gradual drift, and it stays O(1).' },
    { name: 'Sliding-Window', role: 'Kept as a simple window-stats primitive the other detectors build their features from.' },
  ],
  familyLegend: [
    { cat: 'statistical', d: 'Flags points that stray from the recent mean or spread (Z-Score, MAD, Sliding-Window).' },
    { cat: 'smoothing', d: 'Tracks a running, exponentially-weighted average of the signal (EWMA).' },
    { cat: 'change-point', d: 'Watches for a lasting shift in the signal’s statistics over time (CUSUM, Page-Hinkley, ADWIN, DDM).' },
    { cat: 'state-space', d: 'Models a hidden internal state and predicts the next value (Kalman filter).' },
    { cat: 'pattern', d: 'Compares shapes and subsequences, or the frequency spectrum (Matrix Profile, Spectral Residual, SAX).' },
    { cat: 'forecasting', d: 'Fits a model, predicts ahead, and flags large prediction errors (ARIMA).' },
    { cat: 'segmentation', d: 'Splits the series into uniform segments at change-points (PELT, Binary Segmentation).' },
  ],
  coverage: [
    { cond: 'Burst traffic', primary: 'Z-Score / MAD', support: 'EWMA control chart' },
    { cond: 'Sudden rate change', primary: 'CUSUM', support: 'Page-Hinkley' },
    { cond: 'Gradual drift', primary: 'Page-Hinkley', support: 'EWMA' },
    { cond: 'Transient (1 to 3 samp)', primary: 'Z-Score / MAD', support: 'Sliding-window max' },
    { cond: 'Periodicity shift', primary: 'Sliding-window variance', support: 'EWMA variance' },
  ],
  justification: 'The six that made it through all share three things the other nine do not. They still make statistical sense at 10 to 50 samples, they update one sample at a time with no re-fitting, and they fit the memory and compute budget. They also split neatly into two camps: some track the baseline (EWMA, sliding window) and others catch changes (CUSUM, Page-Hinkley, Z-Score, MAD). That split is exactly what set up Phase 2 to test them and Phase 3 to combine them.',
}

// ---------------------------------------------------------------- Phase 2 ----
export const PHASE2 = {
  goal: 'Take the six survivors and put them to work on real ISP traffic, with anomalies we injected ourselves so we always knew the right answer. The point was to see exactly which detector catches which kind of anomaly, and whether any single one could handle them all.',
  method: [
    { k: 'The Data', v: 'Real per-IP byte counts from CESNET-TimeSeries24 (10-minute buckets, ~280 points each), normalised so every series sits on the same scale.' },
    { k: 'The Anomalies we injected', v: 'Four kinds, each sized in standard deviations: a 5-sample burst, a step to a new level, a slow ramp, and a single-sample spike.' },
    { k: 'The Sweep', v: 'Six detectors × four anomaly types × four window sizes × 30 repeats, which comes to 2,880 runs in all.' },
    { k: 'What we measured', v: 'Detection rate, false-positive rate, and how fast each one reacted. We report detection rate rather than F1, because these rare anomalies make sample-F1 collapse to near zero for everyone.' },
  ],
  findings: [
    'MAD and Z-Score own the spikes and transients, with near-perfect detection, but Z-Score starts slipping on slower changes (rate-shift 0.67, drift 0.60).',
    'EWMA, CUSUM and Page-Hinkley are the mirror image: strong on sustained shifts and drift, but they smooth a one-sample transient away (Page-Hinkley catches it only 43% of the time).',
    'And the real sting: the detectors that catch everything do it by alerting constantly. MAD hits full recall at about a 14.6% false-positive rate; Z-Score stays clean (~4.5%) but misses more. You get high recall or few false alarms, but not both.',
    'Sliding-Window came last in every anomaly type and every window, so we kept it only as a building block.',
  ],
}

// ---------------------------------------------------------------- Phase 3 ----
export const PHASE3 = {
  goal: 'Take the six benchmarked detectors and turn them into something you would actually deploy. The aim is to keep the detection but cut the false alarms, and we do it with a confirmation gate and two specialised voting layers.',
  gate: {
    title: 'The confirmation gate (n = 2)',
    how: 'It wraps any detector and only lets it fire after two alarms in a row. A one off noise blip never survives that, while a real anomaly, which lasts several samples, passes straight through. And once it starts firing it keeps firing until the streak breaks, so we do not lose per-sample recall.',
  },
  layers: [
    { name: 'Spike layer', mode: 'AND', members: 'GatedMAD ∧ GatedZScore', why: 'Both instant-change detectors have to agree before it fires, which drops the combined false alarm rate to around one percent while staying fast on bursts and transients.' },
    { name: 'Sustained layer', mode: 'OR', members: 'GatedEWMA ∨ GatedCUSUM', why: 'The two catch a shift at slightly different moments, so we take whichever fires first. Each one is already gated, so the noise stays low.' },
    { name: 'Two-layer fusion', mode: 'OR', members: 'Spike ∨ Sustained', why: 'Spike problems and sustained problems fail in different ways, so ORing the two layers covers both without bringing the old noise back.' },
  ],
  roster: '14 detectors in all: the 6 Phase-2 singles, plus 4 gated versions (GatedZScore, GatedMAD, GatedEWMA, GatedCUSUM) and 4 ensembles (Spike_AND, Spike_OR, Sustained_OR, TwoLayerEnsemble).',
  fprReduction: [
    { det: 'MAD', before: 14.6, after: 5.6 },
    { det: 'Z-Score', before: 5.1, after: 0.7 },
    { det: 'CUSUM', before: 11.8, after: 5.7 },
    { det: 'EWMA', before: 19.1, after: 19.0 },
  ],
  findings: [
    'The confirmation gate wipes out 50 to 85 percent of the false positives on the spike detectors. Z-Score drops from 5.1% down to 0.7% and MAD from 14.6% to 5.6%, and both keep most of the real detection.',
    'EWMA barely moves, and that is expected. Its false alarms come in runs, not one-offs, so a two-in-a-row gate has nothing to catch.',
    'The full two-layer ensemble catches the most real anomalies (recall around 0.47), but at a higher false alarm rate of about 0.20. That is a deliberate choice: catch everything, and let a human sort it out.',
  ],
  justification: 'Phase 3 proved the idea works. The gate, the two layers and the two-in-a-row rule are all small and simple enough to port straight to C. But it is still four detectors bolted together, which means four separate piles of state. That raised the obvious question for Phase 4: could one detector, built from scratch, do the same job in a fraction of the memory?',
}

// ---------------------------------------------------------------- Phase 4 ----
export const PHASE4 = {
  goal: 'Pick the one detector we would actually ship. We rebuilt around 20 candidates and scored each on intelligence and cost at the same time, behind a hard gate of under 100 microseconds and under 100 bytes, and kept the one that covers all four anomaly types inside that budget.',
  intel: 'intel = 0.45·VUS-PR + 0.30·F1 + 0.15·(MCC+1)/2 + 0.10·latency-score',
  intelParts: [
    { w: '0.45', k: 'VUS-PR', d: 'a threshold-free score, averaged over a small timing tolerance. It is the fair way to rank rare anomalies that might be flagged a sample or two late.' },
    { w: '0.30', k: 'F1', d: 'measured at each detector’s own best operating point, so the comparison is fair.' },
    { w: '0.15', k: 'MCC', d: 'Matthews correlation, rescaled to 0 to 1, a balanced accuracy check.' },
    { w: '0.10', k: 'latency', d: 'rewards catching the anomaly quickly and penalises being slow.' },
  ],
  budget: 'The cost gate is not a trade-off, it is a hard line. A detector has to come in under 100 microseconds and under 100 bytes, measured in C. The cheap O(1) detectors always pass, the ones that buffer a window pass only up to about window 22, and the big voting and cascade ensembles blow the budget entirely.',
  whyUnified: [
    'unified is the only detector inside budget that covers all four anomaly types in one unit, and it posts the highest threshold-free score (VUS-PR 0.42) of anything we tested, over-budget rivals included.',
    'deriv is actually the cheapest point on the Pareto front (20 bytes, about 5 nanoseconds), but it only handles spikes and transients, so it is the pick when you already know the failure mode.',
    'At window sizes 20 to 50, the single 96-byte unified reaches event-F1 above 0.90 on spikes, drift, periodicity and transients all at once.',
    'In C the maths runs in double precision so it matches Python exactly, and the 96 bytes is the on-device float32 state. Python, C and JavaScript all give identical scores, a maximum difference of zero.',
  ],
  justification: 'unified takes Phase 3’s four-detector ensemble and replaces it with one purpose-built 96-byte unit whose three heads cover all four types at 0.90+ event-F1, inside the budget, with a C twin we have verified matches. That unit is exactly what we packaged as the Final Pipeline.',
}
