"""
Unit tests for VotingLayer.
"""
import pytest

from ensemble.voting_layer import VotingLayer
from _helpers import MockDetector


def test_and_mode_requires_all_children():
    """AND: votes < N children → no alarm."""
    a = MockDetector([True,  False, True], name="A")
    b = MockDetector([False, True,  True], name="B")
    layer = VotingLayer([a, b], mode="AND", layer_name="Spike")
    out = [layer.update(0.0).is_anomaly for _ in range(3)]
    assert out == [False, False, True]


def test_or_mode_any_child_suffices():
    """OR: any vote → alarm."""
    a = MockDetector([True,  False, False], name="A")
    b = MockDetector([False, True,  False], name="B")
    layer = VotingLayer([a, b], mode="OR", layer_name="Spike")
    out = [layer.update(0.0).is_anomaly for _ in range(3)]
    assert out == [True, True, False]


def test_alarm_value_is_vote_count():
    a = MockDetector([True,  True,  False], name="A")
    b = MockDetector([True,  False, False], name="B")
    c = MockDetector([False, True,  False], name="C")
    layer = VotingLayer([a, b, c], mode="OR")
    votes = [layer.update(0.0).alarm_value for _ in range(3)]
    assert votes == [2.0, 2.0, 0.0]


def test_score_is_max_child_score():
    a = MockDetector([True], scripted_scores=[3.0], name="A")
    b = MockDetector([True], scripted_scores=[7.5], name="B")
    layer = VotingLayer([a, b], mode="AND")
    r = layer.update(0.0)
    assert r.score == 7.5


def test_reset_propagates_to_all_children():
    a = MockDetector([True, True], name="A")
    b = MockDetector([True, True], name="B")
    layer = VotingLayer([a, b], mode="AND")
    layer.update(0.0)
    layer.update(0.0)
    assert layer.update(0.0).is_anomaly is False
    layer.reset()
    assert layer.update(0.0).is_anomaly is True


def test_name_format_and_mode():
    a = MockDetector([], name="GatedMAD(n=2)")
    b = MockDetector([], name="GatedZScore(n=2)")
    layer = VotingLayer([a, b], mode="AND", layer_name="Spike")
    assert layer.name == "Spike_AND(GatedMAD+GatedZScore)"


def test_name_format_or_mode():
    a = MockDetector([], name="GatedEWMA(n=2)")
    b = MockDetector([], name="GatedCUSUM(n=2)")
    layer = VotingLayer([a, b], mode="OR", layer_name="Sustained")
    assert layer.name == "Sustained_OR(GatedEWMA+GatedCUSUM)"


def test_invalid_mode_raises():
    a = MockDetector([], name="A")
    b = MockDetector([], name="B")
    with pytest.raises(ValueError):
        VotingLayer([a, b], mode="XOR")


def test_too_few_children_raises():
    with pytest.raises(ValueError):
        VotingLayer([MockDetector([], name="A")], mode="AND")
    with pytest.raises(ValueError):
        VotingLayer([], mode="OR")


def test_and_three_children():
    """AND with 3 children: needs all 3 to fire."""
    a = MockDetector([True,  True,  True], name="A")
    b = MockDetector([True,  True,  False], name="B")
    c = MockDetector([False, True,  True], name="C")
    layer = VotingLayer([a, b, c], mode="AND")
    out = [layer.update(0.0).is_anomaly for _ in range(3)]
    assert out == [False, True, False]
