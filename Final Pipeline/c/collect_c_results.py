"""Run parity_check.exe + bench.exe, parse their output, write results/c_results.json.

Gives the dashboard the hard C evidence (parity PASS, state_bytes, ns/sample)
without hand-copying numbers. Run after build.ps1 has produced the exes.

Run:  python collect_c_results.py     (from Final Pipeline/c)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))


def _exe(name):
    p = os.path.join(BUILD, name)
    return p if os.path.exists(p) else p + ".exe"


def main():
    parity_exe = _exe("parity_check")
    bench_exe = _exe("bench")
    data = os.path.join(BUILD, "parity_data.txt")
    if not (os.path.exists(parity_exe) and os.path.exists(bench_exe)):
        print("  parity_check/bench not built; run build.ps1 first")
        return 1

    par = subprocess.run([parity_exe, data, "24"], capture_output=True, text=True)
    ben = subprocess.run([bench_exe], capture_output=True, text=True)
    ptxt, btxt = par.stdout, ben.stdout

    def grab(pat, txt, cast=float, default=None):
        m = re.search(pat, txt)
        return cast(m.group(1)) if m else default

    parity = dict(
        passed=("PARITY: PASS" in ptxt),
        max_diff=grab(r"max \|C - Python\|\s*=\s*([0-9.eE+-]+)", ptxt),
        samples=grab(r"samples=(\d+)", ptxt, int),
        state_bytes=grab(r"state_bytes\s*=\s*(\d+)", ptxt, int),
        tolerance=1e-4,
    )

    rows = []
    for m in re.finditer(r"^\s*(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+(OK|OVER)\s*$", btxt, re.M):
        rows.append(dict(window=int(m.group(1)), ns_per_sample=float(m.group(2)),
                         us_per_sample=float(m.group(3)), ok=(m.group(4) == "OK")))
    bench = dict(
        sizeof_struct=grab(r"sizeof\(UnifiedDetector\)\s*=\s*(\d+)", btxt, int),
        state_bytes=grab(r"state_bytes\(\)\s*=\s*(\d+)", btxt, int),
        rows=rows,
        budget_pass=("-> PASS" in btxt or "->  PASS" in btxt),
    )

    out = dict(detector="unified", parity=parity, bench=bench,
               budget=dict(max_us=100, max_bytes=100))
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "c_results.json")
    json.dump(out, open(path, "w"), indent=2)
    print(f"wrote {path}")
    print(f"  parity: {'PASS' if parity['passed'] else 'FAIL'} "
          f"(max_diff={parity['max_diff']})  bench: "
          f"{rows[0]['ns_per_sample'] if rows else '?'} ns/sample  "
          f"state_bytes={bench['state_bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
