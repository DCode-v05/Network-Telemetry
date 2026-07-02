# Unified Detector — Standalone On-Device Anomaly Detector

A single **96-byte** streaming time-series anomaly detector that covers **four
anomaly types** (spike, drift, periodicity loss, transient) in one unit, with a
**parity-verified C99 twin**, a **JS twin**, and a **live interactive dashboard**
where the detector runs in-browser sample-by-sample. Extracted from the Phase 4
research repo as a self-contained final deliverable.

The detector is one streaming unit with three internal heads sharing a single
state block, fused by `max`:

| head | statistic | catches |
|------|-----------|---------|
| 1 · derivative | first-difference z-score, anomaly-aware **HOLD** baseline | spike, transient |
| 2 · EWMA control-chart | held EWMA vs shared windowed σ, output **CLIPPED at 0.9** | drift |
| 3 · gated ACF-drop | lag-k autocorrelation drop, **armed only** when periodic | periodicity loss |

`score = max(head1, head2, head3)`, alert when `score >= threshold`.

## Verified results (this package, reproducible)

- **Footprint:** `state_bytes() = 96` (5 float scalars + 17-deep ring buffer + int counters) — **< 100-byte budget**.
- **Speed:** **~55 ns/sample** measured in C (`QueryPerformanceCounter`) — ~1800× under the 100 µs budget.
- **Python ↔ C ↔ JS parity:** **max |Δ| = 0.000e+00** over 1560 samples (tolerance 1e-4) — the detector is bit-for-bit identical in all three languages, so the live in-browser dashboard runs the *same* algorithm as the C twin.
- **Synthetic (all 4 types, one stream):** sample **F1 = 0.822**, PR-AUC 0.692, **5/5 events detected**, mean latency 4.8 samples.
- **Real NAB:** speed_7578 **4/4** windows (PR-AUC 1.7×), machine_temperature **4/4** @ 0.9 % FPR, ec2_latency **3/3** — every labelled failure window flagged at < 1 % FPR.

## Layout

```
Final Pipeline/
├── python/
│   ├── unified_detector.py   # standalone UnifiedDetector: init / update(x)->score / state_bytes()
│   ├── datasets.py           # vendored injectors + synthetic generators + NAB loader (from Phase 4)
│   ├── pipeline.py           # one-sample-at-a-time streaming generator + causal standardizer
│   ├── run_demo.py           # CLI: stream a file, print per-sample evidence + TPR/FPR/F1/latency, write results JSON
│   ├── make_demo_data.py     # build synthetic_demo.csv (all 4 types) + stage 3 NAB streams (read-only)
│   └── export_streams.py     # export raw streams -> dashboard/public/data/streams.json (for the live UI)
├── c/
│   ├── unified.h / unified.c # C99 twin: unified_init / unified_update / unified_state_bytes
│   ├── parity_check.c        # asserts C scores == Python scores (PASS/FAIL, max |Δ|)
│   ├── parity_gen.py         # writes the parity fixture from the Python reference
│   ├── bench.c               # measured ns/sample + budget gate (state_bytes<100, time<100µs)
│   ├── score_cli.c           # stdin values -> scores (the C engine the server invokes)
│   ├── collect_c_results.py  # runs the exes -> results/c_results.json (for the dashboard)
│   └── build.ps1             # compile parity + bench + score_cli (MinGW-w64 gcc -O2 -std=c99)
├── data/
│   ├── synthetic_demo.csv    # generated: all 4 anomaly types with known labels
│   └── nab_streams/          # 3 real labelled NAB CSVs + combined_windows.json
├── results/                  # generated: synthetic_results.json, nab_results.json, c_results.json
├── dashboard/                # React + Vite + ECharts multi-page app (Vercel theme, dual light/dark)
│   ├── src/pages/            #   Overview · Problem&Theory · Architecture · Live Pipeline · Evaluation · Source
│   └── src/lib/unified.js     #   the detector ported to JS (parity-verified) — runs live in the browser
├── server.py                 # engine server (stdlib) for the Live Pipeline's Python/C engines
├── run_all.ps1               # one-shot: data -> Python demo -> C build+verify -> collect -> exports -> sync
└── README.md
```

The `python/` folder also has three dashboard exporters: `export_streams.py` (raw
streams for the live page), `export_eval.py` (the 40-detector cross-phase catalogue),
and `export_source.py` (the Python/C/JS source for the code viewer).

## Quick start

### One-shot (Windows / PowerShell)
```powershell
cd "Final Pipeline"
powershell -NoProfile -File run_all.ps1      # data -> demo -> C parity+bench -> sync dashboard data
cd dashboard
npm install                                   # first time only
npm run dev                                    # open the printed http://localhost:5173/ URL
```

