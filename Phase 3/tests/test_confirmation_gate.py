"""
Unit tests for ConfirmationGate.
"""
import pytest

from ensemble.confirmation_gate import ConfirmationGate
from _helpers import MockDetector


def _alarms_from_run(gate: ConfirmationGate, n_samples: int) -> list:
    """Run gate on n dummy samples; return list of bools (is_anomaly per step)."""
    return [gate.update(0.0).is_anomaly for _ in range(n_samples)]


def test_single_alarm_does_not_fire():
    """Gate(n=2): a single child alarm should NOT fire the gate."""
    child = MockDetector([False, False, True, False, False], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=2)
    out   = _alarms_from_run(gate, 5)
    assert out == [False, False, False, False, False]


def test_two_consecutive_alarms_fire_on_second():
    """Gate(n=2): the SECOND consecutive child alarm fires the gate."""
    child = MockDetector([False, True, True, False], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=2)
    out   = _alarms_from_run(gate, 4)
    assert out == [False, False, True, False]


def test_streak_continues_firing_while_active():
    """While streak >= n the gate continues firing — required for per-sample TPR."""
    child = MockDetector([True, True, True, True, True], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=2)
    out   = _alarms_from_run(gate, 5)
    assert out == [False, True, True, True, True]


def test_non_consecutive_alarms_do_not_fire():
    """Two child alarms separated by a non-alarm should not fire (streak resets)."""
    child = MockDetector([True, False, True, False, True], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=2)
    out   = _alarms_from_run(gate, 5)
    assert out == [False, False, False, False, False]


def test_reset_clears_streak():
    """After reset, a single fresh alarm must not fire."""
    child = MockDetector([True, True, True], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=2)
    # Build streak, fire
    assert _alarms_from_run(gate, 2) == [False, True]
    gate.reset()
    # Reset child too: re-arm the script
    child.reset()
    # First alarm after reset must not fire alone
    child2 = MockDetector([True], name="MAD")
    gate2  = ConfirmationGate(child2, n_consecutive=2)
    assert gate2.update(0.0).is_anomaly is False


def test_higher_n_threshold():
    """Gate(n=3): need three consecutive alarms."""
    child = MockDetector([True, True, True, True], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=3)
    out   = _alarms_from_run(gate, 4)
    assert out == [False, False, True, True]


def test_n_equals_one_passes_through():
    """Gate(n=1) is the identity — every child alarm fires the gate."""
    child = MockDetector([False, True, False, True], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=1)
    out   = _alarms_from_run(gate, 4)
    assert out == [False, True, False, True]


def test_invalid_n_raises():
    child = MockDetector([], name="MAD")
    with pytest.raises(ValueError):
        ConfirmationGate(child, n_consecutive=0)


def test_name_format():
    child = MockDetector([], name="MAD(w=20, thr=3.5)")
    gate  = ConfirmationGate(child, n_consecutive=2)
    assert gate.name == "GatedMAD(n=2)"


def test_alarm_value_reports_streak():
    """alarm_value should equal the current streak length each step."""
    child = MockDetector([True, True, False, True], name="MAD")
    gate  = ConfirmationGate(child, n_consecutive=2)
    streaks = [gate.update(0.0).alarm_value for _ in range(4)]
    assert streaks == [1.0, 2.0, 0.0, 1.0]


def test_score_forwarded_from_child():
    child = MockDetector(
        scripted_alarms=[True, True],
        scripted_scores=[3.7, 4.2],
        name="MAD",
    )
    gate  = ConfirmationGate(child, n_consecutive=2)
    r1 = gate.update(0.0)
    r2 = gate.update(0.0)
    assert r1.score == 3.7
    assert r2.score == 4.2
