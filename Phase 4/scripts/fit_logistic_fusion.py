"""Offline fitter for cand_logistic_fusion.LogisticFusion.

Drives the detector through update() over a labelled make_suite (collecting the per-sample
feature vector it exposes via .last_features), standardizes the features, and fits a logistic
regression head by gradient descent. Prints the resulting FEAT_MU / FEAT_SD / W / B constants
to paste into the candidate. Plain python + numpy is fine here (this runs OFFLINE, not on
device).

Usage:
  python scripts/fit_logistic_fusion.py [--window 16] [--seeds 6] [--epochs 4000]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src", "python"))

from datasets.synthetic import make_suite          # noqa: E402
from tsad.candidates.cand_logistic_fusion import LogisticFusion, _NFEAT  # noqa: E402

TYPES = ["spike", "drift", "periodicity", "transient"]


def collect(window, seeds, seed_start=0):
    """Drive the detector; return features, labels, type, and a per-sample KEEP mask.

    For SUSTAINED events (drift, periodicity) the deep interior is not point-detectable by
    a streaming O(window) feature once the baseline has adapted -- forcing the head to call
    the whole interior positive only drowns the onset signal that event-F1 actually rewards.
    So for those types we keep, as positives, only an ONSET window after the event start (and
    a couple of samples before/after transitions); the undetectable interior is dropped from
    training (keep=False). Spike/transient keep every sample (they are point anomalies).
    """
    suite = make_suite(seeds=range(seed_start, seed_start + seeds))
    X, Y, T = [], [], []
    ONSET = 24  # samples after an event start that we still expect a detectable signal
    for s in suite:
        atype = s.meta["anomaly_type"]
        raw = np.asarray(s.labels).astype(int)
        # the detector emits the spike/transient score with a 1-sample lag (centered
        # curvature scores sample t-1 at step t), so train against a +/-1 DILATED label,
        # matching the +/-tol the event metric credits anyway.
        labels = raw.copy()
        labels[1:] |= raw[:-1]
        labels[:-1] |= raw[1:]
        keep = np.ones(len(labels), dtype=bool)
        if atype in ("drift", "periodicity"):
            for (a, b) in s.events:
                if b > a + ONSET:                # drop the undetectable sustained interior
                    keep[a + ONSET:b + 1] = False
        det = LogisticFusion(window=window)
        warm = det.warmup
        for i, x in enumerate(s.values):
            det.update(float(x))
            if det.n <= warm or not keep[i]:
                continue
            X.append(det.last_features)
            Y.append(int(labels[i]))
            T.append(atype)
    return np.asarray(X, dtype=float), np.asarray(Y, dtype=float), np.asarray(T)


def fit(X, Y, T, epochs=4000, lr=0.2, l2=1e-4, nonneg=True, posw=None):
    """Weighted, optionally non-negative-constrained logistic regression.

    Features are all "higher == more anomalous" z-scores, so the fused head should have
    NON-NEGATIVE weights (a soft-OR). Constraining weights to >= 0 stops the bursty-base
    contamination from driving a feature's weight negative (which would suppress real
    detections). ``posw`` extra-upweights positives (recall lever for event-F1).
    """
    n, d = X.shape
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-6] = 1.0
    Xs = (X - mu) / sd

    # per-(type,class) sample weights: balance the 4 types equally and balance pos/neg
    # within each type, so the rare periodicity type and the rare positives are not drowned.
    pmul = 0.5 if posw is None else posw / (posw + 1.0)
    nmul = 1.0 - pmul
    w = np.ones(n)
    for t in TYPES:
        tm = (T == t)
        if tm.sum() == 0:
            continue
        pos = tm & (Y == 1)
        neg = tm & (Y == 0)
        npos, nneg = pos.sum(), neg.sum()
        if npos > 0:
            w[pos] = (1.0 / len(TYPES)) * pmul / npos
        if nneg > 0:
            w[neg] = (1.0 / len(TYPES)) * nmul / nneg
    w *= n / w.sum()

    theta = np.zeros(d)
    b = 0.0
    for ep in range(epochs):
        z = Xs @ theta + b
        p = 1.0 / (1.0 + np.exp(-z))
        g = (p - Y) * w
        grad_theta = Xs.T @ g / n + l2 * theta
        grad_b = g.sum() / n
        theta -= lr * grad_theta
        b -= lr * grad_b
        if nonneg:
            theta[theta < 0.0] = 0.0
    return mu, sd, theta, b


CAND = os.path.join(HERE, "..", "src", "python", "tsad", "candidates",
                    "cand_logistic_fusion.py")


def _fmt(v):
    return "(" + ", ".join(f"{x:.6g}" for x in v) + ")"


def write_constants(mu, sd, theta, b):
    import re
    with open(CAND, "r", encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r"    FEAT_MU = .*", f"    FEAT_MU = {_fmt(mu)}", src, count=1)
    src = re.sub(r"    FEAT_SD = .*", f"    FEAT_SD = {_fmt(sd)}", src, count=1)
    src = re.sub(r"    W = .*", f"    W = {_fmt(theta)}", src, count=1)
    src = re.sub(r"    B = .*", f"    B = {b:.6g}", src, count=1)
    with open(CAND, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"# wrote constants into {CAND}")


def report(window, seeds, epochs, write=False, l2=1e-4, lr=0.2, posw=None):
    X, Y, T = collect(window, seeds)
    mu, sd, theta, b = fit(X, Y, T, epochs=epochs, lr=lr, l2=l2, posw=posw)

    print(f"# fit window={window} seeds={seeds} n={len(Y)} pos={int(Y.sum())}")
    print(f"    FEAT_MU = {_fmt(mu)}")
    print(f"    FEAT_SD = {_fmt(sd)}")
    print(f"    W = {_fmt(theta)}")
    print(f"    B = {b:.6g}")
    # quick separation sanity per type
    Xs = (X - mu) / sd
    p = 1.0 / (1.0 + np.exp(-(Xs @ theta + b)))
    for t in TYPES:
        tm = T == t
        if tm.sum() == 0:
            continue
        pp = p[tm & (Y == 1)]
        pn = p[tm & (Y == 0)]
        print(f"# {t:11s} mean(pos)={pp.mean():.3f} mean(neg)={pn.mean():.3f} "
              f"sep={pp.mean()-pn.mean():.3f}")
    if write:
        write_constants(mu, sd, theta, b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=16)
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--epochs", type=int, default=5000)
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--lr", type=float, default=0.2)
    ap.add_argument("--posw", type=float, default=None)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    report(args.window, args.seeds, args.epochs, write=args.write,
           l2=args.l2, lr=args.lr, posw=args.posw)
