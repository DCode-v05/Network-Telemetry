"""
Phase 3 dashboard — Plotly-based interactive HTML report.

Adapted from Phase 2's generator. Differences:
- Extended DET_ORDER / DET_COLORS to include gated and ensemble detectors.
- Two new figures:
    Figure 9  — Ensemble vs Best-Individual F1 (per anomaly type).
    Figure 10 — Confirmation gate FP reduction.
- Optional Figure 11 when --compare_phase2_csv is provided.
- Reads from Phase 3/results/csv/ and emits Phase 3/results/dashboard.html.
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_HERE      = os.path.dirname(os.path.abspath(__file__))
_PHASE3    = os.path.dirname(_HERE)
if _PHASE3 not in sys.path:
    sys.path.insert(0, _PHASE3)

from evaluation.phase3_metrics import (
    load_aggregated_csv,
    load_raw_csv,
    ensemble_vs_best_single,
    gate_fp_reduction,
    per_anomaly_winner,
)

BASE_DIR    = _PHASE3
AGG_CSV     = os.path.join(BASE_DIR, "results", "csv", "aggregated_results.csv")
RAW_CSV     = os.path.join(BASE_DIR, "results", "csv", "raw_trial_results.csv")
OUTPUT_HTML = os.path.join(BASE_DIR, "results", "dashboard.html")

ANOMALY_TYPES = ["burst", "rate_shift", "gradual_drift", "transient"]

DET_ORDER = [
    "ZScore", "MAD", "EWMA", "CUSUM", "PageHinkley", "SlidingWindow",
    "GatedZScore", "GatedMAD", "GatedEWMA", "GatedCUSUM",
    "Spike_AND", "Spike_OR", "Sustained_OR", "TwoLayerEnsemble",
]

DET_COLORS = {
    "ZScore":           "#1D9E75",
    "MAD":              "#7F77DD",
    "EWMA":             "#D85A30",
    "CUSUM":            "#378ADD",
    "PageHinkley":      "#BA7517",
    "SlidingWindow":    "#888780",
    "GatedZScore":      "#A8D5C2",
    "GatedMAD":         "#BBB6E8",
    "GatedEWMA":        "#EBB7A2",
    "GatedCUSUM":       "#A2C4E8",
    "Spike_AND":        "#E0457B",
    "Spike_OR":         "#F09EBC",
    "Sustained_OR":     "#7BC8B7",
    "TwoLayerEnsemble": "#F4C152",
}

_FIG_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Segoe UI, system-ui, sans-serif", size=13),
    margin=dict(l=60, r=30, t=50, b=50),
)



def short_name(full_name: str) -> str:
    """'GatedMAD(n=2)' -> 'GatedMAD'; 'Spike_AND(MAD+ZScore)' -> 'Spike_AND'.
    'TwoLayerEnsemble[default]' -> 'TwoLayerEnsemble'."""
    base = full_name.split("(", 1)[0]
    return base.split("[", 1)[0]


def det_color(short: str) -> str:
    return DET_COLORS.get(short, "#888888")


def load_data():
    missing = [p for p in (AGG_CSV, RAW_CSV) if not os.path.exists(p)]
    if missing:
        print("\n[dashboard] ERROR: Required CSV files not found:")
        for p in missing:
            print(f"  - {p}")
        print("\nRun the evaluation first:  python main.py")
        sys.exit(1)

    agg_df = pd.read_csv(AGG_CSV)
    raw_df = pd.read_csv(RAW_CSV)
    agg_df["detector_short"] = agg_df["detector"].apply(short_name)
    raw_df["detector_short"] = raw_df["detector"].apply(short_name)
    return agg_df, raw_df


def _present_window_sizes(agg_df: pd.DataFrame) -> list:
    """Window sizes actually present in the data (smoke runs may use only one)."""
    return sorted(agg_df["window_size"].unique().tolist())



def _heatmap_figure(agg_df, z_col, title_prefix, colorscale):
    windows = _present_window_sizes(agg_df)
    dets    = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]

    traces = []
    all_annotations = []
    for idx, w in enumerate(windows):
        sub = agg_df[agg_df["window_size"] == w]
        z_matrix = []
        for d in dets:
            row = []
            for at in ANOMALY_TYPES:
                cell = sub[(sub["detector_short"] == d) & (sub["anomaly_type"] == at)]
                row.append(float(cell[z_col].values[0]) if len(cell) else 0.0)
            z_matrix.append(row)

        ann = []
        for ri, d in enumerate(dets):
            for ci, at in enumerate(ANOMALY_TYPES):
                v = z_matrix[ri][ci]
                ann.append(dict(
                    x=ci, y=ri, text=f"{v:.2f}", showarrow=False,
                    font=dict(color="white" if v > 0.55 else "#333", size=11),
                ))
        all_annotations.append(ann)

        traces.append(go.Heatmap(
            z=z_matrix, x=ANOMALY_TYPES, y=dets,
            colorscale=colorscale, zmin=0, zmax=1,
            showscale=True,
            hovertemplate=("<b>%{y}</b><br>Anomaly: %{x}<br>"
                           f"{z_col}: " + "%{z:.3f}<extra></extra>"),
            visible=(idx == 0),
        ))

    buttons = []
    for idx, w in enumerate(windows):
        buttons.append(dict(
            label=f"Window = {w}",
            method="update",
            args=[
                {"visible": [i == idx for i in range(len(windows))]},
                {"title.text": f"{title_prefix} — Window Size {w}",
                 "annotations": all_annotations[idx]},
            ],
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text=f"{title_prefix} — Window Size {windows[0]}", x=0.5),
        xaxis=dict(title="Anomaly Type"),
        yaxis=dict(title="Detector"),
        annotations=all_annotations[0],
        height=max(420, len(dets) * 28 + 120),
        updatemenus=[dict(type="dropdown", direction="down",
                          x=1.0, xanchor="right", y=1.12, yanchor="top",
                          buttons=buttons, showactive=True)] if len(windows) > 1 else [],
    )
    return fig


def make_f1_heatmap(agg_df):
    return _heatmap_figure(agg_df, "f1_mean", "F1 Score Heatmap", "YlGn")


def make_detection_rate_heatmap(agg_df):
    return _heatmap_figure(agg_df, "detection_rate", "Detection Rate Heatmap", "RdYlGn")



def make_tpr_fpr_bars(agg_df):
    dets = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]
    grouped = (agg_df.groupby(["detector_short", "anomaly_type"])
               [["tpr_mean", "fpr_mean"]].mean().reset_index())

    tpr_traces, fpr_traces = [], []
    for d in dets:
        sub = grouped[grouped["detector_short"] == d]
        tpr_vals = [float(sub[sub["anomaly_type"] == at]["tpr_mean"].values[0])
                    if len(sub[sub["anomaly_type"] == at]) else 0.0
                    for at in ANOMALY_TYPES]
        fpr_vals = [float(sub[sub["anomaly_type"] == at]["fpr_mean"].values[0])
                    if len(sub[sub["anomaly_type"] == at]) else 0.0
                    for at in ANOMALY_TYPES]
        common = dict(x=ANOMALY_TYPES, name=d, marker_color=det_color(d),
                      legendgroup=d,
                      hovertemplate="%{x}<br>" + d + ": %{y:.3f}<extra></extra>")
        tpr_traces.append(go.Bar(**common, y=tpr_vals, visible=True))
        fpr_traces.append(go.Bar(**common, y=fpr_vals, visible=False))

    n = len(dets)
    fpr_shape = [dict(type="line", xref="paper", x0=0, x1=1,
                      y0=0.05, y1=0.05,
                      line=dict(color="#e94560", width=1.5, dash="dash"))]
    buttons = [
        dict(label="TPR", method="update",
             args=[{"visible": [True]*n + [False]*n},
                   {"yaxis.title.text": "TPR (True Positive Rate)", "shapes": []}]),
        dict(label="FPR", method="update",
             args=[{"visible": [False]*n + [True]*n},
                   {"yaxis.title.text": "FPR (False Positive Rate)", "shapes": fpr_shape}]),
    ]

    fig = go.Figure(data=tpr_traces + fpr_traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        barmode="group",
        title=dict(text="TPR & FPR by Anomaly Type (avg across window sizes)", x=0.5),
        xaxis=dict(title="Anomaly Type"),
        yaxis=dict(title="TPR (True Positive Rate)", range=[0, 1]),
        legend=dict(orientation="h", y=-0.25),
        updatemenus=[dict(type="dropdown", direction="down",
                          x=1.0, xanchor="right", y=1.12, yanchor="top",
                          buttons=buttons, showactive=True)],
    )
    return fig



def make_f1_vs_window(agg_df):
    windows = _present_window_sizes(agg_df)
    dets    = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]
    if len(windows) < 2:
        fig = go.Figure(go.Bar(x=dets, y=[0]*len(dets)))
        fig.update_layout(**_FIG_LAYOUT,
                          title=dict(text="F1 vs Window — single window only", x=0.5),
                          height=300)
        return fig

    traces = []
    for at in ANOMALY_TYPES:
        for d in dets:
            sub = (agg_df[(agg_df["detector_short"] == d)
                          & (agg_df["anomaly_type"] == at)]
                   .sort_values("window_size"))
            traces.append(go.Scatter(
                x=sub["window_size"].tolist(),
                y=sub["f1_mean"].tolist(),
                mode="lines+markers",
                name=d, legendgroup=d,
                showlegend=(at == ANOMALY_TYPES[0]),
                line=dict(color=det_color(d), width=2),
                marker=dict(size=7),
                visible=(at == ANOMALY_TYPES[0]),
                hovertemplate=(f"<b>{d}</b> / {at}<br>"
                               "Window: %{x}<br>F1: %{y:.3f}<extra></extra>"),
            ))

    n_dets = len(dets)
    buttons = []
    for ai, at in enumerate(ANOMALY_TYPES):
        visible_arr = []
        for ti in range(len(ANOMALY_TYPES)):
            visible_arr.extend([ti == ai] * n_dets)
        buttons.append(dict(label=at.replace("_", " ").title(), method="update",
            args=[{"visible": visible_arr},
                  {"title.text": f"F1 Score vs Window Size — {at.replace('_',' ').title()}"}]))

    fig = go.Figure(data=traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text=f"F1 Score vs Window Size — {ANOMALY_TYPES[0].replace('_',' ').title()}", x=0.5),
        xaxis=dict(title="Window Size", tickvals=windows),
        yaxis=dict(title="Mean F1 Score", range=[0, 1]),
        legend=dict(orientation="h", y=-0.25),
        updatemenus=[dict(type="dropdown", direction="down",
                          x=1.0, xanchor="right", y=1.12, yanchor="top",
                          buttons=buttons, showactive=True)],
    )
    return fig



def make_latency_bars(agg_df):
    filtered = agg_df[agg_df["avg_detection_latency"] >= 0].copy()
    filtered = filtered.sort_values(
        ["anomaly_type", "detector_short"],
        key=lambda col: col.map(
            {v: i for i, v in enumerate(ANOMALY_TYPES)} if col.name == "anomaly_type"
            else {v: i for i, v in enumerate(DET_ORDER)}
        ) if col.name in ("anomaly_type", "detector_short") else col,
    )
    filtered["label"] = filtered["detector_short"] + " / " + filtered["anomaly_type"]

    fig = go.Figure(go.Bar(
        x=filtered["avg_detection_latency"].tolist(),
        y=filtered["label"].tolist(),
        orientation="h",
        marker_color=[det_color(d) for d in filtered["detector_short"]],
        error_x=dict(type="data",
                     array=filtered["stdev_detection_latency"].tolist(),
                     visible=True, color="rgba(255,255,255,0.5)"),
        hovertemplate=("<b>%{y}</b><br>Avg Latency: %{x:.2f} samples<extra></extra>"),
    ))
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text="Detection Latency (samples after anomaly start)", x=0.5),
        xaxis=dict(title="Avg Detection Latency (samples)"),
        yaxis=dict(autorange="reversed"),
        height=max(400, len(filtered) * 18 + 100),
    )
    return fig



def make_radar_chart(agg_df):
    dets = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]
    AXES = ["F1 Score", "TPR", "Precision", "Detection Rate", "Low FPR"]
    COLS = ["f1_mean", "tpr_mean", "precision_mean", "detection_rate", "fpr_mean"]

    raw = {}
    for d in dets:
        sub = agg_df[agg_df["detector_short"] == d]
        vals = [sub[c].mean() for c in COLS]
        vals[-1] = 1.0 - vals[-1]
        raw[d] = vals

    axis_min = [min(raw[d][i] for d in dets) for i in range(len(AXES))]
    axis_max = [max(raw[d][i] for d in dets) for i in range(len(AXES))]

    def normalize(vals):
        return [(v - axis_min[i]) / max(axis_max[i] - axis_min[i], 1e-9)
                for i, v in enumerate(vals)]

    traces = []
    for d in dets:
        norm = normalize(raw[d])
        r    = norm + [norm[0]]
        theta = AXES + [AXES[0]]
        color = det_color(d)
        rr, gg, bb = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        custom = [f"{AXES[i]}: {raw[d][i]:.3f}" for i in range(len(AXES))] \
                 + [f"{AXES[0]}: {raw[d][0]:.3f}"]
        traces.append(go.Scatterpolar(
            r=r, theta=theta, fill="toself",
            fillcolor=f"rgba({rr},{gg},{bb},0.18)",
            line=dict(color=color, width=2),
            name=d,
            hovertemplate="<b>" + d + "</b><br>%{customdata}<extra></extra>",
            customdata=custom,
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text="Detector Capability Profile (normalized)", x=0.5),
        polar=dict(radialaxis=dict(visible=True, range=[0, 1], tickfont=dict(size=10)),
                   angularaxis=dict(tickfont=dict(size=11))),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig



def make_ensemble_vs_best_individual(agg_rows):
    deltas = ensemble_vs_best_single(agg_rows, ensemble_name="TwoLayerEnsemble")
    if not deltas:
        fig = go.Figure()
        fig.update_layout(**_FIG_LAYOUT,
                          title=dict(text="Ensemble vs Best Individual — no data", x=0.5),
                          height=300)
        return fig

    df = pd.DataFrame(deltas)
    g = df.groupby("anomaly_type").agg(
        ensemble_f1   = ("ensemble_f1",   "mean"),
        best_f1       = ("best_single_f1", "mean"),
        ensemble_tpr  = ("ensemble_tpr",  "mean"),
        ensemble_fpr  = ("ensemble_fpr",  "mean"),
        best_tpr      = ("best_single_tpr", "mean"),
        best_fpr      = ("best_single_fpr", "mean"),
        best_name     = ("best_single", lambda s: s.value_counts().index[0]),
    ).reindex(ANOMALY_TYPES)

    x = ANOMALY_TYPES
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=g["best_f1"].values,
        name="Best individual F1",
        marker_color="#7F77DD",
        text=[f"{name.split('(')[0]}<br>F1={f:.2f}"
              for name, f in zip(g["best_name"], g["best_f1"])],
        textposition="outside",
        hovertemplate=("Best: %{text}<br>"
                       "TPR: %{customdata[0]:.3f}<br>"
                       "FPR: %{customdata[1]:.3f}<extra></extra>"),
        customdata=np.stack([g["best_tpr"], g["best_fpr"]], axis=1),
    ))
    fig.add_trace(go.Bar(
        x=x, y=g["ensemble_f1"].values,
        name="TwoLayerEnsemble F1",
        marker_color="#F4C152",
        text=[f"F1={f:.2f}" for f in g["ensemble_f1"]],
        textposition="outside",
        hovertemplate=("Ensemble<br>"
                       "TPR: %{customdata[0]:.3f}<br>"
                       "FPR: %{customdata[1]:.3f}<extra></extra>"),
        customdata=np.stack([g["ensemble_tpr"], g["ensemble_fpr"]], axis=1),
    ))
    fig.update_layout(
        **_FIG_LAYOUT,
        barmode="group",
        title=dict(text="Ensemble vs Best Individual Detector (avg across windows)", x=0.5),
        xaxis=dict(title="Anomaly Type"),
        yaxis=dict(title="Mean F1 Score", range=[0, 1.15]),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig



def make_gate_fp_reduction(raw_rows):
    reductions = gate_fp_reduction(raw_rows)
    if not reductions:
        fig = go.Figure()
        fig.update_layout(**_FIG_LAYOUT,
                          title=dict(text="Gate FP Reduction — no gated detectors found", x=0.5),
                          height=300)
        return fig

    families = list(reductions.keys())
    fp_red   = [reductions[f]["fp_reduction_pct"] * 100 for f in families]
    tp_ret   = [reductions[f]["tp_retention_pct"] * 100 for f in families]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=fp_red, y=families, orientation="h",
        name="FPs eliminated by gate",
        marker_color="#1D9E75",
        text=[f"{v:.1f}%" for v in fp_red],
        textposition="outside",
        hovertemplate="%{y}<br>FP reduction: %{x:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=tp_ret, y=families, orientation="h",
        name="TP retained after gating",
        marker_color="#D85A30",
        text=[f"{v:.1f}%" for v in tp_ret],
        textposition="outside",
        hovertemplate="%{y}<br>TP retained: %{x:.1f}%<extra></extra>",
        visible="legendonly",
    ))
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text="Confirmation-Gate Effect: FP reduction vs TP retention", x=0.5),
        xaxis=dict(title="Percent (%)", range=[0, 110]),
        yaxis=dict(title="Detector family", autorange="reversed"),
        legend=dict(orientation="h", y=-0.25),
        height=max(320, len(families) * 50 + 120),
    )
    return fig



def make_phase_comparison(p2_rows, p3_rows):
    p2_winner = per_anomaly_winner(p2_rows)
    p3_deltas = ensemble_vs_best_single(p3_rows, ensemble_name="TwoLayerEnsemble")
    p3_df     = pd.DataFrame(p3_deltas) if p3_deltas else None
    if p3_df is None or p3_df.empty:
        return None

    p3_by_anom = p3_df.groupby("anomaly_type")["ensemble_f1"].mean()

    rows = []
    for at in ANOMALY_TYPES:
        if at in p2_winner and at in p3_by_anom.index:
            rows.append({
                "anomaly_type":   at,
                "phase2_winner":  p2_winner[at]["detector"].split("(", 1)[0],
                "phase2_f1":      p2_winner[at]["f1_mean"],
                "phase3_ensemble_f1": float(p3_by_anom[at]),
            })
    if not rows:
        return None

    df = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["anomaly_type"], y=df["phase2_f1"],
                         name="Phase 2 best individual", marker_color="#7F77DD",
                         text=df["phase2_winner"], textposition="outside"))
    fig.add_trace(go.Bar(x=df["anomaly_type"], y=df["phase3_ensemble_f1"],
                         name="Phase 3 TwoLayerEnsemble", marker_color="#F4C152",
                         text=[f"{v:.2f}" for v in df["phase3_ensemble_f1"]],
                         textposition="outside"))
    fig.update_layout(
        **_FIG_LAYOUT,
        barmode="group",
        title=dict(text="Phase 2 best individual vs Phase 3 ensemble", x=0.5),
        xaxis=dict(title="Anomaly Type"),
        yaxis=dict(title="Mean F1 Score", range=[0, 1.15]),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig



def fig_to_html(fig, first=False):
    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if first else False,
        config={"displayModeBar": True, "responsive": True},
    )


def build_html(chart_divs, timestamp, has_compare):
    compare_section = (f"""
    <section id="phase-compare">
      <h2>Phase 2 vs Phase 3</h2>
      <p class="desc">Side-by-side: Phase 2's best individual detector vs the
        Phase 3 TwoLayerEnsemble, per anomaly type.</p>
      {chart_divs['phase_compare']}
    </section>""" if has_compare else "")

    compare_link = (
        '<a href="#phase-compare">Phase 2 vs 3</a>'
        if has_compare else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Phase 3 — Ensemble Anomaly Detection Dashboard</title>
  <style>
    :root[data-theme="dark"] {{
      --bg: #1a1a2e; --surface: #16213e; --text: #e0e0e0;
      --subtext: #8899aa; --border: #2a2a5a;
      --nav-bg: #0f3460; --accent: #F4C152;
    }}
    :root[data-theme="light"] {{
      --bg: #f0f2f8; --surface: #ffffff; --text: #1a1a2e;
      --subtext: #556677; --border: #c5c8d8;
      --nav-bg: #1a1a2e; --accent: #F4C152;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif;
           background: var(--bg); color: var(--text);
           transition: background 0.25s, color 0.25s; }}

    nav {{ position: sticky; top: 0; z-index: 100; background: var(--nav-bg);
           padding: 0 2rem; height: 52px; display: flex; align-items: center;
           gap: 1rem; box-shadow: 0 2px 10px rgba(0,0,0,0.4); }}
    .nav-logo {{ font-size: 0.92rem; font-weight: 700; color: #fff;
                 margin-right: auto; white-space: nowrap; letter-spacing: 0.02em; }}
    nav a {{ color: #aabbcc; text-decoration: none; font-size: 0.78rem;
             padding: 0.3rem 0.5rem; border-radius: 5px;
             transition: background 0.15s, color 0.15s; white-space: nowrap; }}
    nav a:hover {{ background: rgba(255,255,255,0.12); color: #fff; }}
    #theme-btn {{ background: var(--accent); border: none; border-radius: 6px;
                  color: #1a1a2e; cursor: pointer; padding: 0.3rem 0.75rem;
                  font-size: 0.78rem; font-weight: 700; }}
    #theme-btn:hover {{ opacity: 0.85; }}

    header {{ background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
              padding: 3rem 2rem 2rem; text-align: center; }}
    header h1 {{ font-size: 1.75rem; color: #fff; margin-bottom: 0.5rem; font-weight: 700; }}
    header .subtitle {{ color: #aac; font-size: 0.9rem; line-height: 1.6; }}
    header .generated {{ margin-top: 0.6rem; font-size: 0.75rem; color: #6677aa; }}

    main {{ max-width: 1380px; margin: 0 auto; padding: 2rem 1.5rem; }}
    section {{ background: var(--surface); border: 1px solid var(--border);
               border-radius: 12px; padding: 1.5rem 1.75rem; margin-bottom: 2rem;
               scroll-margin-top: 60px; transition: background 0.25s, border-color 0.25s; }}
    section h2 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 0.35rem; color: var(--text); }}
    section p.desc {{ font-size: 0.82rem; color: var(--subtext); margin-bottom: 1rem; line-height: 1.55; }}

    footer {{ text-align: center; padding: 1.5rem; font-size: 0.75rem;
              color: var(--subtext); border-top: 1px solid var(--border); }}
  </style>
</head>
<body>

  <nav>
    <span class="nav-logo">Phase 3 — Ensemble Detection</span>
    <a href="#f1-heatmap">F1</a>
    <a href="#tpr-fpr">TPR/FPR</a>
    <a href="#f1-window">F1 vs W</a>
    <a href="#det-rate">Det. Rate</a>
    <a href="#latency">Latency</a>
    <a href="#radar">Radar</a>
    <a href="#ensemble-vs-best">Ensemble</a>
    <a href="#gate-fp">Gate effect</a>
    {compare_link}
    <button id="theme-btn" onclick="toggleTheme()">Light Mode</button>
  </nav>

  <header>
    <h1>Phase 3 — Two-Layer Ensemble Anomaly Detection</h1>
    <p class="subtitle">
      14 detectors &nbsp;&middot;&nbsp; 4 anomaly types &nbsp;&middot;&nbsp;
      4 window sizes &nbsp;&middot;&nbsp;
      Spike (MAD ∧ Z-Score) ∨ Sustained (EWMA ∨ CUSUM) with 2-of-2 confirmation gate
    </p>
    <p class="generated">Generated: {timestamp}</p>
  </header>

  <main>

    <section id="ensemble-vs-best">
      <h2>Ensemble vs Best Individual Detector</h2>
      <p class="desc">Mean F1 of the TwoLayerEnsemble next to the best individual
        detector per anomaly type (averaged across window sizes). Hover for TPR
        and FPR.</p>
      {chart_divs['ensemble_vs_best']}
    </section>

    <section id="gate-fp">
      <h2>Confirmation-Gate Effect</h2>
      <p class="desc">For each base detector, the bar shows the percentage of
        false positives eliminated by wrapping it in a 2-of-2 confirmation gate.
        Toggle the legend to also show the percentage of true positives retained.</p>
      {chart_divs['gate_fp']}
    </section>

    <section id="f1-heatmap">
      <h2>F1 Score Heatmap</h2>
      <p class="desc">Mean F1 per detector and anomaly type. Use the dropdown
        to switch window sizes.</p>
      {chart_divs['f1_heatmap']}
    </section>

    <section id="tpr-fpr">
      <h2>TPR vs FPR</h2>
      <p class="desc">Grouped bars per detector, averaged across window sizes.
        Toggle TPR/FPR via the dropdown. Dashed line = 5% FPR target.</p>
      {chart_divs['tpr_fpr']}
    </section>

    <section id="f1-window">
      <h2>F1 vs Window Size</h2>
      <p class="desc">F1 trend across window sizes per anomaly type. Use the
        dropdown to filter.</p>
      {chart_divs['f1_window']}
    </section>

    <section id="det-rate">
      <h2>Detection Rate Heatmap</h2>
      <p class="desc">Fraction of trials where the anomaly was detected within
        the 5-sample detection window.</p>
      {chart_divs['det_rate']}
    </section>

    <section id="latency">
      <h2>Detection Latency</h2>
      <p class="desc">Average samples between anomaly start and first alarm
        (only for trials that detected). Error bars: ±1σ.</p>
      {chart_divs['latency']}
    </section>

    <section id="radar">
      <h2>Detector Capability Radar</h2>
      <p class="desc">Normalized 0–1 profile across F1, TPR, Precision,
        Detection Rate, and Low FPR (1 − FPR).</p>
      {chart_divs['radar']}
    </section>

    {compare_section}

  </main>

  <footer>
    Phase 3 — Two-Layer Ensemble &nbsp;&middot;&nbsp;
    HP CPP Internship &nbsp;&middot;&nbsp; Generated {timestamp}
  </footer>

  <script>
    function toggleTheme() {{
      const html = document.documentElement;
      const isDark = html.getAttribute('data-theme') === 'dark';
      html.setAttribute('data-theme', isDark ? 'light' : 'dark');
      document.getElementById('theme-btn').textContent = isDark ? 'Dark Mode' : 'Light Mode';
    }}
  </script>

</body>
</html>"""



