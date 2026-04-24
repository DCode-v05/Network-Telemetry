# src/detectors/base.py
# ─────────────────────────────────────────────────────────────────────────────
# THIS IS THE INTEGRATION CONTRACT.
# Every detector (Persons 3, 4, 5) MUST subclass DetectorBase and implement
# the three abstract methods below. The harness (Person 6) calls only these
# three methods — nothing else.
#
# Do NOT change this interface without a team-wide discussion.
# ─────────────────────────────────────────────────────────────────────────────

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class DetectionResult:
    """
    Returned by DetectorBase.update() on every sample.

    Fields
    ------
    is_anomaly   : True if this sample is flagged as anomalous.
    score        : The detector's internal anomaly score at this step.
                   Higher = more anomalous (used for ROC/AUC curves).
    alarm_value  : The internal statistic that triggered the alarm (e.g. CUSUM C+).
                   Useful for debugging and plotting detector internals.
    """
    is_anomaly  : bool
    score       : float
    alarm_value : float = 0.0


class DetectorBase(ABC):
    """
    Abstract base class for all anomaly detectors in this project.

    Subclass this and implement:
        update(value)  → called once per sample, returns DetectionResult
        reset()        → resets all internal state (called between trials)
        name           → string name of the detector

    Design rules (enforced by convention, not Python):
    - update() must be O(1) in time and O(1) in memory (except WindowBuffer detectors)
    - No pandas inside any detector
    - No external library calls inside update() — pure Python/numpy only
    - All parameters passed via __init__, not hardcoded
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable detector name. Used in result tables and plot titles."""
        ...

    @abstractmethod
    def update(self, value: float) -> DetectionResult:
        """
        Process one new sample and return a detection decision.

        Parameters
        ----------
        value : The new sample value (already normalized by the pipeline).

        Returns
        -------
        DetectionResult with is_anomaly, score, alarm_value.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """
        Reset all internal state to initial conditions.
        Called by the harness between trials.
        """
        ...

    def run_on_series(self, series: np.ndarray) -> list:
        """
        Convenience method: run detector over a full array, return list of
        DetectionResult, one per sample.

        The harness uses this for batch evaluation.
        """
        self.reset()
        return [self.update(float(x)) for x in series]
