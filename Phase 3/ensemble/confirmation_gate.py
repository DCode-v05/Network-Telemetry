"""
ConfirmationGate — wrap any DetectorBase so it requires N consecutive child
alarms before declaring an anomaly.

Motivation: Phase 2 showed that singleton false alarms drown true positives in
class-imbalanced settings (5–20 anomalous samples in a 280-sample series).
Gating with n_consecutive=2 eliminates most singleton FPs without retraining
the underlying detector or shrinking its TPR on multi-sample anomalies.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _phase2_bridge import DetectorBase, DetectionResult


def _base_name(child_name: str) -> str:
    """Strip parameter suffix from a Phase 2 detector name.

    'ZScore(w=10, thr=3.0)' -> 'ZScore'
    'MAD(w=20, thr=3.5)'    -> 'MAD'
    """
    return child_name.split("(", 1)[0]


class ConfirmationGate(DetectorBase):
    """
    Fires only when its child detector alarms on n consecutive samples.

    While the streak is >= n_consecutive, the gate continues firing every
    sample so per-sample TPR/FPR remain meaningful. The streak resets to 0 on
    any sample where the child does not alarm.

    Parameters
    ----------
    child         : DetectorBase    — underlying detector to wrap.
    n_consecutive : int (default 2) — alarms required to fire.

    Attributes
    ----------
    score        — forwarded from child (preserves ROC-friendliness).
    alarm_value  — current streak length (useful for dashboard inspection).
    """

    def __init__(self, child: DetectorBase, n_consecutive: int = 2):
        if n_consecutive < 1:
            raise ValueError(f"n_consecutive must be >= 1, got {n_consecutive}")
        self._child         = child
        self._n_consecutive = int(n_consecutive)
        self._streak        = 0

    @property
    def name(self) -> str:
        return f"Gated{_base_name(self._child.name)}(n={self._n_consecutive})"

    def update(self, value: float) -> DetectionResult:
        child_result = self._child.update(value)

        if child_result.is_anomaly:
            self._streak += 1
        else:
            self._streak = 0

        is_anomaly = self._streak >= self._n_consecutive

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = child_result.score,
            alarm_value = float(self._streak),
        )

    def reset(self) -> None:
        self._streak = 0
        self._child.reset()
