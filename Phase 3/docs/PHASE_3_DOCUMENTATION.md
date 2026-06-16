# Phase 3 — Two-Layer Ensemble Anomaly Detection

**Project:** On-Device Network Telemetry Analytics
**Phase:** 3 — Ensemble + Confirmation Gate (Python prototype)
**Builds on:** Phase 2 (six-detector benchmark, complete)
**Language:** Python 3.10+
**Sponsor:** HP CPP Internship

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Goals Carried Over From Phase 2](#2-goals-carried-over-from-phase-2)
3. [Ensemble Design Rationale](#3-ensemble-design-rationale)
4. [Architecture](#4-architecture)
5. [`ConfirmationGate`](#5-confirmationgate)
6. [`VotingLayer`](#6-votinglayer)
7. [`TwoLayerEnsemble`](#7-twolayerensemble)
8. [Configuration (`ENSEMBLE` block)](#8-configuration-ensemble-block)
9. [Harness Changes vs Phase 2](#9-harness-changes-vs-phase-2)
10. [Detector Roster](#10-detector-roster)
11. [Re-Benchmark Protocol](#11-re-benchmark-protocol)
12. [Metrics Reference](#12-metrics-reference)
13. [Expected Result Patterns](#13-expected-result-patterns)
14. [Reading the Dashboard](#14-reading-the-dashboard)
15. [Limitations & Risks](#15-limitations--risks)
16. [Phase 4 Recommendations (C++ Port Path)](#16-phase-4-recommendations-c-port-path)
17. [Repository Layout](#17-repository-layout)
18. [How to Run](#18-how-to-run)

---

## 1. Executive Summary

Phase 2 concluded that **no single detector covers all four anomaly types**. The class-imbalanced setting (5–20 anomalous samples in a ~280-sample series) also crippled precision: even a 5% per-sample false-positive rate generates more false alarms than there are true positives.

Phase 3 implements the two-layer ensemble + confirmation-gate architecture recommended in [`Phase 2/docs/PHASE_2_DOCUMENTATION.md`](../../Phase%202/docs/PHASE_2_DOCUMENTATION.md), section 14:

```
     ┌─────────────────────────────────────────┐
     │  Layer 1 — Spike pipeline               │
     │      Gated MAD ∧ Gated Z-Score          │ ──┐
     └─────────────────────────────────────────┘   │
                                                   ▼   alarm if either layer fires
     ┌─────────────────────────────────────────┐ ┌─────────────────────┐
     │  Layer 2 — Sustained-change pipeline    │ │ TwoLayerEnsemble    │
     │      Gated EWMA ∨ Gated CUSUM           │─►│                     │
     └─────────────────────────────────────────┘ └─────────────────────┘
```

Each base detector is wrapped in a `ConfirmationGate(n=2)` that requires two consecutive child alarms before firing. Layer 1 votes AND (high precision); Layer 2 votes OR (high recall, since EWMA and CUSUM lock onto sustained shifts at different times).

Implementation is **100% additive over Phase 2**: every Phase 2 detector and the harness contract are reused unchanged. Phase 3 adds three new classes (each subclassing `DetectorBase`) and a small evaluation/visualisation layer.

## 2. Goals Carried Over From Phase 2

- **Reproducibility** — same CESNET dataset, same hyperparameters, same RNG seed.
- **Same `DetectorBase` contract** — ensembles plug into the existing harness with zero glue.
- **No pandas inside detectors** — every ensemble class is plain Python + the bridge re-export of NumPy-only Phase 2 detectors. Mechanical C++ portability preserved for Phase 4.
- **Centralised configuration** — `Phase 3/config.py` extends Phase 2's config; nothing is hard-coded inside detectors.

## 3. Ensemble Design Rationale

### Why a confirmation gate?
A 2-of-2 gate eliminates singleton false alarms — typical of MAD/Z-Score on tail noise — while preserving detection on multi-sample anomalies. Burst (5 samples), rate-shift (20 samples), and gradual-drift (20 samples) all comfortably exceed the 2-sample threshold; only `transient` (1 sample by design) is theoretically lost, but `transient` is also the anomaly type Phase 2 already detected reliably without help.

### Why AND in the spike layer?
MAD and Z-Score both flag the same instant-deviation events. AND-voting keeps the agreement (both detectors corroborate) and rejects the noise that fools only one statistic. Phase 2 measured per-detector burst FPRs of 4.6% (Z-Score) and 14.8% (MAD); the AND of two near-independent 5–15% FPRs drops compound FPR to roughly 1%, below the 5% Phase 2 target.

### Why OR in the sustained layer?
EWMA and CUSUM lock onto sustained changes via different mechanisms (frozen baseline + control limit vs. accumulating evidence). They tend to fire at *different samples* during the same shift. AND-voting would require simultaneous detection (rare); OR-voting takes whichever detector trips first, which improves detection latency without sacrificing many false positives because both detectors are already gated to 2-of-2.

### Why OR fusion at the top level?
Burst/transient is a Layer-1 problem; rate-shift/drift is a Layer-2 problem. The two layers have nearly disjoint failure modes — combining them with OR captures the union of their coverage. The gates inside each layer have already absorbed the per-layer FP overhead, so the top-level OR does not re-introduce the original noise.

## 4. Architecture

```
                                ┌─────────────────────┐
   sample x                     │  AnomalyInjector    │  (Phase 2 — unchanged)
   ──────►  CESNET CSV ──►─►─►──┤  inject burst /     │
            (Phase 2 loader)    │  rate_shift / drift │
                                │  / transient        │
                                └────────┬────────────┘
                                         │  signal + labels
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │  Phase 3 build_detectors(window_size)        │
                  │  returns 14 DetectorBase instances           │
                  └──────────────────────────────────────────────┘
                                         │
                  ┌──────────────────────┴──────────────────────┐
                  │                                             │
                  ▼                                             ▼
   ┌───────────────────────┐               ┌────────────────────────────────┐
   │ Phase 2 individuals   │               │ Phase 3 ensemble layer (NEW)   │
   │ Z, MAD, EWMA, CUSUM,  │               │ ┌─────────────────────────┐    │
   │ PageHinkley,          │               │ │ ConfirmationGate(MAD,n) │    │
   │ SlidingWindow         │               │ │ ConfirmationGate(Z,  n) │    │
   └───────────────────────┘               │ │ ConfirmationGate(EWMA,n)│    │
                                           │ │ ConfirmationGate(CUSUM,n)│   │
                                           │ └────────────┬────────────┘    │
                                           │              ▼                 │
                                           │ ┌─────────────────────────┐    │
                                           │ │ VotingLayer(AND/OR)     │    │
                                           │ └────────────┬────────────┘    │
                                           │              ▼                 │
                                           │ ┌─────────────────────────┐    │
                                           │ │ TwoLayerEnsemble        │    │
                                           │ └─────────────────────────┘    │
                                           └────────────────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │  Phase 2 metrics + Phase 3 phase3_metrics.py │
                  │  → results/csv/                              │
                  │  → results/dashboard.html                    │
                  └──────────────────────────────────────────────┘
```

## 5. `ConfirmationGate`

Source: [`ensemble/confirmation_gate.py`](../ensemble/confirmation_gate.py).

```python
class ConfirmationGate(DetectorBase):
    def __init__(self, child: DetectorBase, n_consecutive: int = 2)
```

**Behaviour**: forwards every sample to `child.update`. Maintains an internal `_streak` counter that increments on a child alarm and resets on any non-alarm. Declares `is_anomaly = (_streak >= n_consecutive)`.

**Edge case** — *streak continuation*: while the streak remains ≥ n the gate keeps firing every sample. This is required by Phase 2's `compute_metrics`, which counts per-sample TPR/FPR. A 5-sample anomaly with n=2 produces 4 in-window alarms (samples 2–5), preserving recall.

**Reset semantics**: `reset()` clears `_streak` to 0 *and* propagates to the child detector. This is verified by the parametrised base-contract test (`tests/test_ensemble_base_contract.py::test_reset_is_idempotent`).

**Output fields**:
- `score = child.score` (preserves ROC compatibility)
- `alarm_value = float(_streak)` (visible in dashboard for debugging)
- `name = "Gated{base}(n={n})"`, e.g. `"GatedMAD(n=2)"`

## 6. `VotingLayer`

Source: [`ensemble/voting_layer.py`](../ensemble/voting_layer.py).

```python
class VotingLayer(DetectorBase):
    def __init__(self, children: list[DetectorBase], mode: str = "AND",
                 layer_name: str = "Voting")
```

**Modes**:
- `"AND"` — every child must alarm on the same sample. Suppresses single-detector noise.
- `"OR"` — any child alarming is enough. Maximises coverage.

**Output fields**:
- `score = max(child.score for child in children)` — monotonic, suitable for ROC.
- `alarm_value = vote count` — number of children that fired this step.
- `name` — `"{layer_name}_{mode}({c1+c2+...})"`, e.g. `"Spike_AND(GatedMAD+GatedZScore)"`.

**Validation**: requires ≥ 2 children and `mode ∈ {"AND", "OR"}`; otherwise raises `ValueError` in `__init__`.

## 7. `TwoLayerEnsemble`

Source: [`ensemble/two_layer_ensemble.py`](../ensemble/two_layer_ensemble.py).

```python
class TwoLayerEnsemble(DetectorBase):
    def __init__(self, spike_layer: DetectorBase,
                 sustained_layer: DetectorBase,
                 use_routing: bool = False,
                 name_suffix: str = "")
```

**Fusion rule**: `is_anomaly = spike OR sustained`.
**Score**: `max(spike.score, sustained.score)`.
**`alarm_value` attribution**:

| Spike fired? | Sustained fired? | alarm_value |
|--------------|------------------|-------------|
| ✓            | (any)            | 1.0         |
| ✗            | ✓                | 2.0         |
| ✗            | ✗                | 0.0         |

Attribution lets the dashboard colour-code which layer caught each anomaly — useful when diagnosing missed anomalies.

**`use_routing` flag**: reserved for an experimental per-anomaly-type routing mode. Off by default — using ground-truth anomaly labels to choose layers at test time would be evaluation leakage.

## 8. Configuration (`ENSEMBLE` block)

In [`config.py`](../config.py):

```python
ENSEMBLE = {
    "confirmation_n":  2,
    "spike_layer":     {"members": ["mad", "zscore"], "voting_mode": "AND"},
    "sustained_layer": {"members": ["ewma", "cusum"], "voting_mode": "OR"},
    "include_individual_baselines": True,
    "include_gated_baselines":      True,
    "include_or_variant":           True,
}
```

`DETECTORS`, `INJECTION`, `WINDOW_SIZES`, `ANOMALY_TYPES`, `N_TRIALS`, `RANDOM_SEED`, and `DATA_DIR` are inherited verbatim from Phase 2 via [`_phase2_bridge.py`](../_phase2_bridge.py) — Phase 3 results stay row-for-row comparable with Phase 2's.

## 9. Harness Changes vs Phase 2

[`evaluation/harness.py`](../evaluation/harness.py) is a shallow copy of Phase 2's harness. Only `build_detectors(window_size)` was rewritten — the trial loop, CSV writers, sanitiser, and aggregation logic are unchanged. Output schemas (`raw_trial_results.csv`, `aggregated_results.csv`) are byte-compatible with Phase 2's.

The harness gained one new optional config knob: `MAX_SAMPLES_PER_SERIES` (None by default). Setting it crops every loaded series before injection. Used only for smoke runs (`--quick` sets it to 2000) — leave `None` for the full benchmark.

## 10. Detector Roster

`build_detectors(window_size)` returns 14 detectors, in dashboard order:

| # | Name (as it appears in CSV) | Group |
|---|------------------------------|-------|
| 1 | `ZScore(w=W, thr=3.0)`             | individual |
| 2 | `MAD(w=W, thr=3.5)`                | individual |
| 3 | `EWMA(lambda=0.2, L=3.5)`          | individual |
| 4 | `CUSUM(k=0.5, h=3.5)`              | individual |
| 5 | `PageHinkley(delta=0.5, lambda=12.0)` | individual |
| 6 | `SlidingWindow(mean, w=W, thr=3.0)`| individual |
| 7 | `GatedCUSUM(n=2)`                  | gated |
| 8 | `GatedEWMA(n=2)`                   | gated |
| 9 | `GatedMAD(n=2)`                    | gated |
| 10 | `GatedZScore(n=2)`                | gated |
| 11 | `Spike_AND(GatedMAD+GatedZScore)`  | voting layer |
| 12 | `Sustained_OR(GatedEWMA+GatedCUSUM)`| voting layer |
| 13 | `Spike_OR(GatedMAD+GatedZScore)`   | ablation |
| 14 | `TwoLayerEnsemble`                 | top-level |

Total trial count: `4 windows × 4 anomaly types × 14 detectors × 30 trials = 6,720`.

## 11. Re-Benchmark Protocol

Use the **same** dataset, hyperparameters, and trial counts as Phase 2 — that is the entire point. Do not retune Phase 2 hyperparameters in Phase 3.

```bash
cd "Phase 3"
python main.py                                                          # full run
python main.py --compare_phase2_csv ../Phase\ 2/results/csv/aggregated_results.csv
```

Acceptance criteria (verified post-run):

| Criterion | Threshold |
|-----------|-----------|
| `gate_fp_reduction` positive for ≥ 3 of 4 base detectors  | central claim |
| `ensemble_vs_best_single` FPR ≤ best-single FPR for ≥ 3 of 4 anomaly types | central claim |
| Ensemble TPR within 5 pp of best-single TPR per anomaly | acceptable cost |
| All unit tests pass (`pytest tests/`)                   | wiring |

## 12. Metrics Reference

Plain-language reference for the metrics in the Phase 3 evaluation
(`evaluation/metrics_report.py`) and the columns in every results table.
Example numbers come from the w=20, 30-trial run (1,680 trials).

### 12.1 The foundation — 4 counts per trial

Every metric is built by comparing, for each sample, the detector's alarm
against the ground-truth label (anomaly or normal):

| Count | Name           | Plain meaning                                      |
| :---: | -------------- | -------------------------------------------------- |
| **TP** | True Positive  | Anomaly happened **and** the detector fired. ✅ hit |
| **FP** | False Positive | Normal sample **but** the detector fired. ❌ false alarm |
| **TN** | True Negative  | Normal sample **and** the detector stayed quiet. ✅ |
| **FN** | False Negative | Anomaly happened **but** the detector missed it. ❌ miss |

These are the `tp, fp, tn, fn` columns in `raw_trial_results.csv`. Everything
below is just a ratio of these four numbers.

### 12.2 The metrics

#### Accuracy
- **Plain:** Of *all* samples, what fraction did the detector label correctly?
- **Formula:** `(TP + TN) / (TP + FP + TN + FN)`
- **Range:** 0–1 · **higher is better**
- **⚠️ Misleading on this task:** ~99% of samples are normal, so a detector that
  *never fires* still scores ~0.99. Do **not** rank detectors by accuracy alone.
- **Example:** `Spike_AND` = **0.992** looks excellent — but it catches only ~6%
  of real anomalies (see its TPR). High accuracy here mostly means "stayed quiet."

#### Precision
- **Plain:** When the detector fires, how often is it actually right?
- **Formula:** `TP / (TP + FP)`
- **Range:** 0–1 · **higher is better**
- **⚠️** Very low here because the few real anomalies (5–20 samples) are swamped
  by false alarms across a ~40,000-sample series.

#### TPR — True Positive Rate (a.k.a. Recall / Detection Rate)
- **Plain:** Of *all the real anomalies*, what fraction did the detector catch?
- **Formula:** `TP / (TP + FN)`
- **Range:** 0–1 · **higher is better**
- **Example:** `TwoLayerEnsemble` TPR = **0.47** → catches ~47% of anomalies;
  `Spike_AND` TPR = **0.06** → catches ~6%.

#### FPR — False Positive Rate
- **Plain:** Of *all the normal samples*, what fraction did the detector wrongly flag?
- **Formula:** `FP / (FP + TN)`
- **Range:** 0–1 · **lower is better**
- **Example:** The confirmation gate's whole job: `MAD` FPR **0.146 → GatedMAD 0.056**;
  `ZScore` FPR **0.051 → GatedZScore 0.007**. Fewer false alarms.

#### F1 Score
- **Plain:** One number that balances Precision and Recall (their harmonic mean).
  Rewards catching anomalies **without** spamming false alarms.
- **Formula:** `2 · (Precision · Recall) / (Precision + Recall)`
- **Range:** 0–1 · **higher is better**
- **This is the honest headline metric** for imbalanced anomaly detection.
- **⚠️** Absolute values look tiny here (~0.005) because precision is tiny on long
  series — compare detectors **relative to each other**, not against 1.0.

### 12.3 "TPR vs FPR" — why they are shown as a pair

TPR and FPR are the two halves of one trade-off:

- **TPR ↑** = catch more real anomalies (good)
- **FPR ↓** = raise fewer false alarms (good)

You want **high TPR _and_ low FPR**. Each detector is one point on this trade-off:

| Detector            | TPR (catch) | FPR (false alarms) | Reading                          |
| ------------------- | :---------: | :----------------: | -------------------------------- |
| `Spike_AND`         |    0.06     |       0.007        | Barely fires — ultra-safe, misses most |
| `GatedMAD`          |    0.35     |       0.056        | Balanced precision side          |
| `TwoLayerEnsemble`  |    0.47     |       0.196        | Catches the most, at more false alarms |

This is the ROC-style view. **F1 collapses this pair into a single score.**

### 12.4 Table columns

**`metrics_report.py` console tables** (per detector, averaged over all trials):

| Table                      | Columns              | What each column is                          |
| -------------------------- | -------------------- | -------------------------------------------- |
| **ACCURACY PER DETECTOR**  | `detector`, `accuracy` | Name; mean accuracy (sorted best-first)    |
| **F1 SCORE PER DETECTOR**  | `detector`, `f1`     | Name; mean F1 (sorted best-first)            |
| **TPR vs FPR PER DETECTOR**| `detector`, `tpr`, `fpr` | Name; mean recall and mean false-alarm rate |

**`results/csv/metrics_report.csv`** (saved summary, one row per detector):

| Column      | Meaning                                                                |
| ----------- | ---------------------------------------------------------------------- |
| `detector`  | Detector name + its parameters, e.g. `MAD(w=20, thr=3.5)`              |
| `n_trials`  | How many trial rows were averaged (30 trials × 4 anomaly types = 120)  |
| `accuracy`  | Mean accuracy across those trials                                      |
| `f1`        | Mean F1 score                                                          |
| `tpr`       | Mean True Positive Rate (recall)                                       |
| `fpr`       | Mean False Positive Rate                                               |
| `precision` | Mean precision                                                         |

**`results/csv/raw_trial_results.csv`** (one row per single trial — the source data):

| Column              | Meaning                                                        |
| ------------------- | ------------------------------------------------------------- |
| `detector`          | Detector name + parameters                                    |
| `anomaly_type`      | `burst` / `rate_shift` / `gradual_drift` / `transient`        |
| `window_size`       | Sliding-window length used (20 here)                          |
| `trial`             | Trial index for this combination (0…29)                       |
| `tpr`, `fpr`, `precision`, `f1` | The metrics above, for this one trial             |
| `detection_latency` | Samples between anomaly start and first correct alarm (lower = faster) |
| `tp`, `fp`, `tn`, `fn` | The four raw counts from §12.1                             |

**`results/csv/aggregated_results.csv`** (one row per detector × anomaly × window):
Same idea, but each metric appears as a `_mean` and a `_std` pair (e.g.
`f1_mean`, `f1_std`) summarising the 30 trials, plus `detection_rate` (fraction
of trials in which the anomaly was caught at least once) and
`avg_detection_latency` / `stdev_detection_latency`.

### 12.5 How to read these together (one-line rule)

> **Accuracy** says "looks busy/quiet", **F1** says "is it actually good", and
> **TPR vs FPR** says "what trade-off did it make to get there." On this
> imbalanced task, trust **F1** and the **TPR/FPR pair** — not raw accuracy.

## 13. Expected Result Patterns

Based on Phase 2's per-detector breakdown:

- **Burst** — best individual ≈ MAD (89% TPR, 14% FPR). Ensemble: MAD ∧ Z-Score should drop FPR sharply (target < 5%) at modest TPR cost (~75%). Layer 1 wins.
- **Transient** — best individual ≈ MAD/Z-Score (90%+ TPR). Single-sample anomaly cannot benefit from gating; ensemble is no better than the best individual (and may be slightly worse — known design tradeoff).
- **Rate shift** — best individual ≈ EWMA. Ensemble: GatedEWMA ∨ GatedCUSUM should preserve EWMA's coverage while reducing 27% baseline FPR through gating. Layer 2 wins.
- **Gradual drift** — best individual ≈ Page-Hinkley. Phase 3 default sustained layer is `EWMA ∨ CUSUM` — Page-Hinkley is *not* in the default ensemble. If drift detection regresses, swap `cusum` for `page_hinkley` in `ENSEMBLE.sustained_layer.members`.

The dashboard's *Ensemble vs Best Individual* figure tells this story per anomaly type.

### 13.1 Measured F1 — results snapshot

> **Run config:** window = 20, N_TRIALS = 30, 99 IP series, **full-length
> (uncropped) series**, all four anomaly types. Source:
> `results/csv/metrics_report.csv` and `results/csv/aggregated_results.csv`.
> F1 is absolute-small here because uncropped ~40,000-sample series make the
> positive class (5–20 anomalous samples) extremely rare — read the columns
> **relative to each other**, not against 1.0 (see §15).

**F1 per detector** (mean over all four anomaly types, sorted best-first):

| Detector | F1 | TPR | FPR |
| -------- | -----: | ----: | ----: |
| GatedCUSUM(n=2)                     | 0.0223 | 0.280 | 0.057 |
| CUSUM(k=0.5, h=3.5)                 | 0.0075 | 0.480 | 0.120 |
| GatedEWMA(n=2)                      | 0.0058 | 0.423 | 0.190 |
| Sustained_OR(GatedEWMA+GatedCUSUM)  | 0.0057 | 0.431 | 0.191 |
| EWMA(lambda=0.2, L=3.5)             | 0.0054 | 0.505 | 0.204 |
| TwoLayerEnsemble                    | 0.0050 | 0.466 | 0.196 |
| Spike_OR(GatedMAD+GatedZScore)      | 0.0042 | 0.348 | 0.056 |
| GatedMAD(n=2)                       | 0.0042 | 0.346 | 0.056 |
| GatedZScore(n=2)                    | 0.0036 | 0.065 | 0.007 |
| Spike_AND(GatedMAD+GatedZScore)     | 0.0034 | 0.064 | 0.007 |
| MAD(w=20, thr=3.5)                  | 0.0022 | 0.655 | 0.146 |
| PageHinkley(delta=0.5, lambda=12.0) | 0.0021 | 0.346 | 0.139 |
| SlidingWindow(mean, w=20, thr=3.0)  | 0.0019 | 0.270 | 0.286 |
| ZScore(w=20, thr=3.0)               | 0.0017 | 0.378 | 0.051 |

**Best F1 per anomaly type** (with the ensemble shown for comparison):

| Anomaly | Best detector by F1 | F1 | TPR | FPR | TwoLayerEnsemble F1 |
| ------- | ------------------- | -----: | ----: | ----: | -----: |
| burst         | GatedCUSUM(n=2)       | 0.017 | 0.373 | 0.057 | 0.004 |
| transient     | ZScore(w=20, thr=3.0) | 0.001 | 1.000 | 0.049 | 0.000 |
| rate_shift    | GatedCUSUM(n=2)       | 0.038 | 0.315 | 0.049 | 0.009 |
| gradual_drift | GatedCUSUM(n=2)       | 0.034 | 0.298 | 0.051 | 0.007 |

**Reading:** by F1, the gated single detector **GatedCUSUM wins 3 of 4** anomaly
types — it keeps FPR low while still catching enough, which F1 rewards. The
`TwoLayerEnsemble` reaches the **highest recall** (TPR 0.54–0.56 per type) but its
OR-fusion lifts FPR to ~0.20, so its F1 trails. This is the precision cost of the
union design; F1 stays low in absolute terms because of the class imbalance
described in §15.

## 14. Reading the Dashboard

[`results/dashboard.html`](../results/dashboard.html) — generated automatically by `main.py` unless `--no_dashboard`.

Sections (in order):

1. **Ensemble vs Best Individual** — headline grouped bar of F1 per anomaly type. Hover for TPR/FPR.
2. **Confirmation-Gate Effect** — bar of % FPs eliminated per detector family; toggle TP retention via legend.
3. **F1 Score Heatmap** — detectors × anomaly types, dropdown for window size.
4. **TPR vs FPR** — grouped bars; toggle metric.
5. **F1 vs Window Size** — line plot per anomaly type.
6. **Detection Rate Heatmap**.
7. **Detection Latency** — horizontal bars with error bars.
8. **Detector Capability Radar** — normalised 5-axis profile.
9. **Phase 2 vs Phase 3** *(only when `--compare_phase2_csv` is supplied)*.

Theme toggle is in the top-right (gold "Light Mode" button on dark theme).

## 15. Limitations & Risks

- **Class imbalance is unchanged.** Phase 3 reduces FPs but cannot raise precision above what the 5–20-positive-samples-out-of-N regime allows. Precision will still look low in absolute terms; F1 is the appropriate headline metric.
- **Routing left off by default.** The `use_routing=True` flag exists for ablation only — it leaks ground-truth anomaly type into detection. Do not present routed results as "the ensemble".
- **Page-Hinkley is not in the default sustained layer.** Drift detection may regress vs the Phase-2 best (Page-Hinkley). If this matters, swap `cusum` → `page_hinkley` in `ENSEMBLE.sustained_layer.members` and re-run.
- **Single-feature only.** Phase 3 still operates on `n_bytes` only, like Phase 2. Multi-feature fusion is out of scope.
- **No C++ port.** Per the user-confirmed scope, Phase 3 is a Python prototype. Phase 4 is the C++ port path (see §16).

## 16. Phase 4 Recommendations (C++ Port Path)

The Phase 3 ensemble classes are written specifically with portability in mind: pure Python-level state, no dynamic dispatch beyond polymorphism, no NumPy in the ensemble layer (only inside the wrapped Phase 2 detectors, which themselves use only Welford / sort / arithmetic).

A faithful C++ port is a mechanical translation:
- `ConfirmationGate` → 4 bytes of state (`uint16_t streak`, `uint16_t n`) + a pointer to the wrapped detector.
- `VotingLayer` → fixed-size `std::array<DetectorBase*, K>` + a `mode` enum.
- `TwoLayerEnsemble` → two pointers to layers + an attribution byte.

State budget per ensemble instance (4 layers wrapping 4 base detectors): ~50 bytes assuming each base detector fits Phase 2's stated 100-byte target. Per-update cost: 4 deeply nested calls + 1 OR — well below 100 µs on an ARM control-plane CPU.

Recommended Phase 4 deliverables:
1. C++ implementations of `DetectorBase`, `WindowBuffer`, the four base detectors used in the ensemble, plus the three Phase 3 classes.
2. A C++ harness that replays the Phase 3 raw CSV against the C++ ensemble and bit-matches Python alarm sequences trial-by-trial.
3. A microbenchmark proving < 100 µs per `update()` and < 100 bytes of state per ensemble instance on the target ARM core.

## 17. Repository Layout

```
Phase 3/
├── _phase2_bridge.py                       — sys.path shim + Phase 2 re-exports
├── config.py                                — extends Phase 2 with ENSEMBLE block
├── main.py                                  — CLI entry
├── ensemble/
│   ├── __init__.py
│   ├── confirmation_gate.py                — ConfirmationGate
│   ├── voting_layer.py                     — VotingLayer
│   └── two_layer_ensemble.py               — TwoLayerEnsemble
├── evaluation/
│   ├── __init__.py
│   ├── harness.py                          — build_detectors + trial loop
│   └── phase3_metrics.py                   — winner / deltas / gate FP reduction
├── dashboard/
│   └── generate_report.py                  — Plotly HTML, 8 base + 2 new figures
├── tests/
│   ├── conftest.py                         — pytest bootstrap
│   ├── _helpers.py                         — MockDetector test double
│   ├── test_confirmation_gate.py           — 11 tests
│   ├── test_voting_layer.py                — 10 tests
│   ├── test_two_layer_ensemble.py          — 11 tests (incl. real detectors)
│   └── test_ensemble_base_contract.py      — 16 tests (4 ensembles × 4 contract checks)
├── docs/
│   └── PHASE_3_DOCUMENTATION.md            — this file
└── results/
    ├── csv/
    │   ├── aggregated_results.csv          — 14 detectors × 4 anomalies × 4 windows = 224 rows
    │   └── raw_trial_results.csv           — 6,720 rows after a full run
    └── dashboard.html
```

The `src/` package convention from Phase 2 is intentionally dropped — Phase 3 sits flat under its own root so that placing Phase 2 onto `sys.path` (via the bridge) does not collide with Phase 3's own packages. This is the only structural deviation from Phase 2's layout.

## 18. How to Run

### Setup

Phase 3 reuses Phase 2's `requirements.txt` and the existing `Phase 2/env/` virtualenv. From a fresh checkout:

```bash
cd "Phase 2"
python -m venv env
env\Scripts\activate                 # Windows
pip install -r requirements.txt
cd "../Phase 3"
```

Phase 3 reads CESNET CSVs from `Phase 2/data/ip_addresses_sample/agg_10_minutes/` — the data directory is shared, not duplicated.

### Smoke run (~30 seconds)

```bash
python main.py --quick --no_plot --no_dashboard
```

`--quick` sets `MAX_IPS=10`, `N_TRIALS=3`, `WINDOW_SIZES=[20]`, `MAX_SAMPLES_PER_SERIES=2000`. Useful for verifying the wiring.

### Full benchmark (~70 minutes on a laptop)

```bash
python main.py --compare_phase2_csv "../Phase 2/results/csv/aggregated_results.csv"
```

### Test suite (~0.2 seconds)

```bash
pytest tests/ -v
```

Expected: 48 tests passing, including 16 parametrised base-contract tests.

### Dashboard standalone

```bash
python dashboard/generate_report.py
```

Reads `results/csv/*.csv`, writes `results/dashboard.html`.

### CLI flags (`main.py`)

| Flag | Effect |
|------|--------|
| `--signal n_packets`            | Override `PRIMARY_SIGNAL` |
| `--max_ips N`                   | Limit number of IP series loaded |
| `--max_samples N`               | Crop each series to N samples (None = no crop) |
| `--n_trials N`                  | Override `N_TRIALS` |
| `--window_sizes 10 20`          | Override `WINDOW_SIZES` |
| `--confirmation_n N`            | Override `ENSEMBLE.confirmation_n` (ablation) |
| `--no_plot`                     | Skip matplotlib plots |
| `--no_dashboard`                | Skip HTML dashboard |
| `--compare_phase2_csv PATH`     | Add Phase 2 vs Phase 3 comparison figure |
| `--quick`                       | Smoke-run shortcut (see above) |

---

*Document version: Phase 3 — generated 2026-04-29.*
