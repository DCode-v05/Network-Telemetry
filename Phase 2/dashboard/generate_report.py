# dashboard/generate_report.py
#
# Generates a self-contained interactive HTML dashboard from evaluation CSVs.
# Run standalone:  python dashboard/generate_report.py
# Or called automatically by main.py after evaluation.

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG_CSV     = os.path.join(BASE_DIR, "results", "csv", "aggregated_results.csv")
RAW_CSV     = os.path.join(BASE_DIR, "results", "csv", "raw_trial_results.csv")
OUTPUT_HTML = os.path.join(BASE_DIR, "results", "dashboard.html")

# ── Config constants ──────────────────────────────────────────────────────────
ANOMALY_TYPES = ["burst", "rate_shift", "gradual_drift", "transient"]
WINDOW_SIZES  = [10, 20, 30, 50]
DET_ORDER     = ["ZScore", "MAD", "EWMA", "CUSUM", "PageHinkley", "SlidingWindow"]

DET_COLORS = {
    "ZScore":        "#1D9E75",
    "MAD":           "#7F77DD",
    "EWMA":          "#D85A30",
    "CUSUM":         "#378ADD",
    "PageHinkley":   "#BA7517",
    "SlidingWindow": "#888780",
}

# Common Plotly layout kwargs applied to every figure
_FIG_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Segoe UI, system-ui, sans-serif", size=13),
    margin=dict(l=60, r=30, t=50, b=50),
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def short_name(full_name: str) -> str:
    """'ZScore(w=10, thr=3.0)' -> 'ZScore'. Mirrors visualise.py convention."""
    return full_name.split("(")[0]


def det_color(short: str) -> str:
    return DET_COLORS.get(short, "#888888")


def load_data() -> tuple:
    """Load CSVs, add detector_short column. Exit with clear message if missing."""
    missing = [p for p in (AGG_CSV, RAW_CSV) if not os.path.exists(p)]
    if missing:
        print("\n[dashboard] ERROR: Required CSV files not found:")
        for p in missing:
            print(f"  - {p}")
        print(
            "\nRun the evaluation first:\n"
            "  python main.py\n"
            "Then re-run:\n"
            "  python dashboard/generate_report.py\n"
        )
        sys.exit(1)

    agg_df = pd.read_csv(AGG_CSV)
    raw_df = pd.read_csv(RAW_CSV)
    agg_df["detector_short"] = agg_df["detector"].apply(short_name)
    raw_df["detector_short"] = raw_df["detector"].apply(short_name)
    return agg_df, raw_df


# ── Chart builders ────────────────────────────────────────────────────────────

