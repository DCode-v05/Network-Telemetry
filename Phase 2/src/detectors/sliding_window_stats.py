# src/detectors/sliding_window_stats.py
import numpy as np
from src.detectors.base import DetectorBase, DetectionResult
from src.pipeline.window_buffer import WindowBuffer


class SlidingWindowStatsDetector(DetectorBase):
    """
    Sliding window statistics detector.

    Tracks a chosen statistic (mean, variance, or max) over a rolling window
    and compares it against a baseline computed during warmup.

    Parameters
    ----------
    window_size : Window size N.
    stat        : Statistic to monitor: "mean" | "variance" | "max"
    threshold   : How many baseline-std units of deviation triggers an alarm.
    warmup      : Samples used to estimate expected stat baseline.
    """

    VALID_STATS = ("mean", "variance", "max")

    def __init__(
        self,
        window_size: int,
        stat:        str   = "mean",
        threshold:   float = 3.0,
        warmup:      int   = 30,
    ):
        if stat not in self.VALID_STATS:
            raise ValueError(f"stat must be one of {self.VALID_STATS}, got '{stat}'")

        self._window_size = window_size
        self._stat        = stat
        self._threshold   = threshold
        self._warmup      = warmup
        self._buffer      = WindowBuffer(capacity=window_size)

        self._stat_mean   = 0.0
        self._stat_std    = 1.0
        self._n           = 0
        self._warmup_done = False
        self._warmup_vals = []

    @property
    def name(self) -> str:
        return f"SlidingWindow({self._stat}, w={self._window_size}, thr={self._threshold})"

    def update(self, value: float) -> DetectionResult:
        self._buffer.push(value)
        self._n += 1

        if not self._buffer.is_full():
            return DetectionResult(is_anomaly=False, score=0.0, alarm_value=0.0)

        current_stat = self._compute_stat()

        if not self._warmup_done:
            self._warmup_vals.append(current_stat)
            if self._n >= self._warmup + self._window_size:
                vals             = np.array(self._warmup_vals, dtype=np.float64)
                self._stat_mean  = float(np.mean(vals))
                self._stat_std   = float(np.std(vals, ddof=1)) if len(vals) > 1 else 1.0
                if self._stat_std < 1e-10:
                    self._stat_std = 1.0
                self._warmup_done = True
            return DetectionResult(is_anomaly=False, score=0.0, alarm_value=0.0)

        score       = abs(current_stat - self._stat_mean) / self._stat_std
        is_anomaly  = score > self._threshold
        alarm_value = current_stat

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def get_stats(self) -> dict:
        if self._buffer.size() < 2:
            return {"mean": 0.0, "variance": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean":     self._buffer.mean(),
            "variance": self._buffer.variance(),
            "std":      self._buffer.std(),
            "min":      self._buffer.minimum(),
            "max":      self._buffer.maximum(),
        }

    def _compute_stat(self) -> float:
        if self._stat == "mean":
            return self._buffer.mean()
        elif self._stat == "variance":
            return self._buffer.variance()
        elif self._stat == "max":
            return self._buffer.maximum()
        return 0.0

    def reset(self) -> None:
        self._buffer.reset()
        self._stat_mean   = 0.0
        self._stat_std    = 1.0
        self._n           = 0
        self._warmup_done = False
        self._warmup_vals = []
