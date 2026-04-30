"""
Parametrized base-contract test — every Phase 3 ensemble class must honour the
DetectorBase contract so it plugs into the Phase 2 harness with zero glue.

Mirrors Phase 2's `TestBaseContract` parametrization
(Phase 2/tests/test_detectors.py).
"""
import numpy as np
import pytest

from ensemble.confirmation_gate  import ConfirmationGate
from ensemble.voting_layer       import VotingLayer
from ensemble.two_layer_ensemble import TwoLayerEnsemble
from _helpers                    import MockDetector
from _phase2_bridge              import (
    DetectionResult,
    MADDetector, ZScoreDetector, EWMADetector, CUSUMDetector,
)


def _build_gate():
    return ConfirmationGate(
        MADDetector(window_size=20, threshold=3.5),
        n_consecutive=2,
    )


def _build_voting_and():
    return VotingLayer(
        children = [
            ConfirmationGate(MADDetector(window_size=20, threshold=3.5),    n_consecutive=2),
            ConfirmationGate(ZScoreDetector(window_size=20, threshold=3.0), n_consecutive=2),
        ],
        mode       = "AND",
        layer_name = "Spike",
    )


def _build_voting_or():
    return VotingLayer(
        children = [
            ConfirmationGate(EWMADetector(lambda_=0.2, L=3.5, warmup=20),  n_consecutive=2),
            ConfirmationGate(CUSUMDetector(k=0.5,    h=3.5, warmup=20),    n_consecutive=2),
        ],
        mode       = "OR",
        layer_name = "Sustained",
    )


def _build_two_layer():
    return TwoLayerEnsemble(_build_voting_and(), _build_voting_or())


_FACTORIES = [
    pytest.param(_build_gate,        id="ConfirmationGate"),
    pytest.param(_build_voting_and,  id="VotingLayer_AND"),
    pytest.param(_build_voting_or,   id="VotingLayer_OR"),
    pytest.param(_build_two_layer,   id="TwoLayerEnsemble"),
]


@pytest.mark.parametrize("factory", _FACTORIES)
def test_name_is_str_and_nonempty(factory):
    detector = factory()
    assert isinstance(detector.name, str)
    assert detector.name != ""


@pytest.mark.parametrize("factory", _FACTORIES)
def test_update_returns_detection_result(factory):
    detector = factory()
    out = detector.update(0.5)
    assert isinstance(out, DetectionResult)
    assert isinstance(out.is_anomaly, bool)
    assert isinstance(out.score, float)
    assert isinstance(out.alarm_value, float)


@pytest.mark.parametrize("factory", _FACTORIES)
def test_run_on_series_correct_length(factory):
    detector = factory()
    rng      = np.random.default_rng(123)
    series   = rng.standard_normal(150)
    results  = detector.run_on_series(series)
    assert len(results) == len(series)
    assert all(isinstance(r, DetectionResult) for r in results)


@pytest.mark.parametrize("factory", _FACTORIES)
def test_reset_is_idempotent(factory):
    """Two run_on_series calls bracketed by reset should produce identical alarm sequences."""
    detector = factory()
    rng      = np.random.default_rng(7)
    series   = rng.standard_normal(150)

    a_first  = [r.is_anomaly for r in detector.run_on_series(series)]
    a_second = [r.is_anomaly for r in detector.run_on_series(series)]

    assert a_first == a_second, \
        "Detector did not produce identical results across resets — state is leaking."
