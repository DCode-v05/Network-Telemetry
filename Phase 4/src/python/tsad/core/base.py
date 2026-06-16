"""Base streaming anomaly detector contract.

Every detector in Phase 4 (Python reference *and* its on-device C twin) obeys this
contract so that (a) the evaluation harness can treat them uniformly and (b) the C
port can be checked for numerical parity against the Python reference.

Hard rules (these make the "lightweight" claim honest):
  * Pure scalar arithmetic only inside ``update`` -- NO numpy, NO list comprehensions
    over the whole history, NO batch reprocessing. Mirror what C would do.
  * Bounded state, allocated once in ``reset``. ``update`` is O(1) or O(window).
  * ``update(x)`` returns a continuous anomaly score (>= 0; higher == more anomalous).
  * The binary decision is ``score >= self.threshold``.
  * During warm-up the detector returns 0.0 (it has not seen enough data to judge).

State-size accounting: each subclass declares the scalar/buffer state it keeps via
``state_floats`` / ``state_buffer_len`` so the Python footprint estimate and the C
``sizeof(struct)`` agree and can be checked against the < 100 byte budget.
"""

from __future__ import annotations


class Detector:
    """Abstract streaming detector. Subclasses implement ``reset`` and ``update``."""

    name = "base"

    def __init__(self, window: int = 30, threshold: float = 3.0,
                 warmup: int | None = None, **params):
        self.window = int(window)
        self.threshold = float(threshold)
        self.warmup = int(warmup) if warmup is not None else max(3, self.window // 3)
        self.params = dict(params)
        self.reset()

    def reset(self) -> None:
        """Reset all streaming state. Subclasses override and MUST call super().reset()."""
        self.n = 0
        self.last_score = 0.0

    def update(self, x: float) -> float:
        """Process one sample; return a continuous anomaly score (>= 0)."""
        raise NotImplementedError

    def flag(self, x: float) -> int:
        """Update with ``x`` and return the binary decision at the current threshold."""
        return 1 if self.update(x) >= self.threshold else 0

    def score_stream(self, xs) -> list[float]:
        """Run over an iterable, returning the per-sample score series (eval helper)."""
        out = []
        ap = out.append
        up = self.update
        for x in xs:
            ap(up(float(x)))
        return out

    def warm(self) -> bool:
        """True once the detector has passed warm-up and is allowed to alert."""
        return self.n > self.warmup

    def state_floats(self) -> int:
        """Count of float32 scalars held in steady state (EXCLUDING any ring buffer)."""
        return 0

    def state_buffer_len(self) -> int:
        """Length of any float32 ring buffer the detector keeps (0 if none)."""
        return 0

    def state_bytes(self) -> int:
        """Approx on-device footprint (float32 model): scalars + buffer + int counters.

        The authoritative number is the C ``sizeof(struct)`` measured in WF-C; this is
        the Python-side estimate used for an early budget sanity check.
        """
        return self.state_floats() * 4 + self.state_buffer_len() * 4 + 8
