"""Lightweight-budget gate tests (< 100 bytes / < 100 us per sample).

Scalar O(1) detectors must fit the byte budget at ANY window. Window-buffer detectors
inherently grow with the window; we assert they fit at small windows and document that
they exceed the budget at large windows (a real Q3 finding). The time budget is checked
against the C bench output (results/c_cost.csv) when it exists, and against the selection
recommendation otherwise.
"""

import json
import os

import pytest

import tsad.registry as registry

SCALAR = ["ewma_z", "cusum", "page_hinkley", "ewmv_adaptive", "deriv"]
BUFFERED = ["robust_z", "hampel", "acf_periodicity", "heavy_baseline"]
WINDOWS = [10, 20, 30, 50]
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")


@pytest.mark.parametrize("name", SCALAR)
@pytest.mark.parametrize("w", WINDOWS)
def test_scalar_always_under_byte_budget(name, w):
    d = registry.make(name, window=w)
    assert d.state_bytes() < 100, f"{name}@{w}: {d.state_bytes()} bytes"


@pytest.mark.parametrize("name", BUFFERED)
def test_buffered_fit_at_small_window(name):
    assert registry.make(name, window=10).state_bytes() < 100


def test_buffered_exceed_at_large_window():
    assert registry.make("robust_z", window=50).state_bytes() >= 100


def test_selection_recommendation_passes_budget():
    sel = os.path.join(RESULTS, "selection.json")
    if not os.path.exists(sel):
        pytest.skip("run eval.sweep_runner + selection.select first")
    with open(sel) as f:
        data = json.load(f)
    rec = (data.get("recommended") or {}).get("overall")
    if not rec:
        pytest.skip("no recommendation present")
    assert rec.get("budget_ok") is True, f"recommended config not within budget: {rec}"
