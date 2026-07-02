"""Generate the parity fixture: identical input + the Python reference scores.

Writes c/build/parity_data.txt with one "value  py_score" pair per line. The C
parity_check reads this file, streams the SAME values through the C twin, and
asserts its scores match `py_score` to <= 1e-4.

Parity is a test of the DETECTOR, so raw values are used (no standardization).
Coverage: the all-4-types synthetic stream (unit scale) plus a slice of a raw
NAB stream (thousands scale) to stress the maths across very different scales.

Run:  python parity_gen.py        (from Final Pipeline/c)
"""

from __future__ import annotations

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))

from unified_detector import UnifiedDetector  # noqa: E402

DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
BUILD = os.path.join(HERE, "build")
WINDOW = 24


def _read_value_col(path, limit=None):
    out = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        col = "value" if "value" in cols else cols[-1]
        for row in reader:
            try:
                out.append(float(row[col]))
            except (ValueError, TypeError, KeyError):
                continue
            if limit and len(out) >= limit:
                break
    return out


def main():
    os.makedirs(BUILD, exist_ok=True)
    values = _read_value_col(os.path.join(DATA, "synthetic_demo.csv"))
    # append a slice of the first staged NAB stream as a different-scale parity stress
    import glob
    nab_csvs = sorted(glob.glob(os.path.join(DATA, "nab_streams", "*", "*.csv")))
    if nab_csvs:
        values += _read_value_col(nab_csvs[0], limit=600)

    det = UnifiedDetector(window=WINDOW)
    out_path = os.path.join(BUILD, "parity_data.txt")
    with open(out_path, "w") as f:
        for x in values:
            s = det.update(float(x))
            f.write(f"{x!r} {s!r}\n")
    print(f"wrote {out_path}  ({len(values)} samples, window={WINDOW})")


if __name__ == "__main__":
    main()
