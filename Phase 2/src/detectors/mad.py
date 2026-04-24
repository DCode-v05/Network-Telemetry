# src/detectors/mad.py
# Person 3 owns this file.
#
# MAD (Median Absolute Deviation) anomaly detector.
# More robust than Z-Score for heavy-tailed / bursty traffic distributions.

import numpy as np
from src.detectors.base import DetectorBase, DetectionResult
from src.pipeline.window_buffer import WindowBuffer


class MADDetector(DetectorBase):
    """
    Sliding-window Median Absolute Deviation anomaly detector.

    Robust Z-score:
        robust_Z = 0.6745 * (x - median(window)) / MAD(window)
        MAD = median(|x_i - median(window)|)

    The constant 0.6745 makes MAD consistent with standard deviation
    under a Gaussian distribution.

    Flags if |robust_Z| > threshold.

    Parameters
    ----------
    window_size : Reference window size.
    threshold   : Robust Z threshold. Typical: 3.0–4.0.
                  From config.py: DETECTORS["mad"]["threshold"]
    """

    # Consistency constant: makes MAD ≈ σ under normality
    _CONSISTENCY_FACTOR = 0.6745

    def __init__(self, window_size: int, threshold: float = 3.5):
        self._window_size = window_size
        self._threshold   = threshold
        self._buffer      = WindowBuffer(capacity=window_size)

    @property
    def name(self) -> str:
        return f"MAD(w={self._window_size}, thr={self._threshold})"

    def update(self, value: float) -> DetectionResult:
        """
        Process one sample.

        Note: MAD requires a full window before it can produce a meaningful
        score (median of < window_size samples has lower statistical efficiency).
        """
        is_anomaly  = False
        score       = 0.0
        alarm_value = 0.0

        if self._buffer.is_full():
            window = self._buffer.to_array()

            med = float(np.median(window))
            mad = float(np.median(np.abs(window - med)))

            if mad > 1e-10:
                robust_z    = self._CONSISTENCY_FACTOR * (value - med) / mad
                score       = abs(robust_z)
                alarm_value = robust_z
                is_anomaly  = score > self._threshold
            # If MAD ≈ 0 (near-constant window): no anomaly declared
            # A perfectly constant signal cannot be flagged via deviation

        self._buffer.push(value)

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def reset(self) -> None:
        self._buffer.reset()
