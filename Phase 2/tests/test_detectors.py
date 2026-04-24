# tests/test_detectors.py
# Tests for all 6 detectors.
# Each test verifies:
#   1. The detector can run on a clean signal without false alarms
#   2. The detector fires on an obvious injected anomaly
#   3. reset() truly clears state
#   4. run_on_series() returns one result per sample
# Run: pytest tests/test_detectors.py -v

import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.detectors.zscore              import ZScoreDetector
from src.detectors.mad                 import MADDetector
from src.detectors.ewma                import EWMADetector
from src.detectors.cusum               import CUSUMDetector
from src.detectors.page_hinkley        import PageHinkleyDetector
from src.detectors.sliding_window_stats import SlidingWindowStatsDetector
from src.detectors.base                import DetectionResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_signal():
    """200-sample stationary Gaussian signal."""
    rng = np.random.default_rng(1)
    return rng.normal(0.0, 1.0, 200)


@pytest.fixture
def signal_with_burst():
    """Clean Gaussian with a large burst at position 150."""
    rng = np.random.default_rng(2)
    sig = rng.normal(0.0, 1.0, 200)
    sig[150:154] += 15.0   # Very large spike — all detectors should catch this
    return sig, 150


@pytest.fixture
def signal_with_step():
    """Clean Gaussian with a sustained step shift starting at position 120."""
    rng = np.random.default_rng(3)
    sig = rng.normal(0.0, 1.0, 200)
    sig[120:] += 8.0       # Big step change
    return sig, 120


# ── Helper ────────────────────────────────────────────────────────────────────

def any_alarm_after(results, start_idx, window=20):
    """Return True if any result in [start_idx, start_idx+window) is an alarm."""
    end = min(start_idx + window, len(results))
    return any(r.is_anomaly for r in results[start_idx:end])


def count_alarms(results):
    return sum(1 for r in results if r.is_anomaly)


# ── Z-Score ───────────────────────────────────────────────────────────────────

class TestZScoreDetector:

    def test_returns_detection_result(self, clean_signal):
        det = ZScoreDetector(window_size=20)
        result = det.update(clean_signal[0])
        assert isinstance(result, DetectionResult)
        assert isinstance(result.is_anomaly, bool)
        assert isinstance(result.score, float)

    def test_run_on_series_length(self, clean_signal):
        det = ZScoreDetector(window_size=20)
        results = det.run_on_series(clean_signal)
        assert len(results) == len(clean_signal)

    def test_no_alarms_on_clean_signal(self, clean_signal):
        det = ZScoreDetector(window_size=20, threshold=3.0)
        results = det.run_on_series(clean_signal)
        # Allow at most 5% false alarms — Gaussian tails at threshold=3 can produce
        # occasional alarms on short (N=200) samples; 5% is a realistic budget
        assert count_alarms(results) / len(results) < 0.05

    def test_detects_burst(self, signal_with_burst):
        sig, start = signal_with_burst
        det = ZScoreDetector(window_size=20, threshold=3.0)
        results = det.run_on_series(sig)
        assert any_alarm_after(results, start, window=5)

    def test_name_contains_detector_type(self):
        det = ZScoreDetector(window_size=20)
        assert "ZScore" in det.name

    def test_reset_clears_state(self, clean_signal):
        det = ZScoreDetector(window_size=20)
        det.run_on_series(clean_signal)
        det.reset()
        # After reset, first update should not alarm
        result = det.update(0.0)
        assert not result.is_anomaly

    def test_score_zero_before_window_full(self):
        det = ZScoreDetector(window_size=20)
        for _ in range(19):
            r = det.update(1.0)
            assert r.score == 0.0


# ── MAD ───────────────────────────────────────────────────────────────────────

class TestMADDetector:

    def test_run_on_series_length(self, clean_signal):
        det = MADDetector(window_size=20)
        assert len(det.run_on_series(clean_signal)) == len(clean_signal)

    def test_no_alarms_on_clean_signal(self, clean_signal):
        det = MADDetector(window_size=20, threshold=3.5)
        results = det.run_on_series(clean_signal)
        # Allow up to 5% — MAD on short windows has heavier tails than Z-Score
        assert count_alarms(results) / len(results) < 0.05

    def test_detects_burst(self, signal_with_burst):
        sig, start = signal_with_burst
        det = MADDetector(window_size=20, threshold=3.5)
        results = det.run_on_series(sig)
        assert any_alarm_after(results, start, window=5)

    def test_reset(self, clean_signal):
        det = MADDetector(window_size=20)
        det.run_on_series(clean_signal)
        det.reset()
        assert det._buffer.size() == 0

    def test_name(self):
        assert "MAD" in MADDetector(window_size=10).name


# ── EWMA ──────────────────────────────────────────────────────────────────────

class TestEWMADetector:

    def test_run_on_series_length(self, clean_signal):
        det = EWMADetector(warmup=20)
        assert len(det.run_on_series(clean_signal)) == len(clean_signal)

    def test_no_alarms_during_warmup(self, clean_signal):
        warmup = 20
        det    = EWMADetector(warmup=warmup)
        results = det.run_on_series(clean_signal)
        assert not any(r.is_anomaly for r in results[:warmup])

    def test_detects_step_shift(self, signal_with_step):
        sig, start = signal_with_step
        det = EWMADetector(lambda_=0.3, L=3.0, warmup=30)
        results = det.run_on_series(sig)
        # EWMA should detect the sustained step within 20 samples
        assert any_alarm_after(results, start, window=20)

    def test_detects_burst(self, signal_with_burst):
        sig, start = signal_with_burst
        det = EWMADetector(lambda_=0.5, L=3.0, warmup=20)
        results = det.run_on_series(sig)
        assert any_alarm_after(results, start, window=5)

    def test_reset(self, clean_signal):
        det = EWMADetector(warmup=20)
        det.run_on_series(clean_signal)
        det.reset()
        assert det._n == 0

    def test_invalid_lambda_raises(self):
        with pytest.raises(ValueError):
            EWMADetector(lambda_=0.0)
        with pytest.raises(ValueError):
            EWMADetector(lambda_=1.0)

    def test_name(self):
        assert "EWMA" in EWMADetector().name


