# src/injector/anomaly_injector.py
# Person 2 owns this file.
#
# Injects controlled anomalies into clean CESNET baseline segments.
# This is why we can measure ground truth TPR/FPR — the injected position
# is known exactly.
#
# Design: each function takes a clean numpy array and injection parameters,
# returns a new array with the anomaly injected + a binary label array
# (0 = normal, 1 = anomalous sample).

import numpy as np
from typing import Tuple
from dataclasses import dataclass


@dataclass
class InjectionResult:
    """
    Result of a single anomaly injection.

    Fields
    ------
    signal       : The modified signal array (clean baseline + injected anomaly).
    labels       : Binary array, same length as signal. 1 = anomalous sample.
    inject_start : Index where the anomaly begins.
    inject_end   : Index where the anomaly ends (exclusive).
    anomaly_type : String identifier of the anomaly type.
    """
    signal       : np.ndarray
    labels       : np.ndarray
    inject_start : int
    inject_end   : int
    anomaly_type : str


class AnomalyInjector:
    """
    Injects controlled anomalies into a clean time series.

    Usage
    -----
        injector = AnomalyInjector(random_seed=42)
        result = injector.inject_burst(clean_signal, magnitude=5.0, duration=3)
        # result.signal  → signal with burst injected
        # result.labels  → ground truth labels
    """

    def __init__(self, random_seed: int = 42):
        self._rng = np.random.default_rng(random_seed)

    # ── Public injection methods ──────────────────────────────────────────────

    def inject_burst(
        self,
        signal:    np.ndarray,
        magnitude: float = 5.0,
        duration:  int   = 3,
        position:  int   = None,
    ) -> InjectionResult:
        """
        Inject a burst: a short-lived spike above the local baseline.

        The spike is: x[i] += magnitude * local_std for i in [start, start+duration)

        Parameters
        ----------
        signal    : Clean normalized time series (1D numpy array).
        magnitude : Spike height in units of local std.
        duration  : Length of the spike in samples.
        position  : Injection start index. If None, chosen randomly from
                    the middle 50% of the series to ensure enough context.
        """
        signal, start = self._prepare(signal, duration, position)
        local_std     = self._local_std(signal, start)

        modified = signal.copy()
        for i in range(start, start + duration):
            modified[i] += magnitude * local_std

        labels = self._make_labels(len(signal), start, start + duration)
        return InjectionResult(
            signal       = modified,
            labels       = labels,
            inject_start = start,
            inject_end   = start + duration,
            anomaly_type = "burst",
        )

    def inject_rate_shift(
        self,
        signal:    np.ndarray,
        magnitude: float = 3.0,
        duration:  int   = 20,
        position:  int   = None,
    ) -> InjectionResult:
        """
        Inject a sustained rate shift (step change).

        After the injection point, the signal is shifted up by magnitude * local_std
        for `duration` samples.

        This models a network device switching to a new steady-state traffic level.
        """
        signal, start = self._prepare(signal, duration, position)
        local_std     = self._local_std(signal, start)
        shift         = magnitude * local_std

        modified = signal.copy()
        for i in range(start, start + duration):
            modified[i] += shift

        labels = self._make_labels(len(signal), start, start + duration)
        return InjectionResult(
            signal       = modified,
            labels       = labels,
            inject_start = start,
            inject_end   = start + duration,
            anomaly_type = "rate_shift",
        )

    def inject_gradual_drift(
        self,
        signal:   np.ndarray,
        slope:    float = 0.2,
        duration: int   = 15,
        position: int   = None,
    ) -> InjectionResult:
        """
        Inject a gradual drift: signal increases linearly over `duration` samples.

        The drift at sample i is: slope * local_std * (i - start)

        Models a slow, progressive increase in traffic (e.g., growing DDoS).
        """
        signal, start = self._prepare(signal, duration, position)
        local_std     = self._local_std(signal, start)

        modified = signal.copy()
        for i in range(start, start + duration):
            drift        = slope * local_std * (i - start + 1)
            modified[i] += drift

        labels = self._make_labels(len(signal), start, start + duration)
        return InjectionResult(
            signal       = modified,
            labels       = labels,
            inject_start = start,
            inject_end   = start + duration,
            anomaly_type = "gradual_drift",
        )

    def inject_transient(
        self,
        signal:    np.ndarray,
        magnitude: float = 6.0,
        position:  int   = None,
    ) -> InjectionResult:
        """
        Inject a transient anomaly: a single-sample spike.

        This is the hardest case for most detectors — only 1 sample is anomalous.
        """
        duration      = 1
        signal, start = self._prepare(signal, duration, position)
        local_std     = self._local_std(signal, start)

        modified          = signal.copy()
        modified[start]  += magnitude * local_std

        labels = self._make_labels(len(signal), start, start + 1)
        return InjectionResult(
            signal       = modified,
            labels       = labels,
            inject_start = start,
            inject_end   = start + 1,
            anomaly_type = "transient",
        )

    def inject(
        self,
        signal:       np.ndarray,
        anomaly_type: str,
        params:       dict,
    ) -> InjectionResult:
        """
        Dispatch injection by anomaly_type string.
        Convenience method for the harness.

        Parameters
        ----------
        anomaly_type : "burst" | "rate_shift" | "gradual_drift" | "transient"
        params       : Dict of keyword args passed to the injection function.
        """
        dispatch = {
            "burst":         self.inject_burst,
            "rate_shift":    self.inject_rate_shift,
            "gradual_drift": self.inject_gradual_drift,
            "transient":     self.inject_transient,
        }
        if anomaly_type not in dispatch:
            raise ValueError(
                f"Unknown anomaly_type '{anomaly_type}'. "
                f"Valid: {list(dispatch.keys())}"
            )
        return dispatch[anomaly_type](signal, **params)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _prepare(
        self,
        signal:   np.ndarray,
        duration: int,
        position: int = None,
    ) -> Tuple[np.ndarray, int]:
        """
        Validate signal and determine injection start position.
        Returns (signal_as_float64, start_index).
        """
        signal = np.asarray(signal, dtype=np.float64)
        n      = len(signal)

        if n < 60 + duration:
            raise ValueError(
                f"Signal too short ({n} samples) for injection "
                f"with duration={duration}. Need at least {60 + duration}."
            )

        if position is None:
            # Inject somewhere in the middle 50% of the series
            lo    = n // 4
            hi    = 3 * n // 4 - duration
            if lo >= hi:
                lo = 30
                hi = n - duration - 10
            start = int(self._rng.integers(lo, hi))
        else:
            start = position
            if start < 30 or start + duration > n - 10:
                raise ValueError(
                    f"position={position} with duration={duration} is too close "
                    "to the series boundary. Need at least 30 clean samples before "
                    "injection and 10 after."
                )

        return signal, start

    def _local_std(self, signal: np.ndarray, start: int, lookback: int = 30) -> float:
        """
        Estimate local standard deviation from the `lookback` samples before injection.
        Falls back to global std if local region is near-constant.
        """
        begin     = max(0, start - lookback)
        local_seg = signal[begin:start]
        std       = float(np.std(local_seg))
        if std < 1e-6:
            std = float(np.std(signal))
        if std < 1e-6:
            std = 1.0
        return std

    @staticmethod
    def _make_labels(length: int, start: int, end: int) -> np.ndarray:
        """Create binary label array: 1 in [start, end), 0 elsewhere."""
        labels         = np.zeros(length, dtype=np.int8)
        labels[start:end] = 1
        return labels
