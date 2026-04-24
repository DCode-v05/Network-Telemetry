# Algorithm Study Document
## Evaluate and Compare Lightweight Time-Series Techniques for Network Telemetry Using Short Observation Windows (10–50 Samples)

**Project Phase:** Phase 1 — Algorithm Study & Data Preparation  
**Prepared for:** Research Project — On-Device Network Telemetry Analytics  
**Scope:** Study of 15 candidate algorithms; selection rationale for Phase 2 experimentation

---

## Table of Contents

1. [Introduction & Scope](#1-introduction--scope)
2. [Evaluation Framework](#2-evaluation-framework)
3. [Algorithm Studies](#3-algorithm-studies)
   - 3.1 Z-Score
   - 3.2 MAD (Median Absolute Deviation)
   - 3.3 EWMA (Exponentially Weighted Moving Average)
   - 3.4 CUSUM (Cumulative Sum Control Chart)
   - 3.5 Page-Hinkley Test
   - 3.6 Sliding Window Statistics
   - 3.7 ADWIN (Adaptive Windowing)
   - 3.8 DDM (Drift Detection Method)
   - 3.9 Kalman Filter
   - 3.10 Matrix Profile
   - 3.11 Spectral Residual
   - 3.12 SAX / HOT SAX
   - 3.13 ARIMA (Autoregressive Integrated Moving Average)
   - 3.14 PELT (Pruned Exact Linear Time)
   - 3.15 Binary Segmentation
4. [Comparative Summary](#4-comparative-summary)
5. [Conclusion: Selection & Rejection Rationale](#5-conclusion-selection--rejection-rationale)
6. [References](#6-references)

---

## 1. Introduction & Scope

This document presents a structured study of fifteen candidate time-series algorithms evaluated against the specific requirements of on-device network telemetry analytics. The deployment target is the control plane processor of a network switch or router — an environment defined by strict constraints: observation windows of 10–50 samples, memory budgets under 100 bytes per metric, sub-millisecond per-sample compute time and no access to scientific computing libraries.

The algorithms studied span five broad families:
- **Statistical deviation methods** (Z-Score, MAD, Sliding Window Statistics)
- **Exponential smoothing** (EWMA)
- **Change-point detection** (CUSUM, Page-Hinkley, ADWIN, DDM)
- **State estimation** (Kalman Filter)
- **Pattern/structural analysis** (Matrix Profile, Spectral Residual, SAX/HOT SAX)

For each algorithm, this document covers: operating principle, suitability for short windows, computational and memory profile, anomaly types detectable, and known limitations. The document concludes with a selection rationale for Phase 2 experimentation and a theoretically-grounded rejection rationale for algorithms deemed incompatible with the project's constraints — without requiring empirical validation.

---

## 2. Evaluation Framework

Each algorithm is assessed against the following criteria, aligned with the project's deployment constraints and detection goals:

| Criterion | Description |
|---|---|
| **Minimum window viability** | Does the algorithm function meaningfully with N = 10–50 samples? |
| **Streaming compatibility** | Can it update incrementally with one new sample at a time? |
| **Memory footprint** | What state must be maintained per metric? |
| **Computational cost** | What is the per-sample complexity? |
| **Anomaly types** | Which conditions can it detect: bursts, rate shifts, periodicity changes, transients? |
| **Parameterization burden** | Does it require extensive tuning that depends on data volume? |
| **Theoretical fitness** | Are there fundamental theoretical reasons it fails under short windows? |

**Network conditions to detect** (as defined in Phase 1 scope):
- **Burst traffic** — sudden short-lived spike in packet/byte rate
- **Sudden rate changes** — step-change in baseline traffic level
- **Periodicity shifts** — loss or disruption of a regular pattern
- **Transient anomalies** — brief spikes/drops lasting 1–3 samples

**Observation window sizes:** 10, 20, 30, 50 samples

---

## 3. Algorithm Studies

---

### 3.1 Z-Score (Standard Score)

**Principle:**  
The Z-score measures how many standard deviations a data point lies from the mean of a reference window. A point is flagged as anomalous if |Z| > threshold (typically 2–3).

```
Z = (x - μ) / σ
```

Where μ is the window mean and σ is the window standard deviation.

**Short-Window Behavior:**  
Z-score is functional at N ≥ 10, but the reliability of σ estimation degrades at very small N. With N = 10, a single outlier can inflate σ sufficiently to mask itself (masking effect). This is a known statistical limitation — the sample standard deviation is a biased estimator at small N, and the breakdown worsens as N decreases [1].

**Streaming Compatibility:** Yes — with a sliding window, mean and variance can be updated incrementally using Welford's online algorithm [2], requiring O(1) compute and O(1) memory (just maintain running sum and sum-of-squares).

**Memory Footprint:** ~3 values (count, running mean, running M2). Negligible.

**Detects:**
-  Burst traffic (spike above mean)
-  Transient anomalies
-  Sudden rate changes (detects the spike but not the sustained shift)
-  Periodicity shifts

**Limitations:**
- Assumes approximate normality; network traffic is often heavy-tailed or bursty [3]
- Sensitive to non-stationary baselines; mean shifts cause false positives
- Masking effect at small N when multiple anomalies are present

**Verdict:** Viable for baseline spike detection. Simple to implement. Sensitive to distribution assumptions.

---

### 3.2 MAD (Median Absolute Deviation)

**Principle:**  
MAD is a robust alternative to Z-score, using the median instead of the mean, making it resistant to outliers:

```
MAD = median(|xi - median(x)|)
Robust Z = 0.6745 * (x - median(x)) / MAD
```

The constant 0.6745 scales MAD to be consistent with the standard deviation under normality [4].

**Short-Window Behavior:**  
More robust than Z-score at small N because the median is resistant to the masking effect. However, at N = 10, the median is computed from only 10 points — its statistical efficiency is lower than the mean (asymptotic relative efficiency of 0.637 vs. Gaussian [4]). Still functional and more reliable than Z-score for heavy-tailed distributions typical of network traffic.

**Streaming Compatibility:** Limited — computing the median requires sorting or a order-statistic data structure. A naive implementation requires O(N log N) per update. For small N (≤ 50), this is acceptable in absolute terms (sorting 50 numbers is trivial), but it does not update in pure O(1) streaming fashion.

**Memory Footprint:** Requires storing the full window: O(N) — e.g., 50 float values ≈ 400 bytes. Slightly above the 100-byte target at N = 50, but manageable at N = 10–20.

**Detects:**
-  Burst traffic
-  Transient anomalies
-  Sudden rate changes (same limitation as Z-score)
-  Periodicity shifts

**Limitations:**
- Not a true streaming algorithm (requires full window in memory)
- No temporal sensitivity — order of samples within window is ignored
- Less statistically efficient than mean-based methods under normality

**Verdict:** More robust than Z-score for non-Gaussian traffic. Slight memory and compute overhead but still lightweight. Candidate for short-window spike detection.

---

### 3.3 EWMA (Exponentially Weighted Moving Average)

**Principle:**  
EWMA assigns exponentially decreasing weights to past observations, controlled by smoothing parameter λ ∈ (0, 1):

```
S_t = λ * x_t + (1 - λ) * S_{t-1}
```

A control chart flags anomalies when the EWMA statistic exceeds control limits:

```
UCL/LCL = μ_0 ± L * σ * sqrt(λ / (2 - λ))
```

Where μ_0 is a target baseline and L is the number of sigma limits [5].

**Short-Window Behavior:**  
EWMA is inherently a streaming algorithm — it requires only the previous EWMA value and the new sample. It does not depend on a window size in the traditional sense; instead, λ implicitly defines the effective memory length (≈ 1/λ samples). This makes it naturally suited for short observation contexts. At small N, EWMA converges faster than sample-statistics methods and is effective from the very first sample after initialization.

**Streaming Compatibility:** Perfect — O(1) update, O(1) memory (stores only S_t and baseline μ_0).

**Memory Footprint:** ~2–3 values. Negligible.

**Detects:**
-  Burst traffic (sudden spike above control limit)
-  Sudden rate changes (gradual shift detected via sustained deviation)
-  Transient anomalies
-  Periodicity shifts (indirectly — disrupted periodicity changes EWMA variance)

**Limitations:**
- Requires baseline μ_0 to be initialized — performance depends on quality of initial estimate
- A single λ value controls the tradeoff between responsiveness (high λ) and smoothing (low λ); requires tuning
- Does not explicitly model or detect structural changes; outputs a smoothed signal, not a change probability

**Verdict:** Excellent fit for this project. Minimal resource use, streaming-native, works at any window size. Strong candidate for Phase 2.

---

### 3.4 CUSUM (Cumulative Sum Control Chart)

**Principle:**  
CUSUM accumulates deviations from a target value μ_0, designed to detect sustained shifts away from baseline. Two statistics track upward and downward deviations:

```
C+_t = max(0, C+_{t-1} + (x_t - μ_0 - k))
C-_t = max(0, C-_{t-1} - (x_t - μ_0 + k))
```

An alarm is raised when C+ or C- exceeds threshold h. k is the allowable slack (typically k = δ/2 where δ is the shift magnitude to detect) [6].

**Short-Window Behavior:**  
CUSUM is a sequential, streaming algorithm — it updates with each new sample and maintains no window. It is well-suited for detecting small, persistent shifts that accumulate over time. Its performance at short windows is strong precisely because it accumulates evidence rather than requiring a full window of data.

**Streaming Compatibility:** Perfect — O(1) update, O(1) memory.

**Memory Footprint:** ~4 values (C+, C−, μ_0, k). Negligible.

**Detects:**
-  Sudden rate changes (primary design purpose)
-  Burst traffic (rapid accumulation of C+)
-  Transient anomalies (with appropriate k)
-  Periodicity shifts

**Limitations:**
- Parameters k and h require prior knowledge of the expected shift magnitude and acceptable false positive rate [6]
- After an alarm, the statistic must be reset — the reset strategy affects subsequent detection
- Sensitive to baseline μ_0; requires accurate initialization or adaptive baseline tracking

**Verdict:** Highly suitable for change-point and rate-shift detection. Streaming-native, O(1) cost. Strong candidate for Phase 2.

---

### 3.5 Page-Hinkley Test

**Principle:**  
The Page-Hinkley (PH) test is a sequential hypothesis test for detecting a persistent change in the mean of a signal. It accumulates a running sum of deviations:

```
m_t = x_t - x̄_t - δ
PH_t = sum_{i=1}^{t} m_i
M_t = max(PH_1, ..., PH_t)
```

An alarm is raised when M_t - PH_t > λ (threshold) [7].

**Short-Window Behavior:**  
Like CUSUM, PH is a sequential test requiring no fixed window. It accumulates deviations from a running mean, making it adaptive to non-stationary baselines. At short observation lengths, it is functional from the first sample.

**Streaming Compatibility:** Yes — O(1) update per sample. Maintains running sum, running mean, and maximum of PH statistic.

**Memory Footprint:** ~4 values. Negligible.

**Detects:**
-  Sudden rate changes
-  Gradual drift (better than CUSUM for gradual shifts)
-  Burst traffic (detects sustained bursts; may miss brief transients)
-  Periodicity shifts

**Relationship to CUSUM:**  
Page-Hinkley is functionally similar to one-sided CUSUM. The key difference is that PH tracks the maximum of the cumulative sum rather than resetting — making it more sensitive to gradual drift but potentially slower to reset after a change [7].

**Limitations:**
- Threshold λ requires tuning; overly sensitive settings produce false positives on bursty traffic
- Detects only unidirectional shifts; bidirectional change requires two separate PH statistics
- Less studied in network telemetry contexts than CUSUM

**Verdict:** A viable alternative or complement to CUSUM for gradual drift scenarios. Candidate for Phase 2.

---

### 3.6 Sliding Window Statistics

**Principle:**  
Sliding window statistics maintain a fixed-size rolling buffer of the N most recent samples, computing descriptive statistics (mean, variance, min, max, range, skewness) over that window. Anomalies are detected by comparing current statistics to historical baseline statistics or fixed thresholds.

**Short-Window Behavior:**  
This is the most direct approach for short windows — the window size IS the observation window. At N = 10–50 samples, all statistics are computed over exactly the available data. This makes it inherently compatible with the project's observation window sizes.

**Streaming Compatibility:** Yes with incremental computation. Mean and variance can be updated in O(1) using Welford's method; min/max require O(N) scan on eviction unless augmented with a monotonic deque structure (O(1) amortized) [8].

**Memory Footprint:** O(N) — the buffer of N samples. At N = 50 with 4-byte floats: 200 bytes. Slightly above 100-byte target at maximum window; fine at N = 10–30.

**Detects:**
-  Burst traffic (mean/max spike)
-  Sudden rate changes (mean shift between windows)
-  Transient anomalies (max deviation from mean)
-  Periodicity shifts (variance increase detectable)

**Limitations:**
- Raw statistics carry no model of expected behavior; comparisons require a separate baseline
- Window boundary effects: abrupt changes in statistics when anomalous point enters or leaves window
- No probabilistic framework; threshold setting is heuristic

**Verdict:** A foundational primitive rather than a standalone detector. Highly useful as a feature extractor feeding into other detectors (e.g., EWMA or CUSUM on derived statistics). Candidate for Phase 2 as a supporting component.

---

### 3.7 ADWIN (Adaptive Windowing)

**Principle:**  
ADWIN maintains a variable-length window of recent data and automatically detects change points by comparing statistics of sub-windows. When the means of two sub-windows differ beyond a statistically significant bound (derived from Hoeffding's inequality), ADWIN shrinks the window by dropping the older sub-window [9]:

```
|μ_W0 - μ_W1| ≥ ε_cut
where ε_cut = sqrt((1/2m) * ln(4n/δ))
```

**Short-Window Behavior:**  
ADWIN's design assumes it can grow its window as long as the distribution is stationary. At N = 10–50 samples, ADWIN is severely constrained — it cannot split the window into meaningful sub-windows with sufficient statistical power. Hoeffding's inequality, which underpins ADWIN's change detection bound, requires a minimum sample count per sub-window for the bound to be tight. With total N = 10, splitting into two sub-windows of N = 5 each produces a very loose (wide) bound, making ADWIN insensitive to real changes [9][10].

**Streaming Compatibility:** Yes — incremental updates.

**Memory Footprint:** Variable — ADWIN stores data in a compressed bucket structure. In the worst case at small N, memory is O(N).

**Limitations (Short-Window Specific):**
- Statistical power of sub-window comparison degrades sharply at small N — theoretically, ADWIN's detection guarantee requires N large enough for Hoeffding bounds to be informative
- At N = 10–50, ADWIN behaves essentially as a fixed small window, losing its adaptive advantage
- Designed for concept drift detection in machine learning streams, not specifically for network anomaly detection at the timescales relevant here [9]

**Verdict:** Theoretically unsuitable for N = 10–50. ADWIN's core mechanism requires window sizes well beyond the project's constraint to operate as designed. **Rejected on theoretical grounds.**

---

### 3.8 DDM (Drift Detection Method)

**Principle:**  
DDM was designed for supervised concept drift detection in classification settings. It monitors the error rate p_t and standard deviation s_t of a classifier's predictions over time, raising a warning or alarm when:

```
p_t + s_t ≥ p_min + 2 * s_min  (warning)
p_t + s_t ≥ p_min + 3 * s_min  (drift alarm)
```

Where p_min and s_min are the minimum observed values [11].

**Short-Window Behavior & Fundamental Mismatch:**  
DDM requires a binary error signal (correct/incorrect prediction) from a classifier. Network telemetry is a continuous-valued time series — there is no classifier and no error rate signal. Adapting DDM to continuous data would require discretizing the signal into binary outcomes (e.g., "above threshold" or "below threshold"), which is essentially reducing it to simple threshold-based detection — losing DDM's statistical machinery entirely.

Furthermore, DDM's statistical bounds are derived for error rates converging over long sequences (hundreds to thousands of samples). It accumulates statistics over an unbounded growing window, not a fixed short window [11].

**Verdict:** Fundamentally mismatched to the problem domain. DDM operates on classifier error rates in a supervised learning context; this project has no classifier and no labels during online detection. Additionally, its statistical guarantees require large N. **Rejected on both domain mismatch and short-window theoretical grounds.**

---

### 3.9 Kalman Filter

**Principle:**  
The Kalman Filter (KF) is an optimal recursive Bayesian estimator for linear Gaussian state-space models. It models the system as:

```
State:       x_t = A * x_{t-1} + w_t     (process noise w ~ N(0, Q))
Observation: z_t = H * x_t + v_t          (measurement noise v ~ N(0, R))
```

The filter produces an optimal estimate x̂_t and covariance P_t via predict-update cycles. Anomalies are detected via the innovation (residual) z_t - H * x̂_t [12].

**Short-Window Behavior:**  
The Kalman Filter is a streaming algorithm — it processes one sample at a time with O(1) compute (for scalar state). It does not require a fixed window; it maintains a running state estimate. This makes it theoretically applicable at any window size.

However, the KF requires accurate specification of:
- Process noise covariance Q (how much the true state varies)
- Measurement noise covariance R (sensor noise level)
- State transition matrix A (dynamics model)

For network telemetry, these parameters are not known a priori and are highly non-stationary. An incorrectly specified KF diverges or produces poor estimates. The Extended/Unscented Kalman Filter variants that handle nonlinearity increase computational cost significantly [12].

**Streaming Compatibility:** Yes — O(1) per-sample update for scalar state.

**Memory Footprint:** For scalar state: ~5 values (x̂, P, Q, R, A). Negligible for scalar case; grows quadratically with state dimension.

**Detects:**
-  Transient anomalies (innovation residual spikes)
-  Burst traffic (large innovation)
-  Rate changes (depends on model specification)
-  Periodicity shifts (requires augmented state model)

**Limitations:**
- Requires accurate process model; network traffic is highly non-stationary and model misspecification is the norm, not the exception [13]
- Parameter estimation (Q, R) from short windows is unreliable — the EM algorithm for KF parameter learning requires large N [12]
- Adds conceptual and implementation complexity beyond what the detection task warrants given simpler alternatives

**Verdict:** While streaming-compatible, the Kalman Filter's reliance on accurate model specification makes it brittle for non-stationary network traffic without substantial engineering effort. Simpler alternatives (EWMA, CUSUM) achieve comparable detection with far less complexity. **Rejected — not on hard theoretical grounds, but on practical fitness grounds: complexity-to-benefit ratio is unfavorable given the project's constraints and goals.**

---

### 3.10 Matrix Profile

**Principle:**  
The Matrix Profile (MP) is a data structure that stores, for every subsequence in a time series, the distance to its nearest neighbor (most similar subsequence) elsewhere in the series. It enables efficient motif discovery, discord detection (anomalies = subsequences with large nearest-neighbor distance), and segmentation [14].

Computation relies on the STOMP or SCRIMP algorithms using z-normalized Euclidean distance:

```
MP[i] = min_{j: |i-j| > m} dist(T[i:i+m], T[j:j+m])
```

**Short-Window Behavior — Fundamental Constraint:**  
The Matrix Profile requires a minimum of 2m samples (where m is the subsequence length) to have at least one valid comparison pair. For meaningful anomaly detection via discord discovery, substantially more samples are needed. The complexity of computing MP is O(N² log N) time — applied to the full time series, not a single sample [14].

More critically: the Matrix Profile is a **batch algorithm**. It processes an entire time series at once. While incremental variants exist (e.g., STAMP), they still require maintaining an O(N) data structure and performing O(N) work per new sample. This directly violates the project's streaming, O(1)-per-sample constraint.

At N = 10–50 total samples, the Matrix Profile has insufficient data to find meaningful nearest-neighbor pairs — the statistical concept of "discord" loses meaning when the entire series is 10 points long [14].

**Verdict:** Fundamentally unsuitable for short windows and streaming on-device processing. The algorithm is designed for long time series batch analysis on server hardware. **Rejected on theoretical grounds: batch nature, O(N²) complexity, and statistical invalidity at N = 10–50.**

---

### 3.11 Spectral Residual

**Principle:**  
Spectral Residual (SR) is based on the visual saliency model from computer vision, applied to time-series anomaly detection. It computes the FFT of the series, estimates the average log spectrum, subtracts it, and transforms back to get a "saliency map" — points with high saliency are anomalies [15]:

```
1. Compute log amplitude: A = log(|FFT(x)|)
2. Compute average log spectrum: AL = mean_filter(A)
3. Spectral residual: SR = A - AL
4. Saliency map: S = IFFT(exp(SR + i * phase))^2
```

**Short-Window Behavior — Fundamental Constraint:**  
FFT-based methods have a fundamental resolution constraint: frequency resolution Δf = 1/(N * Δt). At N = 10 samples, only 5 unique frequency components are available — insufficient to meaningfully characterize the spectral structure of a signal or isolate anomalous components. The saliency computation becomes numerically unstable and statistically unreliable at small N [15][16].

Moreover, SR was designed for long univariate time-series (Microsoft's SR-CNN paper used window sizes of 256+ points [15]). The "average log spectrum" estimation via mean filtering requires sufficient frequency resolution to produce a meaningful smoothed reference.

**Verdict:** Theoretically invalid at N = 10–50. Spectral analysis requires N >> 50 to provide meaningful frequency resolution. The FFT of 10–50 samples cannot reliably distinguish anomalous spectral components from noise. **Rejected on theoretical grounds: frequency resolution constraint and batch FFT requirement.**

---

### 3.12 SAX / HOT SAX

**Principle:**  
Symbolic Aggregate approXimation (SAX) converts a time series into a symbolic (string) representation by: (1) normalizing the series, (2) applying Piecewise Aggregate Approximation (PAA) to reduce dimensionality, and (3) mapping PAA coefficients to symbols using Gaussian distribution breakpoints [17].

HOT SAX extends SAX for discord (anomaly) discovery: it searches for the subsequence whose nearest neighbor (in SAX symbolic space) is farthest away — the most unusual subsequence [17].

**Short-Window Behavior — Fundamental Constraint:**  
SAX requires z-normalization of each subsequence. At short lengths (N < 20 per subsequence), z-normalization is statistically unreliable — a subsequence of 10 points with near-zero variance will normalize to a flat or numerically unstable representation [17]. The PAA step further reduces dimensionality (e.g., a subsequence of 10 reduced to 3–5 symbols), discarding most temporal information.

HOT SAX's discord discovery relies on comparing many subsequences to find the most anomalous one. With a total series of 10–50 points, there are too few subsequences for the approach to be meaningful — the combinatorial search space collapses.

Furthermore, SAX is a batch representation method, not a streaming anomaly detector. It builds a symbolic representation of a complete series before analysis begins.

**Verdict:** Theoretically unsuitable for this project's window sizes. SAX/HOT SAX was designed for long time-series discord discovery (original paper used N = 1000+ [17]). Z-normalization instability at small N and the batch nature of the approach make it incompatible with on-device streaming detection. **Rejected on theoretical grounds: statistical instability at small N and batch processing requirement.**

---

### 3.13 ARIMA (AutoRegressive Integrated Moving Average)

**Principle:**  
ARIMA is a classical time-series forecasting model that predicts future values based on past observations and past errors. It combines three components:

- AutoRegression (AR): dependence on previous values  
- Integration (I): differencing to achieve stationarity  
- Moving Average (MA): dependence on past errors  
```
x_t = Σ (φ_i * x_{t-i}) + Σ (θ_j * ε_{t-j}) + ε_t
```


**Short-Window Behavior — Fundamental Constraint:**  
ARIMA requires a sufficiently long historical sequence to estimate its parameters (φ, θ). Parameter estimation is typically done using maximum likelihood or least squares, which requires **hundreds of samples for stable estimation**. At N = 10–50, the model is underdetermined and produces unreliable forecasts.

Additionally, ARIMA assumes **stationarity**, which is rarely true for network telemetry due to bursty and non-stationary traffic patterns.

**Streaming Compatibility:**  
Limited. While incremental variants exist, standard ARIMA is **batch-oriented**, requiring model re-fitting as new data arrives.

**Memory Footprint:**  
O(p + q) parameters plus historical values. Moderate.

**Detects:**
- Forecast deviations (indirect anomaly detection)
- Long-term trends (if properly trained)

**Limitations:**
- Requires large training data
- High computational cost (model fitting)
- Not suitable for real-time streaming
- Assumes stationarity
- Poor performance under short observation windows


**Verdict:**  
ARIMA is unsuitable for this project due to its reliance on large datasets, batch processing, and high computational overhead. The short-window constraint (N = 10–50) fundamentally prevents reliable parameter estimation.  
**Rejected on theoretical and practical grounds.**

---

### 3.14 PELT (Pruned Exact Linear Time)

**Principle:**  
PELT is an optimal change-point detection algorithm that partitions a time series into segments such that each segment has consistent statistical properties (e.g., mean or variance). It minimizes a global cost function with a penalty for adding change points:
```
min Σ [C(segment)] + β * (# of change points)
```

Dynamic programming with pruning ensures near-linear time complexity.


**Short-Window Behavior — Fundamental Constraint:**  
PELT requires sufficient data to identify statistically meaningful segments. At N = 10–50, there are too few samples to form reliable segments, and the cost function becomes unstable. The algorithm may either over-segment (false positives) or fail to detect real changes.


**Streaming Compatibility:**  
No. PELT is inherently a **batch algorithm** that processes the entire time series to compute optimal segmentation.


**Memory Footprint:**  
O(N) — requires storing the full sequence and dynamic programming tables.


**Detects:**
- Change points (mean/variance shifts)
- Structural breaks


**Limitations:**
- Requires full data sequence (non-streaming)
- Computational overhead higher than lightweight methods
- Not reliable for very short sequences
- Requires penalty parameter tuning


**Verdict:**  
PELT is theoretically optimal for change-point detection but incompatible with streaming constraints and short window sizes.  
**Rejected on theoretical grounds: batch nature and insufficient data for segmentation.**

---

### 3.15 Binary Segmentation

**Principle:**  
Binary Segmentation is a recursive change-point detection algorithm. It identifies a change point in the full series, splits the series at that point, and recursively applies the same procedure to subsegments.


**Short-Window Behavior:**  
Binary Segmentation performs better than PELT under limited data but still requires enough samples to identify statistically significant splits. At N = 10–50, detection reliability is limited and sensitive to noise.


**Streaming Compatibility:**  
No. It operates on a **fixed batch of data** and does not support incremental updates.


**Memory Footprint:**  
O(N) — requires storing the full window.


**Detects:**
- Sudden rate changes (step changes)
- Structural breaks


**Limitations:**
- Not streaming-friendly
- Sensitive to noise (high false positives)
- Requires sufficient data for reliable splits
- May miss subtle changes or detect spurious ones


**Verdict:**  
Binary Segmentation is simpler than PELT but still not suitable for real-time on-device telemetry analytics due to its batch nature and limited reliability at small window sizes.  
**Rejected on practical grounds.**

---
---

## 4. Comparative Summary

| Algorithm | Min Viable N | Streaming | Memory | Anomaly Types | Verdict |
|---|---|---|---|---|---|
| **Z-Score** | ~15 |  O(1) | Negligible | Spikes, transients |  Selected |
| **MAD** | ~10 |  O(N) | O(N) ~200B | Spikes, transients |  Selected |
| **EWMA** | Any |  O(1) | Negligible | Spikes, shifts, transients |  Selected |
| **CUSUM** | Any |  O(1) | Negligible | Shifts, bursts, transients |  Selected |
| **Page-Hinkley** | Any |  O(1) | Negligible | Shifts, gradual drift |  Selected |
| **Sliding Window Stats** | 10 |  O(1)* | O(N) ~200B | All (as features) |  Selected |
| **ADWIN** | ~200+ |  | Variable | Distribution shift |  Rejected |
| **DDM** | ~500+ |  | Negligible | Classifier drift only |  Rejected |
| **Kalman Filter** | Any |  O(1) | Negligible | Transients, spikes | Rejected |
| **Matrix Profile** | ~1000+ |  Batch | O(N) | Motifs, discords |  Rejected |
| **Spectral Residual** | ~256+ |  Batch | O(N) | Spectral anomalies |  Rejected |
| **SAX / HOT SAX** | ~500+ | Batch | O(N) | Discords |  Rejected |
| **ARIMA** | ~100+ |  | Moderate | Forecast-based anomalies |  Rejected |
| **PELT** | ~100+ |  | O(N) | Change points |  Rejected |
| **Binary Segmentation** | ~50+ |  | O(N) | Step changes |  Rejected |

*With augmented deque structure for O(1) min/max

---

## 5. Conclusion: Selection & Rejection Rationale

### 5.1 Algorithms Selected for Phase 2 Experimentation

The following six algorithms are carried forward for empirical evaluation in Phase 2. They share three properties: (1) theoretical validity at N = 10–50 samples, (2) streaming/incremental operation compatible with on-device deployment, and (3) a resource profile consistent with the project's memory and compute constraints.

| Algorithm | Primary Role in Phase 2 |
|---|---|
| **EWMA** | Baseline smoothing + spike/shift detection via control chart |
| **CUSUM** | Change-point and sustained rate-shift detection |
| **Page-Hinkley** | Gradual drift detection; comparison with CUSUM |
| **Z-Score** | Baseline spike detection; lightweight reference method |
| **MAD** | Robust spike detection for heavy-tailed/bursty traffic |
| **Sliding Window Statistics** | Feature extraction primitive for derived detectors |

These algorithms form two natural layers that may be combined in Phase 2: (1) a **baseline tracking layer** (EWMA, Sliding Window Stats) and (2) a **change detection layer** (CUSUM, Page-Hinkley, Z-Score, MAD).

### 5.2 Algorithms Rejected — Theoretical Grounds

The following algorithms are excluded without requiring empirical testing. In each case, a theoretical property — independent of dataset characteristics — makes the algorithm incompatible with the project's constraints.

---

**ADWIN** — *Rejected: Minimum sample requirement exceeds project window*

ADWIN's change detection mechanism is grounded in Hoeffding's inequality, which bounds the probability that the sample mean deviates from the true mean. The bound tightens as N grows. For ADWIN to reliably detect a distribution shift, each sub-window must contain enough samples for the Hoeffding bound to be informative. At total N = 10–50, splitting the window produces sub-windows of N = 5–25, where the Hoeffding bound is too loose to distinguish real changes from random variation [9][10]. ADWIN was designed and validated on streams of thousands to millions of samples — its adaptive windowing mechanism is meaningless at the scale of this project.

*Reference: Bifet & Gavalda (2007). "Learning from time-changing data with adaptive windowing." SIAM SDM.*

---

**DDM (Drift Detection Method)** — *Rejected: Domain mismatch and statistical requirement*

DDM operates on binary error signals from a classification model — it monitors whether a classifier's prediction error rate is increasing over time. This project has no classifier and generates no binary error signal; telemetry data is continuous-valued. Adapting DDM by thresholding continuous data into binary outcomes reduces it to a cruder form of threshold detection, eliminating its statistical basis entirely. Furthermore, DDM requires hundreds of samples to estimate stable error rate statistics [11]. Both the domain mismatch and the sample-size requirement disqualify it.

*Reference: Gama et al. (2004). "Learning with drift detection." SBIA.*

---

**Kalman Filter** — *Rejected: Model specification infeasibility under project constraints*

While the Kalman Filter is technically streaming-compatible and O(1) in the scalar case, its performance depends critically on accurate specification of process noise Q and measurement noise R. For non-stationary network traffic, these parameters are unknown and time-varying. Estimating them reliably requires either large historical datasets or an expectation-maximization (EM) procedure — both incompatible with the project's short-window, on-device constraint. An incorrectly specified Kalman Filter diverges or underperforms simpler alternatives [12][13]. Given that EWMA and CUSUM achieve equivalent or better detection with no model specification burden, the Kalman Filter offers no practical advantage here.

*Reference: Welch & Bishop (1995). "An introduction to the Kalman filter." UNC Chapel Hill TR.*

---

**Matrix Profile** — *Rejected: Batch algorithm with O(N²) complexity*

The Matrix Profile is fundamentally a batch algorithm. Computing the profile requires all-pairs distance computation between subsequences — O(N² log N) time over the full series [14]. Incremental variants still require O(N) work per new sample, violating the O(1) per-sample constraint. At N = 10–50, there are insufficient subsequence pairs for the discord concept to be statistically meaningful — the "most unusual subsequence" in a 50-point series is not comparable to anomaly detection in the thousands-of-points context for which MP was designed.

*Reference: Yeh et al. (2016). "Matrix profile I: All pairs similarity joins for time series." IEEE ICDM.*

---

**Spectral Residual** — *Rejected: FFT frequency resolution constraint*

The FFT of a signal of length N produces N/2 unique frequency components with resolution Δf = 1/(N·Δt). At N = 10, only 5 frequency components are available — the spectrum cannot distinguish meaningful frequency structure from noise. Spectral Residual relies on subtracting a smoothed log-spectrum to isolate anomalous frequency components; this operation is numerically unreliable and statistically invalid at such coarse resolution [15][16]. The method was developed and validated on time series of 256–1024+ points.

*Reference: Ren et al. (2019). "Time-series anomaly detection service at Microsoft." KDD.*

---

**SAX / HOT SAX** — *Rejected: z-normalization instability and batch nature*

SAX requires z-normalization of subsequences before symbolic encoding. At subsequence lengths of 10 or fewer, near-constant subsequences produce near-zero standard deviations, causing numerical instability or degenerate normalizations [17]. HOT SAX's discord discovery requires comparing many subsequences — a combinatorial search that collapses to triviality at total N = 10–50. SAX was designed for long time-series (original evaluation on N = 1000–100,000 points). Its symbolic representation provides no benefit at the scale of this project and introduces unnecessary complexity.

*Reference: Lin et al. (2007). "Experiencing SAX: A novel symbolic representation of time series." DAMI.*

---

**ARIMA (AutoRegressive Integrated Moving Average)** — *Rejected: Parameter estimation infeasibility under short-window constraint*

ARIMA models require estimation of autoregressive (AR) and moving-average (MA) coefficients using methods such as maximum likelihood. These estimators rely on sufficiently large sample sizes. At N = 10–50, the parameter estimation becomes unstable and often non-identifiable.

Additionally, ARIMA assumes stationarity in the underlying process. Network telemetry signals are highly non-stationary, and such short windows are insufficient to validate or enforce stationarity.

ARIMA fitting is iterative and computationally expensive, making it incompatible with the O(1) per-sample requirement of on-device processing.

*Reference: Box, G. E. P., Jenkins, G. M., Reinsel, G. C., & Ljung, G. M. (2015). "Time Series Analysis: Forecasting and Control." Wiley.*

---

**PELT (Pruned Exact Linear Time)** — *Rejected: Global optimization requirement incompatible with streaming and short windows*

PELT detects change points by minimizing a global cost function over all possible segmentations of the time series using dynamic programming.

The method requires access to the full sequence and sufficient data to estimate segment statistics reliably. At N = 10–50, segment sizes are too small for stable estimation, leading to unreliable change detection.

PELT is inherently a batch algorithm, as each new sample can alter the optimal segmentation, making it unsuitable for streaming or incremental processing.

*Reference: Killick, R., Fearnhead, P., & Eckley, I. A. (2012). "Optimal detection of changepoints with a linear computational cost." Journal of the American Statistical Association.*

---

**Binary Segmentation** — *Rejected: Recursive segmentation instability under small-sample and high-noise conditions*

Binary Segmentation detects change points by recursively splitting the time series based on statistical tests.

At N = 10–50, recursive splitting quickly produces very small segments, where statistical estimates become unreliable. This leads to either over-segmentation due to noise or missed detections due to insufficient data.

The method also requires repeated scans of the full window, making it incompatible with strict streaming constraints.

*Reference: Scott, A. J., & Knott, M. (1974). "A cluster analysis method for grouping means in the analysis of variance." Biometrics.*

---

### 5.3 Detection Coverage of Selected Algorithms

| Network Condition | Primary Algorithm | Supporting Algorithm |
|---|---|---|
| Burst traffic | Z-Score / MAD | EWMA control chart |
| Sudden rate change | CUSUM | Page-Hinkley |
| Gradual drift | Page-Hinkley | EWMA |
| Transient anomaly (1–3 samples) | Z-Score / MAD | Sliding Window max |
| Periodicity shift | Sliding Window variance | EWMA variance |

---

## 6. References

[1] Grubbs, F.E. (1969). "Procedures for detecting outlying observations in samples." *Technometrics*, 11(1), 1–21.

[2] Welford, B.P. (1962). "Note on a method for calculating corrected sums of squares and products." *Technometrics*, 4(3), 419–420.

[3] Leland, W.E. et al. (1994). "On the self-similar nature of Ethernet traffic." *IEEE/ACM Transactions on Networking*, 2(1), 1–15.

[4] Rousseeuw, P.J. & Croux, C. (1993). "Alternatives to the median absolute deviation." *Journal of the American Statistical Association*, 88(424), 1273–1283.

[5] Roberts, S.W. (1959). "Control chart tests based on geometric moving averages." *Technometrics*, 1(3), 239–250.

[6] Page, E.S. (1954). "Continuous inspection schemes." *Biometrika*, 41(1/2), 100–115.

[7] Page, E.S. (1955). "A test for a change in a parameter occurring at an unknown point." *Biometrika*, 42(3/4), 523–527.

[8] Lemire, D. (2006). "Streaming maximum-minimum filter using no more than three comparisons per element." *Nordic Journal of Computing*, 13(4), 328–339.

[9] Bifet, A. & Gavalda, R. (2007). "Learning from time-changing data with adaptive windowing." *Proceedings of SIAM SDM*, 443–448.

[10] Hoeffding, W. (1963). "Probability inequalities for sums of bounded random variables." *Journal of the American Statistical Association*, 58(301), 13–30.

[11] Gama, J. et al. (2004). "Learning with drift detection." *Proceedings of SBIA*, LNAI 3171, 286–295.

[12] Welch, G. & Bishop, G. (1995). "An introduction to the Kalman filter." *UNC Chapel Hill TR 95-041*.

[13] Jazwinski, A.H. (1970). *Stochastic Processes and Filtering Theory*. Academic Press.

[14] Yeh, C.C.M. et al. (2016). "Matrix profile I: All pairs similarity joins for time series: A unifying view that includes motifs, discords and shapelets." *IEEE ICDM*, 1317–1322.

[15] Ren, H. et al. (2019). "Time-series anomaly detection service at Microsoft." *Proceedings of ACM KDD*, 3009–3017.

[16] Harris, F.J. (1978). "On the use of windows for harmonic analysis with the discrete Fourier transform." *Proceedings of the IEEE*, 66(1), 51–83.

[17] Lin, J. et al. (2007). "Experiencing SAX: A novel symbolic representation of time series." *Data Mining and Knowledge Discovery*, 15(2), 107–144.

[18] Box, G.E.P., Jenkins, G.M., Reinsel, G.C., & Ljung, G.M. (2015). *Time Series Analysis: Forecasting and Control*. Wiley.

[19] Hamilton, J.D. (1994). *Time Series Analysis*. Princeton University Press.

[20] Killick, R., Fearnhead, P., & Eckley, I.A. (2012). "Optimal detection of changepoints with a linear computational cost." *Journal of the American Statistical Association*, 107(500), 1590–1598.

[21] Scott, A.J. & Knott, M. (1974). "A cluster analysis method for grouping means in the analysis of variance." *Biometrics*, 30(3), 507–512.

[22] Fryzlewicz, P. (2014). "Wild binary segmentation for multiple change-point detection." *Annals of Statistics*, 42(6), 2243–2281.

---

*Document prepared for Phase 1 of the project "Evaluate and Compare Lightweight Time-Series Techniques for Network Telemetry Using Short Observation Windows." Algorithms marked as selected will be implemented, benchmarked and empirically evaluated in Phase 2.*
