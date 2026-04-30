"""
VotingLayer — meta-detector that combines 2+ children via AND/OR voting.

AND mode (high precision): every child must alarm on the same sample.
OR mode  (high recall):    any child alarming is enough.

Used by Phase 3 to combine the gated MAD + gated Z-Score (spike pipeline) and
the gated EWMA + gated CUSUM (sustained-change pipeline). Voting layers
themselves are children of TwoLayerEnsemble.
"""
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _phase2_bridge import DetectorBase, DetectionResult


def _short_child_name(child_name: str) -> str:
    """'GatedMAD(n=2)' -> 'GatedMAD'; 'ZScore(w=10, thr=3.0)' -> 'ZScore'."""
    return child_name.split("(", 1)[0]


_VALID_MODES = {"AND", "OR"}


class VotingLayer(DetectorBase):
    """
    Combines child detectors by AND or OR voting.

    Parameters
    ----------
    children    : list[DetectorBase]
        Two or more child detectors. Updated in order on every sample.
    mode        : "AND" or "OR" (default "AND")
        Vote-combination rule.
    layer_name  : str (default "Voting")
        Used in `name` for dashboard grouping (e.g. "Spike", "Sustained").

    Attributes on returned DetectionResult
    --------------------------------------
    is_anomaly  : combined vote per `mode`.
    score       : max child score (monotonic, ROC-friendly).
    alarm_value : number of children that alarmed (0..len(children)).
    """

    def __init__(
        self,
        children: List[DetectorBase],
        mode: str = "AND",
        layer_name: str = "Voting",
    ):
        if len(children) < 2:
            raise ValueError(
                f"VotingLayer requires at least 2 children, got {len(children)}"
            )
        if mode not in _VALID_MODES:
            raise ValueError(
                f"mode must be one of {_VALID_MODES}, got {mode!r}"
            )
        self._children   = list(children)
        self._mode       = mode
        self._layer_name = layer_name

    @property
    def name(self) -> str:
        members = "+".join(_short_child_name(c.name) for c in self._children)
        return f"{self._layer_name}_{self._mode}({members})"

    def update(self, value: float) -> DetectionResult:
        results = [c.update(value) for c in self._children]
        votes   = sum(1 for r in results if r.is_anomaly)

        if self._mode == "AND":
            is_anomaly = votes == len(self._children)
        else:  # "OR"
            is_anomaly = votes > 0

        max_score = max(r.score for r in results) if results else 0.0

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = max_score,
            alarm_value = float(votes),
        )

    def reset(self) -> None:
        for c in self._children:
            c.reset()
