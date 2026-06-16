"""C <-> Python numerical parity.

Contract the C library must satisfy (WF-C builds to this):
  * An executable ``parity`` (parity.exe on Windows) at  Phase 4/src/c/build/parity[.exe]
  * Usage:  parity <detector_slug> <window>
            reads whitespace/newline-separated float values from stdin,
            prints exactly one anomaly score per input value to stdout.
  * The C compute path uses double precision so it matches the float64 Python reference
    to within 1e-4 (the < 100 byte deployment footprint is the float32 model, reported
    separately by the bench -- precision and footprint are decoupled by design).

Skips cleanly if the binary has not been built yet.
"""

import os
import subprocess

import numpy as np
import pytest

import tsad.registry as registry

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "src", "c", "build")
SINGLES = ["ewma_z", "robust_z", "hampel", "cusum", "page_hinkley",
           "ewmv_adaptive", "deriv", "acf_periodicity", "heavy_baseline"]
TOL = 1e-4


def _exe():
    for cand in ("parity.exe", "parity"):
        p = os.path.join(BUILD, cand)
        if os.path.exists(p):
            return p
    return None


@pytest.mark.parametrize("name", SINGLES)
def test_parity(name):
    exe = _exe()
    if not exe:
        pytest.skip("C parity binary not built (run scripts/build_c.ps1)")
    rng = np.random.default_rng(3)
    vals = 50.0 + rng.normal(0, 1.0, size=200)
    vals[60] += 18.0
    vals[120:140] += 6.0  # a sustained shift to exercise change-point detectors
    d = registry.make(name, window=20)
    py = [d.update(float(x)) for x in vals]

    inp = "\n".join(repr(float(x)) for x in vals)
    out = subprocess.run([exe, name, "20"], input=inp, capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, f"{name}: C exited {out.returncode}: {out.stderr}"
    cs = [float(t) for t in out.stdout.split()]
    assert len(cs) == len(py), f"{name}: C produced {len(cs)} scores, expected {len(py)}"
    diff = max(abs(a - b) for a, b in zip(py, cs))
    assert diff < TOL, f"{name}: max |C-Py| = {diff:.2e} exceeds {TOL}"
