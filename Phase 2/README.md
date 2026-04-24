# Network Telemetry Phase 2 — Anomaly Detection Evaluation

**Project:** Evaluate and Compare Lightweight Time-Series Techniques for Network Telemetry  
**Dataset:** CESNET-TimeSeries24  
**Phase:** 2 — Implementation & Benchmarking  
**Language:** Python 3.10+

---

## Project Goal

Empirically evaluate 6 selected algorithms (EWMA, CUSUM, Page-Hinkley, Z-Score, MAD,
Sliding Window Stats) against 4 injected anomaly types (burst, rate shift, gradual drift,
transient) across 4 window sizes (N = 10, 20, 30, 50) using real CESNET network traffic
as the baseline signal.

---

## Directory Structure

```
network_telemetry_phase2/
├── data/                        # Put your CESNET CSV files here
│   └── README_data.md           # Instructions for data placement
├── src/
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── loader.py            # CESNET CSV loading and normalization
│   │   └── window_buffer.py     # Sliding window circular buffer
│   ├── injector/
│   │   ├── __init__.py
│   │   └── anomaly_injector.py  # 4 anomaly injection functions
│   ├── detectors/
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract base class all detectors implement
│   │   ├── zscore.py
│   │   ├── mad.py
│   │   ├── ewma.py
│   │   ├── cusum.py
│   │   ├── page_hinkley.py
│   │   └── sliding_window_stats.py
│   └── evaluation/
│       ├── __init__.py
│       ├── harness.py           # Runs all algorithms × all window sizes × all conditions
│       └── metrics.py           # TPR, FPR, F1, detection latency
├── tests/
│   ├── test_detectors.py        # Unit tests for each detector
│   ├── test_injector.py         # Unit tests for anomaly injection
│   └── test_pipeline.py         # Unit tests for data loading
├── results/
│   ├── csv/                     # Raw results output here
│   └── plots/                   # Generated plots output here
├── notebooks/
│   └── exploration.ipynb        # EDA on CESNET sample
├── docs/
│   └── phase2_results.md        # Auto-generated results summary
├── main.py                      # Single entry point — runs full evaluation
├── config.py                    # All parameters in one place
├── requirements.txt
└── README.md
```

---

## Quick Start (Local)

### 1. Clone / set up environment

```bash
cd network_telemetry_phase2
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Place CESNET data

Copy your CESNET ip_addresses_sample CSVs into `data/ip_addresses_sample/`.
The loader expects files named like `<ip_id>.csv` matching the CESNET format.

```
data/
└── ip_addresses_sample/
    ├── 0.csv
    ├── 1.csv
    └── ...
```

### 3. Run full evaluation

```bash
python main.py
```

Results are written to `results/csv/` and plots to `results/plots/`.

### 4. Run tests

```bash
pytest tests/ -v
```

---

## Team Split (6 people)

| Person | Module | Files to own |
|--------|--------|--------------|
| 1 | Data Pipeline | `src/pipeline/loader.py`, `src/pipeline/window_buffer.py` |
| 2 | Anomaly Injector | `src/injector/anomaly_injector.py` |
| 3 | Detectors A | `src/detectors/zscore.py`, `src/detectors/mad.py` |
| 4 | Detectors B | `src/detectors/ewma.py`, `src/detectors/sliding_window_stats.py` |
| 5 | Detectors C | `src/detectors/cusum.py`, `src/detectors/page_hinkley.py` |
| 6 | Evaluation Harness | `src/evaluation/harness.py`, `src/evaluation/metrics.py`, `main.py` |

**Integration contract:** Everyone depends on `src/detectors/base.py` and
`src/pipeline/window_buffer.py`. These must be finalized in Week 1 before
parallel work begins.

---

## Configuration

All tunable parameters live in `config.py`. Change parameters there, not inside modules.
