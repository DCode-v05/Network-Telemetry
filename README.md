# Network Telemetry Anomaly Detection

**On-device, lightweight time-series anomaly detection for network switches — finding which streaming algorithms stay accurate under a hard < 100 µs / < 100 byte budget, with parity-verified C twins.**

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![C](https://img.shields.io/badge/C-A8B9CC?style=flat&logo=c&logoColor=black) ![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat&logo=numpy&logoColor=white) ![SciPy](https://img.shields.io/badge/SciPy-8CAAE6?style=flat&logo=scipy&logoColor=white) ![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react&logoColor=61DAFB) ![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white) ![Apache ECharts](https://img.shields.io/badge/Apache%20ECharts-AA344D?style=flat&logo=apacheecharts&logoColor=white) ![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat&logo=pytest&logoColor=white)

## Overview

Network switches emit a lot of telemetry — link utilisation, packet rate, queue depth, error counters, jitter — at sub-second granularity. The usual approach is to ship all of it to a central collector and run analytics there, or fall back to static thresholds on the device. This project asks a narrower question: can you run useful anomaly detection *on the switch itself*, on the ARM-class control-plane processor, where you get a few kilobytes of RAM and need to answer in microseconds?

That turns into a concrete resource budget. Each detector sees one sample at a time, keeps state in **under 100 bytes per monitored metric**, updates in **under 100 microseconds**, works on short observation windows of **10–50 samples**, and has to be implementable in plain C with O(1) (or near-O(1)) arithmetic. The work is a four-phase empirical study that takes ~15 candidate time-series techniques, narrows them down, benchmarks them on real ISP traffic and on labelled synthetic anomalies, and ends with a production build where every detector has a portable C twin that is numerically verified against its Python reference.

It was built during my time on the HPE (Aruba/HP CPP) side — the target hardware framing is HPE Aruba switches — and the whole thing is structured as a research repo: theory, single-detector benchmark, ensemble, then a production phase that measures both detection quality *and* real CPU/memory cost and picks a winner under the budget. The headline recommendation is the `deriv` first-difference z-score detector at **4.9 ns/sample and 20 bytes**, which turns out to be Pareto-dominant — the cheapest *and* the most accurate overall.

## Key Features

- **Four-phase study, each building on the last** — algorithm theory → single-detector benchmark → confirmation-gated ensemble → production build with C twins.
- **~20 streaming detectors** spanning statistical (EWMA/EWMV z-score), robust (median + MAD, Hampel), change-point (CUSUM, Page-Hinkley), derivative (first-difference), spectral (lag-k autocorrelation drop), and several ensembles (layered, voting, cascade, plus a single all-in-one `unified` detector).
- **One shared detector contract** — every detector, single or ensemble, implements the same `update(x) -> score >= 0` streaming interface, returns 0.0 during warm-up, and decides via `score >= threshold`. The registry is the single source of truth for which detectors exist and what anomaly types each targets.
- **Real datasets** — CESNET-TimeSeries24 (10-minute aggregated ISP traffic, 283 IPs) in Phase 2, plus 14 NAB streams (realTraffic + realKnownCause) alongside labelled synthetic anomalies in Phase 4.
- **Labelled anomaly injection** — ground-truth burst/spike, gradual drift, periodicity loss, and transient anomalies at configurable magnitude, duration and position, so every benchmark is reproducible and scored against known labels.
- **Parity-verified C99 twin** — `tsad.c` ports nine single detectors to portable C; a `parity.c` harness checks the C output matches the Python reference to ≤ 1e-4, and `bench.c` measures true per-sample latency with `QueryPerformanceCounter`.
- **Two-axis selection** — detectors are scored on detection quality (VUS-PR, F1, MCC, latency, false-positive rate) *and* measured cost (ns/sample, state bytes), then chosen by a Pareto/scorecard analysis behind a hard budget gate.
- **Per-phase interactive dashboards** — each phase ships a React + Vite + Apache ECharts dashboard that builds to a single self-contained HTML file you open in a browser (no server).
- **Test-backed contracts** — pytest suites across the phases cover the detector contract, the anomaly injector, the sliding-window buffer, the budget gate, and C-to-Python parity.

## How It Works

### Phase 1 — Algorithm study (theory)

The starting point was a written study of ~15 candidate time-series techniques against the on-device evaluation criteria. Nine were rejected on memory/compute/history grounds — ADWIN, DDM, Kalman filtering, Matrix Profile, Spectral Residual, SAX, ARIMA, PELT, Binary Segmentation — because they need too much state, too much compute, or long histories that don't fit a 10–50 sample window. Six finalists were carried forward for empirical testing: Z-Score, MAD, EWMA, CUSUM, Page-Hinkley, and Sliding-Window stats. Outputs are the algorithm study document and the evaluation criteria spec under `Phase 1/`.

### Phase 2 — Single-detector benchmark

The six finalists were implemented against a shared `DetectorBase` contract and run on real CESNET-TimeSeries24 traffic. The data pipeline standardises the per-IP CSV schema, picks the `n_bytes` signal by default, and feeds it through a fixed-capacity circular buffer that keeps mean and variance in O(1) via Welford's online algorithm — no recomputation per update. A labelled injector adds burst / rate-shift / drift / transient anomalies with known positions.

The sweep is 6 detectors × 4 window sizes (10, 20, 30, 50) × 4 anomaly types × 30 trials = **2,880 runs**, scored on TPR, FPR, F1, detection latency and AUC. The headline finding: no single detector wins across all anomaly classes — MAD leads on bursts and transients, EWMA on rate shifts, Page-Hinkley and CUSUM on drifts — and precision collapses under the class imbalance (a handful of anomalous samples in a ~280-sample series). That motivated the ensemble in Phase 3.

### Phase 3 — Two-layer confirmation-gated ensemble

Phase 3 is fully additive over Phase 2 — it reuses every Phase 2 detector, hyperparameter, dataset, RNG seed and harness via a bridge module, so results stay row-comparable. It adds three classes:

- `ConfirmationGate(child, n)` — wraps any detector and only fires after `n` consecutive child alarms, which suppresses the singleton false alarms that MAD/Z-Score throw on tail noise.
- `VotingLayer(children, mode="AND"|"OR")` — combines gated children; score is the max child score (so it stays ROC-compatible), and it reports the vote count.
- `TwoLayerEnsemble(spike_layer, sustained_layer)` — a high-precision spike pipeline (gated MAD AND gated Z-Score) and a high-recall sustained pipeline (gated EWMA OR gated CUSUM), fused with a top-level OR and per-layer attribution so the dashboard can show which layer caught each anomaly.

The re-benchmark is 14 detectors × 4 windows × 4 types × 30 trials = **6,720 runs**. The finding: confirmation gating cuts false positives sharply (MAD 14.6 → 5.6 %, Z-Score 5.1 → 0.74 %, CUSUM 12 → 5.7 % FPR) while the ensemble keeps recall within ~4 percentage points of the best single detector.

### Phase 4 — Production build with a C twin

Phase 4 is the main deliverable. It rebuilds a fresh field of detectors as a self-contained product and evaluates them on **two axes at once**: detection quality and real measured cost.

- **Detectors:** nine single (`ewma_z`, `robust_z`, `hampel`, `cusum`, `page_hinkley`, `ewmv_adaptive`, `deriv`, `acf_periodicity`, and a deliberately-heavy `heavy_baseline` control) plus three combined (`layered` = EWMA→CUSUM OR-fusion; `voting` = 4-member soft vote; `cascade` = a cheap EWMA pre-filter gating an expensive robust confirm). An improvement study and a unified-detector search add anomaly-aware "hold" baselines, confirmation-gated variants, and the `unified` detector, taking the registry to ~20 entries.
- **Datasets:** labelled synthetic generators inject the four anomaly types at {4, 6, 9}σ across multiple seeds, plus 14 real NAB streams for external validity.
- **Intelligence metrics:** PR-AUC and threshold-free **VUS-PR** (the headline), F1 / precision / recall / MCC at the best operating point, an event-tolerant F1 (±2-sample) at the operator-tuned threshold for point anomalies, a NAB-like early-detection score, detection latency, and false-positives per 1000 samples.
- **Cost metrics:** authoritative per-sample time from the C twin via `QueryPerformanceCounter`, float32 state-byte footprint (`tsad_state_bytes`), a Python cross-check, and an ARM-cycle projection. The < 100 µs / < 100 byte budget is a **hard gate** in selection.

The runtime side (what would ship to the switch) and the evaluation harness (what chose it) share the exact same detector contract. The C twin in `src/c/` is a single `TsadDetector` struct plus `tsad_init` / `tsad_update` / `tsad_state_bytes`, with a ring buffer for the window-based detectors and pure scalar recursion for the O(1) ones. A parity harness streams the same input through C and Python and asserts the scores agree.

### The `unified` detector

A search across parallel strategies produced one streaming unit, `unified`, that covers all four anomaly types in **96 bytes** of shared state (five float scalars + an integer period + a 17-deep ring buffer + counters). Three heads read that shared state and the output is the max of their normalised scores:

- a derivative head with an anomaly-aware "hold" baseline → spikes and transients,
- a held EWMA control-chart head with a clipped output → drift,
- a gated ACF-drop head that only arms when the signal is actually periodic → periodicity loss.

The no-dilution tricks (clip the drift output so a legitimate step can't out-shout a spike; keep the periodicity head silent on aperiodic signals; share one state block instead of four) are what let a single 96-byte unit do the job of a naive 4-detector vote that would cost ~424 bytes.

## Results / Highlights

These figures come from the committed Phase 4 results (`results/selection.json`, the measured C cost data, and the 308-line `Phase4_Report.md`), anchored to the repo's own reconciliation across the phase docs.

- **Recommended default: `deriv` (first-difference z-score), window 50 — 4.9 ns/sample, 20 bytes, Pareto-dominant** (cheapest and most accurate overall), F1 ≈ 0.665, near-zero detection latency, and uniquely window-robust (almost no accuracy loss down to a 10-sample window).
- **Memory, not compute, is the binding constraint.** On the x86 host every detector runs far under the 100 µs budget — from 4.9 ns/sample (`deriv`) to ~2.0 µs/sample (`heavy_baseline`). What breaks the budget is bytes: window-buffer detectors hold a `float[window]` ring and exceed 100 bytes past ~window 22, while the O(1) recursive detectors (16–32 bytes) fit at any window — and those same O(1) detectors are also the most window-robust.
- **A single 96-byte `unified` detector clears event-F1 ≥ 0.90 on all four controlled anomaly types** at window 30–50 (spike 0.98, drift 0.91, periodicity 1.00, transient 0.98; min 0.91) — once a spike is defined at a detectable ≥ 6σ magnitude and scored with the operationally-fair ±2-sample event metric. It is the top detector by VUS-PR overall.
- **Condition → algorithm map** (each empirical winner matches its design intent): drift → `ewmv_adaptive` (F1 ≈ 0.84), periodicity → `acf_periodicity` (F1 ≈ 0.87), spike and transient → `deriv` (F1 ≈ 0.71 / 0.74).
- **Confirmation gating cuts false positives 50–85 %** (Phase 3) while keeping recall within ~4 points of the best single detector.
- **Scale:** Phase 2 ran 2,880 trials, Phase 3 ran 6,720, and Phase 4 totals roughly 24,800 evaluation runs across its core sweep and improvement studies, with ~180+ tests across the phases and C↔Python parity verified to ≤ 1e-4.
- **Honest limits:** a 4σ single-sample spike is within normal noise and is a proven detection limit for any lightweight causal detector; real mixed, unlabelled-by-type NAB traffic stays below 0.90 — expected for single-metric detection under this budget.

## Tech Stack

- **Languages:** Python 3.10+, C (C99), JavaScript, PowerShell
- **Data / analysis:** NumPy, SciPy, pandas (Phase 2/3), Matplotlib, seaborn, tqdm; Phase 4's evaluation pipeline depends only on NumPy + the Python standard library so it runs on memory-constrained hosts
- **On-device twin:** portable C99 compiled with MinGW-w64 / gcc (`-O2`), benchmarked for ns/sample and state bytes and parity-verified against the Python reference
- **Dashboards:** React 18, Vite, Apache ECharts, `vite-plugin-singlefile` (self-contained build); Plotly is kept only as a legacy fallback report
- **Testing:** pytest (detector contract, injector, window buffer, budget gate, parity)
- **Datasets:** CESNET-TimeSeries24 (Zenodo), Numenta Anomaly Benchmark (NAB)

## Getting Started

### Prerequisites

- Python 3.10+
- A C compiler for the Phase 4 twin — MinGW-w64 / gcc (the build script is PowerShell)
- Node.js 18+ and npm (only if you want to (re)build the dashboards)
- The CESNET sample archive for Phase 2 (download instructions below)

### Installation

```bash
git clone https://github.com/DCode-v05/Network-Telementry.git
cd Network-Telementry

# Phase 2 environment
cd "Phase 2"
python -m venv env
env\Scripts\activate          # Windows
# source env/bin/activate      # macOS / Linux
pip install -r requirements.txt
```

For Phase 2 you also need the CESNET-TimeSeries24 sample (`ip_addresses_sample.tar.gz`, ~171 MB) from its Zenodo release. Extract the per-IP CSVs into `Phase 2/data/ip_addresses_sample/`; if they land under an `agg_10_minutes/` subfolder, point `DATA_DIR` in `Phase 2/config.py` at it.

### Running

```bash
# Phase 2 — single-detector benchmark (2,880 trials)
cd "Phase 2"
python main.py
pytest tests/ -v

# Phase 3 — ensemble benchmark (reuses Phase 2's env + data)
cd "../Phase 3"
python main.py --quick --no_plot --no_dashboard      # ~30s smoke run
python main.py --compare_phase2_csv "../Phase 2/results/csv/aggregated_results.csv"
pytest tests/ -v

# Phase 4 — production build + C twin (self-contained; auto-downloads NAB)
powershell -NoProfile -File "Phase 4\scripts\run_all.ps1"   # data -> sweep -> C build/bench -> selection -> figures -> dashboard -> tests
python -m pytest "Phase 4\tests" -q
```

To stream a single signal through any Phase 4 detector and watch live alerts:

```bash
cd "Phase 4\src\python"
python -m cli.stream_demo --detector deriv --window 50 --synthetic spike
```

## Usage

- **Run a benchmark.** `Phase 2/main.py` runs the full single-detector sweep; `Phase 3/main.py` runs the ensemble sweep and can compare row-for-row against Phase 2 with `--compare_phase2_csv`; `Phase 4/scripts/run_all.ps1` runs the whole production pipeline end to end.
- **Tune it.** Phase 2 sweep and detector parameters live in `Phase 2/config.py`; the Phase 3 ensemble settings (confirmation N, layer membership, voting mode) live in `Phase 3/config.py` and inherit everything else from Phase 2 verbatim.
- **Read the outputs.** Per-trial CSVs land under each phase's `results/csv/`; Phase 4 writes `results/selection.json` (the recommendation), the measured C cost CSV, and `report/Phase4_Report.md`.
- **Explore the dashboards.** Each phase builds a self-contained HTML dashboard you open directly in a browser — Phase 2's "Signal Lab" (KPIs, performance-matrix heatmap, window-sensitivity lines), Phase 3's "Ensemble Command" (architecture diagram, confirmation-gate effect, leaderboard), and Phase 4's accuracy-vs-window / Pareto / cost-budget views.
- **Deploy the C twin.** `Phase 4/src/c/tsad.c` + `tsad.h` is the artifact meant to run on-device — `tsad_init`, `tsad_update(x) -> score`, `tsad_state_bytes`.

## Project Structure

```
Network-Telementry/
├── Phase 1/                          # Algorithm study (theory) + evaluation criteria spec
│   ├── Algorithm_Study_Document.md   # 15 candidates analysed, 6 finalists, 9 rejected
│   └── HPE_Evaluation_Criteria_Specification.md
│
├── Phase 2/                          # Single-detector benchmark on real CESNET traffic
│   ├── src/pipeline/                 # CESNET loader + O(1) Welford sliding-window buffer
│   ├── src/injector/                 # Labelled burst / rate-shift / drift / transient injection
│   ├── src/detectors/                # base.py contract + zscore, mad, ewma, cusum, page_hinkley, …
│   ├── src/evaluation/               # 2,880-trial harness, metrics, plots
│   ├── dashboard/web/                # React + Vite + ECharts "Signal Lab"
│   ├── tests/                        # pipeline / injector / detector tests
│   ├── main.py · config.py · requirements.txt
│
├── Phase 3/                          # Two-layer confirmation-gated ensemble (additive over P2)
│   ├── _phase2_bridge.py             # Re-exports Phase 2 so results stay comparable
│   ├── ensemble/                     # confirmation_gate, voting_layer, two_layer_ensemble
│   ├── evaluation/                   # 6,720-trial harness + gate-FP-reduction metrics
│   ├── dashboard/web/                # React + Vite + ECharts "Ensemble Command"
│   └── tests/                        # gate / voting / ensemble + parametrised base-contract
│
├── Phase 4/                          # Production build: intelligence + lightweight, with a C twin
│   ├── src/python/tsad/              # Detector library (core contract, detectors, ensembles, registry)
│   ├── src/python/eval/              # sweep_runner, metrics_intel, profile_cost, figures (numpy + stdlib)
│   ├── src/python/selection/         # scorecard, pareto, mapping, select -> selection.json
│   ├── src/python/cli/stream_demo.py # Stream a signal through any detector -> live alerts
│   ├── src/c/                        # tsad.c/.h + parity.c + bench.c + build.ps1 (the on-device twin)
│   ├── dashboard/                    # React + Vite + ECharts (accuracy-vs-window, Pareto, cost/budget)
│   ├── results/                      # selection.json, metrics.json, measured C cost
│   ├── report/Phase4_Report.md       # Answers all six problem-statement questions
│   ├── tests/                        # contract, budget gate, C<->Python parity
│   └── scripts/run_all.ps1           # One-shot end-to-end pipeline
│
└── README.md
```

---

## Contact

**Portfolio:** [Denistan](https://www.denistan.me)<br>
**LinkedIn:** [Denistan](https://www.linkedin.com/in/denistanb)<br>
**GitHub:** [DCode-v05](https://github.com/DCode-v05)<br>
**LeetCode:** [Denistan_B](https://leetcode.com/u/Denistan_B)<br>
**Email:** [denistanb05@gmail.com](mailto:denistanb05@gmail.com)

Made with ❤️ by **Denistan B**