### Step by step
```powershell
# 1. generate demo data (synthetic all-4-types + stage 3 NAB streams, read-only)
python python\make_demo_data.py

# 2. stream through the detector one sample at a time -> results/*.json
python python\run_demo.py --all              # synthetic + all NAB
python python\run_demo.py --synthetic        # just the all-4-types stream
python python\run_demo.py --nab speed_7578   # a single NAB stream
python python\run_demo.py --input data\synthetic_demo.csv --threshold 0.9 --plot

# 3. build + verify the C twin (parity PASS + bench ns/sample + budget gate)
powershell -NoProfile -File c\build.ps1
python c\collect_c_results.py                # -> results/c_results.json

# 4. dashboard data + launch
python python\export_streams.py                 # raw streams -> live page
python python\export_eval.py                     # 40-detector catalogue -> Evaluation page
python python\export_source.py                   # Python/C/JS source -> Source page
powershell -NoProfile -File dashboard\sync_data.ps1
cd dashboard ; npm install ; npm run dev        # open http://localhost:5173/
```

### The dashboard (multi-page explainer)
A production-grade **Vercel-themed** app (Geist Sans + Geist Mono, **dual light/dark**
that defaults to the browser setting) with a sidebar and six pages:

- **Overview** — headline numbers and quick nav.
- **Problem & Theory** — the on-device constraint (< 100 µs / < 100 B / 10–50 samples) and the four anomaly types explained with sparklines.
- **Architecture** — the unified detector diagram: three heads, the shared 96-byte state, and exactly which head detects which anomaly.
- **Live Pipeline** — pick an input **and an engine (JS / Python / C)**, hit **▶ stream**, and watch the detector process it **one sample at a time**: value+score traces draw live, alerts fire, the **three head VU meters** light up to show which head caught each anomaly, and recall/FPR/F1/latency update continuously. Transport, threshold slider, and window are interactive.
- **Evaluation** — the **40 detectors across Phase 2/3/4**, with a sortable Phase 4 leaderboard, the intelligence-vs-cost budget gate, the condition→algorithm map, and **why `unified` was chosen** (highest budget-passing VUS-PR, all four types, 96 B).

### Live Pipeline engines (JS / Python / C)
The Live Pipeline can execute the detector in three languages:
- **JS** runs entirely in the browser (no setup) — the parity-verified JS twin.
- **Python** and **C** run on a tiny local **engine server** (`server.py`, Python
  stdlib only): Python imports the real detector; C pipes the signal through the
  compiled `score_cli.exe`. Start it with `python server.py` (port 8008); the UI
  auto-detects it. All three engines produce identical scores (parity Δ = 0), and
  the UI shows the real per-engine execution time.

## Requirements
- **Python 3.10+** with **numpy** (the only third-party dep). `--plot` optionally uses matplotlib (skipped if absent).
- **C:** MinGW-w64 gcc (`build.ps1` pins the WinLibs UCRT path — edit `$mingw` if yours differs).
- **Dashboard:** Node 18+ / npm.

## Notes on the numbers (honest framing)
- **Operating threshold.** The fusion boundary is 1.0, but the drift head is intentionally **clipped at 0.9** so a slow drift can’t out-shout a spike. The single deployed threshold that keeps all four heads active is therefore **0.9** (the synthetic demo default). Override with `--threshold`.
- **Real data.** Raw NAB streams arrive on wildly different scales, so they are **z-scored causally** (running Welford, one sample at a time) before detection, and reported at a **label-free top-1 % operating point** plus the **threshold-free PR-AUC** — the fair metric for rare anomalies on raw univariate data. A streaming change-detector flags anomaly *onsets*, so event-level detection is the primary metric; sample-level recall on long sustained regions is naturally lower. The three streams were chosen empirically from NAB (PR-AUC lift ≥ 1.4×); nyc_taxi was excluded because its anomalies are subtle daily-seasonality shifts (period ≈ 48) beyond a 17-sample-buffer detector’s reach.
- **Precision vs footprint (C).** The C compute path is **double precision** (so parity vs float64 Python is exact); the 96-byte figure is the **float32 on-device state model** reported by `unified_state_bytes()`. `sizeof(struct)` (248 B) is the double working struct — the two are decoupled by design, exactly as in the Phase 4 twin.

## Provenance
Extracted read-only from `Phase 4/` of the Network-Telemetry research repo:
- detector math ← `src/python/tsad/ensembles/unified.py` (byte-for-byte score parity verified)
- injectors / synthetic / NAB loader ← `src/python/datasets/`
- C idioms ← `src/c/tsad.c` (the `unified` detector itself had no C twin in the repo; it is ported fresh here).
The original Phase 4 codebase is **not modified** by anything in this package.