def _heatmap_figure(agg_df: pd.DataFrame, z_col: str, title_prefix: str,
                    colorscale: str) -> go.Figure:
    """
    Shared logic for F1 and Detection Rate heatmaps.
    One go.Heatmap trace per window_size; dropdown toggles visibility.
    """
    dets = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]

    traces = []
    all_annotations = []   # one list of annotation dicts per window_size

    for idx, w in enumerate(WINDOW_SIZES):
        sub = agg_df[agg_df["window_size"] == w]

        # Build z matrix: rows=detectors, cols=anomaly_types
        z_matrix = []
        for d in dets:
            row = []
            for at in ANOMALY_TYPES:
                cell = sub[(sub["detector_short"] == d) & (sub["anomaly_type"] == at)]
                val  = float(cell[z_col].values[0]) if len(cell) else 0.0
                row.append(val)
            z_matrix.append(row)

        # Annotation dicts for this window_size
        ann_list = []
        for ri, d in enumerate(dets):
            for ci, at in enumerate(ANOMALY_TYPES):
                val = z_matrix[ri][ci]
                ann_list.append(dict(
                    x=ci, y=ri,
                    text=f"{val:.2f}",
                    showarrow=False,
                    font=dict(
                        color="white" if val > 0.55 else "#333",
                        size=12,
                    ),
                ))
        all_annotations.append(ann_list)

        traces.append(go.Heatmap(
            z=z_matrix,
            x=ANOMALY_TYPES,
            y=dets,
            colorscale=colorscale,
            zmin=0, zmax=1,
            showscale=True,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Anomaly: %{x}<br>"
                f"{z_col}: " + "%{z:.3f}<extra></extra>"
            ),
            visible=(idx == 0),
        ))

    # Dropdown buttons
    buttons = []
    for idx, w in enumerate(WINDOW_SIZES):
        visible_arr = [i == idx for i in range(len(WINDOW_SIZES))]
        buttons.append(dict(
            label=f"Window = {w}",
            method="update",
            args=[
                {"visible": visible_arr},
                {
                    "title.text": f"{title_prefix} — Window Size {w}",
                    "annotations": all_annotations[idx],
                },
            ],
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text=f"{title_prefix} — Window Size {WINDOW_SIZES[0]}", x=0.5),
        xaxis=dict(title="Anomaly Type"),
        yaxis=dict(title="Detector"),
        annotations=all_annotations[0],
        updatemenus=[dict(
            type="dropdown",
            direction="down",
            x=1.0, xanchor="right",
            y=1.12, yanchor="top",
            buttons=buttons,
            showactive=True,
        )],
    )
    return fig


def make_f1_heatmap(agg_df: pd.DataFrame) -> go.Figure:
    return _heatmap_figure(agg_df, "f1_mean", "F1 Score Heatmap", "YlGn")


def make_detection_rate_heatmap(agg_df: pd.DataFrame) -> go.Figure:
    return _heatmap_figure(agg_df, "detection_rate", "Detection Rate Heatmap", "RdYlGn")


def make_tpr_fpr_bars(agg_df: pd.DataFrame) -> go.Figure:
    """
    Grouped bars: x=anomaly_type, one bar per detector.
    Dropdown switches between tpr_mean and fpr_mean.
    """
    dets = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]

    # Average across window_sizes for each (detector, anomaly_type)
    grouped = (
        agg_df.groupby(["detector_short", "anomaly_type"])[["tpr_mean", "fpr_mean"]]
        .mean()
        .reset_index()
    )

    tpr_traces, fpr_traces = [], []
    for d in dets:
        sub = grouped[grouped["detector_short"] == d]
        # Align to ANOMALY_TYPES order
        tpr_vals = [float(sub[sub["anomaly_type"] == at]["tpr_mean"].values[0])
                    if len(sub[sub["anomaly_type"] == at]) else 0.0
                    for at in ANOMALY_TYPES]
        fpr_vals = [float(sub[sub["anomaly_type"] == at]["fpr_mean"].values[0])
                    if len(sub[sub["anomaly_type"] == at]) else 0.0
                    for at in ANOMALY_TYPES]

        common = dict(x=ANOMALY_TYPES, name=d, marker_color=det_color(d),
                      legendgroup=d, hovertemplate="%{x}<br>" + d + ": %{y:.3f}<extra></extra>")
        tpr_traces.append(go.Bar(**common, y=tpr_vals, visible=True))
        fpr_traces.append(go.Bar(**common, y=fpr_vals, visible=False))

    n = len(dets)
    tpr_visible = [True]  * n + [False] * n
    fpr_visible = [False] * n + [True]  * n

    # FPR reference line shape
    fpr_shape = [dict(
        type="line", xref="paper", x0=0, x1=1,
        y0=0.05, y1=0.05,
        line=dict(color="#e94560", width=1.5, dash="dash"),
    )]

    buttons = [
        dict(
            label="TPR (True Positive Rate)",
            method="update",
            args=[
                {"visible": tpr_visible},
                {"yaxis.title.text": "TPR (True Positive Rate)", "shapes": []},
            ],
        ),
        dict(
            label="FPR (False Positive Rate)",
            method="update",
            args=[
                {"visible": fpr_visible},
                {"yaxis.title.text": "FPR (False Positive Rate)", "shapes": fpr_shape},
            ],
        ),
    ]

    fig = go.Figure(data=tpr_traces + fpr_traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        barmode="group",
        title=dict(text="TPR & FPR by Anomaly Type (avg across window sizes)", x=0.5),
        xaxis=dict(title="Anomaly Type"),
        yaxis=dict(title="TPR (True Positive Rate)", range=[0, 1]),
        legend=dict(orientation="h", y=-0.2),
        updatemenus=[dict(
            type="dropdown",
            direction="down",
            x=1.0, xanchor="right",
            y=1.12, yanchor="top",
            buttons=buttons,
            showactive=True,
        )],
    )
    return fig


