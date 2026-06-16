"""
Unit + integration tests for TwoLayerEnsemble.

Mock-driven tests verify fusion logic and attribution.
Real-detector tests verify end-to-end behaviour on synthetic signals.
"""
import numpy as np
import pytest

from ensemble.confirmation_gate  import ConfirmationGate
from ensemble.voting_layer       import VotingLayer
from ensemble.two_layer_ensemble import TwoLayerEnsemble
from _helpers                    import MockDetector
from _phase2_bridge              import (
    MADDetector, ZScoreDetector, EWMADetector, CUSUMDetector,
)



def test_spike_only_attribution():
    """When only the spike layer fires, alarm_value should be 1.0."""
    spike     = MockDetector([True],  name="Spike")
    sustained = MockDetector([False], name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained)
    r         = ens.update(0.0)
    assert r.is_anomaly is True
    assert r.alarm_value == 1.0


def test_sustained_only_attribution():
    """When only the sustained layer fires, alarm_value should be 2.0."""
    spike     = MockDetector([False], name="Spike")
    sustained = MockDetector([True],  name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained)
    r         = ens.update(0.0)
    assert r.is_anomaly is True
    assert r.alarm_value == 2.0


def test_both_layers_attribution_to_spike():
    """When both fire, attribution favours the spike layer (1.0)."""
    spike     = MockDetector([True], name="Spike")
    sustained = MockDetector([True], name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained)
    r         = ens.update(0.0)
    assert r.is_anomaly is True
    assert r.alarm_value == 1.0


def test_neither_fires():
    spike     = MockDetector([False], name="Spike")
    sustained = MockDetector([False], name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained)
    r         = ens.update(0.0)
    assert r.is_anomaly is False
    assert r.alarm_value == 0.0


def test_score_is_max_of_layers():
    spike     = MockDetector([True], scripted_scores=[2.5], name="Spike")
    sustained = MockDetector([True], scripted_scores=[7.1], name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained)
    r         = ens.update(0.0)
    assert r.score == 7.1


def test_reset_propagates_to_both_layers():
    spike     = MockDetector([True], name="Spike")
    sustained = MockDetector([True], name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained)
    ens.update(0.0)
    assert ens.update(0.0).is_anomaly is False
    ens.reset()
    assert ens.update(0.0).is_anomaly is True


def test_name_default():
    spike     = MockDetector([], name="Spike_AND(MAD+ZScore)")
    sustained = MockDetector([], name="Sustained_OR(EWMA+CUSUM)")
    ens       = TwoLayerEnsemble(spike, sustained)
    assert ens.name == "TwoLayerEnsemble"


def test_name_with_suffix():
    spike     = MockDetector([], name="Spike")
    sustained = MockDetector([], name="Sustained")
    ens       = TwoLayerEnsemble(spike, sustained, name_suffix="default")
    assert ens.name == "TwoLayerEnsemble[default]"



def _build_default_ensemble(window_size: int = 20) -> TwoLayerEnsemble:
    """Same composition the harness will use in the full benchmark."""
    warmup = max(window_size, 20)
    spike = VotingLayer(
        children = [
            ConfirmationGate(MADDetector(window_size=window_size, threshold=3.5),    n_consecutive=2),
            ConfirmationGate(ZScoreDetector(window_size=window_size, threshold=3.0), n_consecutive=2),
        ],
        mode       = "AND",
        layer_name = "Spike",
    )
    sustained = VotingLayer(
        children = [
            ConfirmationGate(EWMADetector(lambda_=0.2, L=3.5, warmup=warmup),     n_consecutive=2),
            ConfirmationGate(CUSUMDetector(k=0.5,    h=3.5, warmup=warmup),       n_consecutive=2),
        ],
        mode       = "OR",
        layer_name = "Sustained",
    )
    return TwoLayerEnsemble(spike, sustained)


def _make_synthetic_signal(rng: np.random.Generator, n: int = 200) -> np.ndarray:
    """Stationary normal noise — used as a clean baseline."""
    return rng.standard_normal(n).astype(np.float64)


def test_burst_triggers_within_window():
    """A 5σ burst injected at sample 100 should be flagged within 5 samples."""
    rng    = np.random.default_rng(42)
    signal = _make_synthetic_signal(rng, n=200)
    inject_start = 100
    duration     = 5
    signal[inject_start:inject_start + duration] += 6.0

    ens     = _build_default_ensemble(window_size=20)
    results = ens.run_on_series(signal)

    region = results[inject_start : inject_start + 10]
    assert any(r.is_anomaly for r in region), \
        "Ensemble failed to detect a 6σ 5-sample burst within 10 samples"


def test_clean_signal_low_fpr():
    """On a 200-sample stationary signal, ensemble FPR must stay below 10%."""
    rng    = np.random.default_rng(0)
    signal = _make_synthetic_signal(rng, n=200)
    ens    = _build_default_ensemble(window_size=20)
    results = ens.run_on_series(signal)

    n_alarms = sum(1 for r in results if r.is_anomaly)
    fpr      = n_alarms / len(results)
    assert fpr < 0.10, f"Clean-signal FPR was {fpr:.3f}; expected < 0.10"


def test_burst_attribution_is_spike():
    """When a burst fires the ensemble, attribution should be 1.0 (spike layer)."""
    rng    = np.random.default_rng(42)
    signal = _make_synthetic_signal(rng, n=200)
    inject_start = 100
    signal[inject_start:inject_start + 5] += 6.0

    ens     = _build_default_ensemble(window_size=20)
    results = ens.run_on_series(signal)

    fired_in_burst = [r for r in results[inject_start : inject_start + 10] if r.is_anomaly]
    assert fired_in_burst, "no alarm to inspect attribution on"
    assert fired_in_burst[0].alarm_value == 1.0
