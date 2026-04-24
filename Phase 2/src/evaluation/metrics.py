# src/evaluation/metrics.py
# Person 6 owns this file.
#
# All evaluation metrics for Phase 2.
# Inputs are always: ground truth label arrays + detector output arrays.

import numpy as np
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class EvalMetrics:
    """
    Complete evaluation result for one (detector, anomaly_type, window_size, trial).
    """
    detector_name  : str
    anomaly_type   : str
    window_size    : int
    trial          : int

    # Core metrics
    tpr            : float   # True Positive Rate = TP / (TP + FN)
    fpr            : float   # False Positive Rate = FP / (FP + TN)
    precision      : float   # TP / (TP + FP)
    f1             : float   # 2 * (precision * recall) / (precision + recall)

    # Detection latency (samples after anomaly start before first alarm)
    # -1 means the anomaly was never detected
    detection_latency : int

    # Raw counts
    tp  : int
    fp  : int
    tn  : int
    fn  : int

    def to_dict(self) -> dict:
        return {
            "detector":          self.detector_name,
            "anomaly_type":      self.anomaly_type,
            "window_size":       self.window_size,
            "trial":             self.trial,
            "tpr":               round(self.tpr, 4),
            "fpr":               round(self.fpr, 4),
            "precision":         round(self.precision, 4),
            "f1":                round(self.f1, 4),
            "detection_latency": self.detection_latency,
            "tp":  self.tp,
            "fp":  self.fp,
            "tn":  self.tn,
            "fn":  self.fn,
        }


def compute_metrics(
    labels:         np.ndarray,
    predictions:    np.ndarray,
    inject_start:   int,
    detector_name:  str,
    anomaly_type:   str,
    window_size:    int,
    trial:          int,
    detection_window: int = 5,
) -> EvalMetrics:
    """
    Compute all evaluation metrics for one trial.

    Parameters
    ----------
    labels          : Binary ground truth (0=normal, 1=anomalous). Shape (N,).
    predictions     : Binary detector output (0=no alarm, 1=alarm). Shape (N,).
    inject_start    : Sample index where anomaly was injected.
    detector_name   : Name string.
    anomaly_type    : "burst" | "rate_shift" | "gradual_drift" | "transient"
    window_size     : Window size used in this trial.
    trial           : Trial index.
    detection_window: Max samples after inject_start that count as "timely" detection.
    """
    labels      = np.asarray(labels,      dtype=np.int8)
    predictions = np.asarray(predictions, dtype=np.int8)

    assert len(labels) == len(predictions), "labels and predictions must have same length"

    tp = int(np.sum((labels == 1) & (predictions == 1)))
    fp = int(np.sum((labels == 0) & (predictions == 1)))
    tn = int(np.sum((labels == 0) & (predictions == 0)))
    fn = int(np.sum((labels == 1) & (predictions == 0)))

    tpr       = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr       = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1        = (
        2 * precision * tpr / (precision + tpr)
        if (precision + tpr) > 0
        else 0.0
    )

    # Detection latency: first alarm index within detection_window after inject_start
    latency = _compute_latency(predictions, inject_start, detection_window)

    return EvalMetrics(
        detector_name     = detector_name,
        anomaly_type      = anomaly_type,
        window_size       = window_size,
        trial             = trial,
        tpr               = tpr,
        fpr               = fpr,
        precision         = precision,
        f1                = f1,
        detection_latency = latency,
        tp  = tp,
        fp  = fp,
        tn  = tn,
        fn  = fn,
    )


def _compute_latency(
    predictions:      np.ndarray,
    inject_start:     int,
    detection_window: int,
) -> int:
    """
    Find how many samples after inject_start the first alarm occurs.
    Returns -1 if no alarm within detection_window samples of inject_start.
    """
    end = min(inject_start + detection_window, len(predictions))
    for i in range(inject_start, end):
        if predictions[i] == 1:
            return i - inject_start
    return -1


def aggregate_metrics(metrics_list: List[EvalMetrics]) -> dict:
    """
    Aggregate a list of EvalMetrics (across trials) into mean ± std summary.
    Used by the harness to produce the results table.
    """
    if not metrics_list:
        return {}

    fields = ["tpr", "fpr", "precision", "f1"]
    result = {
        "detector":     metrics_list[0].detector_name,
        "anomaly_type": metrics_list[0].anomaly_type,
        "window_size":  metrics_list[0].window_size,
        "n_trials":     len(metrics_list),
    }

    for f in fields:
        vals = [getattr(m, f) for m in metrics_list]
        result[f"{f}_mean"] = round(float(np.mean(vals)), 4)
        result[f"{f}_std"]  = round(float(np.std(vals)), 4)

    latencies = [m.detection_latency for m in metrics_list if m.detection_latency >= 0]
    result["detection_rate"]          = round(len(latencies) / len(metrics_list), 4)
    result["avg_detection_latency"]   = round(float(np.mean(latencies)), 2) if latencies else -1.0
    result["stdev_detection_latency"] = round(float(np.std(latencies)), 2)  if latencies else 0.0

    return result
