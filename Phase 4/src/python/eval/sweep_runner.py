"""The evaluation sweep: every detector x window x stream, scored on intelligence +
lightweight cost, aggregated and written for the selection stage and the dashboard.

Outputs (under Phase 4/results/):
  * runs.csv     -- one row per (detector, window, stream) with all intelligence metrics
  * cost.csv     -- one row per (detector, window) with Python cost (C cost merged later)
  * metrics.json -- compact aggregates the dashboard + selection consume

Run:  python -m eval.sweep_runner            (full sweep)
      python -m eval.sweep_runner --quick    (small sweep for smoke tests)
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from datasets.synthetic import make_suite
from datasets.real_loaders import load_nab
from eval.metrics_intel import evaluate
from eval.profile_cost import profile_detector
from eval.tabio import write_csv, group_mean, jsonsafe
import tsad.registry as registry

WINDOWS = [10, 20, 30, 50]
ANOMALY_ORDER = ["spike", "drift", "transient", "periodicity", "real"]
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "results"))

_STREAMS = None


def build_streams(seeds, include_real=True):
    streams = make_suite(seeds=seeds)
    if include_real:
        streams.extend(load_nab())
    return streams


def _init_worker(seeds, include_real):
    global _STREAMS
    _STREAMS = build_streams(seeds, include_real)


def _run_task(args):
    detname, window, idx = args
    s = _STREAMS[idx]
    det = registry.make(detname, window=window)
    scores = det.score_stream(s.values)
    m = evaluate(s.labels, scores, s.events, n=len(s.values))
    rec = dict(detector=detname, window=window, source=s.meta.get("source"),
               anomaly_type=s.meta.get("anomaly_type"), base=s.meta.get("base"),
               seed=s.meta.get("seed"), mag=s.meta.get("mag"),
               stream=s.name, family=registry.family(detname))
    rec.update(m)
    return rec


def _progress(msg):
    """Append a flushed progress line to results/progress.txt (observable mid-run)."""
    try:
        os.makedirs(RESULTS, exist_ok=True)
        with open(os.path.join(RESULTS, "progress.txt"), "a") as f:
            f.write(msg + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass


def _run_serial(tasks, seeds, include_real):
    _init_worker(seeds, include_real)
    _progress(f"serial start: {len(tasks)} runs")
    records = []
    for i, t in enumerate(tasks):
        records.append(_run_task(t))
        if (i + 1) % 500 == 0:
            _progress(f"  {i + 1}/{len(tasks)} runs done")
    _progress(f"serial done: {len(records)} runs")
    return records


def _run_parallel(tasks, seeds, include_real, n_jobs):
    """Parallel sweep; transparently falls back to serial if the process pool dies
    (e.g. Windows commit-limit / BrokenProcessPool)."""
    from concurrent.futures.process import BrokenProcessPool
    records = []
    try:
        with ProcessPoolExecutor(max_workers=n_jobs, initializer=_init_worker,
                                 initargs=(seeds, include_real)) as ex:
            for i, rec in enumerate(ex.map(_run_task, tasks, chunksize=16)):
                records.append(rec)
                if (i + 1) % 2000 == 0:
                    print(f"  ...{i + 1}/{len(tasks)} runs done ({n_jobs} workers)")
        return records
    except (BrokenProcessPool, OSError) as e:
        print(f"[sweep] parallel pool failed ({type(e).__name__}: {e}); falling back to serial")
        return _run_serial(tasks, seeds, include_real)


def measure_costs(detnames, windows, ref_len=600, reps=3):
    """Python cost per (detector, window), measured on a representative stream length."""
    rng = np.random.default_rng(0)
    ref = (50.0 + rng.normal(0, 1.0, size=ref_len)).tolist()
    rows = []
    for detname in detnames:
        for w in windows:
            try:
                c = profile_detector(registry.make_factory(detname, window=w), ref, reps=reps)
            except Exception as e:
                c = {"py_ns_per_sample": float("nan"), "py_ns_p99": float("nan"),
                     "state_bytes": -1, "tracemalloc_bytes": -1, "error": str(e)}
            pyns = c.get("py_ns_per_sample")
            rows.append(dict(detector=detname, window=w, family=registry.family(detname),
                             py_us_per_sample=(pyns / 1000.0 if pyns else None), **c))
    return rows


METRIC_COLS = ["pr_auc", "vus_pr", "f1", "precision", "recall", "event_f1",
               "event_precision", "event_recall", "event_f1_opt", "mcc", "pa_f1",
               "nab", "nab_low_fp", "detected_frac", "latency", "fp_per_1k"]


def aggregate(runs):
    by_dw = group_mean(runs, ["detector", "window", "family"], METRIC_COLS)
    by_dwt = group_mean(runs, ["detector", "window", "anomaly_type"], METRIC_COLS)
    return by_dw, by_dwt


def run_sweep(seeds, windows, include_real=True, n_jobs=None):
    detnames = registry.all_names()
    streams = build_streams(seeds, include_real)
    tasks = [(d, w, i) for d in detnames for w in windows for i in range(len(streams))]
    print(f"[sweep] {len(detnames)} detectors x {len(windows)} windows x "
          f"{len(streams)} streams = {len(tasks)} runs")

    if n_jobs is None:
        n_jobs = max(1, min(4, (os.cpu_count() or 2) - 1))

    records = _run_serial(tasks, seeds, include_real) if n_jobs == 1 else \
        _run_parallel(tasks, seeds, include_real, n_jobs)

    cost = measure_costs(detnames, windows)
    return records, cost


def write_outputs(runs, cost):
    os.makedirs(RESULTS, exist_ok=True)
    write_csv(os.path.join(RESULTS, "runs.csv"), runs)
    write_csv(os.path.join(RESULTS, "cost.csv"), cost)
    by_dw, by_dwt = aggregate(runs)
    write_csv(os.path.join(RESULTS, "agg_detector_window.csv"), by_dw)
    write_csv(os.path.join(RESULTS, "agg_detector_window_type.csv"), by_dwt)

    windows = sorted({r["window"] for r in runs})
    atypes = {r["anomaly_type"] for r in runs}
    payload = jsonsafe({
        "windows": windows,
        "detectors": registry.all_names(),
        "anomaly_types": [t for t in ANOMALY_ORDER if t in atypes],
        "budget": {"max_us": 100.0, "max_bytes": 100},
        "agg_detector_window": by_dw,
        "agg_detector_window_type": by_dwt,
        "cost": cost,
    })
    with open(os.path.join(RESULTS, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[sweep] wrote results to {RESULTS}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small smoke sweep")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--no-real", action="store_true")
    args = ap.parse_args()

    if args.quick:
        seeds = range(2)
        windows = [10, 30]
        include_real = False
    else:
        seeds = range(args.seeds)
        windows = WINDOWS
        include_real = not args.no_real

    runs, cost = run_sweep(seeds, windows, include_real=include_real, n_jobs=args.jobs)
    write_outputs(runs, cost)
    by_dw, _ = aggregate(runs)
    best = {}
    for r in by_dw:
        d, v = r["detector"], (r["vus_pr"] or 0.0)
        if d not in best or v > (best[d]["vus_pr"] or 0.0):
            best[d] = r
    top = sorted(best.values(), key=lambda r: (r["vus_pr"] or 0.0), reverse=True)
    print("\nTop detectors by mean VUS-PR (best window):")
    print(f"{'detector':16s} {'win':>3} {'vus_pr':>7} {'f1':>6} {'mcc':>6} {'latency':>8}")
    for r in top:
        lat = r["latency"]
        lat_s = f"{lat:8.2f}" if isinstance(lat, (int, float)) and lat == lat else f"{'nan':>8}"
        print(f"{r['detector']:16s} {r['window']:>3} {(r['vus_pr'] or 0):7.3f} "
              f"{(r['f1'] or 0):6.3f} {(r['mcc'] or 0):6.3f} {lat_s}")


if __name__ == "__main__":
    main()
