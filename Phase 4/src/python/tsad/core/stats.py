"""Tiny scalar-stats helpers shared by detectors.

Pure arithmetic, no numpy -- these mirror what the C twin computes. Kept here so the
median / MAD logic is written and tested once.
"""

from __future__ import annotations

MAD_TO_SIGMA = 1.4826  # consistency factor: MAD * k estimates Gaussian sigma


def median_sorted(sorted_vals: list[float]) -> float:
    """Median of an already-sorted list. O(1)."""
    m = len(sorted_vals)
    if m == 0:
        return 0.0
    mid = m // 2
    if m % 2:
        return sorted_vals[mid]
    return 0.5 * (sorted_vals[mid - 1] + sorted_vals[mid])


def median(vals: list[float]) -> float:
    return median_sorted(sorted(vals))


def mad(vals: list[float], med: float | None = None) -> float:
    """Median absolute deviation about the median (raw, NOT scaled by 1.4826)."""
    if not vals:
        return 0.0
    if med is None:
        med = median(vals)
    devs = sorted(abs(v - med) for v in vals)
    return median_sorted(devs)
