"""Generate report/dashboard figures from the sweep results (stdlib + numpy + matplotlib).

Reads results/{agg_detector_window.csv, agg_detector_window_type.csv, cost.csv} and writes
PNGs to report/figures/. Robust to a missing C-cost merge (falls back to Python cost).
Run:  python -m eval.figures
"""

from __future__ import annotations

import os
from collections import OrderedDict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from eval.tabio import read_csv, group_mean
from selection.scorecard import intelligence_score, cost_for, passes_budget

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "results"))
FIGS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "report", "figures"))


def _load():
    agg = read_csv(os.path.join(RESULTS, "agg_detector_window.csv"))
    agt = read_csv(os.path.join(RESULTS, "agg_detector_window_type.csv"))
    cost = read_csv(os.path.join(RESULTS, "cost.csv"))
    return agg, agt, cost


def _by(rows, key):
    out = OrderedDict()
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def fig_accuracy_vs_window(agg):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for metric, ax in zip(["vus_pr", "f1"], axes):
        for det, g in _by(agg, "detector").items():
            g = sorted(g, key=lambda r: r["window"])
            xs = [r["window"] for r in g]
            ys = [r[metric] if r[metric] is not None else np.nan for r in g]
            ax.plot(xs, ys, marker="o", label=det, linewidth=1.4)
        ax.set_xlabel("window (samples)"); ax.set_ylabel(metric.upper())
        ax.set_title(f"{metric.upper()} vs observation window"); ax.grid(alpha=0.3)
    axes[1].legend(fontsize=7, ncol=2, loc="lower right")
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "accuracy_vs_window.png"), dpi=130)
    plt.close(fig)


def fig_window_degradation(agg):
    m = group_mean(agg, ["window"], ["vus_pr", "f1", "mcc"])
    m = sorted(m, key=lambda r: r["window"])
    xs = [r["window"] for r in m]
    fig, ax = plt.subplots(figsize=(7, 5))
    for col in ["vus_pr", "f1", "mcc"]:
        ax.plot(xs, [r[col] for r in m], marker="s", label=col.upper())
    ax.set_xlabel("window (samples)"); ax.set_ylabel("mean score across detectors")
    ax.set_title("Accuracy vs window size (mean over all detectors)")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "window_degradation.png"), dpi=130)
    plt.close(fig)


def fig_pareto(agg, cost):
    cidx = {(r["detector"], r["window"]): r for r in cost}
    best = {}
    for row in agg:
        intel = intelligence_score(row)
        d = row["detector"]
        if d not in best or intel > best[d][0]:
            us, by, _ = cost_for(d, row["window"], cidx)
            best[d] = (intel, row["window"], us, by)
    xs, ys, names, oks = [], [], [], []
    for d, (intel, w, us, by) in best.items():
        if us is None:
            continue
        xs.append(us); ys.append(intel); names.append(f"{d}\nw={w}")
        oks.append(passes_budget(us, by)[0])
    fig, ax = plt.subplots(figsize=(9, 6))
    xs, ys = np.array(xs), np.array(ys)
    colors = ["#2ca02c" if ok else "#d62728" for ok in oks]
    ax.scatter(xs, ys, c=colors, s=60, zorder=3)
    for x, y, n in zip(xs, ys, names):
        ax.annotate(n, (x, y), fontsize=7, xytext=(4, 4), textcoords="offset points")
    order = np.argsort(xs); fx, fy, best_y = [], [], -1
    for i in order:
        if ys[i] > best_y:
            fx.append(xs[i]); fy.append(ys[i]); best_y = ys[i]
    ax.plot(fx, fy, "--", color="#1f77b4", label="Pareto frontier", zorder=2)
    ax.set_xscale("log")
    ax.set_xlabel("cost: microseconds per sample (log scale)")
    ax.set_ylabel("intelligence score")
    ax.set_title("Intelligence vs cost (green = within budget)")
    ax.legend(); ax.grid(alpha=0.3, which="both")
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "pareto.png"), dpi=130)
    plt.close(fig)


def fig_type_heatmap(agt):
    best = {}
    dets, types = [], []
    for r in agt:
        d, t, v = r["detector"], r["anomaly_type"], r["vus_pr"]
        if d not in dets:
            dets.append(d)
        if t not in types:
            types.append(t)
        k = (d, t)
        if v is not None and (k not in best or v > best[k]):
            best[k] = v
    mat = np.full((len(dets), len(types)), np.nan)
    for i, d in enumerate(dets):
        for j, t in enumerate(types):
            if (d, t) in best:
                mat[i, j] = best[(d, t)]
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(mat, aspect="auto", cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(len(types)), types, rotation=30, ha="right")
    ax.set_yticks(range(len(dets)), dets, fontsize=8)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            if not np.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center",
                        color="white" if mat[i, j] < 0.6 else "black", fontsize=7)
    ax.set_title("VUS-PR by detector x anomaly type (best window)")
    fig.colorbar(im, ax=ax, label="VUS-PR")
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "type_heatmap.png"), dpi=130)
    plt.close(fig)


def fig_cost(cost):
    wins = sorted({r["window"] for r in cost})
    w = 20 if 20 in wins else wins[0]
    rows = [r for r in cost if r["window"] == w]
    rows.sort(key=lambda r: (r.get("py_us_per_sample") or 1e9))
    dets = [r["detector"] for r in rows]
    py = [r.get("py_us_per_sample") or np.nan for r in rows]
    has_c = any(r.get("c_us_per_sample") is not None for r in rows)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    ax1.barh(dets, py, color="#9467bd", label="Python")
    if has_c:
        ax1.barh(dets, [r.get("c_us_per_sample") or np.nan for r in rows],
                 color="#ff7f0e", alpha=0.8, label="C")
    ax1.axvline(100, color="red", ls="--", label="100 us budget")
    ax1.set_xlabel("microseconds per sample"); ax1.set_xscale("log")
    ax1.set_title(f"Per-sample CPU cost (window={w})"); ax1.legend(fontsize=8)
    use_c = any(r.get("c_state_bytes") is not None for r in rows)
    by = [(r.get("c_state_bytes") if use_c else r.get("state_bytes")) or np.nan for r in rows]
    ax2.barh(dets, by, color="#17becf")
    ax2.axvline(100, color="red", ls="--", label="100 byte budget")
    ax2.set_xlabel("state bytes per metric")
    ax2.set_title(f"Memory footprint (window={w})"); ax2.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIGS, "cost.png"), dpi=130)
    plt.close(fig)


def main():
    os.makedirs(FIGS, exist_ok=True)
    agg, agt, cost = _load()
    fig_accuracy_vs_window(agg)
    fig_window_degradation(agg)
    fig_pareto(agg, cost)
    fig_type_heatmap(agt)
    fig_cost(cost)
    print(f"wrote figures to {FIGS}")


if __name__ == "__main__":
    main()
