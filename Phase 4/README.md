# Phase 4 — Lightweight Time-Series Anomaly Detection for Network Telemetry

A production-ready, empirically-selected on-device anomaly detector for network telemetry,
built and benchmarked under hard edge constraints: **short observation windows (10–50
samples), < 100 µs/sample, < 100 bytes/metric, basic C arithmetic, streaming one sample at
a time.** Phase 4 builds *multiple* candidate detectors, evaluates them across *multiple
datasets* and *multiple trials* on **both intelligence (accuracy) and lightweight
(CPU/memory)** metrics, then selects the best via Pareto/scorecard analysis — and ships it
as a portable C library plus a Python reference, a CLI demo, an interactive dashboard, and
a report answering all six problem-statement questions.

## What's inside

| Area | Path | Notes |
|---|---|---|
| Detector library (Python reference) | `src/python/tsad/` | 9 single + 3 combined detectors, pure scalar arithmetic |
| On-device twin (C) | `src/c/` | portable C99, double-precision compute, parity-verified |
| Datasets | `src/python/datasets/` | synthetic generators (4 anomaly types) + real NAB loaders |
| Evaluation | `src/python/eval/` | intelligence metrics, cost profiling, sweep runner, figures |
| Selection | `src/python/selection/` | Pareto frontier, scorecard, condition→algorithm map |
| CLI demo | `src/python/cli/stream_demo.py` | stream a CSV → live alerts |
| Dashboard | `dashboard/` | React + Vite + ECharts |
| Tests | `tests/` | detector contract, budget gate, C↔Python parity |
| Report | `report/Phase4_Report.md` | answers Q1–Q6 with evidence |

## The 12 candidate detectors

**Single:** `ewma_z` (EWMA mean+variance z-score), `robust_z` (median+MAD), `hampel`,
`cusum`, `page_hinkley`, `ewmv_adaptive` (EWMA control chart), `deriv` (first-difference),
`acf_periodicity` (lag-k autocorrelation drop), `heavy_baseline` (deliberately heavy, to
show short-window/cost failure).
**Combined:** `layered` (EWMA→CUSUM OR-fusion), `voting` (4-member soft vote), `cascade`
(cheap pre-filter gates an expensive confirm).

## Anomaly types

spike/burst · gradual drift · periodicity loss · transient (microburst) — plus real NAB
streams (mixed mechanisms) for external validity.

## Quick start

```powershell
# one-time: pip install numpy matplotlib pytest ; install MinGW-w64 (gcc) ; (dashboard) npm i
# NOTE: the pipeline deliberately depends only on numpy + stdlib (no pandas) so it runs on
# memory-constrained hosts; matplotlib is used only for the report figures.
# full pipeline: data -> sweep -> C build/bench -> merge -> selection -> figures -> tests
powershell -NoProfile -File scripts\run_all.ps1            # full
powershell -NoProfile -File scripts\run_all.ps1 -Quick     # smoke

# individual stages (run from src/python)
python -m eval.sweep_runner            # evaluation sweep -> results/
python -m selection.select             # choose the best -> results/selection.json
python -m eval.figures                 # report figures -> report/figures/
python -m cli.stream_demo --detector layered --window 20 --synthetic spike

# C twin
powershell -NoProfile -File src\c\build.ps1   # -> src/c/build/{parity,bench}.exe
src\c\build\bench.exe                          # -> results/c_cost.csv

# tests
python -m pytest tests -q
```

## Outputs

- `results/runs.csv` — every (detector × window × stream) with all intelligence metrics
- `results/cost.csv` / `results/c_cost.csv` — Python + C per-sample cost and footprint
- `results/selection.json` — scorecards, Pareto front, condition→algorithm map, recommendation
- `results/metrics.json` — compact aggregates consumed by the dashboard
- `report/figures/*.png` — accuracy-vs-window, Pareto, per-type heatmap, cost charts

## Design principles

1. **Honest lightweight accounting** — detectors use pure scalar arithmetic (no numpy in
   the hot path); the C twin is parity-checked against the Python reference; footprint is
   the float32 deployment model, time is measured on the host and projected to ARM.
2. **Fair, imbalance-aware metrics** — threshold-free PR-AUC / VUS-PR headline; F1/MCC at
   each detector's best operating point; point-adjusted F1 reported only with its caveat.
3. **Budget as a hard gate** — anything over 100 µs or 100 bytes is disqualified regardless
   of accuracy.
