
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from typing import Optional

DET_COLORS = {
    "ZScore":        "#1D9E75",
    "MAD":           "#7F77DD",
    "EWMA":          "#D85A30",
    "CUSUM":         "#378ADD",
    "PageHinkley":   "#BA7517",
    "SlidingWindow": "#888780",
}
ANOMALY_TYPES   = ["burst", "rate_shift", "gradual_drift", "transient"]
WINDOW_SIZES    = [10, 20, 30, 50]


def _color(name: str) -> str:
    for k, c in DET_COLORS.items():
        if k.lower() in name.lower():
            return c
    return "#444441"


def _short(name: str) -> str:
    return name.split("(")[0]


def _load(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["detector_short"] = df["detector"].apply(_short)
    return df


def _save(fig, path: str, dpi: int = 150) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved -> {path}")



class Visualiser:
    """
    Generates all plots for a single evaluation run.

    Parameters
    ----------
    results_csv_dir : folder containing aggregated_results.csv
    plots_dir       : output folder for plots
    iteration       : 1 or 2 — used in titles and filenames
    """

    def __init__(self, results_csv_dir: str, plots_dir: str, iteration: int = 1):
        self.csv_path  = os.path.join(results_csv_dir, "aggregated_results.csv")
        self.plots_dir = plots_dir
        self.iteration = iteration
        os.makedirs(plots_dir, exist_ok=True)

        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(
                f"aggregated_results.csv not found at {self.csv_path}\n"
                "Run main.py first to generate results."
            )
        self.df = _load(self.csv_path)
        print(f"[Visualiser] Loaded {len(self.df)} rows from {self.csv_path}")

    def run_all(self) -> None:
        print(f"[Visualiser] Generating plots for Iteration {self.iteration}...")
        for fn in [
            self.plot_f1_heatmap,
            self.plot_tpr_fpr_bars,
            self.plot_tpr_by_anomaly,
            self.plot_fpr_comparison,
            self.plot_detection_rate,
            self.plot_f1_vs_window,
            self.plot_detection_latency,
            self.plot_radar,
        ]:
            try:
                fn()
            except Exception as e:
                print(f"  WARNING: {fn.__name__} failed: {e}")
        print(f"[Visualiser] Done. Plots in {self.plots_dir}/")

    def _path(self, name: str) -> str:
        return os.path.join(self.plots_dir, f"iter{self.iteration}_{name}.png")

    def _tag(self) -> str:
        return f"Iteration {self.iteration}"


    def plot_f1_heatmap(self) -> None:
        df = self.df
        dets = sorted(df["detector_short"].unique())
        ws   = sorted(df["window_size"].unique())
        ats  = ANOMALY_TYPES

        fig, axes = plt.subplots(1, len(ws), figsize=(5 * len(ws), max(4, len(dets) * 0.65 + 1.5)), sharey=True)
        if len(ws) == 1:
            axes = [axes]

        im = None
        for ax, w in zip(axes, ws):
            mat = np.zeros((len(dets), len(ats)))
            for i, d in enumerate(dets):
                for j, at in enumerate(ats):
                    row = df[(df["detector_short"] == d) & (df["window_size"] == w) & (df["anomaly_type"] == at)]
                    if not row.empty:
                        mat[i, j] = row["f1_mean"].values[0]
            im = ax.imshow(mat, vmin=0, vmax=1, cmap="YlGn", aspect="auto")
            ax.set_xticks(range(len(ats)))
            ax.set_xticklabels([a.replace("_", "\n") for a in ats], fontsize=9)
            ax.set_yticks(range(len(dets)))
            ax.set_yticklabels(dets, fontsize=9)
            ax.set_title(f"N = {w}", fontsize=11, fontweight="bold")
            for i in range(len(dets)):
                for j in range(len(ats)):
                    v = mat[i, j]
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            fontsize=8, color="white" if v > 0.55 else "#2C2C2A")

        if im is not None:
            fig.colorbar(im, ax=axes[-1], label="F1 score", shrink=0.8)
        fig.suptitle(f"F1 score heatmap — {self._tag()}", fontsize=13, y=1.01)
        plt.tight_layout()
        _save(fig, self._path("f1_heatmap"))


    def plot_tpr_fpr_bars(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())
        ats  = ANOMALY_TYPES

        fig, axes = plt.subplots(2, 2, figsize=(14, 9))
        axes = axes.flatten()

        for ax, at in zip(axes, ats):
            tprs = []
            fprs = []
            for d in dets:
                rows = df[(df["detector_short"] == d) & (df["anomaly_type"] == at)]
                tprs.append(rows["tpr_mean"].mean() if not rows.empty else 0)
                fprs.append(rows["fpr_mean"].mean() if not rows.empty else 0)

            x = np.arange(len(dets))
            w = 0.35
            clrs = [_color(d) for d in dets]
            ax.bar(x - w/2, tprs, w, label="TPR", color=clrs, alpha=0.9)
            ax.bar(x + w/2, fprs, w, label="FPR", color=clrs, alpha=0.35, edgecolor=clrs, linewidth=1.2)
            ax.set_xticks(x)
            ax.set_xticklabels(dets, rotation=30, ha="right", fontsize=8)
            ax.set_ylim(0, 1.05)
            ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
            ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
            ax.axhline(y=0.05, color="#D85A30", linestyle="--", linewidth=0.8, label="5% FPR target")
            if ax is axes[0]:
                ax.legend(fontsize=8)
            ax.set_ylabel("Rate")

        fig.suptitle(f"TPR vs FPR by anomaly type — {self._tag()}\n(averaged across window sizes)", fontsize=12)
        plt.tight_layout()
        _save(fig, self._path("tpr_fpr_bars"))


    def plot_tpr_by_anomaly(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())
        ats  = ANOMALY_TYPES

        fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharey=True)
        axes = axes.flatten()

        for ax, at in zip(axes, ats):
            for d in dets:
                rows = df[(df["detector_short"] == d) & (df["anomaly_type"] == at)].sort_values("window_size")
                if rows.empty:
                    continue
                ax.plot(rows["window_size"], rows["tpr_mean"],
                        marker="o", linewidth=2, markersize=5,
                        color=_color(d), label=d)
                ax.fill_between(rows["window_size"],
                                rows["tpr_mean"] - rows["tpr_std"].clip(0),
                                (rows["tpr_mean"] + rows["tpr_std"]).clip(0, 1),
                                alpha=0.12, color=_color(d))
            ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
            ax.set_xlabel("Window size (N)")
            ax.set_ylabel("TPR")
            ax.set_xticks(WINDOW_SIZES)
            ax.set_ylim(0, 1.05)
            ax.grid(axis="y", linewidth=0.4, alpha=0.5)
            if ax is axes[0]:
                ax.legend(fontsize=8, ncol=2)

        fig.suptitle(f"TPR vs window size by anomaly type — {self._tag()}\n(shaded = ±1 std)", fontsize=12)
        plt.tight_layout()
        _save(fig, self._path("tpr_vs_window"))


    def plot_fpr_comparison(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())
        fprs = [df[df["detector_short"] == d]["fpr_mean"].mean() for d in dets]

        fig, ax = plt.subplots(figsize=(9, 4))
        bar_colors = ["#E24B4A" if v > 0.20 else "#EF9F27" if v > 0.10 else "#1D9E75" for v in fprs]
        bars = ax.barh(dets, fprs, color=bar_colors, height=0.5)
        ax.axvline(x=0.05, color="#444441", linestyle="--", linewidth=1, label="5% target")
        ax.axvline(x=0.20, color="#E24B4A", linestyle=":", linewidth=1, label="20% warning")
        for bar, v in zip(bars, fprs):
            ax.text(v + 0.003, bar.get_y() + bar.get_height()/2,
                    f"{v*100:.1f}%", va="center", fontsize=9)
        ax.set_xlabel("Average FPR (across all anomaly types and window sizes)")
        ax.set_xlim(0, max(fprs) * 1.25)
        ax.legend(fontsize=9)
        ax.set_title(f"Average false positive rate — {self._tag()}\n(green < 10%, amber 10-20%, red > 20%)", fontsize=11)
        plt.tight_layout()
        _save(fig, self._path("fpr_summary"))


    def plot_detection_rate(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())
        ats  = ANOMALY_TYPES

        avg_dr = np.zeros((len(dets), len(ats)))
        for i, d in enumerate(dets):
            for j, at in enumerate(ats):
                rows = df[(df["detector_short"] == d) & (df["anomaly_type"] == at)]
                avg_dr[i, j] = rows["detection_rate"].mean() if not rows.empty else 0

        fig, ax = plt.subplots(figsize=(8, max(4, len(dets) * 0.65 + 1.5)))
        im = ax.imshow(avg_dr, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(ats)))
        ax.set_xticklabels([a.replace("_", "\n") for a in ats], fontsize=10)
        ax.set_yticks(range(len(dets)))
        ax.set_yticklabels(dets, fontsize=10)
        for i in range(len(dets)):
            for j in range(len(ats)):
                v = avg_dr[i, j]
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        fontsize=9, color="white" if v < 0.4 or v > 0.75 else "#2C2C2A")
        fig.colorbar(im, ax=ax, label="Detection rate", shrink=0.8)
        ax.set_title(f"Detection rate (avg across window sizes) — {self._tag()}", fontsize=11)
        plt.tight_layout()
        _save(fig, self._path("detection_rate"))


    def plot_f1_vs_window(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())
        ats  = ANOMALY_TYPES

        fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharey=True)
        axes = axes.flatten()

        for ax, at in zip(axes, ats):
            for d in dets:
                rows = df[(df["detector_short"] == d) & (df["anomaly_type"] == at)].sort_values("window_size")
                if rows.empty:
                    continue
                ax.plot(rows["window_size"], rows["f1_mean"],
                        marker="s", linewidth=2, markersize=5,
                        color=_color(d), label=d)
            ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
            ax.set_xlabel("Window size (N)")
            ax.set_ylabel("F1 score")
            ax.set_xticks(WINDOW_SIZES)
            ax.set_ylim(0, max(0.1, df["f1_mean"].max() * 1.15))
            ax.grid(axis="y", linewidth=0.4, alpha=0.5)
            if ax is axes[0]:
                ax.legend(fontsize=8, ncol=2)

        fig.suptitle(f"F1 score vs window size — {self._tag()}", fontsize=12)
        plt.tight_layout()
        _save(fig, self._path("f1_vs_window"))


    def plot_detection_latency(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())
        ats  = ANOMALY_TYPES

        fig, axes = plt.subplots(2, 2, figsize=(14, 9))
        axes = axes.flatten()

        for ax, at in zip(axes, ats):
            lats  = []
            lbls  = []
            clrs  = []
            for d in dets:
                rows = df[(df["detector_short"] == d) & (df["anomaly_type"] == at) & (df["avg_detection_latency"] >= 0)]
                if not rows.empty:
                    lats.append(rows["avg_detection_latency"].tolist())
                    lbls.append(d)
                    clrs.append(_color(d))
            if lats:
                bp = ax.boxplot(lats, labels=lbls, patch_artist=True,
                                medianprops={"color": "#2C2C2A", "linewidth": 2})
                for patch, c in zip(bp["boxes"], clrs):
                    patch.set_facecolor(c)
                    patch.set_alpha(0.7)
            ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
            ax.set_ylabel("Detection latency (samples)")
            ax.tick_params(axis="x", rotation=25)
            ax.axhline(y=5, color="#D85A30", linestyle="--", linewidth=0.8, label="5-sample window")

        fig.suptitle(f"Detection latency distribution — {self._tag()}", fontsize=12)
        plt.tight_layout()
        _save(fig, self._path("detection_latency"))


    def plot_radar(self) -> None:
        df   = self.df
        dets = sorted(df["detector_short"].unique())

        metrics = {}
        for d in dets:
            sub = df[df["detector_short"] == d]
            metrics[d] = {
                "TPR burst":    sub[sub["anomaly_type"]=="burst"]["tpr_mean"].mean(),
                "TPR transient":sub[sub["anomaly_type"]=="transient"]["tpr_mean"].mean(),
                "TPR rate shift":sub[sub["anomaly_type"]=="rate_shift"]["tpr_mean"].mean(),
                "TPR gradual drift":sub[sub["anomaly_type"]=="gradual_drift"]["tpr_mean"].mean(),
                "Low FPR (1-FPR)":1 - sub["fpr_mean"].mean(),
            }

        labels = list(list(metrics.values())[0].keys())
        N = len(labels)
        angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})
        for d in dets:
            vals = [metrics[d][l] for l in labels]
            vals += vals[:1]
            ax.plot(angles, vals, linewidth=2, color=_color(d), label=d)
            ax.fill(angles, vals, alpha=0.08, color=_color(d))

        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylim(0, 1)
        ax.set_yticks([0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=7)
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9)
        ax.set_title(f"Detector capability radar — {self._tag()}\n(larger area = better overall)", fontsize=11, pad=20)
        plt.tight_layout()
        _save(fig, self._path("radar"))



