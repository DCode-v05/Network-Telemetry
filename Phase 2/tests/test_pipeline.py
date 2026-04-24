# tests/test_pipeline.py
# Tests for WindowBuffer and the loader interface.
# Run: pytest tests/test_pipeline.py -v

import pytest
import numpy as np
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline.window_buffer import WindowBuffer


class TestWindowBuffer:

    def test_basic_push_and_size(self):
        buf = WindowBuffer(capacity=5)
        assert buf.size() == 0
        buf.push(1.0)
        assert buf.size() == 1
        assert not buf.is_full()

    def test_is_full(self):
        buf = WindowBuffer(capacity=3)
        buf.push(1.0); buf.push(2.0); buf.push(3.0)
        assert buf.is_full()
        assert buf.size() == 3

    def test_mean_simple(self):
        buf = WindowBuffer(capacity=4)
        for v in [1.0, 2.0, 3.0, 4.0]:
            buf.push(v)
        assert abs(buf.mean() - 2.5) < 1e-9

    def test_mean_after_eviction(self):
        # Push 5 values into capacity-4 buffer; oldest should be evicted
        buf = WindowBuffer(capacity=4)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            buf.push(v)
        # Window should now contain [2, 3, 4, 5]
        assert abs(buf.mean() - 3.5) < 1e-9

    def test_variance_single_value(self):
        buf = WindowBuffer(capacity=5)
        buf.push(3.0)
        assert buf.variance() == 0.0

    def test_variance_known_values(self):
        buf = WindowBuffer(capacity=4)
        for v in [2.0, 4.0, 4.0, 4.0]:
            buf.push(v)
        # Sample variance = ((2-3.5)^2 + (4-3.5)^2*3) / 3 — use numpy as reference
        expected = float(np.var([2.0, 4.0, 4.0, 4.0], ddof=1))
        assert abs(buf.variance(ddof=1) - expected) < 1e-9

    def test_std_matches_sqrt_variance(self):
        buf = WindowBuffer(capacity=5)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            buf.push(v)
        assert abs(buf.std() - np.sqrt(buf.variance())) < 1e-9

    def test_to_array_oldest_first(self):
        buf = WindowBuffer(capacity=3)
        buf.push(10.0); buf.push(20.0); buf.push(30.0)
        arr = buf.to_array()
        np.testing.assert_array_almost_equal(arr, [10.0, 20.0, 30.0])

    def test_to_array_after_wraparound(self):
        buf = WindowBuffer(capacity=3)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            buf.push(v)
        arr = buf.to_array()
        # Should contain [3, 4, 5] — oldest first
        np.testing.assert_array_almost_equal(arr, [3.0, 4.0, 5.0])

    def test_min_max(self):
        buf = WindowBuffer(capacity=5)
        for v in [3.0, 1.0, 4.0, 1.0, 5.0]:
            buf.push(v)
        assert buf.minimum() == 1.0
        assert buf.maximum() == 5.0

    def test_reset_clears_state(self):
        buf = WindowBuffer(capacity=3)
        buf.push(1.0); buf.push(2.0); buf.push(3.0)
        buf.reset()
        assert buf.size() == 0
        assert not buf.is_full()
        assert buf.mean() == 0.0

    def test_welford_numerical_stability(self):
        # Large values — check that Welford doesn't accumulate float error
        buf = WindowBuffer(capacity=10)
        vals = [1e8 + i * 0.1 for i in range(10)]
        for v in vals:
            buf.push(v)
        expected_mean = float(np.mean(vals))
        assert abs(buf.mean() - expected_mean) < 1e-3

    def test_capacity_minimum(self):
        with pytest.raises(ValueError):
            WindowBuffer(capacity=1)

    def test_median(self):
        buf = WindowBuffer(capacity=5)
        for v in [1.0, 3.0, 2.0, 5.0, 4.0]:
            buf.push(v)
        assert abs(buf.median() - 3.0) < 1e-9
