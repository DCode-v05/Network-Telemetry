"""Tiny CSV / table helpers (stdlib only) -- replaces pandas in the pipeline.

pandas 3.x eager-imports pyarrow, which stalls badly on memory-constrained hosts; the
whole pipeline therefore depends only on numpy + the standard library. These helpers cover
the few things we used pandas for: CSV read/write, group-by-mean, and JSON-safe cleaning.
"""

from __future__ import annotations

import csv
import math
import os
from collections import OrderedDict


def _coerce(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        return v
    if math.isnan(f):
        return None
    if f.is_integer() and "." not in str(v) and "e" not in str(v).lower():
        return int(f)
    return f


def read_csv(path, numeric=True):
    with open(path, newline="") as f:
        rows = [dict(r) for r in csv.DictReader(f)]
    if numeric:
        for r in rows:
            for k in list(r.keys()):
                r[k] = _coerce(r[k])
    return rows


def write_csv(path, rows, columns=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if columns is None:
        columns = []
        for r in rows:
            for k in r:
                if k not in columns:
                    columns.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})


def group_mean(rows, group_keys, value_keys):
    """Group rows by group_keys and average value_keys (ignoring None/NaN)."""
    groups = OrderedDict()
    for r in rows:
        key = tuple(r.get(k) for k in group_keys)
        if key not in groups:
            groups[key] = {vk: [] for vk in value_keys}
        for vk in value_keys:
            v = r.get(vk)
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                groups[key][vk].append(v)
    out = []
    for key, acc in groups.items():
        d = dict(zip(group_keys, key))
        for vk in value_keys:
            vals = acc[vk]
            d[vk] = sum(vals) / len(vals) if vals else None
        out.append(d)
    return out


def jsonsafe(obj):
    """Recursively replace NaN/Inf with None so json.dump emits valid JSON for browsers."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: jsonsafe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonsafe(v) for v in obj]
    return obj