def compare_iterations(
    csv_iter1: str,
    csv_iter2: str,
    out_dir:   str,
    dpi:       int = 150,
) -> None:
    """
    Generate side-by-side comparison plots between Iteration 1 and Iteration 2.

    Parameters
    ----------
    csv_iter1 : path to aggregated_results.csv from Iteration 1
    csv_iter2 : path to aggregated_results.csv from Iteration 2
    out_dir   : output folder for comparison plots
    """
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(csv_iter1):
        print(f"WARNING: Iter1 CSV not found at {csv_iter1} — comparison plots skipped.")
        return
    if not os.path.exists(csv_iter2):
        print(f"WARNING: Iter2 CSV not found at {csv_iter2} — comparison plots skipped.")
        return

    df1 = _load(csv_iter1)
    df2 = _load(csv_iter2)

    print(f"[compare] Iter1: {len(df1)} rows, Iter2: {len(df2)} rows")

    _compare_tpr(df1, df2, out_dir, dpi)
    _compare_fpr(df1, df2, out_dir, dpi)
    _compare_f1(df1, df2, out_dir, dpi)
    _compare_detection_rate(df1, df2, out_dir, dpi)
    print(f"[compare] Comparison plots saved to {out_dir}/")


def _compare_tpr(df1, df2, out_dir, dpi):
    dets = sorted(set(df1["detector_short"].unique()) | set(df2["detector_short"].unique()))
    ats  = ANOMALY_TYPES

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()

    for ax, at in zip(axes, ats):
        x      = np.arange(len(dets))
        width  = 0.35
        tpr1   = [df1[(df1["detector_short"]==d) & (df1["anomaly_type"]==at)]["tpr_mean"].mean() for d in dets]
        tpr2   = [df2[(df2["detector_short"]==d) & (df2["anomaly_type"]==at)]["tpr_mean"].mean() for d in dets]

        b1 = ax.bar(x - width/2, tpr1, width, label="Iter 1", color="#B4B2A9", alpha=0.9)
        b2 = ax.bar(x + width/2, tpr2, width, label="Iter 2", color=[_color(d) for d in dets], alpha=0.9)

        for i, (v1, v2) in enumerate(zip(tpr1, tpr2)):
            delta = v2 - v1
            if abs(delta) > 0.02:
                color = "#1D9E75" if delta > 0 else "#E24B4A"
                ax.annotate(f"{delta:+.2f}", xy=(x[i] + width/2, v2 + 0.02),
                            ha="center", fontsize=7, color=color, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(dets, rotation=30, ha="right", fontsize=8)
        ax.set_ylim(0, 1.1)
        ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
        if ax is axes[0]:
            ax.legend(fontsize=9)
        ax.set_ylabel("TPR")

    fig.suptitle("TPR comparison: Iteration 1 vs Iteration 2\n(coloured = Iter 2, grey = Iter 1, delta labelled)", fontsize=12)
    plt.tight_layout()
    _save(fig, os.path.join(out_dir, "compare_tpr.png"), dpi)


def _compare_fpr(df1, df2, out_dir, dpi):
    dets = sorted(set(df1["detector_short"].unique()) | set(df2["detector_short"].unique()))

    fpr1 = [df1[df1["detector_short"]==d]["fpr_mean"].mean() for d in dets]
    fpr2 = [df2[df2["detector_short"]==d]["fpr_mean"].mean() for d in dets]

    x     = np.arange(len(dets))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width/2, fpr1, width, label="Iter 1", color="#B4B2A9", alpha=0.9)
    ax.bar(x + width/2, fpr2, width, label="Iter 2", color=[_color(d) for d in dets], alpha=0.9)

    for i, (v1, v2) in enumerate(zip(fpr1, fpr2)):
        delta = v2 - v1
        if abs(delta) > 0.01:
            color = "#1D9E75" if delta < 0 else "#E24B4A"
            ax.annotate(f"{delta:+.2f}", xy=(x[i] + width/2, v2 + 0.008),
                        ha="center", fontsize=8, color=color, fontweight="bold")

    ax.axhline(y=0.05, color="#444441", linestyle="--", linewidth=1, label="5% target")
    ax.set_xticks(x)
    ax.set_xticklabels(dets, rotation=20, ha="right", fontsize=9)
    ax.set_ylim(0, max(max(fpr1), max(fpr2)) * 1.3)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
    ax.legend(fontsize=9)
    ax.set_title("Average FPR comparison: Iteration 1 vs Iteration 2\n(green delta = improvement, red = worse)", fontsize=11)
    ax.set_ylabel("Average FPR")
    plt.tight_layout()
    _save(fig, os.path.join(out_dir, "compare_fpr.png"), dpi)


