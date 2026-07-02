"""run_demo.py -- stream a telemetry file through the standalone `unified` detector.

Processes the input ONE SAMPLE AT A TIME (via pipeline.stream_detect), prints
per-sample evidence (timestamp, value, score, alert, and whether it lines up
with a true anomaly window), and prints a summary: sample-level TPR / FPR /
precision / F1 plus event-level detection rate and detection latency (in samples).

It also writes a results JSON (per-sample series + summary + events) for the
React dashboard.

Examples (run from Final Pipeline/python):
  python run_demo.py --synthetic                 # the all-4-types synthetic stream
  python run_demo.py --nab nyc_taxi              # one staged NAB stream
  python run_demo.py --all                       # synthetic + all NAB -> results/*.json
  python run_demo.py --input ../data/synthetic_demo.csv --threshold 0.9 --plot

Dependencies: Python stdlib + numpy. --plot additionally needs matplotlib
(optional; skipped with a notice if not installed).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

from unified_detector import UnifiedDetector
from pipeline import csv_row_stream, values_stream, stream_detect
from datasets import load_nab

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))
SYNTH_CSV = os.path.join(DATA, "synthetic_demo.csv")

# Default deployed operating threshold. The detector's internal fusion boundary is
# 1.0, but the drift head is intentionally CLIPPED at DR_CAP = 0.9 so a slow drift
# can never out-shout a spike under max-fusion. A single deployed threshold that
# keeps ALL four heads active (including drift) therefore sits at 0.9. Override
# with --threshold. (Parity and bench compare raw scores, so this is demo-only.)
OPERATING_THRESHOLD = 0.9
# Real (NAB) streams are causally standardized and reported at a label-free
# alert-budget operating point: flag the top (100 - NAB_OP_PERCENTILE)% scores.
NAB_OP_PERCENTILE = 99


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _runs_to_events(labels, atype=None):
    """Contiguous label==1 runs -> list of (type, start, end)."""
    events = []
    i, n = 0, len(labels)
    while i < n:
        if labels[i] == 1:
            j = i
            while j + 1 < n and labels[j + 1] == 1 and (atype is None or atype[j + 1] == atype[i]):
                j += 1
            events.append(((atype[i] if atype else "anomaly"), i, j))
            i = j + 1
        else:
            i += 1
    return events


def sample_metrics(labels, alerts):
    tp = fp = tn = fn = 0
    for l, a in zip(labels, alerts):
        if a and l:
            tp += 1
        elif a and not l:
            fp += 1
        elif not a and l:
            fn += 1
        else:
            tn += 1
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * prec * tpr / (prec + tpr) if (prec + tpr) else 0.0
    return dict(tp=tp, fp=fp, tn=tn, fn=fn, tpr=tpr, fpr=fpr, precision=prec, f1=f1)


def event_detection(events, alerts, tol=2):
    """Per event: detected if any alert within [start, end+tol]; latency = first-start."""
    out = []
    n = len(alerts)
    for (etype, s, e) in events:
        hit = None
        for i in range(s, min(n, e + 1 + tol)):
            if alerts[i]:
                hit = i
                break
        out.append(dict(type=etype, start=s, end=e,
                        detected=hit is not None,
                        latency=(hit - s) if hit is not None else None))
    return out


def average_precision(labels, scores):
    """Threshold-free PR-AUC (rank-based average precision). Scale-invariant."""
    P = sum(labels)
    if P == 0:
        return 0.0
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    tp = fp = 0
    ap = 0.0
    prev_r = 0.0
    for i in order:
        if labels[i]:
            tp += 1
        else:
            fp += 1
        r = tp / P
        p = tp / (tp + fp)
        ap += (r - prev_r) * p
        prev_r = r
    return ap


def _percentile(vals, q):
    """q-th percentile (0-100) of a list -- used for the label-free NAB operating point."""
    s = sorted(vals)
    return s[int((q / 100.0) * (len(s) - 1))]


# ---------------------------------------------------------------------------
# one stream
# ---------------------------------------------------------------------------

def run_stream(name, source_iter, labels, events, atype, threshold, window, max_print, quiet,
               standardize=False, op_percentile=None):
    """Stream one series through the unified detector and score it.

    standardize     -- causally z-score the input before detection (for raw real streams).
    op_percentile   -- if set, the operating threshold is that percentile of the score
                       distribution (a label-free alert budget), instead of `threshold`.
    """
    det = UnifiedDetector(window=window)

    # pass 1: stream and collect raw scores (detection is fully online, one sample at a time)
    rows, scores = [], []
    for smp in stream_detect(det, source_iter, threshold=0.0, standardize=standardize):
        scores.append(smp.score)
        rows.append(dict(i=smp.i, timestamp=smp.timestamp, value=round(smp.value, 4),
                        score=round(smp.score, 5)))

    # choose operating threshold (percentile-based for real streams, else fixed)
    if op_percentile is not None and scores:
        thr = _percentile(scores, op_percentile)
    else:
        thr = det.threshold if threshold is None else float(threshold)

    alerts = [1 if s >= thr else 0 for s in scores]
    for r, a in zip(rows, alerts):
        r["alert"] = a
        r["label"] = int(labels[r["i"]]) if labels is not None else None

    n = len(rows)
    n_alerts = sum(alerts)
    summary = dict(n=n, n_alerts=n_alerts)
    ev_detail = []
    if labels is not None:
        summary["n_anomalous"] = int(sum(labels))
        summary["sample"] = sample_metrics(labels, alerts)
        summary["pr_auc"] = average_precision(labels, scores)
        summary["pr_auc_baseline"] = sum(labels) / len(labels) if labels else 0.0
        ev_detail = event_detection(events, alerts)
        ndet = sum(1 for e in ev_detail if e["detected"])
        lats = [e["latency"] for e in ev_detail if e["detected"]]
        summary["events"] = dict(total=len(ev_detail), detected=ndet,
                                 detection_rate=(ndet / len(ev_detail) if ev_detail else 0.0),
                                 mean_latency=(sum(lats) / len(lats) if lats else None))

    # ---- console evidence ----
    if not quiet:
        print(f"\n=== stream: {name} ===")
        opnote = (f"  [standardized, operating@p{op_percentile}]"
                  if op_percentile is not None else "")
        print(f"detector=unified  window={window}  threshold={thr:.3f}{opnote}  "
              f"state_bytes={det.state_bytes()}")
        print(f"samples={n}  alerts={n_alerts}"
              + (f"  anomalous_samples={summary.get('n_anomalous')}" if labels is not None else ""))
        shown = 0
        for r in rows:
            if not r["alert"]:
                continue
            tag = ""
            if r["label"] is not None:
                tag = "  <-- TRUE anomaly" if r["label"] else "  (false positive)"
            ts = f" t={r['timestamp']}" if r["timestamp"] else ""
            print(f"  ALERT i={r['i']:6d}{ts} value={r['value']:.3f} score={r['score']:.3f}{tag}")
            shown += 1
            if shown >= max_print:
                print(f"  ... ({n_alerts - shown} more alerts suppressed)")
                break
        if labels is not None:
            sm = summary["sample"]
            print(f"  sample-level : TPR={sm['tpr']:.3f}  FPR={sm['fpr']:.3f}  "
                  f"precision={sm['precision']:.3f}  F1={sm['f1']:.3f}  "
                  f"(TP={sm['tp']} FP={sm['fp']} FN={sm['fn']} TN={sm['tn']})")
            print(f"  PR-AUC       : {summary['pr_auc']:.3f}  "
                  f"(random baseline {summary['pr_auc_baseline']:.3f}, threshold-free)")
            ev = summary["events"]
            ml = f"{ev['mean_latency']:.1f}" if ev["mean_latency"] is not None else "n/a"
            print(f"  event-level  : detected {ev['detected']}/{ev['total']} events "
                  f"(rate={ev['detection_rate']:.2f})  mean latency={ml} samples")
            for e in ev_detail:
                lat = f"{e['latency']}" if e["detected"] else "MISS"
                print(f"       {e['type']:12s} [{e['start']},{e['end']}]  "
                      f"{'detected' if e['detected'] else 'missed  '}  latency={lat}")

    result = dict(
        meta=dict(stream=name, detector="unified", window=window, threshold=thr,
                  state_bytes=det.state_bytes(), standardized=bool(standardize),
                  op_percentile=op_percentile),
        summary=summary,
        events=ev_detail,
        series=rows,
    )
    return result


def _load_synthetic():
    labels, atype, ts, vals = [], [], [], []
    with open(SYNTH_CSV, newline="") as f:
        for r in csv.DictReader(f):
            vals.append(float(r["value"]))
            labels.append(int(r["label"]))
            atype.append(r.get("anomaly_type", "") or "anomaly")
            ts.append(r.get("timestamp"))
    events = _runs_to_events(labels, atype)
    return vals, ts, labels, atype, events


def _plot(result, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("  [--plot] matplotlib not installed; skipping plot (JSON + dashboard still produced)")
        return
    series = result["series"]
    xs = [r["i"] for r in series]
    vals = [r["value"] for r in series]
    scs = [r["score"] for r in series]
    thr = result["meta"]["threshold"]
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(11, 5))
    ax1.plot(xs, vals, lw=0.8)
    for e in result["events"]:
        ax1.axvspan(e["start"], e["end"], color="orange", alpha=0.25)
    ax1.set_ylabel("value")
    ax1.set_title(result["meta"]["stream"])
    ax2.plot(xs, scs, lw=0.8, color="crimson")
    ax2.axhline(thr, ls="--", color="k", lw=0.8)
    ax2.set_ylabel("score"); ax2.set_xlabel("sample")
    fig.tight_layout(); fig.savefig(path, dpi=120)
    print(f"  wrote plot {path}")


def main():
    ap = argparse.ArgumentParser(description="Stream a file through the unified detector.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--synthetic", action="store_true", help="use data/synthetic_demo.csv (all 4 types)")
    g.add_argument("--nab", help="run one staged NAB stream by filename substring (e.g. nyc_taxi)")
    g.add_argument("--input", help="stream an arbitrary CSV (needs a 'value' column)")
    g.add_argument("--all", action="store_true", help="synthetic + all NAB -> results/*.json")
    ap.add_argument("--threshold", type=float, default=None, help="override decision threshold")
    ap.add_argument("--window", type=int, default=24)
    ap.add_argument("--max-print", type=int, default=30, help="max ALERT lines to print")
    ap.add_argument("--plot", action="store_true", help="also save a PNG (needs matplotlib)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)

    # default action when nothing specified: synthetic
    if not (args.synthetic or args.nab or args.input or args.all):
        args.synthetic = True

    op_thr = args.threshold if args.threshold is not None else OPERATING_THRESHOLD
    if not args.quiet and args.threshold is None:
        print(f"[operating threshold = {op_thr} (drift head saturates at DR_CAP=0.9; "
              f"override with --threshold)]")

    def do_synthetic():
        vals, ts, labels, atype, events = _load_synthetic()
        res = run_stream("synthetic_demo (all 4 types)", values_stream(vals, ts),
                         labels, events, atype, op_thr, args.window,
                         args.max_print, args.quiet)
        out = os.path.join(RESULTS, "synthetic_results.json")
        json.dump(res, open(out, "w"))
        print(f"  wrote {out}")
        if args.plot:
            _plot(res, os.path.join(RESULTS, "synthetic_plot.png"))
        return res

    def do_nab(sub=None):
        streams = load_nab()
        if not streams:
            print("  no NAB streams staged (run make_demo_data.py first)")
            return []
        picked = [s for s in streams if sub is None or sub in s.meta["name"]]
        # Real streams: causal standardization + a label-free top-1% operating point
        # (fixed thresholds are meaningless across raw scales; PR-AUC is the fair,
        #  threshold-free headline). Override with --threshold if you want a fixed cut.
        nab_thr = args.threshold  # None unless user overrides
        nab_pct = None if args.threshold is not None else NAB_OP_PERCENTILE
        results = []
        for s in picked:
            short = os.path.basename(s.meta["name"])
            res = run_stream(f"NAB {short}", values_stream(s.values),
                             list(int(x) for x in s.labels),
                             [("real", a, b) for (a, b) in s.events],
                             None, nab_thr, args.window, args.max_print, args.quiet,
                             standardize=True, op_percentile=nab_pct)
            results.append(res)
            if args.plot:
                _plot(res, os.path.join(RESULTS, f"nab_{short.replace('.csv','')}.png"))
        return results

    if args.synthetic:
        do_synthetic()
    elif args.nab:
        res = do_nab(args.nab)
        if res:
            json.dump(res, open(os.path.join(RESULTS, "nab_results.json"), "w"))
            print(f"  wrote {os.path.join(RESULTS, 'nab_results.json')}")
    elif args.input:
        name = os.path.basename(args.input)
        res = run_stream(name, csv_row_stream(args.input), None, [], None,
                         op_thr, args.window, args.max_print, args.quiet)
        out = os.path.join(RESULTS, "input_results.json")
        json.dump(res, open(out, "w")); print(f"  wrote {out}")
        if args.plot:
            _plot(res, os.path.join(RESULTS, "input_plot.png"))
    elif args.all:
        syn = do_synthetic()
        nab = do_nab()
        json.dump(nab, open(os.path.join(RESULTS, "nab_results.json"), "w"))
        print(f"  wrote {os.path.join(RESULTS, 'nab_results.json')}")
        # small combined index for the dashboard
        idx = dict(synthetic=syn["meta"] | syn["summary"].get("events", {}),
                   nab=[r["meta"] | r["summary"].get("events", {}) for r in nab])
        json.dump(idx, open(os.path.join(RESULTS, "index.json"), "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
