# src/detectors/page_hinkley.py
import math
from src.detectors.base import DetectorBase, DetectionResult


class PageHinkleyDetector(DetectorBase):
    """
    Page-Hinkley test for change-point and gradual drift detection.

    PH_t = sum of (x_i - x_bar_t - delta)
    M_t  = max(PH_1 ... PH_t)
    Alarm when (M_t - PH_t) > lambda_

    Two instances (upward + downward) to catch both directions.
    """

    def __init__(
        self,
        delta:   float = 0.5,
        lambda_: float = 50.0,
        alpha:   float = 0.9999,
        warmup:  int   = 20,
    ):
        self._delta   = delta
        self._lambda  = lambda_
        self._alpha   = alpha
        self._warmup  = max(warmup, 10)

        self._ph_up   = 0.0
        self._max_up  = 0.0
        self._ph_dn   = 0.0
        self._max_dn  = 0.0

        self._mu      = 0.0
        self._sigma0  = 1.0
        self._n       = 0
        self._welf_mean = 0.0
        self._welf_M2   = 0.0

    @property
    def name(self) -> str:
        return f"PageHinkley(delta={self._delta}, lambda={self._lambda})"

    def update(self, value: float) -> DetectionResult:
        self._n += 1

        if self._n <= self._warmup:
            delta           = value - self._welf_mean
            self._welf_mean += delta / self._n
            delta2          = value - self._welf_mean
            self._welf_M2  += delta * delta2

            if self._n == self._warmup:
                self._mu     = self._welf_mean
                var          = self._welf_M2 / (self._n - 1) if self._n > 1 else 0.0
                self._sigma0 = math.sqrt(var) if var > 0 else 1.0
                self._ph_up  = 0.0
                self._max_up = 0.0
                self._ph_dn  = 0.0
                self._max_dn = 0.0

            return DetectionResult(is_anomaly=False, score=0.0, alarm_value=0.0)

        z = (value - self._mu) / self._sigma0

        # Update adaptive mean
        self._mu = self._alpha * self._mu + (1.0 - self._alpha) * value

        # Upward direction
        self._ph_up  += z - self._delta
        self._max_up  = max(self._max_up, self._ph_up)
        ph_score_up   = self._max_up - self._ph_up

        # Downward direction
        self._ph_dn  += -z - self._delta
        self._max_dn  = max(self._max_dn, self._ph_dn)
        ph_score_dn   = self._max_dn - self._ph_dn

        score       = max(ph_score_up, ph_score_dn)
        is_anomaly  = score > self._lambda
        alarm_value = ph_score_up - ph_score_dn

        if is_anomaly:
            if ph_score_up >= ph_score_dn:
                self._ph_up  = 0.0
                self._max_up = 0.0
            else:
                self._ph_dn  = 0.0
                self._max_dn = 0.0

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def reset(self) -> None:
        self._ph_up      = 0.0
        self._max_up     = 0.0
        self._ph_dn      = 0.0
        self._max_dn     = 0.0
        self._mu         = 0.0
        self._sigma0     = 1.0
        self._n          = 0
        self._welf_mean  = 0.0
        self._welf_M2    = 0.0