def make_f1_vs_window(agg_df: pd.DataFrame) -> go.Figure:
    """
    Line chart: x=window_size, y=f1_mean.
    24 traces (6 detectors × 4 anomaly_types). Dropdown filters by anomaly_type.
    """
    dets = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]

    traces = []
    for at in ANOMALY_TYPES:
        for d in dets:
            sub = (agg_df[(agg_df["detector_short"] == d) & (agg_df["anomaly_type"] == at)]
                   .sort_values("window_size"))
            traces.append(go.Scatter(
                x=sub["window_size"].tolist(),
                y=sub["f1_mean"].tolist(),
                mode="lines+markers",
                name=d,
                legendgroup=d,
                showlegend=(at == ANOMALY_TYPES[0]),
                line=dict(color=det_color(d), width=2),
                marker=dict(size=7),
                visible=(at == ANOMALY_TYPES[0]),
                hovertemplate=(
                    f"<b>{d}</b> / {at}<br>"
                    "Window: %{x}<br>"
                    "F1: %{y:.3f}<extra></extra>"
                ),
            ))

    n_dets = len(dets)
    buttons = []
    for ai, at in enumerate(ANOMALY_TYPES):
        visible_arr = []
        for ti in range(len(ANOMALY_TYPES)):
            visible_arr.extend([ti == ai] * n_dets)
        buttons.append(dict(
            label=at.replace("_", " ").title(),
            method="update",
            args=[
                {"visible": visible_arr},
                {"title.text": f"F1 Score vs Window Size — {at.replace('_', ' ').title()}"},
            ],
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text=f"F1 Score vs Window Size — {ANOMALY_TYPES[0].replace('_', ' ').title()}", x=0.5),
        xaxis=dict(title="Window Size", tickvals=WINDOW_SIZES),
        yaxis=dict(title="Mean F1 Score", range=[0, 1]),
        legend=dict(orientation="h", y=-0.2),
        updatemenus=[dict(
            type="dropdown",
            direction="down",
            x=1.0, xanchor="right",
            y=1.12, yanchor="top",
            buttons=buttons,
            showactive=True,
        )],
    )
    return fig


