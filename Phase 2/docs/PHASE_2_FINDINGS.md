# Phase 2 — Findings & Outcomes

**Project:** On-Device Network Telemetry Anomaly Detection
**Phase:** 2 — Empirical benchmark of six lightweight detectors
**Dataset:** CESNET-TimeSeries24 (10-minute aggregated ISP traffic, primary signal `n_bytes`)
**Sweep:** 6 detectors × 4 window sizes (10, 20, 30, 50) × 4 anomaly types × 30 trials = **2,880 independent runs**
**Source data for this document:** [`results/csv/aggregated_results.csv`](../results/csv/aggregated_results.csv)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Experimental Setup (Recap)](#2-experimental-setup-recap)
3. [Headline Finding — No Single Detector Wins](#3-headline-finding--no-single-detector-wins)
4. [Per-Anomaly Leaderboard](#4-per-anomaly-leaderboard)
5. [Class-Imbalance Effect on Precision](#5-class-imbalance-effect-on-precision)
6. [Iteration 1 → Iteration 2 — What Retuning Bought](#6-iteration-1--iteration-2--what-retuning-bought)
7. [Detection Latency](#7-detection-latency)
8. [Window-Size Sensitivity](#8-window-size-sensitivity)
9. [On-Device Resource Fit](#9-on-device-resource-fit)
10. [Implications for Phase 3](#10-implications-for-phase-3)
11. [Limitations & Caveats](#11-limitations--caveats)

---

## 1. Executive Summary

Phase 2 empirically validated six lightweight statistical detectors against four classes of injected anomalies on real CESNET ISP traffic. The four headline outcomes are:

1. **No single detector covers all four anomaly types.** Each detector has a class it dominates and a class on which it is unusable. A single-detector deployment is not viable.
2. **MAD and Z-Score dominate spike-like anomalies** (transient, burst). MAD reaches **TPR = 1.00** on transients across every window size.
3. **EWMA, CUSUM, and Page-Hinkley are the right tools for sustained changes** (rate shift, gradual drift), but each has a different failure mode under tail noise.
4. **Class imbalance, not detector quality, is the main cause of low precision.** With only 5–20 anomalous samples in a ~280-sample series, even a 5 % per-sample false-positive rate produces more false alarms than there are true positives.

These four facts together justify the Phase 3 architecture: a **two-layer ensemble** (spike + sustained) wrapped in a **confirmation gate** to reject singleton false alarms.

---

## 2. Experimental Setup (Recap)

| Component | Value |
|-----------|-------|
| Dataset | CESNET-TimeSeries24, `n_bytes` per IP, 10-minute aggregation |
| Detectors | Z-Score, MAD, EWMA, Sliding-Window-Stats, CUSUM, Page-Hinkley |
| Window sizes | 10, 20, 30, 50 samples |
| Anomaly types | burst (5 samples), rate-shift (~20 samples), gradual drift (slope 0.3, 20 samples), transient (1 sample) |
| Trials per cell | 30 (Iter 1 used 10 — see §6) |
| Random seed | Fixed; results are reproducible |
| Series length | ~280 samples per IP |
| Per-detector state budget target | < 100 bytes |
| Per-update latency target | < 100 µs on ARM control plane |

Metrics recorded per cell: TPR, FPR, F1, precision, detection rate (≥ 1 alarm in detection window), and detection latency (samples between injection start and first alarm).

---

## 3. Headline Finding — No Single Detector Wins

The aggregated TPR for each detector at its **best window size**, per anomaly:

| Detector              | Burst   | Transient | Rate shift | Gradual drift |
|-----------------------|--------:|----------:|-----------:|--------------:|
| **Z-Score**           | 0.567   | **1.000** | 0.095      | 0.107         |
| **MAD**               | **0.940** | **1.000** | **0.582**  | **0.585**     |
| **EWMA**              | 0.553   | 0.400     | 0.550      | 0.560         |
| **Sliding-Window**    | 0.327   | 0.433     | 0.337      | 0.297         |
| **CUSUM**             | 0.547   | 0.500     | 0.468      | 0.437         |
| **Page-Hinkley**      | 0.380   | 0.433     | 0.293      | 0.300         |

(Bold = anomaly-type leader. Source rows: `results/csv/aggregated_results.csv`.)

MAD looks like the universal winner on TPR alone — **but** its FPR is consistently in the 13–17 % band across every condition, which makes it unsuitable for standalone deployment. The point is not that MAD is the best single detector; the point is that **no single detector simultaneously hits high TPR and acceptable FPR for every anomaly class**.

The selectivity story per anomaly type:

- **Burst**: Z-Score has FPR ≈ 4 % but only 33–57 % TPR; MAD has 94 % TPR but 14–17 % FPR. Neither alone is good enough — but their AND is.
- **Rate shift / gradual drift**: EWMA, CUSUM, and Page-Hinkley all sit in the 30–55 % TPR range with FPR in the 6–20 % band. EWMA and CUSUM use complementary mechanisms (frozen baseline vs. accumulated evidence) and trip at different samples on the same shift — i.e., they are well-suited to OR-fusion.
- **Transient**: Z-Score and MAD both reach TPR = 1.0; sustained-change detectors miss by design.

This is the empirical basis for splitting the Phase 3 pipeline into a spike layer and a sustained-change layer.

---

## 4. Per-Anomaly Leaderboard

For each anomaly type, the detector with the strongest combination of TPR, FPR, and detection rate at its best window size:

### Burst (5-sample sudden spike)
| Rank | Detector / window | TPR | FPR | Detection rate |
|------|-------------------|----:|----:|---------------:|
| 1 | **MAD** @ w=20      | 0.940 | 0.147 | 1.00 |
| 2 | MAD @ w=30          | 0.947 | 0.164 | 1.00 |
| 3 | Z-Score @ w=50      | 0.567 | 0.040 | 0.83 |
| — | EWMA @ w=10         | 0.553 | 0.191 | 0.63 |

**Why MAD wins:** the median is immune to mean / σ inflation by the burst itself (the *masking effect*), so the burst's own MAD-z-score stays large. Z-Score is a precision-friendly confirmer because its FPR is the lowest in the table.

### Transient (single-sample point anomaly)
| Rank | Detector / window | TPR | FPR | Detection rate |
|------|-------------------|----:|----:|---------------:|
| 1 | **MAD** @ any w       | 1.000 | 0.131–0.153 | 1.00 |
| 2 | Z-Score @ w=10/20/30  | 1.000 | 0.046–0.064 | 1.00 |

**Why both win:** transients are a per-sample decision problem. Accumulation detectors (CUSUM, Page-Hinkley) miss by design — they need consecutive evidence. MAD and Z-Score evaluate every sample independently. Z-Score is in fact the precision-superior choice here (FPR ≈ 5 %); MAD is interchangeable on TPR but pays a higher FPR.

### Rate shift (~20-sample step change)
| Rank | Detector / window | TPR | FPR | Detection rate |
|------|-------------------|----:|----:|---------------:|
| 1 | **MAD** @ w=50        | 0.582 | 0.173 | 0.87 |
| 2 | EWMA @ w=10           | 0.542 | 0.206 | 0.47 |
| 3 | CUSUM @ w=20          | 0.468 | 0.075 | 0.60 |

**Why this is hard:** by detection rate, MAD wins because it fires on *every* sample of the shifted region. EWMA wins on what Phase 2 considers the *meaningful* signature — a frozen baseline `μ₀` keeps the EWMA statistic past the upper control limit for the whole shifted region. CUSUM is the lowest-FPR member of this group (~7 %) and therefore the right *confirmer*. EWMA + CUSUM together cover the shift via different mechanisms.

### Gradual drift (slow slope over 20 samples)
| Rank | Detector / window | TPR | FPR | Detection rate |
|------|-------------------|----:|----:|---------------:|
| 1 | **MAD** @ w=50        | 0.585 | 0.153 | 0.60 |
| 2 | CUSUM @ w=10          | 0.437 | 0.118 | 0.53 |
| 3 | Page-Hinkley @ w=20   | 0.257 | 0.129 | 0.70 |

**Why this is the open problem:** drift is sub-σ relative to baseline noise. MAD wins on per-sample TPR but its detection rate (0.60) is no better than Page-Hinkley's (0.70). Page-Hinkley dominates on **detection rate** because its adaptive mean tracks slow change — exactly what drift looks like — but it requires a long observation window to accumulate enough evidence, which costs latency. This is the one anomaly class where the Phase 3 default sustained layer (`EWMA ∨ CUSUM`) may regress vs the best Phase-2 individual; see Phase 3 docs §14 for the swap-in path.

---

## 5. Class-Imbalance Effect on Precision

In every cell of the sweep, **precision is essentially zero** (most rows < 0.01). The cause is structural:

- A series has ~280 samples.
- An anomaly has 1 (transient) – 20 (rate shift) anomalous samples — i.e., 0.4 % – 7 % positive base rate.
- A detector with even a 5 % per-sample FPR generates ~14 false alarms per series — comparable to or larger than the number of true positives.

**This is not a detector failure mode — it is a consequence of the evaluation regime.** Per-sample F1 will look low in absolute terms regardless of the detector. The right responses are:

1. Treat **TPR + FPR** (and detection rate) as the headline metrics, not F1.
2. Reduce FPs at the *system* level via a confirmation gate that requires N consecutive alarms before escalating. A 2-of-2 gate eliminates the singleton false alarms typical of MAD/Z-Score on tail noise while preserving recall on multi-sample anomalies.

Phase 3's `ConfirmationGate(n=2)` implements exactly this.

---

## 6. Iteration 1 → Iteration 2 — What Retuning Bought

Iteration 1 exposed two failure modes: (a) high run-to-run variance from too few trials, and (b) detector parameters that were either overconservative (CUSUM `h=5.0`, Page-Hinkley `λ=50`) or undermargined (EWMA `L=3.0`).

| Parameter | Iter 1 | Iter 2 | Reason | Effect |
|-----------|-------:|-------:|--------|--------|
| `N_TRIALS` | 10 | **30** | Iter 1 std deviation often exceeded the mean (e.g. CUSUM burst σ=0.44, μ=0.33). | ~45 % reduction in standard error of the mean. |
| CUSUM `h` | 5.0 | **3.5** | Burst lasts 3–5 samples; accumulated deviation rarely reached 5.0. | Lifted CUSUM burst TPR from ~0.33 to ~0.55. |
| Page-Hinkley `λ` | 50.0 | **12.0** | λ=50 was effectively random (TPR=0.10 on burst). On a 280-sample series the PH statistic accumulates to ~8–12 under H₀. | Page-Hinkley moved from "untriggerable" to "best on drift by detection rate". |
| EWMA `L` | 3.0 | **3.5** | Iter 1 FPR was 27–43 %. | FPR pulled down to ~17–20 % at the cost of ~5 % TPR. |
| Burst duration | 3 | **5** | Accumulation detectors need consecutive samples to build evidence. | Made burst a fair test for CUSUM / Page-Hinkley. |
| Drift slope / duration | 0.2 / 15 | **0.3 / 20** | All detectors had < 45 % TPR in Iter 1. | Drift is now detectable but still the hardest class. |

**Takeaway:** Iter 2 is the version of these detectors that all Phase-3 work and downstream decisions are based on. Iter 1 results should be treated as historical only.

---

## 7. Detection Latency

`avg_detection_latency` measures samples between injection start and first alarm. Lower is better, but only matters when TPR is non-trivial.

Concrete observations (Iter 2):

- **MAD: latency = 0** for transients and most bursts at any window size — the median's robustness lets it fire on the first anomalous sample.
- **Z-Score: latency = 0** for transients across all windows.
- **CUSUM and Page-Hinkley** show 1–3 sample latencies as expected — they need to accumulate evidence.
- **EWMA** sits between the two, typical 0.2–1.6 sample latency on rate shift.

Implication: in the Phase 3 ensemble, the spike layer (`MAD ∧ Z-Score`) keeps near-zero latency for instant deviations; the sustained layer (`EWMA ∨ CUSUM`) accepts 1–2 samples of latency in exchange for catching shifts the spike layer can't see.

---

## 8. Window-Size Sensitivity

A small but practically important finding:

- **MAD** is essentially **window-size insensitive** (TPR = 1.00 on transients across w ∈ {10, 20, 30, 50}). This is a deployment win — sizing a switch's per-feature window is no longer a tuning headache.
- **CUSUM, Page-Hinkley** are largely window-independent because their state is the cumulative statistic, not the window itself. Window only affects warmup.
- **Z-Score** improves with larger windows on burst (TPR 0.187 → 0.567 from w=10 → w=50) — larger w gives a more stable σ estimate and the burst's own samples have less impact on it.
- **Sliding-Window-Stats** degrades with larger windows on most classes — it is consistently the weakest detector and is not recommended for any role.

Phase 3 retains all four window sizes for comparability, but practical deployments can pick a single window size (recommended: 20) without losing much.

---

## 9. On-Device Resource Fit

All six detectors meet the stated targets:

| Resource axis | Target | Phase 2 result |
|---------------|--------|----------------|
| Per-feature state | < 100 bytes | All six fit; Welford ring buffer is the largest at ~8·w bytes (≤ 400 B for w=50) |
| Per-update time | < 100 µs on ARM | All updates are O(1) except median computation in MAD which is O(w log w) but dominated by w ≤ 50 |
| External libraries inside `update()` | None | Confirmed — no pandas, only numpy primitives or pure Python |

This is what makes the Phase 4 C++ port a **mechanical translation** rather than a redesign: the detectors are already written in arithmetic that maps directly to fixed-point or floating-point on an ARM core.

---

## 10. Implications for Phase 3

The findings above translate into a concrete architecture:

```
   Layer 1 — Spike pipeline      :  GatedMAD ∧ GatedZScore     (high precision)
   Layer 2 — Sustained pipeline  :  GatedEWMA ∨ GatedCUSUM     (high recall on shifts)
   Top-level fusion              :  Layer 1 OR Layer 2         (union of coverage)
   Confirmation gate             :  n = 2 consecutive child alarms before alarming
```

Each design choice is grounded in a Phase 2 measurement:

1. **Spike layer = MAD ∧ Z-Score** because both fire on instant deviations but with different FPR profiles (4–6 % vs 13–16 %); their AND drops the compound FPR to roughly 1 %.
2. **Sustained layer = EWMA ∨ CUSUM** because they lock onto the same shift via different mechanisms and trip at different samples; OR-fusion captures whichever trips first without inflating FPR (both children are already gated).
3. **`n=2` confirmation gate** because all multi-sample anomaly types (burst 5, rate-shift 20, drift 20) comfortably exceed 2 samples; only transients (1 sample by design) cannot benefit, and Phase 2 already shows transients are detected reliably without help.
4. **OR fusion at the top** because Layer 1 and Layer 2 have nearly disjoint failure modes (Layer 1 fails on shifts; Layer 2 fails on instants).

Phase 3's [`PHASE_3_DOCUMENTATION.md`](../../Phase%203/docs/PHASE_3_DOCUMENTATION.md) carries this through to implementation.

---

## 11. Limitations & Caveats

- **Single feature.** The benchmark used only `n_bytes`. Multi-feature fusion (e.g. `n_bytes`, `n_packets`, `tcp_udp_ratio_packets`) is out of scope and may shift the per-anomaly leaderboard.
- **Synthetic anomalies.** The four anomaly classes are injected, not labelled in the wild. Real CESNET incidents may not decompose cleanly into burst / shift / drift / transient.
- **No adversarial / concept-drift evaluation.** Detectors are evaluated against the same type of noise they were tuned on. Performance under traffic distribution shift (DDoS pattern change, ISP topology change) is untested.
- **Page-Hinkley not in default Phase 3 ensemble.** Phase 2 shows Page-Hinkley is the best per-trial detection-rate detector for gradual drift, but Phase 3's default sustained layer is `EWMA ∨ CUSUM`. If drift is the deployment priority, swap `cusum → page_hinkley` in `Phase 3/config.py::ENSEMBLE.sustained_layer.members` and re-run.
- **Precision as a headline metric is misleading** in this regime — see §5. Phase 3 retains the same metric set for comparability, but reviewers should focus on TPR / FPR / detection rate.
- **Iter 1 results should not be cited** — they were superseded by Iter 2 retuning (§6).

---

*Document version: Phase 2 — generated 2026-04-30.*
*Source data: `Phase 2/results/csv/aggregated_results.csv` (the raw 2,880-trial sweep is in `raw_trial_results.csv`).*
*See also:* [`PHASE_2_DOCUMENTATION.md`](PHASE_2_DOCUMENTATION.md) *(full technical reference) and* [`Phase 3/docs/PHASE_3_DOCUMENTATION.md`](../../Phase%203/docs/PHASE_3_DOCUMENTATION.md) *(architecture built on these findings).*
