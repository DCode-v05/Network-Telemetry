"""Intelligence (detection-quality) metrics for streaming anomaly detection.

Design choices (grounded in the TS-AD evaluation literature, June 2026):
  * Detectors emit a continuous SCORE; threshold-free metrics (PR-AUC, VUS-PR) are the
    primary headline because anomalies are rare (heavy class imbalance makes accuracy
    and ROC-AUC misleading).
  * Threshold-dependent metrics (F1, MCC, NAB-like, latency, FP-rate) are reported at
    each detector's OWN best-F1 operating point, so every detector is judged fairly.
  * Point-adjusted F1 is included but flagged: it is known to INFLATE scores (a random
    scorer can rival informed methods), so it is never used as the headline.
  * VUS-PR here = PR-AUC averaged over a range of tolerance buffers (anomaly regions
    dilated by l = 0..max_buffer); this is time-lag tolerant and threshold-free.
  * NAB-like score rewards EARLY detection within an anomaly window and penalises false
    positives, normalised to (-inf, 100]; a documented simplification of canonical NAB.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------- pure-numpy precision/recall pass
def _pr_pass(labels, scores):
    """One descending-score pass -> (s, precision, recall) cumulative arrays.

    Pure numpy (no sklearn) so evaluation workers stay light and fast. The step
    approximation matches sklearn's average_precision closely and preserves the
    ranking between detectors, which is all the comparison needs.
    """
    order = np.argsort(-scores, kind="mergesort")
    y = labels[order].astype(float)
    s = scores[order]
    tp = np.cumsum(y)
    fp = np.cumsum(1.0 - y)
    P = tp[-1] if len(tp) else 0.0
    recall = tp / (P if P > 0 else 1.0)
    precision = tp / np.maximum(tp + fp, 1.0)
    return s, precision, recall


def average_precision(labels, scores):
    """Area under the precision-recall curve (PR-AUC / AP), pure numpy."""
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    pos = labels.sum()
    if pos == 0 or pos == len(labels):
        return 0.0
    _, precision, recall = _pr_pass(labels, scores)
    dr = np.diff(recall, prepend=0.0)
    return float(np.sum(dr * precision))


# --------------------------------------------------------------------- primitives
def confusion(labels, preds):
    labels = np.asarray(labels).astype(bool)
    preds = np.asarray(preds).astype(bool)
    tp = int(np.sum(labels & preds))
    fp = int(np.sum(~labels & preds))
    fn = int(np.sum(labels & ~preds))
    tn = int(np.sum(~labels & ~preds))
    return tp, fp, fn, tn


def prf(labels, preds):
    tp, fp, fn, tn = confusion(labels, preds)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def mcc(labels, preds):
    tp, fp, fn, tn = confusion(labels, preds)
    num = tp * tn - fp * fn
    den = float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if den <= 0:
        return 0.0
    return num / np.sqrt(den)


# --------------------------------------------------------- threshold-free metrics
def pr_auc(labels, scores):
    return average_precision(labels, scores)


def _dilate(labels, l):
    """Binary dilation of anomaly regions by l samples each side (tolerance buffer)."""
    if l <= 0:
        return np.asarray(labels).astype(int)
    lab = np.asarray(labels).astype(int)
    k = 2 * l + 1
    kernel = np.ones(k, dtype=int)
    out = np.convolve(lab, kernel, mode="same")
    return (out > 0).astype(int)


def vus_pr(labels, scores, max_buffer=10):
    """PR-AUC averaged over tolerance buffers l = 0..max_buffer (VUS-PR approximation)."""
    scores = np.asarray(scores, dtype=float)
    vals = []
    for l in range(0, max_buffer + 1):
        dl = _dilate(labels, l)
        if dl.sum() == 0 or dl.sum() == len(dl):
            continue
        vals.append(average_precision(dl, scores))
    return float(np.mean(vals)) if vals else 0.0


def best_f1_threshold(labels, scores):
    """Sweep all thresholds; return (threshold, f1, precision, recall) at best F1."""
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    if labels.sum() == 0:
        return 0.0, 0.0, 0.0, 0.0
    if scores.max() == scores.min():
        # degenerate: only the "flag everything" operating point exists
        p, r, f = prf(labels, np.ones_like(labels))
        return float(scores.min()), f, p, r
    s, precision, recall = _pr_pass(labels, scores)
    denom = precision + recall
    f1 = np.where(denom > 0, 2 * precision * recall / np.where(denom > 0, denom, 1.0), 0.0)
    i = int(np.argmax(f1))
    return float(s[i]), float(f1[i]), float(precision[i]), float(recall[i])


# ---------------------------------------------------- point-adjusted (flagged) F1
def point_adjusted_preds(preds, events):
    """If any sample inside an event is flagged, flag the whole event (PA convention)."""
    preds = np.asarray(preds).astype(int).copy()
    for (s, e) in events:
        if preds[s:e + 1].any():
            preds[s:e + 1] = 1
    return preds


def best_pa_f1(labels, scores, events):
    """Best-F1 over thresholds using point-adjusted predictions (INFLATED; reported with caveat)."""
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    if labels.sum() == 0:
        return 0.0
    uniq = np.unique(scores)
    if len(uniq) > 30:
        uniq = np.quantile(scores, np.linspace(0, 1, 30))
    best = 0.0
    for thr in uniq:
        preds = (scores >= thr).astype(int)
        preds = point_adjusted_preds(preds, events)
        _, _, f = prf(labels, preds)
        if f > best:
            best = f
    return float(best)


# ----------------------------------------------------- event-level / operational
def detection_latency(events, preds, tol=3):
    """(detected_fraction, mean_latency_samples) measured from each event's start.

    An event counts as detected if a positive prediction falls in [start, end+tol].
    Latency = (first such index) - start (>= 0). Drift/periodicity events use start.
    """
    preds = np.asarray(preds).astype(int)
    n = len(preds)
    lats = []
    detected = 0
    for (s, e) in events:
        hi = min(n - 1, e + tol)
        hit = None
        for i in range(s, hi + 1):
            if preds[i]:
                hit = i
                break
        if hit is not None:
            detected += 1
            lats.append(hit - s)
    frac = detected / len(events) if events else 0.0
    mean_lat = float(np.mean(lats)) if lats else float("nan")
    return frac, mean_lat


def fp_per_1000(labels, preds, events, tol=3):
    """False positives (flags outside any tolerance-padded event) per 1000 samples."""
    preds = np.asarray(preds).astype(int)
    n = len(preds)
    allowed = np.zeros(n, dtype=bool)
    for (s, e) in events:
        allowed[max(0, s - tol):min(n, e + tol + 1)] = True
    fp = int(np.sum(preds.astype(bool) & ~allowed))
    return 1000.0 * fp / n if n else 0.0


def _nab_sigmoid(rel):
    """NAB scaled scoring: rel in [-1 (just inside leading edge) .. >0 (after window)]."""
    return 2.0 / (1.0 + np.exp(5.0 * rel)) - 1.0


NAB_PROFILES = {
    "standard": dict(tp=1.0, fp=0.11, fn=1.0),
    "low_fp": dict(tp=1.0, fp=0.22, fn=1.0),
    "low_fn": dict(tp=1.0, fp=0.11, fn=2.0),
}


def nab_like_score(labels, preds, events, n, profile="standard"):
    """Normalised NAB-like score in (-inf, 100]; rewards early in-window detection."""
    w = NAB_PROFILES[profile]
    preds = np.asarray(preds).astype(int)
    num_w = max(1, len(events))
    win = max(2, int(0.10 * n / num_w))  # window length per anomaly (NAB heuristic)
    windows = []
    for (s, e) in events:
        c = s  # reward detection near onset
        windows.append((max(0, c - win // 2), min(n - 1, c + win // 2)))

    raw = 0.0
    in_window = np.zeros(n, dtype=bool)
    for (ws, we) in windows:
        in_window[ws:we + 1] = True
        # first detection inside this window
        seg = preds[ws:we + 1]
        idx = np.argmax(seg) if seg.any() else -1
        if seg.any():
            length = max(1, we - ws)
            rel = -1.0 + (idx / length)   # earliest -> -1 (max reward)
            raw += w["tp"] * (_nab_sigmoid(rel) + 1.0) / 2.0  # map to (0,1]
        else:
            raw -= w["fn"]
    # false positives (flags outside any window)
    fp_idx = np.where(preds.astype(bool) & ~in_window)[0]
    raw -= w["fp"] * len(fp_idx)

    null_score = -w["fn"] * len(windows)             # detect nothing
    perfect = w["tp"] * len(windows)                 # all windows detected at onset, no FP
    if perfect - null_score <= 0:
        return 0.0
    return float(100.0 * (raw - null_score) / (perfect - null_score))


# --------------------------------------------------------------------- top level
def evaluate(labels, scores, events, n=None, vus_buffer=10):
    """Full metric bundle for one (detector, stream) run.

    Threshold-free: pr_auc, vus_pr. Threshold-dependent metrics are taken at the
    detector's best-F1 operating point for fairness.
    """
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores, dtype=float)
    if n is None:
        n = len(labels)

    thr, f1, precision, recall = best_f1_threshold(labels, scores)
    preds = (scores >= thr).astype(int)

    det_frac, mean_lat = detection_latency(events, preds)
    return {
        "pr_auc": pr_auc(labels, scores),
        "vus_pr": vus_pr(labels, scores, max_buffer=vus_buffer),
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "mcc": mcc(labels, preds),
        "pa_f1": best_pa_f1(labels, scores, events),
        "nab": nab_like_score(labels, preds, events, n, "standard"),
        "nab_low_fp": nab_like_score(labels, preds, events, n, "low_fp"),
        "detected_frac": det_frac,
        "latency": mean_lat,
        "fp_per_1k": fp_per_1000(labels, preds, events),
        "threshold": thr,
        "anomaly_ratio": float(labels.mean()),
    }
