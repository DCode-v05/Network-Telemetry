"""Export raw input streams for the LIVE dashboard.

Writes dashboard/public/data/streams.json = the raw telemetry (values + ground
truth) for every selectable input. The browser runs the JS `unified` detector
over these one sample at a time, so scores/alerts/metrics are computed LIVE in
the UI (nothing is pre-scored here -- only the raw signal + labels are shipped).

Run:  python export_streams.py     (from Final Pipeline/python)
"""

from __future__ import annotations

import csv
import json
import os

from datasets import load_nab

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
OUT = os.path.normpath(os.path.join(HERE, "..", "dashboard", "public", "data", "streams.json"))

# nicer display names + per-stream live defaults
NAB_INFO = {
    "speed_7578.csv":                              ("Traffic speed sensor (NAB speed_7578)", 2.0),
    "machine_temperature_system_failure.csv":      ("Machine temperature — system failure (NAB)", 1.5),
    "ec2_request_latency_system_failure.csv":      ("EC2 request latency — system failure (NAB)", 2.5),
}


def _runs_to_events(labels, atype):
    events, i, n = [], 0, len(labels)
    while i < n:
        if labels[i] == 1:
            j = i
            while j + 1 < n and labels[j + 1] == 1 and atype[j + 1] == atype[i]:
                j += 1
            events.append({"type": atype[i] or "anomaly", "start": i, "end": j})
            i = j + 1
        else:
            i += 1
    return events


def load_synthetic():
    vals, labels, atype = [], [], []
    with open(os.path.join(DATA, "synthetic_demo.csv"), newline="") as f:
        for r in csv.DictReader(f):
            vals.append(round(float(r["value"]), 4))
            labels.append(int(r["label"]))
            atype.append(r.get("anomaly_type", "") or "anomaly")
    return {
        "id": "synthetic",
        "name": "Synthetic — all four anomaly types",
        "kind": "synthetic",
        "unit": "telemetry value",
        "window": 24,
        "standardize": False,
        "defaultThreshold": 0.9,
        "values": vals,
        "labels": labels,
        "events": _runs_to_events(labels, atype),
    }


def main():
    streams = [load_synthetic()]
    for s in load_nab():
        fname = os.path.basename(s.meta["name"])
        name, thr = NAB_INFO.get(fname, (fname, 2.0))
        streams.append({
            "id": fname.replace(".csv", ""),
            "name": name,
            "kind": "nab",
            "unit": "value",
            "window": 24,
            "standardize": True,
            "defaultThreshold": thr,
            "values": [round(float(v), 4) for v in s.values],
            "labels": [int(x) for x in s.labels],
            "events": [{"type": "real", "start": int(a), "end": int(b)} for (a, b) in s.events],
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"streams": streams}, open(OUT, "w"))
    total = sum(len(s["values"]) for s in streams)
    print(f"wrote {OUT}")
    for s in streams:
        print(f"  {s['id']:34s} {len(s['values']):6d} samples  {len(s['events'])} event(s)  "
              f"standardize={s['standardize']}  thr={s['defaultThreshold']}")
    print(f"  total {total} samples, {os.path.getsize(OUT)//1024} KB")


if __name__ == "__main__":
    main()
