# EVALUATION CRITERIA SPECIFICATION
## Lightweight Time-Series Anomaly Detection for Network Telemetry
### Short Observation Windows (10–50 Samples) — On-Device Intelligence

| Field | Details |
|---|---|
| **Project** | HPE CPP — Lightweight Network Telemetry Analytics |
| **Document type** | Evaluation Criteria Specification |
| **Phase** | Phase 2–5 (Data Preparation through Reporting) |
| **Algorithms** | Z-Score, MAD, EWMA, CUSUM, Page-Hinkley, Sliding Window, Isolation Forest, Random Forest |
| **Datasets** | CESNET-TimeSeries24 (primary), NAB AWS CloudWatch (benchmark), OVS Lab (ground truth) |
| **Target device** | HPE Aruba / ProCurve switches — ARM-class control plane processor |
| **Status** | Phase 1 (algorithm study) complete. Phase 2 in progress. |

---

## 1. Purpose and Scope

This document defines the complete evaluation criteria for assessing lightweight time-series anomaly detection algorithms intended for deployment on the control plane of HPE network switches. Every algorithm evaluated in Phase 3 is assessed against identical, reproducible conditions defined in this specification. Results are not considered valid unless all conditions are met exactly as stated here.

The deployment target is an ARM-class management processor on an HPE switch, subject to three immovable resource constraints:

- **Observation window:** 10–50 samples maximum
- **Memory per monitored metric:** < 100 bytes of persistent state
- **Compute per sample:** < 100 microseconds on ARM-class hardware

Any algorithm or combination that violates these three constraints is considered ineligible for deployment regardless of detection accuracy. Accuracy is evaluated only within the feasibility envelope.

---

## 2. Evaluation Dimensions

All algorithms are evaluated across the following independent variables. Every combination of algorithm × window size × anomaly type × dataset produces one evaluation cell. The total number of primary evaluation cells is 7 algorithms × 4 window sizes × 4 anomaly types = **112 cells** before combination experiments.

| Dimension | Values Tested | Count | Purpose |
|---|---|---|---|
| Algorithm | Z-Score, MAD, EWMA, CUSUM, Page-Hinkley, Sliding Window + Isolation Forest, Random Forest | 7 algorithms | Primary variable |
| Window size N | 10, 20, 30, 50 samples | 4 sizes | Core constraint |
| Anomaly type | Burst, Rate change, Transient, Periodicity shift | 4 types | Detection target |
| Dataset | CESNET-TimeSeries24 (institutions), NAB AWS CloudWatch, OVS lab | 3 datasets | Generalisation |
| Combination | Single algorithm vs layered (EWMA + CUSUM, EWMA + PH, IF + RF) | 6 combinations | Phase 4 |

Data splits must preserve temporal order. Random shuffling is strictly prohibited. The train/validation/test split is **70% / 15% / 15%** in chronological sequence on all datasets.

---

## 3. Detection Accuracy Metrics

All accuracy metrics are computed per evaluation cell — one value per (algorithm, window size, anomaly type, dataset) combination. Global averages are reported alongside per-cell values. Do not report only global averages; granular per-cell results are required for the final recommendation matrix.

| Metric | Priority | Scope | Rationale |
|---|---|---|---|
| F1 Score | Primary | All conditions | Balances false alarms and missed detections |
| Precision | Primary | All conditions | Alarm correctness rate |
| Recall | Primary | All conditions | Anomaly capture rate |
| AUC-ROC | Primary | Score-producing algorithms | Threshold-independent comparison |
| Detection latency | Primary | All conditions | Samples from onset to first alarm |
| False positive rate | Primary | Normal traffic only | Operational nuisance metric |
| Mean time to detect | Secondary | All conditions | Real-time wall-clock equivalent |
| False negative rate | Secondary | Per anomaly type | Missed detection rate by class |

### 3.1 F1 Score (Primary Metric)

F1 is the harmonic mean of Precision and Recall. It is the primary metric because both types of error carry operational cost in network management: a false alarm triggers unnecessary investigation; a missed detection allows a problem to persist undetected.

```
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × (Precision × Recall) / (Precision + Recall)
```

- **Minimum acceptable F1 for deployment recommendation:** 0.75 overall; 0.70 for any individual anomaly type.
- An algorithm scoring below 0.60 on any anomaly type is considered to have **failed** that detection task.

### 3.2 AUC-ROC (Threshold-Independent Comparison)

For algorithms producing a continuous anomaly score (EWMA control chart deviation, CUSUM statistic, Isolation Forest score), the threshold is varied from 0 to the maximum observed score and the ROC curve is computed. AUC-ROC provides a fair comparison between algorithms regardless of whether their thresholds have been optimally tuned. Report both AUC-ROC and the F1 score at the threshold that maximises F1 on the validation set.

