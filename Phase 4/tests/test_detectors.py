"""Contract tests for every registered detector (singles + ensembles)."""

import numpy as np
import pytest

import tsad.registry as registry

WINDOW = 20
SHARP_SPIKE = {"ewma_z", "robust_z", "hampel", "deriv",
               "heavy_baseline", "layered", "voting", "cascade"}
SMOOTH_SPIKE = {"ewmv_adaptive"}


def make_spike_stream(n=140, spike_idx=90, mag=22.0, seed=1):
    rng = np.random.default_rng(seed)
    v = 50.0 + rng.normal(0, 1.0, size=n)
    v[spike_idx] += mag
    return v, spike_idx


@pytest.mark.parametrize("name", registry.all_names())
def test_contract(name):
    v, spike = make_spike_stream()
    d = registry.make(name, window=WINDOW)
    scores = []
    for i, x in enumerate(v):
        s = d.update(float(x))
        assert np.isfinite(s) and s >= 0.0, f"{name}: bad score {s} at i={i}"
        scores.append(s)

    for i in range(min(d.warmup, len(scores))):
        assert scores[i] == 0.0, f"{name}: nonzero score {scores[i]} during warm-up i={i}"


@pytest.mark.parametrize("name", sorted(SHARP_SPIKE))
def test_sharp_spike_elevation(name):
    v, spike = make_spike_stream()
    d = registry.make(name, window=WINDOW)
    scores = [d.update(float(x)) for x in v]
    calm = [scores[i] for i in range(d.warmup + 2, len(scores)) if abs(i - spike) > 5]
    calm_ref = float(np.percentile(calm, 90)) if calm else 0.0
    spike_region = max(scores[spike:spike + 6])
    assert spike_region > max(2.0 * calm_ref, 0.5), \
        f"{name}: spike score {spike_region:.3f} did not exceed 2x calm ref {calm_ref:.3f}"


@pytest.mark.parametrize("name", sorted(SMOOTH_SPIKE))
def test_smooth_spike_elevation(name):
    """Smoothing detectors must still put their peak at the spike, just not 2x calm."""
    v, spike = make_spike_stream()
    d = registry.make(name, window=WINDOW)
    scores = [d.update(float(x)) for x in v]
    calm = [scores[i] for i in range(d.warmup + 2, len(scores)) if abs(i - spike) > 5]
    calm_ref = float(np.percentile(calm, 90)) if calm else 0.0
    spike_region = max(scores[spike:spike + 6])
    assert spike_region > calm_ref, \
        f"{name}: spike score {spike_region:.3f} not above calm ref {calm_ref:.3f}"
    assert spike_region >= 0.8 * max(scores), \
        f"{name}: global peak not near the spike"


def test_state_bytes_declared():
    for name in registry.all_names():
        d = registry.make(name, window=WINDOW)
        assert d.state_bytes() > 0
