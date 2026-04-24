# Network Telemetry Anomaly Detection

## Project Description
This project investigates lightweight, on-device anomaly detection algorithms for real-time network telemetry on HPE Aruba switches. By streaming network metrics through a fixed-size sliding window and evaluating six statistical detectors against four classes of injected anomalies, the system identifies which algorithms deliver the best accuracy, latency, and memory profile within the strict resource budget of an ARM-class control plane processor. Phase 1 delivered a theoretical study of fifteen candidate algorithms; Phase 2 empirically benchmarks the six finalists on real CESNET ISP traffic and produces an interactive HTML dashboard summarising the results.

---

## Project Details

### Problem Statement
Network operators need early warning of traffic anomalies (bursts, sustained rate shifts, gradual drifts, short transients) directly on the switch itself, without offloading data to a central analytics pipeline. The control plane only offers a few kilobytes of RAM and must respond in microseconds, so the detector must run on windows of 10–50 samples, use under 100 bytes of state per monitored feature, and complete each update in under 100 microseconds. This project empirically compares lightweight time-series techniques under those constraints and recommends an architecture for deployment.

### Data Preprocessing
- **Dataset:** CESNET-TimeSeries24 (10-minute aggregated ISP traffic per IP).
- **Primary signal:** `n_bytes`. Secondary signals available: `n_packets`, `average_n_dest_ip`, `tcp_udp_ratio_packets`.
- **Normalisation:** loader standardises column names, casts timestamps, and produces a clean single-IP time series.
- **Sliding window buffer:** fixed-capacity circular buffer with O(1) mean and variance via Welford's online algorithm; no recomputation on update.
- **Anomaly injection:** ground-truth labelled injection of four anomaly types — burst, rate shift, gradual drift, transient — with configurable magnitude, duration and start position for reproducible benchmarking.

### Detector Implementation and Evaluation
- **Detectors implemented (all conform to `DetectorBase`):**
  - Z-Score
  - MAD (Median Absolute Deviation)
  - EWMA (Exponentially Weighted Moving Average)
  - Sliding Window Stats
  - CUSUM (Cumulative Sum)
  - Page-Hinkley
- **Evaluation sweep:** 6 detectors × 4 window sizes (10, 20, 30, 50) × 4 anomaly types × 30 trials = 2,880 independent runs per iteration.
- **Metrics:** True Positive Rate, False Positive Rate, F1 score, detection latency, AUC.
- **Headline finding:** no single detector wins across all anomaly classes — MAD dominates on bursts and transients, EWMA on rate shifts, Page-Hinkley on gradual drifts. A two-layer architecture is recommended for Phase 3.

### Hyperparameter Tuning
Iteration 2 retuned parameters after Iteration 1 exposed false-alarm and missed-detection failure modes. Final values (in `Phase 2/config.py`):
```
{
  'N_TRIALS': 30,
  'CUSUM_h': 3.5,
  'PAGE_HINKLEY_lambda': 12,
  'EWMA_L': 3.5,
  'BURST_DURATION': 5,
  'GRADUAL_DRIFT_SLOPE': 0.3,
  'GRADUAL_DRIFT_DURATION': 20
}
```

### Visualizations
- Per-detector ROC-style scatter (TPR vs FPR)
- F1 heatmaps across window sizes and anomaly types
- Detection-latency box plots
- Per-trial signal overlays showing injection windows and alarm points
- Correlation matrix of detector behaviours
- Interactive Plotly dashboard with light/dark theme toggle

### Interactive Dashboard
The Plotly HTML report provides:
- Filters by detector, window size, and anomaly type
- Hoverable metric breakdowns per trial
- Side-by-side detector comparison plots
- Theme toggle (light/dark)
- Self-contained HTML file — no server required

---

## Tech Stack
- Python 3.10+
- numpy, pandas, scipy
- matplotlib, seaborn
- plotly
- pytest
- jupyter, tqdm

---

## Getting Started

### 1. Clone the repository
```
git clone https://github.com/DCode-v05/Network-Telementry.git
cd Network-Telementry
```

### 2. Install dependencies
```
cd "Phase 2"
python -m venv env
env\Scripts\activate        # Windows
# source env/bin/activate    # macOS / Linux
pip install -r requirements.txt
```

### 3. Place CESNET data
Download `ip_addresses_sample.tar.gz` from the CESNET-TimeSeries24 release on Zenodo:
<https://zenodo.org/records/13382427>

The sample archive is ~171 MB (the full dataset is ~40 GB). Extract it and move the per-IP CSVs into `Phase 2/data/ip_addresses_sample/`:
```
tar -xzf ip_addresses_sample.tar.gz
```

Expected layout:
```
Phase 2/data/
└── ip_addresses_sample/
    ├── 0.csv
    ├── 1.csv
    ├── 2.csv
    └── ...
```