# ── CUSUM ─────────────────────────────────────────────────────────────────────

class TestCUSUMDetector:

    def test_run_on_series_length(self, clean_signal):
        det = CUSUMDetector(warmup=20)
        assert len(det.run_on_series(clean_signal)) == len(clean_signal)

    def test_no_alarms_on_clean_signal(self, clean_signal):
        det     = CUSUMDetector(k=0.5, h=5.0, warmup=20)
        results = det.run_on_series(clean_signal)
        assert count_alarms(results) / len(results) < 0.05

    def test_detects_step_shift(self, signal_with_step):
        sig, start = signal_with_step
        det = CUSUMDetector(k=0.5, h=4.0, warmup=30)
        results = det.run_on_series(sig)
        assert any_alarm_after(results, start, window=15)

    def test_accumulator_resets_after_alarm(self, signal_with_step):
        sig, start = signal_with_step
        det = CUSUMDetector(k=0.5, h=4.0, warmup=30)
        for i, v in enumerate(sig):
            r = det.update(float(v))
            if r.is_anomaly:
                # After alarm, accumulators should be zero
                assert det._C_pos == 0.0
                assert det._C_neg == 0.0
                break

    def test_reset(self, clean_signal):
        det = CUSUMDetector(warmup=20)
        det.run_on_series(clean_signal)
        det.reset()
        assert det._C_pos == 0.0 and det._C_neg == 0.0

    def test_name(self):
        assert "CUSUM" in CUSUMDetector().name


# ── Page-Hinkley ──────────────────────────────────────────────────────────────

class TestPageHinkleyDetector:

    def test_run_on_series_length(self, clean_signal):
        det = PageHinkleyDetector(warmup=20)
        assert len(det.run_on_series(clean_signal)) == len(clean_signal)

    def test_detects_step_shift(self, signal_with_step):
        sig, start = signal_with_step
        det = PageHinkleyDetector(delta=0.5, lambda_=30.0, warmup=30)
        results = det.run_on_series(sig)
        assert any_alarm_after(results, start, window=25)

    def test_reset(self, clean_signal):
        det = PageHinkleyDetector(warmup=20)
        det.run_on_series(clean_signal)
        det.reset()
        assert det._ph_up == 0.0 and det._ph_dn == 0.0

    def test_name(self):
        assert "PageHinkley" in PageHinkleyDetector().name


# ── Sliding Window Stats ──────────────────────────────────────────────────────

class TestSlidingWindowStatsDetector:

    def test_run_on_series_length(self, clean_signal):
        det = SlidingWindowStatsDetector(window_size=20)
        assert len(det.run_on_series(clean_signal)) == len(clean_signal)

    def test_detects_burst_via_max(self, signal_with_burst):
        sig, start = signal_with_burst
        det = SlidingWindowStatsDetector(window_size=20, stat="max", threshold=3.0, warmup=40)
        results = det.run_on_series(sig)
        assert any_alarm_after(results, start, window=10)

    def test_get_stats_returns_dict(self, clean_signal):
        det = SlidingWindowStatsDetector(window_size=10)
        for v in clean_signal[:15]:
            det.update(float(v))
        stats = det.get_stats()
        assert "mean" in stats
        assert "variance" in stats
        assert "max" in stats

    def test_invalid_stat_raises(self):
        with pytest.raises(ValueError):
            SlidingWindowStatsDetector(window_size=10, stat="median")

    def test_reset(self, clean_signal):
        det = SlidingWindowStatsDetector(window_size=20)
        det.run_on_series(clean_signal)
        det.reset()
        assert det._buffer.size() == 0
        assert not det._warmup_done

    def test_name(self):
        assert "SlidingWindow" in SlidingWindowStatsDetector(window_size=10).name


# ── Cross-detector: base contract ─────────────────────────────────────────────

class TestBaseContract:
    """Verify every detector satisfies the DetectorBase contract."""

    DETECTORS = [
        ZScoreDetector(window_size=20),
        MADDetector(window_size=20),
        EWMADetector(warmup=20),
        CUSUMDetector(warmup=20),
        PageHinkleyDetector(warmup=20),
        SlidingWindowStatsDetector(window_size=20),
    ]

    @pytest.mark.parametrize("det", DETECTORS)
    def test_has_name(self, det):
        assert isinstance(det.name, str) and len(det.name) > 0

    @pytest.mark.parametrize("det", DETECTORS)
    def test_update_returns_detection_result(self, det):
        det.reset()
        r = det.update(0.5)
        assert isinstance(r, DetectionResult)

    @pytest.mark.parametrize("det", DETECTORS)
    def test_run_on_series_correct_length(self, det, clean_signal):
        det.reset()
        results = det.run_on_series(clean_signal)
        assert len(results) == len(clean_signal)

    @pytest.mark.parametrize("det", DETECTORS)
    def test_reset_is_idempotent(self, det, clean_signal):
        det.run_on_series(clean_signal)
        det.reset()
        det.reset()   # Second reset should not raise
        r = det.update(0.0)
        assert isinstance(r, DetectionResult)
