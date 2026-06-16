"""Streaming detection demo: feed a telemetry stream one sample at a time, emit alerts.

Examples (run from Phase 4/src/python):
  python -m cli.stream_demo --detector layered --window 20 --synthetic spike
  python -m cli.stream_demo --detector robust_z --window 20 \
         --input ../../data/real/nab/realTraffic/speed_7578.csv --json out.json

Mirrors how the on-device C twin would run: O(1)/O(window) per sample, no look-ahead.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import numpy as np

import tsad.registry as registry
from datasets.synthetic import make_stream


def load_values(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        col = "value" if "value" in cols else cols[-1]
        vals = []
        for row in reader:
            try:
                vals.append(float(row[col]))
            except (ValueError, TypeError, KeyError):
                continue
    return np.asarray(vals, dtype=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default="layered", choices=registry.all_names())
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--threshold", type=float, default=None,
                    help="override the detector's default decision threshold")
    ap.add_argument("--input", help="CSV with a 'value' column")
    ap.add_argument("--synthetic", help="anomaly type for a synthetic demo stream",
                    choices=["spike", "drift", "transient", "periodicity"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", help="write per-sample {value,score,alert,label} JSON here")
    args = ap.parse_args()

    labels = events = None
    if args.input:
        values = load_values(args.input)
        name = os.path.basename(args.input)
    else:
        atype = args.synthetic or "spike"
        s = make_stream(atype, "periodic" if atype == "periodicity" else "flat",
                        seed=args.seed)
        values, labels, events = s.values, s.labels, s.events
        name = s.name

    det = registry.make(args.detector, window=args.window)
    thr = args.threshold if args.threshold is not None else det.threshold

    rows, n_alerts = [], 0
    for i, x in enumerate(values):
        score = det.update(float(x))
        alert = int(score >= thr)
        n_alerts += alert
        rows.append({"i": i, "value": float(x), "score": round(float(score), 5),
                     "alert": alert, "label": int(labels[i]) if labels is not None else None})

    print(f"stream={name}  detector={args.detector}  window={args.window}  thr={thr}")
    print(f"samples={len(values)}  alerts={n_alerts}")
    shown = 0
    for r in rows:
        if r["alert"]:
            tag = ""
            if r["label"] is not None:
                tag = "  <-- TRUE anomaly" if r["label"] else "  (false positive?)"
            print(f"  ALERT i={r['i']:5d} value={r['value']:.3f} score={r['score']:.3f}{tag}")
            shown += 1
            if shown >= 40:
                print("  ... (more alerts suppressed)")
                break

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"meta": {"stream": name, "detector": args.detector,
                                "window": args.window, "threshold": thr},
                       "series": rows}, f)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
