"""Fixed-capacity circular buffer of floats.

Mirrors a C ``struct { float buf[N]; int head; int count; }`` exactly, so a detector
that uses it in Python maps 1:1 onto the on-device implementation. All operations are
O(1) except ``values``/``sorted_values`` which are O(window) -- used only by
window-based detectors (robust-z, Hampel, ACF) that inherently need the window.
"""

from __future__ import annotations


class RingBuffer:
    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self.buf = [0.0] * self.capacity
        self.head = 0
        self.count = 0

    def push(self, x: float) -> None:
        """Append a value, overwriting the oldest once full. O(1)."""
        self.buf[self.head] = float(x)
        self.head = (self.head + 1) % self.capacity
        if self.count < self.capacity:
            self.count += 1

    def is_full(self) -> bool:
        return self.count == self.capacity

    def values(self) -> list[float]:
        """Valid values in chronological (oldest -> newest) order. O(count)."""
        if self.count < self.capacity:
            return self.buf[:self.count]
        return self.buf[self.head:] + self.buf[:self.head]

    def sorted_values(self) -> list[float]:
        """Valid values, ascending. O(count log count) -- used for median/MAD."""
        return sorted(self.values())

    def newest(self) -> float:
        """Most recently pushed value."""
        return self.buf[(self.head - 1) % self.capacity]

    def __len__(self) -> int:
        return self.count
