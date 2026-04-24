# Phase 2 — Complete Documentation

**Project:** On-Device Network Telemetry Analytics
**Sub-title:** Evaluate and Compare Lightweight Time-Series Techniques for Network Telemetry
**Phase:** 2 — Implementation & Benchmarking
**Iteration:** 2
**Dataset:** CESNET-TimeSeries24 (`ip_addresses_sample`, 10-minute aggregation)
**Language:** Python 3.10+
**Team Size:** 6
**Sponsor:** HP CPP Internship

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Tech Stack & Dependencies](#3-tech-stack--dependencies)
4. [Repository Layout](#4-repository-layout)
5. [Configuration (`config.py`)](#5-configuration-configpy)
6. [How to Run](#6-how-to-run)
7. [Iteration 1 → Iteration 2 Changes](#7-iteration-1--iteration-2-changes)
8. [Team Roles & Responsibilities](#8-team-roles--responsibilities)
9. [Module-by-Module Documentation](#9-module-by-module-documentation)
   - [9.1 Person 1 — Arthi — Data Pipeline](#91-person-1--arthi--data-pipeline)
   - [9.2 Person 2 — Madhan — Anomaly Injector](#92-person-2--madhan--anomaly-injector)
   - [9.3 Person 3 — Kishore — Z-Score & MAD Detectors](#93-person-3--kishore--z-score--mad-detectors)
   - [9.4 Person 4 — Denistan — EWMA & Sliding Window Stats](#94-person-4--denistan--ewma--sliding-window-stats)
   - [9.5 Person 5 — Ambika — CUSUM & Page-Hinkley](#95-person-5--ambika--cusum--page-hinkley)
   - [9.6 Person 6 — Alice — Evaluation Harness, Metrics & Visualisation](#96-person-6--alice--evaluation-harness-metrics--visualisation)
10. [The Integration Contract](#10-the-integration-contract)
11. [Testing Strategy](#11-testing-strategy)
12. [Outputs Produced](#12-outputs-produced)
13. [Interactive HTML Dashboard](#13-interactive-html-dashboard)
14. [Key Findings & Architecture Recommendation for Phase 3](#14-key-findings--architecture-recommendation-for-phase-3)
15. [Glossary](#15-glossary)
16. [References](#16-references)

---

## 1. Project Overview

Phase 2 empirically evaluates **6 lightweight time-series anomaly detection algorithms** on real ISP network telemetry to determine which techniques are best suited for on-device deployment in Phase 3.

### Goals

- Implement six classical, low-overhead detectors with a uniform interface.
- Inject **controlled synthetic anomalies** into clean baseline traffic so that ground-truth labels exist for every trial.
- Run a full benchmark grid (4 window sizes × 4 anomaly types × 6 detectors × 30 trials = **2,880 detector evaluations**) and produce reproducible CSV + plot artefacts.
- Justify a two-layer Phase 3 detection pipeline based on measured TPR / FPR / F1 / latency.

### Scope (what is and isn't covered)

| In scope | Out of scope |
|----------|--------------|
| Per-IP univariate detection on `n_bytes` | Multivariate / cross-feature fusion |
| Window sizes 10–50 samples | Long-window or batch-trained models |
| Stationary baseline + injected anomalies | Detection of in-the-wild unlabeled anomalies |
| O(1) / O(N) detectors only | Deep learning, transformers, autoencoders |
| Python research implementation | C++ on-device port (Phase 3) |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              main.py                                │
│              (CLI entry — parses args, runs harness)                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
   ┌──────────────────────┐         ┌──────────────────────┐
   │  src/pipeline/       │         │  src/evaluation/     │
   │  loader.py           │         │  harness.py          │
   │  window_buffer.py    │         │  metrics.py          │
   │  (Person 1 – Arthi)  │         │  visualise.py        │
   └──────────┬───────────┘         │  plots.py            │
              │                     │  (Person 6 – Alice)  │
              ▼                     └──────────┬───────────┘
   ┌──────────────────────┐                    │
   │  src/injector/       │                    │
   │  anomaly_injector.py │◄───────────────────┤
   │  (Person 2 – Madhan) │                    │
   └──────────────────────┘                    │
                                               ▼
                  ┌────────────────────────────────────────┐
                  │             src/detectors/             │
                  │  ┌──────────────────────────────────┐  │
                  │  │  base.py  (DetectorBase contract)│  │
                  │  └──────────────────────────────────┘  │
                  │  ┌──────────────┬──────────────────┐   │
                  │  │ zscore.py    │ mad.py           │   │
                  │  │ (Kishore – P3)                  │   │
                  │  ├──────────────┼──────────────────┤   │
                  │  │ ewma.py      │ sliding_win…py   │   │
                  │  │ (Denistan – P4)                 │   │
                  │  ├──────────────┼──────────────────┤   │
                  │  │ cusum.py     │ page_hinkley.py  │   │
                  │  │ (Ambika – P5)                   │   │
                  │  └──────────────┴──────────────────┘   │
                  └────────────────────────────────────────┘
                                  │
                                  ▼
                  ┌────────────────────────────────────────┐
                  │  results/csv/  +  results/plots/       │
                  │  +  results/dashboard.html             │
                  └────────────────────────────────────────┘
```

**Data flow for one trial:**
`loader.py` → cleans + normalises CESNET CSV → `anomaly_injector.py` injects controlled anomaly → `harness.py` runs each detector sample-by-sample via `DetectorBase.run_on_series()` → `metrics.py` computes TPR/FPR/F1/latency vs ground truth labels → results written to CSV → `visualise.py` and `dashboard/generate_report.py` render plots.

---

## 3. Tech Stack & Dependencies

| Layer | Tool | Version | Purpose |
|-------|------|---------|---------|
| Language | Python | 3.10+ | All code |
| Numerics | NumPy | ≥1.24 | Vector ops, RNG, statistics |
| Tabular I/O | pandas | ≥2.0 | CSV load/aggregation |
| Stats helpers | SciPy | ≥1.11 | Reference implementations |
| Static plots | Matplotlib + Seaborn | ≥3.7 / ≥0.12 | PNG plots in `results/plots/` |
| Interactive dashboard | Plotly | ≥5.18 | `results/dashboard.html` |
| Test runner | Pytest | ≥7.4 | Unit + contract tests |
| Notebooks | Jupyter | ≥1.0 | EDA |
| Progress UI | tqdm | ≥4.66 | Live progress bar in harness |

Source: [requirements.txt](../requirements.txt).

---

## 4. Repository Layout

```
network_telemetry_phase2/
├── data/                        # CESNET CSVs (placed by user — see root README)
├── src/
│   ├── pipeline/                # Person 1 – Arthi
│   │   ├── loader.py
│   │   └── window_buffer.py
│   ├── injector/                # Person 2 – Madhan
│   │   └── anomaly_injector.py
│   ├── detectors/
│   │   ├── base.py              # Integration contract (shared)
│   │   ├── zscore.py            # Person 3 – Kishore
│   │   ├── mad.py               # Person 3 – Kishore
│   │   ├── ewma.py              # Person 4 – Denistan
│   │   ├── sliding_window_stats.py  # Person 4 – Denistan
│   │   ├── cusum.py             # Person 5 – Ambika
│   │   └── page_hinkley.py      # Person 5 – Ambika
│   └── evaluation/              # Person 6 – Alice
│       ├── harness.py
│       ├── metrics.py
│       ├── plots.py
│       └── visualise.py
├── tests/
│   ├── test_pipeline.py         # 14 tests for WindowBuffer
│   ├── test_injector.py         # 19 tests for 4 injection types
│   └── test_detectors.py        # 35+ tests across all 6 detectors + base contract
├── dashboard/
│   └── generate_report.py       # Interactive Plotly HTML dashboard
├── results/
│   ├── csv/                     # raw_trial_results.csv, aggregated_results.csv
│   ├── plots/                   # 8 matplotlib PNGs
│   └── dashboard.html           # 6-chart interactive report
├── docs/
│   └── PHASE_2_DOCUMENTATION.md # ← this file
├── main.py                      # Single CLI entry point
├── config.py                    # All tunable parameters
└── requirements.txt
```

---

## 5. Configuration (`config.py`)

All tunable parameters are centralised — modules never hard-code values. See [config.py](../config.py).

| Section | Parameter | Iter 2 value | Notes |
|---------|-----------|--------------|-------|
| Paths | `DATA_DIR` | `data/ip_addresses_sample/agg_10_minutes` | CESNET 10-min aggregation |
| Paths | `RESULTS_CSV_DIR` | `results/csv` | Output |
| Paths | `RESULTS_PLT_DIR` | `results/plots` | Output |
| Run id | `ITERATION` | `2` | Used for plot titles + filenames |
| Signal | `PRIMARY_SIGNAL` | `n_bytes` | Default monitored feature |
| Signal | `EXTRA_SIGNALS` | `n_packets`, `average_n_dest_ip`, `tcp_udp_ratio_packets` | Future use |
| Sweep | `WINDOW_SIZES` | `[10, 20, 30, 50]` | Detector window N |
| Sweep | `ANOMALY_TYPES` | `["burst","rate_shift","gradual_drift","transient"]` | All 4 injection types |
| Sweep | `MAX_IPS` | `100` | Max series loaded |
| Stats | `N_TRIALS` | **30** (was 10) | ↑ to tighten CIs |
| Stats | `RANDOM_SEED` | `42` | Reproducibility |
| Stats | `MIN_BASELINE_SAMPLES` | `60` | Required pre-injection context |
| Detection | `DETECTION_WINDOW` | `5` | Latency budget after `inject_start` |
| Plot | `PLOT_DPI` / `PLOT_FORMAT` | `150` / `png` | |

### Per-detector defaults (Iteration 2)

```python
DETECTORS = {
  "zscore":         {"threshold": 3.0},
  "mad":            {"threshold": 3.5},
  "ewma":           {"lambda_": 0.2,  "L": 3.5},      # L: 3.0 → 3.5
  "cusum":          {"k": 0.5,        "h": 3.5},      # h: 5.0 → 3.5
  "page_hinkley":   {"delta": 0.5,    "lambda_": 12.0,
                     "alpha": 0.9999},                # λ: 50.0 → 12.0
  "sliding_window": {"stat": "mean",  "threshold": 3.0},
}
```

### Per-anomaly injection defaults (Iteration 2)

```python
INJECTION = {
  "burst":         {"magnitude": 5.0, "duration":  5},  # duration: 3 → 5
  "rate_shift":    {"magnitude": 3.0, "duration": 20},
  "gradual_drift": {"slope": 0.3,     "duration": 20},  # slope: 0.2 → 0.3,
                                                        # duration: 15 → 20
  "transient":     {"magnitude": 6.0},                  # always 1 sample
}
```

---

## 6. How to Run

### Setup

```bash
cd network_telemetry_phase2
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Place data

Download `ip_addresses_sample.tar.gz` from <https://zenodo.org/records/13382427>, extract, and put the per-IP CSVs in `data/ip_addresses_sample/agg_10_minutes/`. See the root [README.md](../../README.md) for schema details and dataset notes.

### Run full evaluation

```bash
python main.py
```

Optional CLI flags ([main.py:15-33](../main.py#L15-L33)):

| Flag | Effect |
|------|--------|
| `--signal n_packets` | Override `PRIMARY_SIGNAL` |
| `--max_ips 50` | Limit IP series loaded |
| `--no_plot` | Skip matplotlib plots |
| `--no_dashboard` | Skip HTML dashboard |
| `--iter1_csv path/to/iter1/aggregated_results.csv` | Generate Iter1-vs-Iter2 comparison plots |

### Run tests

```bash
pytest tests/ -v
```

### Generate dashboard standalone

```bash
python dashboard/generate_report.py
```

---

## 7. Iteration 1 → Iteration 2 Changes

Source-of-truth: header comment in [config.py:1-41](../config.py#L1-L41).

| Parameter | Iter 1 | Iter 2 | Reason |
|-----------|-------|--------|--------|
| `N_TRIALS` | 10 | **30** | Iter1 std deviation often exceeded the mean (e.g. CUSUM burst σ=0.44, μ=0.33). 30 trials cuts the standard error of the mean by ~45%. |
| CUSUM `h` | 5.0 | **3.5** | Burst lasts only 3–5 samples — accumulated deviation rarely reached 5.0. h=3.5 keeps FPR < 10% while giving CUSUM a fair shot at short anomalies. |
| Page-Hinkley `λ` | 50.0 | **12.0** | λ=50 was effectively random (TPR=0.10 on burst). On a 280-sample series the PH statistic accumulates to ~8–12 under H0 — λ=12 is the principled boundary. |
| EWMA `L` | 3.0 | **3.5** | FPR was 27–43% in Iter1. Widening the control band by ½σ projects FPR down to ~15% while losing only ~5% TPR on rate shift. |
| Burst `duration` | 3 | **5** | Accumulation detectors (CUSUM, PH) need consecutive samples to build evidence. |
| Drift `slope` / `duration` | 0.2 / 15 | **0.3 / 20** | All detectors had < 45% TPR on gradual drift in Iter1 — drift was sub-σ relative to baseline noise. |
| MAD / Z-Score / injection magnitudes | unchanged | unchanged | Both detectors performed well. Magnitudes were appropriate. |

---

## 8. Team Roles & Responsibilities

| # | Person | Module owned | Files |
|---|--------|--------------|-------|
| 1 | **Arthi** | Data Pipeline | `src/pipeline/loader.py`, `src/pipeline/window_buffer.py` |
| 2 | **Madhan** | Anomaly Injector | `src/injector/anomaly_injector.py` |
| 3 | **Kishore** | Detectors A — sliding-window spike | `src/detectors/zscore.py`, `src/detectors/mad.py` |
| 4 | **Denistan** | Detectors B — baseline trackers | `src/detectors/ewma.py`, `src/detectors/sliding_window_stats.py` |
| 5 | **Ambika** | Detectors C — change-point detectors | `src/detectors/cusum.py`, `src/detectors/page_hinkley.py` |
| 6 | **Alice** | Evaluation Harness + Metrics + Visualisation | `src/evaluation/harness.py`, `src/evaluation/metrics.py`, `src/evaluation/visualise.py`, `src/evaluation/plots.py`, `main.py` |

**Cross-cutting shared assets** (locked Week 1, no unilateral changes):

- [src/detectors/base.py](../src/detectors/base.py) — `DetectorBase` abstract class + `DetectionResult` dataclass.
- [src/pipeline/window_buffer.py](../src/pipeline/window_buffer.py) — `WindowBuffer` shared by Z-Score, MAD, Sliding Window Stats.

---

## 9. Module-by-Module Documentation

### 9.1 Person 1 — Arthi — Data Pipeline

**Files:** [src/pipeline/loader.py](../src/pipeline/loader.py), [src/pipeline/window_buffer.py](../src/pipeline/window_buffer.py)
**Role:** Foundation everyone else builds on. Loads CESNET CSVs and provides the streaming statistics buffer.

#### 9.1.1 `loader.py` — CESNET dataset loader

Public function: `load_cesnet_sample(data_dir, signal_col="n_bytes", max_ips=None, min_length=200)`.

**What it does** ([loader.py:42-112](../src/pipeline/loader.py#L42-L112)):

1. Discovers CSVs via `glob` on `data_dir/*.csv`.
2. For each file, calls `_read_cesnet_csv()` with a **3-level encoding fallback**: UTF-8 → latin-1 → cp1252 ([loader.py:122-140](../src/pipeline/loader.py#L122-L140)). This prevents silent data loss on Windows where CESNET files can fail the default UTF-8 decoder.
3. Detects header presence by counting columns and checking the marker set `{"n_bytes","n_packets","n_flows"}`. If the column count matches `CESNET_COLUMNS` but no marker exists, it re-reads with explicit `names=`.
4. Extracts `signal_col`, drops NaN/inf samples, **skips series shorter than 200 samples** (cannot support meaningful injection).
5. Applies `_normalize()` — zero-mean unit-variance using the series' own statistics ([loader.py:143-148](../src/pipeline/loader.py#L143-L148)). All detectors then operate on the same numeric scale regardless of whether the raw signal is bytes, packets, or ratios.

**CESNET column schema** ([loader.py:13-33](../src/pipeline/loader.py#L13-L33)) — handles the *re-aggregated* `ip_addresses_sample` format which expands `n_dest_ip / n_dest_asn / n_dest_port` into `sum_*`, `average_*`, `std_*`.

#### 9.1.2 `window_buffer.py` — fixed-capacity circular buffer

`class WindowBuffer(capacity: int)` — **the integration contract** for every window-based detector.

**Design intent:** mirrors how this would be implemented in C++ on-device ([window_buffer.py:1-13](../src/pipeline/window_buffer.py#L1-L13)):

- Fixed capacity, no dynamic resize.
- O(1) `push()`, O(1) `mean()` / `variance()` via Welford's online algorithm.
- All math in plain Python/NumPy — **no pandas inside the buffer**.

| Operation | Complexity | Implementation |
|-----------|------------|----------------|
| `push(value)` | **O(1)** | Welford add + circular head advance + Welford remove on eviction |
| `mean()` | **O(1)** | Running Welford mean |
| `variance(ddof=1)` | **O(1)** | `M2 / (n - ddof)` |
| `std(ddof=1)` | **O(1)** | `sqrt(variance)` |
| `minimum()` / `maximum()` | O(N) | `np.min` / `np.max` on view — acceptable at N≤50 |
| `median()` | O(N log N) | `np.median` on view |
| `to_array()` | O(N) | Returns oldest-first copy (safe to modify) |
| `is_full()` / `size()` / `capacity` | O(1) | Plain accessors |
| `reset()` | O(1) | Zeros buffer + Welford state |

**Welford add/remove** ([window_buffer.py:159-179](../src/pipeline/window_buffer.py#L159-L179)):
- `_welford_add(v)`: standard online update — `delta=v−μ`, `μ += delta/n`, `M2 += delta·(v−μ_new)`.
- `_welford_remove(v)`: inverse downdate when oldest sample is evicted, with `M2 = max(0, …)` numerical guard.

**API guarantee for downstream owners:** Persons 3, 4, 6 all rely on `push / mean / std / is_full / to_array / reset`. Public surface frozen in Week 1.

---

### 9.2 Person 2 — Madhan — Anomaly Injector

**File:** [src/injector/anomaly_injector.py](../src/injector/anomaly_injector.py)
**Role:** Provides ground truth. CESNET contains real but unlabeled anomalies; controlled injection is what makes TPR/FPR/latency measurable.

#### 9.2.1 `InjectionResult` dataclass ([anomaly_injector.py:17-34](../src/injector/anomaly_injector.py#L17-L34))

| Field | Type | Description |
|-------|------|-------------|
| `signal` | `np.ndarray` | Modified signal (clean baseline + anomaly). |
| `labels` | `np.ndarray (int8)` | 1 inside `[inject_start, inject_end)`, else 0. |
| `inject_start` | `int` | Start index. |
| `inject_end` | `int` | End index (exclusive). |
| `anomaly_type` | `str` | `"burst" | "rate_shift" | "gradual_drift" | "transient"`. |

`inject_start` is what the harness uses to compute **detection latency** = first alarm index − `inject_start`.

#### 9.2.2 The four injection methods

| Method | Formula | Default duration | Default magnitude | Models |
|--------|---------|------------------|-------------------|--------|
| `inject_burst` | `x[i] += magnitude * local_std` for `i ∈ [start, start+duration)` | 5 | 5× local σ | Short traffic spike |
| `inject_rate_shift` | `x[i] += magnitude * local_std` (constant) | 20 | 3× local σ | Step change to new baseline |
| `inject_gradual_drift` | `x[i] += slope * local_std * (i - start + 1)` | 20 | slope 0.3 σ/sample | Slow growing DDoS |
| `inject_transient` | `x[start] += magnitude * local_std` | 1 | 6× local σ | Single-sample anomaly / measurement spike |

#### 9.2.3 Local-σ scaling — why it matters

Magnitude is scaled by the **local** standard deviation from the 30 samples preceding the injection point (`_local_std` at [anomaly_injector.py:248-260](../src/injector/anomaly_injector.py#L248-L260)), with a fallback to global σ if the local segment is near-constant. This makes the injection robust to non-stationary baselines — exactly what CESNET traffic is.

#### 9.2.4 Position selection

`_prepare()` ([anomaly_injector.py:210-246](../src/injector/anomaly_injector.py#L210-L246)) picks the start index from the **middle 50%** of the series (via a seeded `np.random.default_rng`), guaranteeing ≥ 30 clean samples before injection and ≥ 10 after. Series shorter than `60 + duration` raise `ValueError` rather than silently corrupt results.

#### 9.2.5 Dispatcher

`AnomalyInjector.inject(signal, anomaly_type, params)` — string-keyed dispatch used by the harness ([anomaly_injector.py:180-206](../src/injector/anomaly_injector.py#L180-L206)). Unknown types raise with the valid list embedded.

---

### 9.3 Person 3 — Kishore — Z-Score & MAD Detectors

**Files:** [src/detectors/zscore.py](../src/detectors/zscore.py), [src/detectors/mad.py](../src/detectors/mad.py)
**Role:** Sliding-window spike detectors. Same family conceptually but different statistical assumptions.

#### 9.3.1 `ZScoreDetector(window_size, threshold=3.0)` ([zscore.py](../src/detectors/zscore.py))

- Computes `z = (value − μ_window) / σ_window` against the rolling window held in `WindowBuffer`.
- Fires when `|z| > threshold`.
- **Decision-then-push**: `z` is computed *before* the new sample enters the buffer ([zscore.py:48-59](../src/detectors/zscore.py#L48-L59)). This avoids the **masking effect** where a large anomaly inflates σ and hides itself.
- σ ≈ 0 guard: no alarm declared on a perfectly flat window.
- O(1) compute via Welford-backed `WindowBuffer.mean()` / `std()`.

#### 9.3.2 `MADDetector(window_size, threshold=3.5)` ([mad.py](../src/detectors/mad.py))

- Robust Z-score: `0.6745 · (x − median) / MAD` where `MAD = median(|xᵢ − median|)`.
- Constant `0.6745 = Φ⁻¹(0.75)` ([mad.py:32-33](../src/detectors/mad.py#L32-L33)) — Rousseeuw–Croux consistency factor that makes MAD ≈ σ under a Gaussian.
- O(N log N) per sample because it sorts the window for the median; storage O(N) for the window — negligible at N ≤ 50.

#### 9.3.3 Why MAD beats Z-Score on bursts

| Property | Z-Score | MAD |
|----------|---------|-----|
| Centre estimate | mean (sensitive to outliers) | median (robust) |
| Spread estimate | standard deviation | MAD |
| Memory | O(1) via Welford | O(N) — full window stored |
| Compute / sample | O(1) | O(N log N) |
| Iter-1 burst TPR | 57.5% | **89.2%** |
| Iter-1 transient TPR | 92.5% | **95.0%** |
| Iter-1 avg FPR | **4.6%** (lowest) | 14.8% (acceptable) |

**Recommendation**: MAD as the **primary** spike detector; Z-Score as the **low-FPR confirmer**.

---

### 9.4 Person 4 — Denistan — EWMA & Sliding Window Stats

**Files:** [src/detectors/ewma.py](../src/detectors/ewma.py), [src/detectors/sliding_window_stats.py](../src/detectors/sliding_window_stats.py)
**Role:** Baseline trackers — sensitive to **sustained** changes rather than instantaneous spikes.

#### 9.4.1 `EWMADetector(lambda_=0.2, L=3.0, warmup=20)` ([ewma.py](../src/detectors/ewma.py))

- Smoothed statistic: `S_t = λ · x_t + (1−λ) · S_{t−1}`.
- Roberts (1959) control limits: `UCL/LCL = μ₀ ± L · σ₀ · √(λ / (2−λ))`.
- Alarm when `S_t > UCL` or `S_t < LCL`.
- **Warmup** uses Welford to estimate `μ₀, σ₀` from the first `warmup` samples (no alarms emitted) ([ewma.py:34-54](../src/detectors/ewma.py#L34-L54)). Warmup floored at 10.
- Validates `λ ∈ (0, 1)` in `__init__` — invalid raises `ValueError`.
- Iteration 2 increased `L` from 3.0 to 3.5 → control band ½σ wider, FPR drops from ~27% to ~15%.

**Why EWMA dominates rate-shift detection**: μ₀ is **frozen** after warmup, so a sustained step change keeps `S_t` past the UCL indefinitely — alarm persists for the entire shifted region. Z-Score and MAD adapt their window to the new mean within N samples and stop firing.

**Why EWMA misses transients**: λ=0.2 means a single 6σ spike contributes only `0.2·6 = 1.2σ` to `S_t`, while UCL ≈ μ₀ + 1.65σ₀. The spike barely breaches the limit by design.

#### 9.4.2 `SlidingWindowStatsDetector(window_size, stat="mean", threshold=3.0, warmup=30)` ([sliding_window_stats.py](../src/detectors/sliding_window_stats.py))

- Tracks one of `{"mean", "variance", "max"}` over a rolling window using `WindowBuffer`.
- **Two-stage warmup**: first the window must fill, then `warmup + window_size` window-statistics are accumulated to estimate `stat_mean, stat_std` of the statistic itself ([sliding_window_stats.py:54-68](../src/detectors/sliding_window_stats.py#L54-L68)).
- Alarm when `|current_stat − stat_mean| / stat_std > threshold`.
- Harness instantiates with `warmup = max(2 · window_size, 40)` ([harness.py:80](../src/evaluation/harness.py#L80)).
- Includes a `get_stats()` introspection helper returning a dict of `{mean, variance, std, min, max}`.
- Invalid `stat` values raise `ValueError` in `__init__`.

| Property | EWMA | Sliding Window Stats |
|----------|------|----------------------|
| Memory | O(1) | O(N) |
| Baseline | Frozen at warmup (μ₀) | Estimated from warmup-stat sequence |
| Iter-1 rate-shift TPR | **65.4%** (best) | 53.0% |
| Iter-1 avg FPR | 27% → ~15% (Iter 2 with L=3.5) | 25.9% |
| Transient TPR | 32.5% (poor by design) | 30.0% (same weakness) |

---

### 9.5 Person 5 — Ambika — CUSUM & Page-Hinkley

**Files:** [src/detectors/cusum.py](../src/detectors/cusum.py), [src/detectors/page_hinkley.py](../src/detectors/page_hinkley.py)
**Role:** Sequential change-point detectors that **accumulate evidence** before alarming.

#### 9.5.1 `CUSUMDetector(k=0.5, h=3.5, warmup=20)` ([cusum.py](../src/detectors/cusum.py))

- Two accumulators, bidirectional:
  - `C⁺_t = max(0, C⁺_{t−1} + z − k)`
  - `C⁻_t = max(0, C⁻_{t−1} − z − k)`
  - where `z = (x − μ₀) / σ₀`, `k` is the allowable slack.
- Alarm when `max(C⁺, C⁻) > h`. **Both accumulators reset to 0 after each alarm** ([cusum.py:59-61](../src/detectors/cusum.py#L59-L61)) — prevents stale evidence triggering repeated false positives after a real change.
- Warmup builds `μ₀, σ₀` with Welford (no alarms during warmup, ≥ 10).
- Iteration 2 dropped `h` from 5.0 to 3.5 because burst lasts only 3–5 samples — accumulating 5σ of evidence in 3 samples was unrealistic.

**Bidirectional rationale**: network anomalies can be either spikes (DDoS, burst) or drops (link failure). One-sided CUSUM would miss downward anomalies entirely.

#### 9.5.2 `PageHinkleyDetector(delta=0.5, lambda_=12.0, alpha=0.9999, warmup=20)` ([page_hinkley.py](../src/detectors/page_hinkley.py))

- Two PH instances (upward + downward):
  - `PH_t += z − δ` (or `−z − δ`)
  - `M_t = max(M_{t−1}, PH_t)`
  - Alarm when `M_t − PH_t > λ`.
- **Adaptive mean**: `μ ← α·μ + (1−α)·x` with `α = 0.9999` ([page_hinkley.py:67](../src/detectors/page_hinkley.py#L67)) — slowly tracks baseline drift, unlike CUSUM's frozen μ₀.
- Resets only the triggered direction after an alarm ([page_hinkley.py:83-89](../src/detectors/page_hinkley.py#L83-L89)).
- Iteration 2 dropped `λ` from 50 to 12 — a principled value: under H0 on a 280-sample series the PH statistic typically tops out around 8–12, so λ=12 is the boundary between reliable detection and reliable non-detection.

| Property | CUSUM | Page-Hinkley |
|----------|-------|--------------|
| Baseline | Fixed after warmup | Adaptive (`α=0.9999`) |
| Key params (Iter 2) | `k=0.5, h=3.5` | `δ=0.5, λ=12.0` |
| Reset on alarm | Both accumulators | Triggered direction only |
| Iter-1 rate-shift TPR | 42.4% | 27.4% |
| Iter-1 burst TPR | 30.0% (expected to improve in Iter2) | 11.7% (expected to improve in Iter2) |
| Memory | O(1) | O(1) |

**Why accumulation detectors struggle with transients**: a single 6σ z-score gives `C⁺ = 6 − 0.5 = 5.5 > 3.5` and *would* fire — but only if the warmup baseline accurately captured σ₀. In practice, transients can leak into the warmup window depending on placement, depressing accuracy. This is a theoretical limitation, not an implementation bug, and motivates using MAD/Z-Score as primary transient detectors in Phase 3.

---

### 9.6 Person 6 — Alice — Evaluation Harness, Metrics & Visualisation

**Files:** [src/evaluation/harness.py](../src/evaluation/harness.py), [src/evaluation/metrics.py](../src/evaluation/metrics.py), [src/evaluation/visualise.py](../src/evaluation/visualise.py), [src/evaluation/plots.py](../src/evaluation/plots.py), [main.py](../main.py)
**Role:** Orchestrates every experiment, computes metrics, writes artefacts, and renders all plots.

#### 9.6.1 `harness.py` — orchestration

`run_evaluation()` ([harness.py:85-159](../src/evaluation/harness.py#L85-L159)) executes the full grid:

```
for window_size in [10, 20, 30, 50]:                  # 4
    for anomaly_type in ["burst","rate_shift",        # 4
                          "gradual_drift","transient"]:
        for trial in range(30):                        # 30
            pick random IP series → inject anomaly
            for detector in [Z, MAD, EWMA, CUSUM, PH, SW]:  # 6
                run_on_series → predictions → metrics
```

**Total = 4 × 4 × 30 × 6 = 2,880 detector evaluations.** Live progress via `tqdm`.

`build_detectors(window_size)` ([harness.py:39-82](../src/evaluation/harness.py#L39-L82)) instantiates the six detectors with parameters from `config.DETECTORS`. **Warmup floor is enforced**: `warmup = max(window_size, 20)` for EWMA/CUSUM/PH; `max(2·window_size, 40)` for Sliding Window — guarantees a stable baseline regardless of N.

`_sanitise()` ([harness.py:18-36](../src/evaluation/harness.py#L18-L36)) replaces Greek letters (`λ → "lambda"`, `δ → "delta"`, etc.) and Unicode quotes with ASCII before CSV write — prevents `UnicodeEncodeError` under Windows cp1252.

CSV outputs ([harness.py:162-206](../src/evaluation/harness.py#L162-L206)):
- `results/csv/raw_trial_results.csv` — every individual trial.
- `results/csv/aggregated_results.csv` — mean ± std per (detector, anomaly_type, window_size).

#### 9.6.2 `metrics.py` — what we measure

`compute_metrics()` ([metrics.py:56-116](../src/evaluation/metrics.py#L56-L116)) returns an `EvalMetrics` dataclass per trial:

| Metric | Formula | Tells you |
|--------|---------|-----------|
| `tpr` | `TP / (TP + FN)` | Anomalous samples caught |
| `fpr` | `FP / (FP + TN)` | Noise on clean traffic |
| `precision` | `TP / (TP + FP)` | Of all alarms, fraction that were real |
| `f1` | `2·P·R / (P + R)` | Precision-recall balance |
| `detection_latency` | First-alarm index − `inject_start` (within `DETECTION_WINDOW=5`) | Reaction speed; `−1` if no alarm in window |

`aggregate_metrics()` ([metrics.py:135-161](../src/evaluation/metrics.py#L135-L161)) collapses N trials into:
- `tpr_mean / tpr_std`, `fpr_mean / fpr_std`, `precision_mean / precision_std`, `f1_mean / f1_std`
- `detection_rate` = fraction of trials with at least one alarm in the detection window
- `avg_detection_latency / stdev_detection_latency` (over trials that *did* detect; `−1` if none)

**The precision problem (and why it isn't a bug):** with 1–20 anomalous samples out of 280, even 5% FPR yields ~13 false alarms vs at most 20 true positives — precision tanks by class imbalance, not by detector failure. Phase 3's confirmation gate (≥ 2 consecutive alarms) addresses this without retraining.

#### 9.6.3 `visualise.py` — eight per-iteration plots + Iter1↔Iter2 comparisons

`Visualiser(results_csv_dir, plots_dir, iteration).run_all()` produces, prefixed `iter{N}_*.png`:

1. **`f1_heatmap`** — F1 grid: detectors × anomaly_types, one panel per window size.
2. **`tpr_fpr_bars`** — grouped TPR/FPR per detector per anomaly type, with 5%-FPR target line.
3. **`tpr_vs_window`** — TPR vs window size with shaded ±1σ bands.
4. **`fpr_summary`** — horizontal bar of avg FPR per detector, green/amber/red coded.
5. **`detection_rate`** — heatmap of detection rate (avg across window sizes).
6. **`f1_vs_window`** — F1 vs N per detector per anomaly type.
7. **`detection_latency`** — boxplot of per-trial latency.
8. **`radar`** — polar capability profile (TPR per anomaly type + 1−FPR axis).

`compare_iterations(csv_iter1, csv_iter2, out_dir)` produces:
- `compare_tpr.png`, `compare_fpr.png`, `compare_f1.png`, `compare_detection_rate.png`
- Each shows side-by-side bars with **green/red delta annotations** (green = improvement). Triggered via `python main.py --iter1_csv path/to/iter1/aggregated_results.csv`.

#### 9.6.4 `plots.py` — legacy 4-plot generator

A simpler matplotlib-only fallback used by `generate_all_plots(aggregated)` ([plots.py:53-71](../src/evaluation/plots.py#L53-L71)) — F1 heatmap, TPR/FPR bars, latency boxplot, F1-vs-window. Same colour palette as `visualise.py`.

#### 9.6.5 `main.py` — CLI driver

- Logs Iter-2 changes to console at startup ([main.py:45-55](../main.py#L45-L55)).
- Validates `DATA_DIR` exists, runs harness, prints aligned summary table ([main.py:118-136](../main.py#L118-L136)).
- Triggers Visualiser → optionally compare_iterations → optionally HTML dashboard. Skips dashboard gracefully if Plotly is missing.

#### 9.6.6 Statistical justification for `N_TRIALS = 30`

Iter1 had std ≥ mean for several configurations (e.g. CUSUM burst σ=0.44 / μ=0.33). 30 trials shrink the standard error of the mean by `1 − √(10/30) ≈ 42%`, narrowing CIs enough to **defensibly rank** detectors.

---

## 10. The Integration Contract

The contract that holds the project together is:

```python
@dataclass
class DetectionResult:
    is_anomaly  : bool
    score       : float        # higher = more anomalous (for ROC/AUC)
    alarm_value : float = 0.0  # internal stat that triggered (for plots/debug)

class DetectorBase(ABC):
    @property @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def update(self, value: float) -> DetectionResult: ...
    @abstractmethod
    def reset(self) -> None: ...
    def run_on_series(self, series) -> list[DetectionResult]:
        self.reset()
        return [self.update(float(x)) for x in series]
```

Source: [src/detectors/base.py](../src/detectors/base.py).

**Convention rules** (enforced by code review, not Python):
- `update()` is O(1) time/memory — except WindowBuffer-based detectors which are O(N) memory.
- No `pandas` import inside any detector.
- No external network/IO in `update()` — pure Python/NumPy only.
- All parameters injected via `__init__`, never hardcoded.

These rules guarantee the detectors are mechanically portable to C++ in Phase 3.

---

## 11. Testing Strategy

`pytest tests/ -v` runs three test modules with **70+ tests** in total.

### 11.1 [tests/test_pipeline.py](../tests/test_pipeline.py) — 14 tests on `WindowBuffer`

- Push/eviction correctness (`test_basic_push_and_size`, `test_is_full`).
- Mean before and after wraparound (`test_mean_after_eviction`).
- Variance verified against `numpy.var(ddof=1)` (`test_variance_known_values`).
- `test_to_array_after_wraparound` — oldest-first ordering across the head pointer.
- `test_welford_numerical_stability` — pushes `1e8 + 0.1·i` and asserts mean accuracy < 1e-3 (catches naive cumulative-sum drift).
- `test_capacity_minimum` — `WindowBuffer(1)` must raise.
- `test_reset_clears_state` — reset returns size=0 and mean=0.

### 11.2 [tests/test_injector.py](../tests/test_injector.py) — 19 tests across all 4 injection types

- Label length matches signal length.
- Injected region marked correctly; outside-region samples unchanged byte-for-byte (`np.testing.assert_array_equal`).
- Monotone increase verified for `gradual_drift` (`diff[i] > diff[i-1]`).
- Exactly 1 label for `transient`.
- Reproducibility under fixed seed (two `AnomalyInjector(seed=7)` produce identical signals).
- Different seeds → varied positions across 20 seeds.
- Short signals (length 50) raise `ValueError`.
- Dispatcher (`inject(...)`) handles all 4 types and raises on unknown type.

### 11.3 [tests/test_detectors.py](../tests/test_detectors.py) — 35+ tests

For **each** detector:
- Returns `DetectionResult` with correct types.
- `run_on_series` returns one result per input sample.
- No alarms during warmup / before window full.
- Detects an obvious injected anomaly.
- `reset()` truly clears internal state.
- Name string contains the detector class name.
- Invalid params raise (e.g. `EWMADetector(lambda_=0)` → `ValueError`).

Plus **4 parametrised `TestBaseContract` tests** that run on every detector:
`test_has_name`, `test_update_returns_detection_result`, `test_run_on_series_correct_length`, `test_reset_is_idempotent`.

The base-contract tests are how the team enforces that any future detector added in Phase 3 plugs into the harness with no glue code.

---

## 12. Outputs Produced

After `python main.py` completes, the artefacts are:

```
results/
├── csv/
│   ├── raw_trial_results.csv         # 2880 rows: every trial
│   └── aggregated_results.csv        # 96 rows: 6 detectors × 4 anomalies × 4 windows
├── plots/
│   ├── iter2_f1_heatmap.png
│   ├── iter2_tpr_fpr_bars.png
│   ├── iter2_tpr_vs_window.png
│   ├── iter2_fpr_summary.png
│   ├── iter2_detection_rate.png
│   ├── iter2_f1_vs_window.png
│   ├── iter2_detection_latency.png
│   └── iter2_radar.png
├── comparison_plots/                 # only if --iter1_csv given
│   ├── compare_tpr.png
│   ├── compare_fpr.png
│   ├── compare_f1.png
│   └── compare_detection_rate.png
└── dashboard.html                    # interactive 6-chart Plotly report
```

**`raw_trial_results.csv` columns**: `detector, anomaly_type, window_size, trial, tpr, fpr, precision, f1, detection_latency, tp, fp, tn, fn`.

**`aggregated_results.csv` columns**: `detector, anomaly_type, window_size, n_trials, tpr_mean, tpr_std, fpr_mean, fpr_std, precision_mean, precision_std, f1_mean, f1_std, detection_rate, avg_detection_latency, stdev_detection_latency`.

---

## 13. Interactive HTML Dashboard

[dashboard/generate_report.py](../dashboard/generate_report.py) builds a single self-contained `results/dashboard.html` (Plotly via CDN) with **dark/light theme toggle** and six chart sections:

1. **F1 Heatmap** — dropdown switches window size; cells annotated with values.
2. **TPR vs FPR** — grouped bars; dropdown switches between TPR and FPR (FPR view shows 5% reference line).
3. **F1 vs Window Size** — dropdown picks anomaly type.
4. **Detection Rate Heatmap** — RdYlGn colour scale; dropdown for window size.
5. **Detection Latency** — horizontal bars with ±σ error bars; entries with latency = −1 excluded.
6. **Detector Capability Radar** — 5 normalised axes (F1, TPR, Precision, Detection Rate, Low FPR = 1−FPR) with raw values shown on hover.

Run automatically by `main.py` unless `--no_dashboard`, or standalone via `python dashboard/generate_report.py`. Common Plotly layout (`_FIG_LAYOUT`) keeps all charts visually consistent. CSS variables drive the theme switch — toggle is a single inline JS function.

---

## 14. Key Findings & Architecture Recommendation for Phase 3

**Headline finding**: no single detector covers all four anomaly types.

| Anomaly | Best detector(s) | Reason |
|---------|------------------|--------|
| Burst | **MAD** > Z-Score | Median is immune to mean/σ inflation by the burst itself |
| Transient | **MAD** ≈ Z-Score | Both make per-sample decisions; accumulation detectors miss by design |
| Rate shift | **EWMA** > CUSUM > SlidingWindow | EWMA's frozen μ₀ keeps S_t past UCL for the entire shifted region |
| Gradual drift | **Page-Hinkley** (Iter 2 retuned) | Adaptive mean tracks slow change; CUSUM's frozen μ₀ accumulates evidence too slowly |

### Recommended Phase 3 architecture: **two-layer pipeline + confirmation gate**

```
                   ┌─────────────────────────────────┐
                   │   Layer 1 — Spike pipeline      │
   stream ──┬───►  │   MAD (primary)                 │ ──┐
            │      │   Z-Score (low-FPR confirmer)   │   │
            │      └─────────────────────────────────┘   │
            │                                            ▼
            │      ┌─────────────────────────────────┐   ┌────────────────┐
            └───►  │   Layer 2 — Sustained-change    │ ─►│ Confirmation   │ ─► escalate
                   │   EWMA (early trigger)          │   │ gate: ≥ 2      │
                   │   CUSUM (persistence confirmer) │   │ consecutive    │
                   └─────────────────────────────────┘   │ alarms         │
                                                         └────────────────┘
```

The confirmation gate directly addresses Iter1's near-zero precision (the false-alarm dominance is a class-imbalance artefact, not a detector failure) **without retraining any detector**.

### Why Python now, C++ later

Phase 2 is research validation — Python is for fast iteration and parameter tuning. The buffer and detectors were intentionally written with no `pandas` and only O(1)/O(N) plain math, so the Phase 3 C++ port for on-device deployment is a mechanical translation, not a redesign.

---

## 15. Glossary

| Term | Meaning |
|------|---------|
| TPR | True Positive Rate = `TP / (TP + FN)` |
| FPR | False Positive Rate = `FP / (FP + TN)` |
| F1 | Harmonic mean of precision and recall |
| Detection rate | Fraction of trials with ≥ 1 alarm in the detection window |
| Detection latency | Samples between `inject_start` and the first alarm (within `DETECTION_WINDOW`) |
| Welford's algorithm | Numerically stable online mean/variance update |
| Masking effect | Spike inflates σ → spike's own z-score appears smaller than truth |
| MAD | Median Absolute Deviation |
| EWMA | Exponentially Weighted Moving Average |
| CUSUM | Cumulative Sum Control Chart |
| PH | Page-Hinkley test |
| Warmup | Initial samples used to estimate baseline; no alarms emitted |
| Confirmation gate | Require N consecutive detector alarms before escalating (Phase 3) |

---

## 16. References

- **CESNET-TimeSeries24 dataset:** <https://zenodo.org/records/13382427>
- Roberts, S. W. (1959). *Control Chart Tests Based on Geometric Moving Averages.* Technometrics.
- Page, E. S. (1954). *Continuous Inspection Schemes.* Biometrika 41(1/2): 100–115.
- Hinkley, D. V. (1971). *Inference about the change-point from cumulative sum tests.* Biometrika 58(3): 509–523.
- Rousseeuw, P. J. & Croux, C. (1993). *Alternatives to the Median Absolute Deviation.* JASA 88(424).
- Leland, W. E. et al. (1994). *On the self-similar nature of Ethernet traffic.* IEEE/ACM Transactions on Networking.
- Welford, B. P. (1962). *Note on a method for calculating corrected sums of squares and products.* Technometrics 4(3).

---

*Document version: Phase 2 — Iteration 2 — generated 2026-04-24.*