def make_latency_bars(agg_df: pd.DataFrame) -> go.Figure:
    """
    Horizontal bar chart: avg detection latency per (detector, anomaly_type).
    Rows with latency == -1 (never detected) are excluded.
    """
    filtered = agg_df[agg_df["avg_detection_latency"] >= 0].copy()
    filtered["detector_short"] = filtered["detector_short"].apply(
        lambda s: s if s in DET_ORDER else s
    )
    filtered = filtered.sort_values(
        ["anomaly_type", "detector_short"],
        key=lambda col: col.map(
            {v: i for i, v in enumerate(ANOMALY_TYPES)} if col.name == "anomaly_type"
            else {v: i for i, v in enumerate(DET_ORDER)}
        ) if col.name in ("anomaly_type", "detector_short") else col,
    )
    filtered["label"] = (
        filtered["detector_short"] + " / " + filtered["anomaly_type"]
    )

    fig = go.Figure(go.Bar(
        x=filtered["avg_detection_latency"].tolist(),
        y=filtered["label"].tolist(),
        orientation="h",
        marker_color=[det_color(d) for d in filtered["detector_short"]],
        error_x=dict(
            type="data",
            array=filtered["stdev_detection_latency"].tolist(),
            visible=True,
            color="rgba(255,255,255,0.5)",
        ),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Avg Latency: %{x:.2f} samples<br>"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text="Detection Latency (samples after anomaly start)", x=0.5),
        xaxis=dict(title="Avg Detection Latency (samples)"),
        yaxis=dict(autorange="reversed"),
        height=max(400, len(filtered) * 22 + 100),
    )
    return fig


def make_radar_chart(agg_df: pd.DataFrame) -> go.Figure:
    """
    Scatterpolar radar chart: 5 axes, one trace per detector.
    Axes: F1, TPR, Precision, Detection Rate, Low FPR (1 - FPR).
    Each axis normalized to [0, 1] across detectors.
    """
    dets = [d for d in DET_ORDER if d in agg_df["detector_short"].unique()]
    AXES = ["F1 Score", "TPR", "Precision", "Detection Rate", "Low FPR"]
    COLS = ["f1_mean", "tpr_mean", "precision_mean", "detection_rate", "fpr_mean"]

    # Raw values per detector (mean across all anomaly_types and window_sizes)
    raw = {}
    for d in dets:
        sub = agg_df[agg_df["detector_short"] == d]
        vals = [sub[c].mean() for c in COLS]
        vals[-1] = 1.0 - vals[-1]   # invert FPR → "Low FPR" (higher = better)
        raw[d] = vals

    # Normalize each axis across detectors
    axis_min = [min(raw[d][i] for d in dets) for i in range(len(AXES))]
    axis_max = [max(raw[d][i] for d in dets) for i in range(len(AXES))]

    def normalize(vals):
        return [
            (v - axis_min[i]) / max(axis_max[i] - axis_min[i], 1e-9)
            for i, v in enumerate(vals)
        ]

    traces = []
    for d in dets:
        norm = normalize(raw[d])
        r    = norm + [norm[0]]          # close the polygon
        theta = AXES + [AXES[0]]

        color = det_color(d)
        r_int = int(color[1:3], 16)
        g_int = int(color[3:5], 16)
        b_int = int(color[5:7], 16)
        fill_color = f"rgba({r_int},{g_int},{b_int},0.2)"

        # Build hover text with raw values
        raw_vals = raw[d]
        custom = [
            f"{AXES[i]}: {raw_vals[i]:.3f}"
            for i in range(len(AXES))
        ] + [f"{AXES[0]}: {raw_vals[0]:.3f}"]

        traces.append(go.Scatterpolar(
            r=r,
            theta=theta,
            fill="toself",
            fillcolor=fill_color,
            line=dict(color=color, width=2),
            name=d,
            hovertemplate="<b>" + d + "</b><br>%{customdata}<extra></extra>",
            customdata=custom,
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        **_FIG_LAYOUT,
        title=dict(text="Detector Capability Profile (normalized)", x=0.5),
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickfont=dict(size=10),
            ),
            angularaxis=dict(tickfont=dict(size=12)),
        ),
        legend=dict(orientation="h", y=-0.1),
    )
    return fig


# ── HTML assembly ─────────────────────────────────────────────────────────────

def fig_to_html(fig: go.Figure, first: bool = False) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if first else False,
        config={"displayModeBar": True, "responsive": True},
    )


