# Network Telemetry Anomaly Detection

## Project Description
This project investigates lightweight, on-device anomaly detection algorithms for real-time network telemetry on HPE Aruba switches. By streaming network metrics through a fixed-size sliding window and evaluating six statistical detectors — and now a two-layer ensemble of those detectors — against four classes of injected anomalies, the system identifies which algorithms deliver the best accuracy, latency, and memory profile within the strict resource budget of an ARM-class control plane processor. Phase 1 delivered a theoretical study of fifteen candidate algorithms; Phase 2 empirically benchmarked the six finalists on real CESNET ISP traffic and produced an interactive HTML dashboard summarising the results; Phase 3 builds a confirmation-gated two-layer ensemble on top of those finalists and re-benchmarks against Phase 2 row-for-row.

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

## Phase 3 — Two-Layer Ensemble + Confirmation Gate

Phase 3 is the architectural answer to Phase 2's headline finding (no single detector wins on every anomaly class) and its precision problem (5–20 anomalous samples in a ~280-sample series collapse precision under any non-trivial FPR). It is **100% additive** over Phase 2 — every Phase 2 detector, hyperparameter, dataset, RNG seed, and harness contract is reused unchanged. Phase 3 adds three new classes (each subclassing `DetectorBase`) and a small evaluation/visualisation layer.

### Architecture
```
   Layer 1 — Spike pipeline        :  GatedMAD ∧ GatedZScore        (high precision)
   Layer 2 — Sustained pipeline    :  GatedEWMA ∨ GatedCUSUM        (high recall)
   Top-level fusion                :  Layer 1 OR Layer 2            (union of coverage)
   Confirmation gate (per child)   :  n = 2 consecutive child alarms before alarm
```

Each base detector is wrapped in a `ConfirmationGate(n=2)` to suppress singleton false alarms typical of MAD/Z-Score on tail noise. Layer 1 votes AND (corroboration); Layer 2 votes OR (EWMA and CUSUM lock onto the same shift via different mechanisms and trip at different samples).

### New components
- `ConfirmationGate(child, n)` — forwards every sample, requires `n` consecutive child alarms before declaring anomaly. Resets propagate to the child.
- `VotingLayer(children, mode="AND"|"OR")` — combines ≥ 2 gated children. `score = max(child.score)` (ROC-compatible); `alarm_value` reports the vote count.
- `TwoLayerEnsemble(spike_layer, sustained_layer)` — top-level OR fusion with per-layer attribution so the dashboard can colour-code which layer caught each anomaly.

### Sweep grid
14 detectors (6 individuals + 4 gated baselines + 3 voting layers + 1 ensemble) × 4 windows × 4 anomaly types × 30 trials = **6,720 trials** per full run.

### Phase 3 acceptance criteria
| Criterion | Threshold |
|-----------|-----------|
| `gate_fp_reduction` positive for ≥ 3 of 4 base detectors | central claim |
| Ensemble FPR ≤ best-single FPR for ≥ 3 of 4 anomaly types | central claim |
| Ensemble TPR within 5 pp of best-single TPR per anomaly | acceptable cost |
| All unit tests pass (`pytest tests/`) | wiring |

Full Phase 3 reference: [`Phase 3/docs/PHASE_3_DOCUMENTATION.md`](Phase%203/docs/PHASE_3_DOCUMENTATION.md). Standalone Phase 2 outcomes summary: [`Phase 2/docs/PHASE_2_FINDINGS.md`](Phase%202/docs/PHASE_2_FINDINGS.md).

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

### 4. Run the full Phase 2 evaluation
```
python main.py
```
Raw trial CSVs are written to `results/csv/`, plots to `results/plots/`, and the interactive report to `results/dashboard/`.

### 5. Run the Phase 2 test suite
```
pytest tests/ -v
```

