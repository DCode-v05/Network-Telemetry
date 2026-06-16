import math
from src.detectors.base import DetectorBase, DetectionResult


class CUSUMDetector(DetectorBase):
    """
    Bidirectional CUSUM control chart.

    C+_t = max(0, C+_{t-1} + (x_t - mu_0 - k))
    C-_t = max(0, C-_{t-1} - (x_t - mu_0 + k))
    Alarm when C+ > h or C- > h.
    """

    def __init__(self, k: float = 0.5, h: float = 5.0, warmup: int = 20):
        self._k      = k
        self._h      = h
        self._warmup = max(warmup, 10)

        self._C_pos  = 0.0
        self._C_neg  = 0.0
        self._mu0    = 0.0
        self._sigma0 = 1.0
        self._n      = 0
        self._welf_mean = 0.0
        self._welf_M2   = 0.0

    @property
    def name(self) -> str:
        return f"CUSUM(k={self._k}, h={self._h})"

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
                self._C_pos  = 0.0
                self._C_neg  = 0.0

            return DetectionResult(is_anomaly=False, score=0.0, alarm_value=0.0)

        z = (value - self._mu0) / self._sigma0

        self._C_pos = max(0.0, self._C_pos + z - self._k)
        self._C_neg = max(0.0, self._C_neg - z - self._k)

        score       = max(self._C_pos, self._C_neg)
        is_anomaly  = score > self._h
        alarm_value = self._C_pos - self._C_neg

        if is_anomaly:
            self._C_pos = 0.0
            self._C_neg = 0.0

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def reset(self) -> None:
        self._C_pos      = 0.0
        self._C_neg      = 0.0
        self._mu0        = 0.0
        self._sigma0     = 1.0
        self._n          = 0
        self._welf_mean  = 0.0
        self._welf_M2    = 0.0
