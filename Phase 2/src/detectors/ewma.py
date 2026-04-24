# src/detectors/ewma.py
import math
from src.detectors.base import DetectorBase, DetectionResult


class EWMADetector(DetectorBase):
    """
    EWMA control chart anomaly detector.

    S_t = lambda_ * x_t + (1 - lambda_) * S_{t-1}
    UCL/LCL = mu_0 +/- L * sigma_0 * sqrt(lambda_ / (2 - lambda_))
    """

    def __init__(self, lambda_: float = 0.2, L: float = 3.0, warmup: int = 20):
        if not (0 < lambda_ < 1):
            raise ValueError("lambda_ must be in (0, 1)")
        self._lambda  = lambda_
        self._L       = L
        self._warmup  = max(warmup, 10)   # never below 10

        self._S       = 0.0
        self._mu0     = 0.0
        self._sigma0  = 1.0
        self._ucl     = 0.0
        self._lcl     = 0.0
        self._n       = 0
        self._welf_mean = 0.0
        self._welf_M2   = 0.0

    @property
    def name(self) -> str:
        return f"EWMA(lambda={self._lambda}, L={self._L})"

    def update(self, value: float) -> DetectionResult:
        self._n += 1

        if self._n <= self._warmup:
            delta           = value - self._welf_mean
            self._welf_mean += delta / self._n
            delta2          = value - self._welf_mean
            self._welf_M2  += delta * delta2

            if self._n == self._warmup:
                self._mu0    = self._welf_mean
                var          = self._welf_M2 / (self._n - 1) if self._n > 1 else 0.0
                self._sigma0 = math.sqrt(var) if var > 0 else 1.0
                spread       = self._L * self._sigma0 * math.sqrt(
                    self._lambda / (2.0 - self._lambda)
                )
                self._ucl    = self._mu0 + spread
                self._lcl    = self._mu0 - spread
                self._S      = self._mu0

            return DetectionResult(is_anomaly=False, score=0.0, alarm_value=0.0)

        self._S = self._lambda * value + (1.0 - self._lambda) * self._S

        score       = abs(self._S - self._mu0) / self._sigma0
        is_anomaly  = (self._S > self._ucl) or (self._S < self._lcl)
        alarm_value = self._S

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def reset(self) -> None:
        self._S          = 0.0
        self._mu0        = 0.0
        self._sigma0     = 1.0
        self._ucl        = 0.0
        self._lcl        = 0.0
        self._n          = 0
        self._welf_mean  = 0.0
        self._welf_M2    = 0.0
