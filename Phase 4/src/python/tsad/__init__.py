"""tsad -- lightweight streaming anomaly detectors for short-window network telemetry.

Phase 4 reference implementation (pure scalar arithmetic; mirrors the on-device C twin).
The detector registry is populated in ``tsad.registry``.
"""

from .core.base import Detector
from .core.ring_buffer import RingBuffer

__all__ = ["Detector", "RingBuffer"]
__version__ = "0.4.0"