### 3.3 Detection Latency

Latency is measured as the number of samples from anomaly onset to the first triggered alarm. It is the single most operationally important metric for on-device use. An alarm that fires 15 samples after anomaly onset on a 1-second polling interval means the condition has been active for 15 seconds before any response is triggered.

```
Latency = (index of first alarm) − (index of anomaly onset)
```

Report mean, median, and 90th-percentile latency per evaluation cell. The latency targets by anomaly type are:

| Anomaly Type | Target (Pass) | Acceptable | Fail Condition |
|---|---|---|---|
| Burst traffic | ≤ 2 samples | ≤ 4 samples | > 4 samples — unacceptable |
| Sudden rate change | ≤ 4 samples | ≤ 8 samples | > 8 samples — unacceptable |
| Transient anomaly | ≤ 1 sample | ≤ 2 samples | > 2 samples — anomaly may have passed |
| Periodicity shift | ≤ 6 samples | ≤ 12 samples | Must catch within one period |

### 3.4 False Positive Rate

FPR is measured separately on normal-traffic-only segments of the test set. This isolates the alarm rate from legitimate traffic and is the metric most directly tied to operator experience. A high FPR means the system generates noise that operators will learn to ignore, defeating the purpose of on-device detection.

```
FPR = FP / (FP + TN)  [measured on normal segments only]
```

- **Target:** FPR < 0.02 (2%) for deployment.
- FPR > 0.05 (5%) **disqualifies** an algorithm from the deployment recommendation regardless of F1 score.

---

## 4. Computational Resource Metrics

Resource metrics are **hard constraints, not soft targets**. An algorithm that exceeds the memory or compute budget is ineligible regardless of detection performance. The constraint applies per monitored metric: a switch monitoring 500 interfaces simultaneously multiplies all memory and compute costs by 500.

### 4.1 Memory State Footprint

Count only the bytes of persistent state maintained between samples. Temporary variables used within a single `update()` call do not count. Model weights for Isolation Forest and Random Forest count in full because they must reside in memory at all times. All values assume 4-byte float32 representation.

| Algorithm | N=10 | N=20 | N=30 | N=50 | Complexity |
|---|---|---|---|---|---|
| Z-Score (Welford) | 12 B | 12 B | 12 B | 12 B | O(1) |
| EWMA control chart | 12 B | 12 B | 12 B | 12 B | O(1) |
| CUSUM (two-sided) | 16 B | 16 B | 16 B | 16 B | O(1) |
| Page-Hinkley | 16 B | 16 B | 16 B | 16 B | O(1) |
| MAD (sliding) | 40 B | 80 B | 120 B | 200 B | O(N) |
| Sliding window stats | 60 B | 100 B | 140 B | 220 B | O(N) |
| Isolation Forest | < 4 KB | < 4 KB | < 4 KB | < 4 KB | O(depth) |
| Random Forest | < 8 KB | < 8 KB | < 8 KB | < 8 KB | O(trees×depth) |

> **Note:** MAD and Sliding Window exceed the 100-byte target at N=50. Both are still valid candidates because: (a) N=20–30 keeps them within budget, and (b) the evaluation will determine whether shorter windows suffice without accuracy loss.

### 4.2 Per-Sample Compute Time

Timing is measured using Python's `time.perf_counter_ns()` over 10,000 samples to eliminate JIT and scheduling noise. The ARM simulation target uses QEMU-ARM or an equivalent emulator. All timing uses single-threaded execution — no parallelism is permitted for the on-device scenario.

| Component | Target (x86) | Target (ARM sim) | Hard Limit |
|---|---|---|---|
| Statistical algorithms (Z-Score, MAD, EWMA, CUSUM, PH) | < 5 μs | < 20 μs | < 100 μs |
| Sliding window statistics | < 10 μs | < 40 μs | < 100 μs |
| Isolation Forest inference | < 20 μs | < 60 μs | < 100 μs |
| Random Forest inference | < 30 μs | < 80 μs | < 100 μs |
| Combined pipeline (all algorithms + model) | < 50 μs | < 150 μs | < 500 μs |

### 4.3 Streaming Complexity Verification

Verify O(1) per-sample behaviour by measuring execution time at N = 10, 20, 30, 50. Plot time vs N. A flat line confirms O(1). A rising line indicates O(N) behaviour. Algorithms with O(N) compute are not eligible for the streaming deployment scenario but may be retained as offline batch baselines for comparison.

### 4.4 Cold-Start Samples