Each file corresponds to one IP address time series with the CESNET-TimeSeries24 schema:
```
id_time, n_flows, n_packets, n_bytes, n_dest_ip, n_dest_asn, n_dest_port,
tcp_udp_ratio_packets, tcp_udp_ratio_bytes, dir_ratio_packets,
dir_ratio_bytes, avg_duration, avg_ttl
```

The loader uses the 10-minute aggregation by default. If the extracted files are nested under `agg_10_minutes/`, update `DATA_DIR` in `Phase 2/config.py` to point there.

### 4. Run the full evaluation
```
python main.py
```
Raw trial CSVs are written to `results/csv/`, plots to `results/plots/`, and the interactive report to `results/dashboard/`.

### 5. Run the test suite
```
pytest tests/ -v
```

---

## Usage
- Use `main.py` to run the full 2,880-trial benchmark end-to-end.
- Tune algorithm or sweep parameters exclusively in `Phase 2/config.py`.
- Inspect per-trial CSV outputs in `results/csv/` and static plots in `results/plots/`.
- Open the generated interactive HTML dashboard in any browser to explore detector behaviour under every condition.
- Refer to `Phase 1/Algorithm_Study_Document .md` for the theoretical rationale behind the six finalist detectors and `Phase 2/docs/PHASE_2_DOCUMENTATION.md` for the full technical reference.

---

## Modules

| Module             | Responsibility                                                   | Files                                                              |
|--------------------|------------------------------------------------------------------|--------------------------------------------------------------------|
| Data Pipeline      | CESNET CSV loading, normalisation, O(1) sliding-window buffer    | `src/pipeline/loader.py`, `src/pipeline/window_buffer.py`          |
| Anomaly Injector   | Inject burst / rate shift / gradual drift / transient with labels| `src/injector/anomaly_injector.py`                                 |
| Detectors A        | Statistical deviation detectors                                  | `src/detectors/zscore.py`, `src/detectors/mad.py`                  |
| Detectors B        | Exponential smoothing detectors                                  | `src/detectors/ewma.py`, `src/detectors/sliding_window_stats.py`   |
| Detectors C        | Change-point / accumulation detectors                            | `src/detectors/cusum.py`, `src/detectors/page_hinkley.py`          |
| Evaluation Harness | Sweep runner, metrics, plots, dashboard                          | `src/evaluation/harness.py`, `src/evaluation/metrics.py`, `main.py`|

**Integration contract:** every detector implements `src/detectors/base.py` and every consumer uses `src/pipeline/window_buffer.py`. These interfaces are the stable seam between modules, and all 89+ tests enforce the contract.

---

## Project Structure
```
Network-Telementry/
│
├── Phase 1/                                  # Algorithm study and evaluation spec
│   ├── Algorithm_Study_Document .md          # Theoretical analysis of 15 candidates
│   ├── HPE_Evaluation_Criteria_Specification.md
│   └── PDFs/                                 # Reference papers
│
├── Phase 2/                                  # Implementation and benchmarking
│   ├── data/                                 # CESNET CSVs go here
│   ├── src/
│   │   ├── pipeline/
│   │   │   ├── loader.py                     # CESNET loader and normalisation
│   │   │   └── window_buffer.py              # O(1) Welford sliding window
│   │   ├── injector/
│   │   │   └── anomaly_injector.py           # Burst / rate shift / drift / transient
│   │   ├── detectors/
│   │   │   ├── base.py                       # DetectorBase contract
│   │   │   ├── zscore.py
│   │   │   ├── mad.py
│   │   │   ├── ewma.py
│   │   │   ├── sliding_window_stats.py
│   │   │   ├── cusum.py
│   │   │   └── page_hinkley.py
│   │   └── evaluation/
│   │       ├── harness.py                    # Full 2,880-trial sweep
│   │       ├── metrics.py                    # TPR, FPR, F1, latency, AUC
│   │       └── visualise.py                  # Matplotlib plots
│   ├── dashboard/
│   │   └── generate_report.py                # Interactive Plotly HTML report
│   ├── tests/
│   │   ├── test_pipeline.py
│   │   ├── test_injector.py
│   │   └── test_detectors.py
│   ├── results/
│   │   ├── csv/                              # Raw trial outputs
│   │   ├── plots/                            # Static PNGs
│   │   └── dashboard/                        # Interactive HTML
│   ├── docs/
│   │   └── PHASE_2_DOCUMENTATION.md          # Full technical reference
│   ├── notebooks/
│   │   └── exploration.ipynb                 # EDA on CESNET sample
│   ├── main.py                               # Single entry point
│   ├── config.py                             # All tunable parameters
│   └── requirements.txt
│
└── README.md                                 # This file
```

---

## Contributing

Contributions are welcome! To contribute:
1. Fork the repository
2. Create a new branch:
   ```bash
   git checkout -b feature/your-feature
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add your feature"
   ```
4. Push to your branch:
   ```bash
   git push origin feature/your-feature
   ```
5. Open a pull request describing your changes.

---

## Contact
- **GitHub:** [DCode-v05](https://github.com/DCode-v05)
- **Email:** denistanb05@gmail.com