### 6. Run Phase 3 (ensemble benchmark)
Phase 3 reuses Phase 2's virtualenv and CESNET data — no extra setup. From the repository root:
```
cd "../Phase 3"
python main.py --quick --no_plot --no_dashboard                                # ~30s smoke run
python main.py --compare_phase2_csv "../Phase 2/results/csv/aggregated_results.csv"   # full ~70 min run
pytest tests/ -v                                                               # 48 tests
```
Outputs: `Phase 3/results/csv/aggregated_results.csv` (224 rows), `Phase 3/results/csv/raw_trial_results.csv` (6,720 rows), `Phase 3/results/dashboard.html`.

---

## Usage
- Use `Phase 2/main.py` to run the full 2,880-trial single-detector benchmark end-to-end.
- Use `Phase 3/main.py` to run the full 6,720-trial ensemble benchmark, optionally comparing row-for-row against Phase 2 with `--compare_phase2_csv`.
- Tune Phase 2 detector / sweep parameters in `Phase 2/config.py`. Tune the Phase 3 ensemble (`confirmation_n`, layer membership, voting mode) in `Phase 3/config.py`. Phase 3 inherits everything else from Phase 2 verbatim via `_phase2_bridge.py` so results are byte-comparable.
- Inspect per-trial CSV outputs in `Phase 2/results/csv/` and `Phase 3/results/csv/`, static plots in `Phase 2/results/plots/`.
- Open the generated interactive HTML dashboards (one per phase) in any browser to explore detector behaviour under every condition.
- Refer to [`Phase 1/Algorithm_Study_Document .md`](Phase%201/Algorithm_Study_Document%20.md) for the theoretical rationale behind the six finalist detectors, [`Phase 2/docs/PHASE_2_DOCUMENTATION.md`](Phase%202/docs/PHASE_2_DOCUMENTATION.md) for the full Phase 2 technical reference, [`Phase 2/docs/PHASE_2_FINDINGS.md`](Phase%202/docs/PHASE_2_FINDINGS.md) for the structured outcomes summary, and [`Phase 3/docs/PHASE_3_DOCUMENTATION.md`](Phase%203/docs/PHASE_3_DOCUMENTATION.md) for the ensemble design and re-benchmark protocol.

---

## Modules

| Module                        | Responsibility                                                       | Files                                                                                  | Phase |
|-------------------------------|----------------------------------------------------------------------|----------------------------------------------------------------------------------------|-------|
| Data Pipeline                 | CESNET CSV loading, normalisation, O(1) sliding-window buffer        | `Phase 2/src/pipeline/loader.py`, `Phase 2/src/pipeline/window_buffer.py`              | 2     |
| Anomaly Injector              | Inject burst / rate shift / gradual drift / transient with labels    | `Phase 2/src/injector/anomaly_injector.py`                                             | 2     |
| Detectors A (spike)           | Statistical deviation detectors                                      | `Phase 2/src/detectors/zscore.py`, `Phase 2/src/detectors/mad.py`                      | 2     |
| Detectors B (baseline track)  | Exponential smoothing detectors                                      | `Phase 2/src/detectors/ewma.py`, `Phase 2/src/detectors/sliding_window_stats.py`       | 2     |
| Detectors C (change point)    | Change-point / accumulation detectors                                | `Phase 2/src/detectors/cusum.py`, `Phase 2/src/detectors/page_hinkley.py`              | 2     |
| Phase 2 Evaluation Harness    | Single-detector sweep, metrics, plots, dashboard                     | `Phase 2/src/evaluation/harness.py`, `Phase 2/src/evaluation/metrics.py`, `Phase 2/main.py` | 2     |
| Confirmation Gate             | Wraps any detector; requires N consecutive child alarms              | `Phase 3/ensemble/confirmation_gate.py`                                                | 3     |
| Voting Layer                  | Combines ≥ 2 gated detectors via AND or OR                           | `Phase 3/ensemble/voting_layer.py`                                                     | 3     |
| Two-Layer Ensemble            | Top-level OR fusion of spike + sustained layers with attribution     | `Phase 3/ensemble/two_layer_ensemble.py`                                               | 3     |
| Phase 2 → Phase 3 Bridge      | sys.path shim + Phase 2 re-exports (config, detectors, harness)      | `Phase 3/_phase2_bridge.py`                                                            | 3     |
| Phase 3 Evaluation Harness    | Ensemble sweep, gate-FP-reduction & ensemble-vs-best metrics         | `Phase 3/evaluation/harness.py`, `Phase 3/evaluation/phase3_metrics.py`, `Phase 3/main.py` | 3     |
| Phase 3 Dashboard             | Plotly HTML report incl. Phase 2 ↔ Phase 3 comparison figure         | `Phase 3/dashboard/generate_report.py`                                                 | 3     |