def generate(output_path: str = OUTPUT_HTML, compare_phase2_csv: str = None) -> None:
    print("[dashboard] Loading evaluation results...")
    agg_df, raw_df = load_data()

    print("[dashboard] Building charts...")
    agg_rows = load_aggregated_csv(AGG_CSV)
    raw_rows = load_raw_csv(RAW_CSV)

    figures = {
        "ensemble_vs_best": make_ensemble_vs_best_individual(agg_rows),
        "gate_fp":          make_gate_fp_reduction(raw_rows),
        "f1_heatmap":       make_f1_heatmap(agg_df),
        "tpr_fpr":          make_tpr_fpr_bars(agg_df),
        "f1_window":        make_f1_vs_window(agg_df),
        "det_rate":         make_detection_rate_heatmap(agg_df),
        "latency":          make_latency_bars(agg_df),
        "radar":            make_radar_chart(agg_df),
    }

    has_compare = False
    if compare_phase2_csv and os.path.isfile(compare_phase2_csv):
        try:
            p2_rows = load_aggregated_csv(compare_phase2_csv)
            comp = make_phase_comparison(p2_rows, agg_rows)
            if comp is not None:
                figures["phase_compare"] = comp
                has_compare = True
        except Exception as e:
            print(f"[dashboard] Phase 2 comparison skipped: {e}")

    chart_divs = {}
    for i, (key, fig) in enumerate(figures.items()):
        chart_divs[key] = fig_to_html(fig, first=(i == 0))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = build_html(chart_divs, timestamp, has_compare=has_compare)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[dashboard] Dashboard written to: {output_path}")


if __name__ == "__main__":
    generate()