From a fresh initialisation with no history, measure how many samples are required before the algorithm reaches steady-state detection performance (defined as F1 within 10% of its fully-warmed value). Algorithms requiring more than 50 samples to warm up are impractical on devices that reboot frequently or encounter new metrics during operation.

- **0–5 samples:** warm-up phase — F1 may be unreliable
- **6–20 samples:** stabilisation phase — F1 approaching steady state
- **21+ samples:** steady state — evaluation window begins here

---

## 5. Parameter Sensitivity Analysis

Sensitivity analysis measures how much an algorithm's performance degrades when its parameters are not perfectly tuned. An algorithm that only works in a narrow parameter range is dangerous in production: the correct parameters for a new network environment are never known in advance, and frequent manual re-tuning is infeasible on hundreds of deployed switches.

For each algorithm and parameter, compute F1 and FPR across the test range below. Report the sensitivity plot (F1 vs parameter value) and the performance gap between best and worst parameter combination. A gap below 10% is considered robust. A gap above 20% disqualifies the parameter combination as a deployment default.

| Algorithm | Parameter | Test Range | Stability Criterion |
|---|---|---|---|
| Z-Score | Threshold z | 1.5, 2.0, 2.5, 3.0, 3.5 | F1 drop < 10% across range = robust |
| MAD | Threshold k | 2.0, 2.5, 3.0, 3.5 | F1 drop < 10% across range = robust |
| EWMA | Smoothing λ | 0.05, 0.10, 0.20, 0.30, 0.50 | F1 > 0.70 at all λ values |
| CUSUM | Slack k, alarm threshold h | k ∈ {0.25σ, 0.5σ, 1σ}, h ∈ {2, 3, 5, 8} | 12 combinations; best combo vs worst < 20% gap |
| Page-Hinkley | Threshold λ, slack δ | λ ∈ {20, 50, 100}, δ ∈ {0.01, 0.05, 0.1} | 9 combinations; best vs worst < 20% gap |
| Isolation Forest | Contamination, n_estimators | cont ∈ {0.05, 0.1, 0.15}, trees ∈ {5, 10, 20} | Stable AUC ± 0.05 across contamination range |
| Random Forest | Max depth, n_estimators | depth ∈ {3, 5, 7}, trees ∈ {5, 10, 20} | F1 variance < 0.05 across depth values |

---

## 6. Robustness Tests

### 6.1 Non-Stationarity Robustness

Real network traffic undergoes legitimate baseline shifts: scheduled backups, business-hours peaks, new applications being deployed. A detector must not continuously false-alarm after a sustained legitimate shift in traffic level.

**Test procedure:** inject a permanent 4× step-up in baseline traffic rate (e.g., 5 Mbps to 20 Mbps) without labelling it as an anomaly. Measure the FPR spike magnitude in the 10 samples immediately following the shift and the number of samples until FPR returns to the pre-shift baseline level.

- **Pass:** FPR spike < 20%; recovery within 20 samples
- **Fail:** FPR spike > 50% or recovery requires > 50 samples

### 6.2 Multi-Anomaly Masking (Z-Score)

The masking effect occurs when multiple simultaneous anomalies inflate the standard deviation, making each individual anomaly appear less extreme. This is a known theoretical limitation of Z-Score at small N.

**Test procedure:** inject 2 simultaneous burst anomalies into a 10-sample window. Compare Recall to the single-burst baseline case. A Recall drop greater than 15 percentage points confirms masking. Report for N = 10, 20, 30.

### 6.3 Cross-Dataset Generalisation

An algorithm trained or parametrised on CESNET-TimeSeries24 (ISP backbone traffic) must generalise to NAB AWS CloudWatch (server infrastructure metrics) without retraining. This tests whether the detection mechanism captures universal anomaly signatures or memorises dataset-specific patterns.

**Pass criterion:** F1 drop from CESNET test set to NAB test set is less than 15 percentage points. A drop greater than 20 percentage points indicates overfitting to CESNET traffic characteristics.

### 6.4 Anomaly Duration Sensitivity

Test detection performance as anomaly duration varies from 1 sample (single-point transient) through 3, 5, 10, and 20 samples (sustained anomaly). Plot F1 vs anomaly duration. Algorithms that only detect sustained anomalies are insufficient for transient burst detection. Algorithms that only detect brief anomalies will miss sustained rate shifts.

---

## 7. Evaluation Scoring Rubric

Each algorithm receives a composite score computed as the weighted sum of five dimension scores. Scores are assigned on a 1–5 integer scale per the criteria below. The composite score determines the deployment recommendation tier.

