"""Pareto-frontier utilities for the intelligence-vs-cost trade-off."""

from __future__ import annotations


def pareto_front(points, x_key, y_key, minimize_x=True, maximize_y=True):
    """Return the subset of `points` (list of dicts) not dominated by any other.

    A point A dominates B if A is at least as good on both axes and strictly better on
    one. Default: minimise x (cost), maximise y (intelligence).
    """
    front = []
    for p in points:
        px, py = p[x_key], p[y_key]
        if px is None or py is None:
            continue
        dominated = False
        for q in points:
            qx, qy = q[x_key], q[y_key]
            if qx is None or qy is None:
                continue
            better_x = (qx <= px) if minimize_x else (qx >= px)
            better_y = (qy >= py) if maximize_y else (qy <= py)
            strict = ((qx < px) if minimize_x else (qx > px)) or \
                     ((qy > py) if maximize_y else (qy < py))
            if better_x and better_y and strict:
                dominated = True
                break
        if not dominated:
            front.append(p)
    front.sort(key=lambda p: p[x_key], reverse=not minimize_x)
    return front