def build_html(chart_divs: dict, timestamp: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Phase 2 — Network Anomaly Detection Dashboard</title>
  <style>
    :root[data-theme="dark"] {{
      --bg:      #1a1a2e;
      --surface: #16213e;
      --text:    #e0e0e0;
      --subtext: #8899aa;
      --border:  #2a2a5a;
      --nav-bg:  #0f3460;
      --accent:  #e94560;
    }}
    :root[data-theme="light"] {{
      --bg:      #f0f2f8;
      --surface: #ffffff;
      --text:    #1a1a2e;
      --subtext: #556677;
      --border:  #c5c8d8;
      --nav-bg:  #1a1a2e;
      --accent:  #e94560;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      transition: background 0.25s, color 0.25s;
    }}

    /* ── Nav ── */
    nav {{
      position: sticky; top: 0; z-index: 100;
      background: var(--nav-bg);
      padding: 0 2rem;
      height: 52px;
      display: flex; align-items: center; gap: 1rem;
      box-shadow: 0 2px 10px rgba(0,0,0,0.4);
    }}
    .nav-logo {{
      font-size: 0.92rem; font-weight: 700; color: #fff;
      margin-right: auto; white-space: nowrap; letter-spacing: 0.02em;
    }}
    nav a {{
      color: #aabbcc; text-decoration: none; font-size: 0.8rem;
      padding: 0.3rem 0.55rem; border-radius: 5px;
      transition: background 0.15s, color 0.15s; white-space: nowrap;
    }}
    nav a:hover {{ background: rgba(255,255,255,0.12); color: #fff; }}
    #theme-btn {{
      background: var(--accent); border: none; border-radius: 6px;
      color: #fff; cursor: pointer; padding: 0.3rem 0.75rem;
      font-size: 0.78rem; font-weight: 600; letter-spacing: 0.03em;
      transition: opacity 0.15s;
    }}
    #theme-btn:hover {{ opacity: 0.85; }}

    /* ── Hero ── */
    header {{
      background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
      padding: 3rem 2rem 2rem; text-align: center;
    }}
    header h1 {{ font-size: 1.75rem; color: #fff; margin-bottom: 0.5rem; font-weight: 700; }}
    header .subtitle {{ color: #aac; font-size: 0.9rem; line-height: 1.6; }}
    header .generated {{ margin-top: 0.6rem; font-size: 0.75rem; color: #6677aa; }}

    /* ── Main layout ── */
    main {{ max-width: 1380px; margin: 0 auto; padding: 2rem 1.5rem; }}

    /* ── Chart sections ── */
    section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem 1.75rem;
      margin-bottom: 2rem;
      scroll-margin-top: 60px;
      transition: background 0.25s, border-color 0.25s;
    }}
    section h2 {{
      font-size: 1.1rem; font-weight: 600;
      margin-bottom: 0.35rem; color: var(--text);
    }}
    section p.desc {{
      font-size: 0.82rem; color: var(--subtext);
      margin-bottom: 1rem; line-height: 1.55;
    }}

    /* ── Footer ── */
    footer {{
      text-align: center; padding: 1.5rem;
      font-size: 0.75rem; color: var(--subtext);
      border-top: 1px solid var(--border);
    }}
  </style>
</head>
<body>

  <nav>
    <span class="nav-logo">Phase 2 — Anomaly Detection</span>
    <a href="#f1-heatmap">F1 Heatmap</a>
    <a href="#tpr-fpr">TPR / FPR</a>
    <a href="#f1-window">F1 vs Window</a>
    <a href="#det-rate">Detection Rate</a>
    <a href="#latency">Latency</a>
    <a href="#radar">Radar</a>
    <button id="theme-btn" onclick="toggleTheme()">Light Mode</button>
  </nav>

  <header>
    <h1>Phase 2 — Network Anomaly Detection Dashboard</h1>
    <p class="subtitle">
      Benchmark results across 6 detectors &nbsp;&middot;&nbsp;
      4 anomaly types &nbsp;&middot;&nbsp;
      4 window sizes &nbsp;&middot;&nbsp;
      30 trials each (CESNET dataset)
    </p>
    <p class="generated">Generated: {timestamp}</p>
  </header>

  <main>

    <section id="f1-heatmap">
      <h2>F1 Score Heatmap</h2>
      <p class="desc">
        Mean F1 score per detector and anomaly type. Use the dropdown (top-right of the chart)
        to switch between window sizes. Darker green = better precision-recall balance.
        Cell values are annotated directly on each tile.
      </p>
      {chart_divs['f1_heatmap']}
    </section>

    <section id="tpr-fpr">
      <h2>True Positive Rate vs False Positive Rate</h2>
      <p class="desc">
        Grouped bars showing mean TPR and FPR per detector, averaged across all window sizes.
        Use the dropdown to switch between metrics. The dashed red line at 0.05 marks
        the typical acceptable FPR threshold when viewing FPR.
      </p>
      {chart_divs['tpr_fpr']}
    </section>

    <section id="f1-window">
      <h2>F1 Score vs Window Size</h2>
      <p class="desc">
        How each detector's mean F1 score changes across window sizes [10, 20, 30, 50].
        Use the dropdown to select an anomaly type. Each line represents one detector;
        colours are consistent with all other charts.
      </p>
      {chart_divs['f1_window']}
    </section>

    <section id="det-rate">
      <h2>Detection Rate Heatmap</h2>
      <p class="desc">
        Proportion of trials in which the anomaly was detected within the 5-sample
        detection window. Red = low detection rate; green = high. Use the dropdown
        to switch window sizes.
      </p>
      {chart_divs['det_rate']}
    </section>

    <section id="latency">
      <h2>Detection Latency</h2>
      <p class="desc">
        Average number of samples elapsed between anomaly injection and first alarm,
        across trials where the anomaly was detected. Error bars show ± 1 standard deviation.
        Entries where the anomaly was never detected (latency = &minus;1) are excluded.
      </p>
      {chart_divs['latency']}
    </section>

    <section id="radar">
      <h2>Detector Capability Radar</h2>
      <p class="desc">
        Normalized 0–1 profile across five axes: F1 Score, TPR, Precision,
        Detection Rate, and Low FPR (1&nbsp;&minus;&nbsp;FPR, so higher is better).
        Each axis is normalized relative to the range across all detectors.
        A larger filled area indicates a stronger overall detector.
      </p>
      {chart_divs['radar']}
    </section>

  </main>

  <footer>
    Phase 2 — Network Anomaly Detection Benchmark &nbsp;&middot;&nbsp;
    HP CPP Internship &nbsp;&middot;&nbsp; Generated {timestamp}
  </footer>

  <script>
    function toggleTheme() {{
      const html = document.documentElement;
      const isDark = html.getAttribute('data-theme') === 'dark';
      html.setAttribute('data-theme', isDark ? 'light' : 'dark');
      document.getElementById('theme-btn').textContent =
        isDark ? 'Dark Mode' : 'Light Mode';
    }}
  </script>

</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def generate(output_path: str = OUTPUT_HTML) -> None:
    """
    Main entry point. Load CSVs → build figures → assemble HTML → write file.
    Called by main.py after evaluation, or run standalone.
    """
    print("[dashboard] Loading evaluation results...")
    agg_df, raw_df = load_data()

    print("[dashboard] Building charts...")
    figures = {
        "f1_heatmap": make_f1_heatmap(agg_df),
        "tpr_fpr":    make_tpr_fpr_bars(agg_df),
        "f1_window":  make_f1_vs_window(agg_df),
        "det_rate":   make_detection_rate_heatmap(agg_df),
        "latency":    make_latency_bars(agg_df),
        "radar":      make_radar_chart(agg_df),
    }

    chart_divs = {}
    for i, (key, fig) in enumerate(figures.items()):
        chart_divs[key] = fig_to_html(fig, first=(i == 0))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = build_html(chart_divs, timestamp)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[dashboard] Dashboard written to: {output_path}")


if __name__ == "__main__":
    generate()