| Dimension | Weight | Score 5 | Score 3 | Score 1 | Scale |
|---|---|---|---|---|---|
| F1 Score (mean, all anomaly types) | 30% | ≥ 0.85 | 0.65–0.84 | < 0.65 | 5/3/1 |
| Detection latency (median samples) | 25% | ≤ 2 | 3–7 | > 7 | 5/3/1 |
| False positive rate (normal traffic) | 20% | < 1% | 1–5% | > 5% | 5/3/1 |
| Memory footprint (bytes, N=50) | 15% | < 50 B | 50–220 B | > 220 B | 5/3/1 |
| Parameter sensitivity (F1 variance) | 10% | < 0.05 | 0.05–0.15 | > 0.15 | 5/3/1 |

**Composite score formula:**

```
Score = (F1 × 0.30) + (Latency × 0.25) + (FPR × 0.20) + (Memory × 0.15) + (Sensitivity × 0.10)
```

**Deployment tiers based on composite score:**

| Score | Tier | Meaning |
|---|---|---|
| ≥ 4.0 | **Recommended** | Algorithm is reliable, fast, and memory-efficient |
| 3.0–3.9 | **Conditional** | Acceptable with specific configuration guidance or window-size restrictions |
| 2.0–2.9 | **Research interest only** | Unsuitable for on-device deployment, useful as offline baseline |
| < 2.0 | **Rejected** | Fails one or more hard constraints; not viable for this project |

---

## 8. Testable Hypotheses

The following hypotheses are derived from the Phase 1 algorithm study. Each must be explicitly confirmed or refuted by the Phase 3 evaluation results. Confirming a hypothesis validates the theoretical reasoning. Refuting one is equally valuable — it indicates that empirical performance on network telemetry diverges from theoretical prediction, which is a publishable finding.

| ID | Name | Prediction | If Confirmed |
|---|---|---|---|
| H1 | CUSUM vs Z-Score on rate changes | CUSUM F1 > Z-Score F1 by ≥ 10% on rate_change anomaly type at all window sizes | Validates CUSUM's evidence accumulation advantage |
| H2 | MAD vs Z-Score on bursts | MAD F1 > Z-Score F1 by ≥ 5% on burst_anomaly type at N ≤ 20 | Validates MAD resistance to masking effect |
| H3 | EWMA + CUSUM vs single algorithms | Layered F1 > best single algorithm F1 by ≥ 5% across all anomaly types | Validates two-layer pipeline architecture |
| H4 | Window size degradation | F1 at N=10 < F1 at N=50 for all algorithms and anomaly types | Validates short-window constraint impact |
| H5 | Z-Score masking at N=10 | Z-Score FN rate increases when 2+ simultaneous anomalies present at N=10 | Confirms known theoretical limitation |
| H6 | EWMA detection latency | EWMA mean latency ≤ 3 samples — lowest across all algorithms | Validates streaming-native design advantage |
| H7 | IF vs RF without anomaly labels | Isolation Forest AUC within 0.05 of Random Forest on CESNET dataset | Validates unsupervised approach viability |
| H8 | Cross-dataset generalisation | F1 drop < 15% from CESNET (training) to NAB AWS (test) for all algorithms | Validates HPE deployment readiness |

---

## 9. Deployment Pass/Fail Criteria

The following criteria determine whether an algorithm is recommended for deployment on HPE switches. Pass/Fail is binary for HPE's decision — an algorithm either meets the operational bar or it does not. The Conditional tier allows deployment with documented restrictions (e.g., only at N ≥ 20, or only for burst detection, not rate-change detection).

| Criterion | Pass (Deploy) | Conditional | Fail (Reject) |
|---|---|---|---|
| F1 score (mean across anomaly types) | ≥ 0.80 | ≥ 0.70 | < 0.60 — do not deploy |
| False positive rate (normal traffic) | < 2% | < 5% | > 5% — operationally unusable |
| Memory state (N=50, per metric) | < 100 B | < 220 B | > 220 B — violates device budget |
| Per-sample CPU time (ARM target) | < 50 μs | < 100 μs | ≥ 100 μs — violates real-time |
| Detection latency — burst/transient | ≤ 2 s | ≤ 4 s | > 8 s — anomaly may be over |
| Cross-dataset F1 drop (CESNET → NAB) | < 10% | < 15% | > 20% — overfit to training data |
| Cold-start samples to stable detection | ≤ 15 | ≤ 30 | > 50 — impractical on reboot |

An algorithm must **pass all seven criteria** to receive an unconditional deployment recommendation. Failing any single criterion results in either a Conditional or Fail rating for that criterion, which flows into the composite score. No algorithm with a Fail on memory or compute criteria is eligible for the deployment recommendation regardless of accuracy.

---

*HPE Connectivity & Protection Platform | Evaluation Criteria Specification — Lightweight Anomaly Detection — Confidential*
