"""Synthetic + real telemetry datasets with ground-truth anomaly labels."""

from .synthetic import Stream, make_stream, make_suite
from .injectors import ANOMALY_TYPES

__all__ = ["Stream", "make_stream", "make_suite", "ANOMALY_TYPES"]
