# src/evaluation/plots.py
import os

# matplotlib backend MUST be set before any other matplotlib import
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from typing import List, Dict, Any

import config as cfg


DETECTOR_COLORS = {
    "ZScore":        "#1D9E75",
    "MAD":           "#7F77DD",
    "EWMA":          "#D85A30",
    "CUSUM":         "#378ADD",
    "PageHinkley":   "#BA7517",
    "SlidingWindow": "#888780",
}


def _det_color(name: str) -> str:
    for key, color in DETECTOR_COLORS.items():
        if key.lower() in name.lower():
            return color
    return "#444441"


def _short_name(full_name: str) -> str:
    """'ZScore(w=20, thr=3.0)' -> 'ZScore'"""
    return full_name.split("(")[0]


def _unique_detectors(aggregated: List[Dict]) -> List[str]:
    seen = []
    for r in aggregated:
        d = r.get("detector", "")
        if d and d not in seen:
            seen.append(d)
    return seen


def _save(name: str) -> None:
    path = os.path.join(cfg.RESULTS_PLT_DIR, f"{name}.{cfg.PLOT_FORMAT}")
    plt.savefig(path, dpi=cfg.PLOT_DPI, bbox_inches="tight")
    plt.close("all")


def generate_all_plots(aggregated: List[Dict[str, Any]]) -> None:
    if not aggregated:
        return
    os.makedirs(cfg.RESULTS_PLT_DIR, exist_ok=True)

    for plot_fn in [
        plot_f1_heatmap,
        plot_tpr_fpr_by_anomaly,
        plot_detection_latency,
        plot_f1_vs_window_size,
    ]:
        try:
            plot_fn(aggregated)
        except Exception as e:
            print(f"Warning: plot {plot_fn.__name__} failed: {e}")
            plt.close("all")
            continue

    print(f"Plots saved to {cfg.RESULTS_PLT_DIR}/")


def plot_f1_heatmap(aggregated: List[Dict[str, Any]]) -> None:
    window_sizes  = sorted(set(r["window_size"] for r in aggregated))
    anomaly_types = cfg.ANOMALY_TYPES
    detectors     = _unique_detectors(aggregated)

    n_ws = len(window_sizes)
    fig, axes = plt.subplots(
        1, n_ws,
        figsize=(5 * n_ws, max(4, len(detectors) * 0.7 + 1)),
        sharey=True,
    )
    if n_ws == 1:
        axes = [axes]

    im = None
    for ax, ws in zip(axes, window_sizes):
        matrix = np.zeros((len(detectors), len(anomaly_types)))
        for i, det in enumerate(detectors):
            for j, at in enumerate(anomaly_types):
                match = [
                    r for r in aggregated
                    if r.get("window_size") == ws
                    and at in r.get("anomaly_type", "")
                    and _short_name(det) in r.get("detector", "")
                ]
                if match:
                    matrix[i, j] = match[0].get("f1_mean", 0.0)

        im = ax.imshow(matrix, vmin=0, vmax=1, cmap="YlGn", aspect="auto")
        ax.set_xticks(range(len(anomaly_types)))
        ax.set_xticklabels([a.replace("_", "\n") for a in anomaly_types], fontsize=9)
        ax.set_yticks(range(len(detectors)))
        ax.set_yticklabels([_short_name(d) for d in detectors], fontsize=9)
        ax.set_title(f"N = {ws}", fontsize=11, fontweight="bold")

        for i in range(len(detectors)):
            for j in range(len(anomaly_types)):
                val   = matrix[i, j]
                color = "white" if val > 0.6 else "#2C2C2A"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=8, color=color)

    if im is not None:
        fig.colorbar(im, ax=axes[-1], label="F1 Score", shrink=0.8)

    fig.suptitle("F1 Score: Detector x Anomaly Type x Window Size",
                 fontsize=13, y=1.01)
    plt.tight_layout()
    _save("f1_heatmap")


