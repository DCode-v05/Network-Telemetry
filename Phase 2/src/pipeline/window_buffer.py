
import numpy as np
from collections import deque
from typing import Optional


class WindowBuffer:
    """
    Fixed-capacity circular buffer with O(1) streaming statistics.

    Usage
    -----
        buf = WindowBuffer(capacity=20)
        buf.push(3.14)
        buf.push(2.71)
        print(buf.mean())
        print(buf.variance())
        print(buf.is_full())
    """

    def __init__(self, capacity: int):
        if capacity < 2:
            raise ValueError("Window capacity must be at least 2.")
        self._capacity  = capacity
        self._buffer    = np.zeros(capacity, dtype=np.float64)
        self._head      = 0
        self._count     = 0

        self._welf_mean = 0.0
        self._welf_M2   = 0.0

        self._max_deque: deque = deque()
        self._min_deque: deque = deque()


    def push(self, value: float) -> None:
        """
        Add a new sample. If buffer is full, the oldest sample is evicted.
        Updates Welford mean/variance and min/max deques incrementally.
        """
        value = float(value)

        if self._count == self._capacity:
            old_value = self._buffer[self._head]
            self._welford_remove(old_value)
        else:
            self._count += 1

        self._buffer[self._head] = value
        self._welford_add(value)


        self._head = (self._head + 1) % self._capacity

    def mean(self) -> float:
        """Current window mean. O(1)."""
        if self._count == 0:
            return 0.0
        return self._welf_mean

    def variance(self, ddof: int = 1) -> float:
        """
        Current window variance.
        ddof=1 → sample variance (unbiased), ddof=0 → population variance.
        O(1).
        """
        if self._count < 2:
            return 0.0
        divisor = self._count - ddof
        if divisor <= 0:
            return 0.0
        return self._welf_M2 / divisor

    def std(self, ddof: int = 1) -> float:
        """Current window standard deviation. O(1)."""
        return float(np.sqrt(self.variance(ddof=ddof)))

    def minimum(self) -> float:
        """Current window minimum. O(N) — acceptable for N ≤ 50."""
        if self._count == 0:
            return 0.0
        return float(np.min(self._view()))

    def maximum(self) -> float:
        """Current window maximum. O(N) — acceptable for N ≤ 50."""
        if self._count == 0:
            return 0.0
        return float(np.max(self._view()))

    def median(self) -> float:
        """Current window median. O(N log N)."""
        if self._count == 0:
            return 0.0
        return float(np.median(self._view()))

    def is_full(self) -> bool:
        """True when buffer has seen at least `capacity` samples."""
        return self._count == self._capacity

    def size(self) -> int:
        """Number of valid samples currently in buffer."""
        return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    def to_array(self) -> np.ndarray:
        """
        Return current window contents as a numpy array, oldest-first.
        Copies the data — safe to modify.
        """
        return self._view().copy()

    def reset(self) -> None:
        """Clear all state. Useful between trials."""
        self._buffer[:] = 0.0
        self._head      = 0
        self._count     = 0
        self._welf_mean = 0.0
        self._welf_M2   = 0.0


    def _view(self) -> np.ndarray:
        """
        Return a view of the current valid window contents, oldest-first.
        No copy — do not modify.
        """
        if self._count < self._capacity:
            return self._buffer[:self._count]
        tail = self._buffer[self._head:]
        head = self._buffer[:self._head]
        return np.concatenate([tail, head])

    def _welford_add(self, value: float) -> None:
        """Welford's online update for a new value."""
        delta           = value - self._welf_mean
        self._welf_mean += delta / self._count
        delta2          = value - self._welf_mean
        self._welf_M2  += delta * delta2

    def _welford_remove(self, value: float) -> None:
        """
        Welford's online downdate (remove oldest value).
        Used when buffer is full and oldest sample is evicted.
        """
        n = self._count
        if n <= 1:
            self._welf_mean = 0.0
            self._welf_M2   = 0.0
            return
        old_mean        = self._welf_mean
        self._welf_mean = (self._welf_mean * n - value) / (n - 1)
        self._welf_M2  -= (value - old_mean) * (value - self._welf_mean)
        self._welf_M2   = max(0.0, self._welf_M2)
