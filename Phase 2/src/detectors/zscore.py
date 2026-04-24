# src/detectors/zscore.py
# Person 3 owns this file.
#
# Z-Score anomaly detector using Welford's online algorithm for O(1) updates.
# Uses WindowBuffer to maintain a rolling reference window.

from src.detectors.base import DetectorBase, DetectionResult
from src.pipeline.window_buffer import WindowBuffer


class ZScoreDetector(DetectorBase):
    """
    Sliding-window Z-Score anomaly detector.

    Flags a sample as anomalous if:
        |Z| = |(x - μ_window) / σ_window| > threshold

    Parameters
    ----------
    window_size : Number of samples in the reference window.
    threshold   : Z-score magnitude above which a sample is flagged.
                  Typical: 2.5–3.5. From config.py: DETECTORS["zscore"]["threshold"]
    """

    def __init__(self, window_size: int, threshold: float = 3.0):
        self._window_size = window_size
        self._threshold   = threshold
        self._buffer      = WindowBuffer(capacity=window_size)

    @property
    def name(self) -> str:
        return f"ZScore(w={self._window_size}, thr={self._threshold})"

    def update(self, value: float) -> DetectionResult:
        """
        Process one sample.

        Decision logic:
        1. If buffer not full yet: push value, no alarm (insufficient reference).
        2. Compute Z using current window stats.
        3. Push value into buffer (window advances).
        4. Return alarm if |Z| > threshold.
        """
        is_anomaly  = False
        score       = 0.0
        alarm_value = 0.0

        if self._buffer.is_full():
            mu    = self._buffer.mean()
            sigma = self._buffer.std(ddof=1)

            if sigma > 1e-10:
                z           = (value - mu) / sigma
                score       = abs(z)
                alarm_value = z
                is_anomaly  = score > self._threshold
            # If sigma ≈ 0 (constant window), no alarm — value is as flat as baseline

        self._buffer.push(value)

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def reset(self) -> None:
        self._buffer.reset()