def plot_tpr_fpr_by_anomaly(aggregated: List[Dict[str, Any]]) -> None:
    anomaly_types = cfg.ANOMALY_TYPES
    detectors     = _unique_detectors(aggregated)
    n_det         = len(detectors)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharey=False)
    axes = axes.flatten()

    for ax, at in zip(axes, anomaly_types):
        tprs = []
        fprs = []
        for det in detectors:
            rows = [
                r for r in aggregated
                if at in r.get("anomaly_type", "")
                and _short_name(det) in r.get("detector", "")
            ]
            tprs.append(float(np.mean([r.get("tpr_mean", 0) for r in rows])) if rows else 0.0)
            fprs.append(float(np.mean([r.get("fpr_mean", 0) for r in rows])) if rows else 0.0)

        x      = np.arange(n_det)
        width  = 0.35
        colors = [_det_color(d) for d in detectors]

        ax.bar(x - width / 2, tprs, width, label="TPR", color=colors, alpha=0.9)
        ax.bar(x + width / 2, fprs, width, label="FPR", color=colors, alpha=0.4,
               edgecolor=colors, linewidth=1.2)

        ax.set_xticks(x)
        ax.set_xticklabels([_short_name(d) for d in detectors],
                           rotation=30, ha="right", fontsize=8)
        ax.set_ylim(0, 1.05)
        ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        ax.axhline(y=0.05, color="#D85A30", linestyle="--", linewidth=0.8,
                   label="5% FPR target")
        if ax is axes[0]:
            ax.legend(fontsize=8)
        ax.set_ylabel("Rate")

    fig.suptitle(
        "True Positive Rate vs False Positive Rate by Anomaly Type\n"
        "(averaged across window sizes)",
        fontsize=12,
    )
    plt.tight_layout()
    _save("tpr_fpr_by_anomaly")


def plot_detection_latency(aggregated: List[Dict[str, Any]]) -> None:
    anomaly_types = cfg.ANOMALY_TYPES
    detectors     = _unique_detectors(aggregated)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    axes = axes.flatten()

    for ax, at in zip(axes, anomaly_types):
        data   = []
        labels = []
        for det in detectors:
            rows = [
                r for r in aggregated
                if at in r.get("anomaly_type", "")
                and _short_name(det) in r.get("detector", "")
                and r.get("avg_detection_latency", -1) >= 0
            ]
            latencies = [r["avg_detection_latency"] for r in rows]
            if latencies:
                data.append(latencies)
                labels.append(_short_name(det))

        if data:
            bp = ax.boxplot(
                data, labels=labels, patch_artist=True,
                medianprops={"color": "#2C2C2A", "linewidth": 2},
            )
            for patch, lbl in zip(bp["boxes"], labels):
                patch.set_facecolor(_det_color(lbl))
                patch.set_alpha(0.7)

        ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
        ax.set_ylabel("Detection latency (samples)")
        ax.tick_params(axis="x", rotation=30)
        ax.axhline(
            y=cfg.DETECTION_WINDOW, color="#D85A30", linestyle="--",
            linewidth=0.8, label=f"Window ({cfg.DETECTION_WINDOW})",
        )

    fig.suptitle("Detection Latency Distribution by Anomaly Type", fontsize=12)
    plt.tight_layout()
    _save("detection_latency")


def plot_f1_vs_window_size(aggregated: List[Dict[str, Any]]) -> None:
    anomaly_types = cfg.ANOMALY_TYPES
    detectors     = _unique_detectors(aggregated)
    window_sizes  = sorted(set(r["window_size"] for r in aggregated))

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharey=True)
    axes = axes.flatten()

    for ax, at in zip(axes, anomaly_types):
        for det in detectors:
            f1s = []
            for ws in window_sizes:
                rows = [
                    r for r in aggregated
                    if at in r.get("anomaly_type", "")
                    and _short_name(det) in r.get("detector", "")
                    and r.get("window_size") == ws
                ]
                f1s.append(rows[0].get("f1_mean", 0.0) if rows else 0.0)

            ax.plot(
                window_sizes, f1s,
                marker="o", linewidth=2, markersize=5,
                color=_det_color(det),
                label=_short_name(det),
            )

        ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
        ax.set_xlabel("Window size (N)")
        ax.set_ylabel("F1 score")
        ax.set_xticks(window_sizes)
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", linewidth=0.4, alpha=0.5)
        if ax is axes[0]:
            ax.legend(fontsize=8, ncol=2)

    fig.suptitle("F1 Score vs Window Size by Anomaly Type", fontsize=12)
    plt.tight_layout()
    _save("f1_vs_window_size")
