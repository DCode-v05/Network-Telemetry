"""
Shared test helpers — kept here (rather than in conftest.py) so test modules
can import them via plain `from _helpers import ...`. pytest treats conftest.py
as a fixture-only file and does not expose its symbols to direct import.
"""
from _phase2_bridge import DetectorBase, DetectionResult


class MockDetector(DetectorBase):
    """
    Test double that replays a scripted sequence of (is_anomaly, score) pairs.

    On each update() call, returns the next entry in the script. Once the
    script is exhausted, returns (False, 0.0) for any further calls.

    Parameters
    ----------
    scripted_alarms : list[bool]
        One entry per expected update() call; True means "fire on this sample".
    scripted_scores : list[float] | None
        Optional matching scores. Defaults to 1.0 for True, 0.0 for False.
    name : str
        Identifier used in alarm-attribution and dashboard.
    """

    def __init__(
        self,
        scripted_alarms,
        scripted_scores=None,
        name: str = "Mock",
    ):
        self._alarms = list(scripted_alarms)
        if scripted_scores is None:
            scripted_scores = [1.0 if a else 0.0 for a in scripted_alarms]
        self._scores = list(scripted_scores)
        self._name   = name
        self._idx    = 0

    @property
    def name(self) -> str:
        return self._name

    def update(self, value: float) -> DetectionResult:
        if self._idx < len(self._alarms):
            is_anomaly = bool(self._alarms[self._idx])
            score      = float(self._scores[self._idx])
            self._idx += 1
        else:
            is_anomaly = False
            score      = 0.0

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = score,
        )

    def reset(self) -> None:
        self._idx = 0