def _compare_f1(df1, df2, out_dir, dpi):
    dets = sorted(set(df1["detector_short"].unique()) | set(df2["detector_short"].unique()))
    ats  = ANOMALY_TYPES

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()

    for ax, at in zip(axes, ats):
        x     = np.arange(len(dets))
        width = 0.35
        f1_1  = [df1[(df1["detector_short"]==d) & (df1["anomaly_type"]==at)]["f1_mean"].mean() for d in dets]
        f1_2  = [df2[(df2["detector_short"]==d) & (df2["anomaly_type"]==at)]["f1_mean"].mean() for d in dets]

        ax.bar(x - width/2, f1_1, width, label="Iter 1", color="#B4B2A9", alpha=0.9)
        ax.bar(x + width/2, f1_2, width, label="Iter 2", color=[_color(d) for d in dets], alpha=0.9)

        for i, (v1, v2) in enumerate(zip(f1_1, f1_2)):
            delta = v2 - v1
            if abs(delta) > 0.001:
                color = "#1D9E75" if delta > 0 else "#E24B4A"
                ax.annotate(f"{delta:+.3f}", xy=(x[i] + width/2, v2 + 0.0005),
                            ha="center", fontsize=7, color=color, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(dets, rotation=30, ha="right", fontsize=8)
        ax.set_title(at.replace("_", " ").title(), fontsize=11, fontweight="bold")
        ax.set_ylabel("F1 score")
        if ax is axes[0]:
            ax.legend(fontsize=9)

    fig.suptitle("F1 score comparison: Iteration 1 vs Iteration 2", fontsize=12)
    plt.tight_layout()
    _save(fig, os.path.join(out_dir, "compare_f1.png"), dpi)


def _compare_detection_rate(df1, df2, out_dir, dpi):
    dets = sorted(set(df1["detector_short"].unique()) | set(df2["detector_short"].unique()))

    dr1 = [df1[df1["detector_short"]==d]["detection_rate"].mean() for d in dets]
    dr2 = [df2[df2["detector_short"]==d]["detection_rate"].mean() for d in dets]

    x     = np.arange(len(dets))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width/2, dr1, width, label="Iter 1", color="#B4B2A9", alpha=0.9)
    ax.bar(x + width/2, dr2, width, label="Iter 2", color=[_color(d) for d in dets], alpha=0.9)

    for i, (v1, v2) in enumerate(zip(dr1, dr2)):
        delta = v2 - v1
        if abs(delta) > 0.01:
            color = "#1D9E75" if delta > 0 else "#E24B4A"
            ax.annotate(f"{delta:+.2f}", xy=(x[i] + width/2, v2 + 0.01),
                        ha="center", fontsize=8, color=color, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(dets, rotation=20, ha="right", fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
    ax.legend(fontsize=9)
    ax.set_title("Detection rate comparison: Iteration 1 vs Iteration 2", fontsize=11)
    ax.set_ylabel("Detection rate (avg across all conditions)")
    plt.tight_layout()
    _save(fig, os.path.join(out_dir, "compare_detection_rate.png"), dpi)