**Integration contract:** every detector — Phase 2 individuals and Phase 3 ensemble classes alike — implements `Phase 2/src/detectors/base.py::DetectorBase`, and every consumer uses `Phase 2/src/pipeline/window_buffer.py`. These interfaces are the stable seam between modules. Phase 2's 89+ tests and Phase 3's 48 tests (incl. parametrised base-contract checks across all four ensemble classes) enforce the contract end-to-end.

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
├── Phase 2/                                  # Single-detector implementation & benchmarking
│   ├── data/                                 # CESNET CSVs go here
│   ├── src/
│   │   ├── pipeline/
│   │   │   ├── loader.py                     # CESNET loader and normalisation
│   │   │   └── window_buffer.py              # O(1) Welford sliding window
│   │   ├── injector/
│   │   │   └── anomaly_injector.py           # Burst / rate shift / drift / transient
│   │   ├── detectors/
│   │   │   ├── base.py                       # DetectorBase contract (shared with Phase 3)
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
│   │   ├── PHASE_2_DOCUMENTATION.md          # Full technical reference
│   │   └── PHASE_2_FINDINGS.md               # Structured outcomes / key findings
│   ├── notebooks/
│   │   └── exploration.ipynb                 # EDA on CESNET sample
│   ├── main.py                               # Single-detector benchmark entry point
│   ├── config.py                             # All tunable parameters
│   └── requirements.txt
│
├── Phase 3/                                  # Two-layer ensemble + confirmation gate
│   ├── _phase2_bridge.py                     # sys.path shim + Phase 2 re-exports
│   ├── config.py                             # Extends Phase 2 with ENSEMBLE block
│   ├── main.py                               # CLI entry (--quick, --compare_phase2_csv, …)
│   ├── ensemble/
│   │   ├── confirmation_gate.py              # ConfirmationGate(child, n=2)
│   │   ├── voting_layer.py                   # VotingLayer(children, mode)
│   │   └── two_layer_ensemble.py             # TwoLayerEnsemble(spike, sustained)
│   ├── evaluation/
│   │   ├── harness.py                        # 6,720-trial sweep, build_detectors(w)
│   │   └── phase3_metrics.py                 # gate_fp_reduction, ensemble_vs_best deltas
│   ├── dashboard/
│   │   └── generate_report.py                # Plotly HTML, 8 base + 2 ensemble figures
│   ├── tests/
│   │   ├── conftest.py                       # pytest bootstrap (path setup)
│   │   ├── _helpers.py                       # MockDetector test double
│   │   ├── test_confirmation_gate.py
│   │   ├── test_voting_layer.py
│   │   ├── test_two_layer_ensemble.py
│   │   └── test_ensemble_base_contract.py    # parametrised across all 4 ensembles
│   ├── docs/
│   │   └── PHASE_3_DOCUMENTATION.md          # Full ensemble design & re-benchmark protocol
│   └── results/
│       ├── csv/                              # 14 detectors × 4 anomalies × 4 windows = 224 rows
│       └── dashboard.html                    # Plotly report with phase 2↔3 comparison
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
