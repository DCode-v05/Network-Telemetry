"""Load downloaded real NAB streams into the common Stream container (stdlib + numpy).

NAB labels are anomaly *windows* (timestamp ranges) in ``combined_windows.json`` keyed by
the file's relative path. We map each window to an inclusive index range -> ``events`` and
mark those samples 1 in ``labels``. Real streams carry mixed/unknown anomaly mechanisms,
so they are bucketed as anomaly_type == "real" for external-validity reporting.

(No pandas: pandas 3.x eager-imports pyarrow which stalls on this host. Plain csv +
datetime is enough and fast.)
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime

import numpy as np

from .synthetic import Stream

HERE = os.path.dirname(os.path.abspath(__file__))
NAB_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "data", "real", "nab"))

_TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
               "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d")


def _parse_ts(s):
    s = (s or "").strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _read_csv(path):
    timestamps, values = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "value" not in reader.fieldnames:
            return None, None
        for row in reader:
            try:
                values.append(float(row["value"]))
            except (ValueError, TypeError, KeyError):
                continue
            timestamps.append(_parse_ts(row.get("timestamp", "")))
    return timestamps, np.asarray(values, dtype=float)


def _windows_to_events(timestamps, windows):
    events = []
    for win in windows:
        a, b = _parse_ts(win[0]), _parse_ts(win[1])
        if a is None or b is None:
            continue
        idx = [i for i, t in enumerate(timestamps) if t is not None and a <= t <= b]
        if idx:
            events.append((idx[0], idx[-1]))
    return events


def load_nab(nab_dir=NAB_DIR):
    """Return list[Stream] for every successfully downloaded + labelled NAB file."""
    labels_path = os.path.join(nab_dir, "combined_windows.json")
    if not os.path.exists(labels_path):
        return []
    with open(labels_path) as f:
        all_windows = json.load(f)

    streams = []
    for rel, windows in all_windows.items():
        path = os.path.join(nab_dir, rel.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        timestamps, values = _read_csv(path)
        if values is None or len(values) == 0:
            continue
        n = len(values)
        labels = np.zeros(n, dtype=int)
        events = _windows_to_events(timestamps, windows)
        for (s, e) in events:
            labels[s:e + 1] = 1
        family = rel.split("/")[0]
        meta = dict(source="nab", anomaly_type="real", base=family,
                    name=rel, n=n, seed=0, mag="real",
                    anomaly_ratio=float(labels.mean()))
        if labels.sum() > 0:    # need at least one labelled anomaly to score against
            streams.append(Stream(values, labels, events, meta))
    return streams


if __name__ == "__main__":
    ss = load_nab()
    print(f"loaded {len(ss)} NAB streams")
    for s in ss[:8]:
        print(f"  {s.meta['name']:55s} len={len(s.values)} "
              f"anomalies={int(s.labels.sum())} events={len(s.events)}")
