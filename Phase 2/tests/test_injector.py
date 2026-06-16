
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.injector.anomaly_injector import AnomalyInjector


@pytest.fixture
def clean_signal():
    """Stationary Gaussian signal — a realistic clean baseline."""
    rng = np.random.default_rng(0)
    return rng.normal(loc=0.0, scale=1.0, size=300)


@pytest.fixture
def injector():
    return AnomalyInjector(random_seed=42)


class TestBurstInjection:

    def test_labels_correct_length(self, injector, clean_signal):
        result = injector.inject_burst(clean_signal, magnitude=5.0, duration=3)
        assert len(result.labels) == len(clean_signal)

    def test_labels_mark_injected_region(self, injector, clean_signal):
        result = injector.inject_burst(clean_signal, magnitude=5.0, duration=3)
        s, e = result.inject_start, result.inject_end
        assert np.all(result.labels[s:e] == 1)

    def test_labels_outside_region_are_zero(self, injector, clean_signal):
        result = injector.inject_burst(clean_signal, magnitude=5.0, duration=3)
        s, e = result.inject_start, result.inject_end
        assert np.all(result.labels[:s] == 0)
        assert np.all(result.labels[e:] == 0)

    def test_signal_elevated_in_injected_region(self, injector, clean_signal):
        result = injector.inject_burst(clean_signal, magnitude=5.0, duration=3)
        s, e = result.inject_start, result.inject_end
        diff = result.signal[s:e] - clean_signal[s:e]
        assert np.all(diff > 0)

    def test_signal_unchanged_outside_region(self, injector, clean_signal):
        result = injector.inject_burst(clean_signal, magnitude=5.0, duration=3)
        s, e = result.inject_start, result.inject_end
        np.testing.assert_array_equal(result.signal[:s], clean_signal[:s])
        np.testing.assert_array_equal(result.signal[e:], clean_signal[e:])

    def test_anomaly_type_string(self, injector, clean_signal):
        result = injector.inject_burst(clean_signal)
        assert result.anomaly_type == "burst"

    def test_reproducible_with_seed(self, clean_signal):
        r1 = AnomalyInjector(random_seed=7).inject_burst(clean_signal)
        r2 = AnomalyInjector(random_seed=7).inject_burst(clean_signal)
        assert r1.inject_start == r2.inject_start
        np.testing.assert_array_equal(r1.signal, r2.signal)

    def test_different_seeds_give_different_positions(self, clean_signal):
        starts = set()
        for seed in range(20):
            r = AnomalyInjector(random_seed=seed).inject_burst(clean_signal)
            starts.add(r.inject_start)
        assert len(starts) > 1


class TestRateShiftInjection:

    def test_shift_persists_for_duration(self, injector, clean_signal):
        result = injector.inject_rate_shift(clean_signal, magnitude=3.0, duration=20)
        s, e = result.inject_start, result.inject_end
        diff = result.signal[s:e] - clean_signal[s:e]
        assert np.all(diff > 0)

    def test_duration_matches_label_count(self, injector, clean_signal):
        result = injector.inject_rate_shift(clean_signal, magnitude=3.0, duration=20)
        assert np.sum(result.labels) == 20

    def test_anomaly_type_string(self, injector, clean_signal):
        result = injector.inject_rate_shift(clean_signal)
        assert result.anomaly_type == "rate_shift"


class TestGradualDriftInjection:

    def test_drift_increases_monotonically(self, injector, clean_signal):
        result = injector.inject_gradual_drift(clean_signal, slope=0.2, duration=15)
        s, e = result.inject_start, result.inject_end
        diff = result.signal[s:e] - clean_signal[s:e]
        for i in range(1, len(diff)):
            assert diff[i] > diff[i - 1], f"Drift not monotone at index {i}"

    def test_anomaly_type_string(self, injector, clean_signal):
        result = injector.inject_gradual_drift(clean_signal)
        assert result.anomaly_type == "gradual_drift"


class TestTransientInjection:

    def test_exactly_one_anomalous_sample(self, injector, clean_signal):
        result = injector.inject_transient(clean_signal, magnitude=6.0)
        assert np.sum(result.labels) == 1

    def test_anomaly_type_string(self, injector, clean_signal):
        result = injector.inject_transient(clean_signal)
        assert result.anomaly_type == "transient"

    def test_single_sample_elevated(self, injector, clean_signal):
        result = injector.inject_transient(clean_signal, magnitude=6.0)
        s = result.inject_start
        assert result.signal[s] > clean_signal[s]


class TestDispatch:

    def test_dispatch_all_types(self, injector, clean_signal):
        for atype in ["burst", "rate_shift", "gradual_drift", "transient"]:
            result = injector.inject(clean_signal, atype, {})
            assert result.anomaly_type == atype

    def test_dispatch_unknown_type_raises(self, injector, clean_signal):
        with pytest.raises(ValueError):
            injector.inject(clean_signal, "unknown_type", {})

    def test_too_short_signal_raises(self, injector):
        short = np.ones(50)
        with pytest.raises(ValueError):
            injector.inject_burst(short, duration=3)
