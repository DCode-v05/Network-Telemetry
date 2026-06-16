import { useEffect, useMemo, useState } from "react";
import EChart from "./EChart.jsx";

const DATA = import.meta.env.BASE_URL + "data/";
const TABS = ["Overview", "Accuracy vs Window", "Intelligence vs Cost", "Anomaly-type map", "Cost & Budget"];
const PALETTE = ["#58a6ff", "#3fb950", "#d29922", "#f85149", "#bc8cff", "#39c5cf",
  "#ff7b72", "#7ee787", "#ffa657", "#a5d6ff", "#ffab70", "#d2a8ff"];

function useData() {
  const [state, set] = useState({ loading: true });
  useEffect(() => {
    Promise.all([
      fetch(DATA + "metrics.json").then((r) => r.json()),
      fetch(DATA + "selection.json").then((r) => r.json()).catch(() => null),
    ])
      .then(([metrics, selection]) => set({ loading: false, metrics, selection }))
      .catch((e) => set({ loading: false, error: String(e) }));
  }, []);
  return state;
}

const fmt = (v, d = 3) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(d));

function RecCard({ title, c }) {
  if (!c) return <div className="card"><h3>{title}</h3><div className="sub">n/a</div></div>;
  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="big">{c.detector} <span className="badge">w={c.window}</span></div>
      <div className="sub">
        intel {fmt(c.intel)} · VUS-PR {fmt(c.vus_pr)} · F1 {fmt(c.f1)}<br />
        {fmt(c.us_per_sample, 3)} µs/sample · {c.state_bytes} bytes{" "}
        <span className={"pill " + (c.budget_ok ? "ok" : "no")}>{c.budget_ok ? "within budget" : "over budget"}</span>
      </div>
    </div>
  );
}

function Overview({ metrics, selection }) {
  const rec = selection?.recommended || {};
  const cmap = selection?.condition_to_algorithm || {};
  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="grid cards">
        <RecCard title="Recommended overall" c={rec.overall} />
        <RecCard title="Best single detector" c={rec.best_single} />
        <RecCard title="Best combined detector" c={rec.best_combined} />
      </div>
      <div className="panel">
        <h2>Condition → algorithm</h2>
        <p className="desc">Best detector per anomaly type (budget-gated, by VUS-PR then F1).</p>
        <table>
          <thead><tr><th>Anomaly type</th><th>Detector</th><th>Window</th><th>VUS-PR</th><th>F1</th><th>Latency</th><th>Design intent</th></tr></thead>
          <tbody>
            {Object.entries(cmap).map(([t, c]) => (
              <tr key={t}>
                <td>{t}</td><td><b>{c.detector}</b></td><td className="num">{c.window}</td>
                <td className="num">{fmt(c.vus_pr)}</td><td className="num">{fmt(c.f1)}</td>
                <td className="num">{fmt(c.latency, 1)}</td>
                <td><span className="badge">{(c.design_targets || []).join(", ") || "—"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Scope</h2>
        <p className="desc">
          {metrics.detectors.length} detectors · windows {metrics.windows.join(", ")} ·
          anomaly types {metrics.anomaly_types.join(", ")} · budget &lt; {metrics.budget.max_us} µs /
          &lt; {metrics.budget.max_bytes} bytes · cost source: {selection?.cost_source || "python"}.
        </p>
      </div>
    </div>
  );
}

function AccuracyVsWindow({ metrics }) {
  const [metric, setMetric] = useState("vus_pr");
  const option = useMemo(() => {
    const rows = metrics.agg_detector_window;
    const byDet = {};
    rows.forEach((r) => { (byDet[r.detector] ||= []).push(r); });
    const series = Object.entries(byDet).map(([det, rs], i) => ({
      name: det, type: "line", smooth: true, symbolSize: 7,
      lineStyle: { width: 2, color: PALETTE[i % PALETTE.length] },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
      data: rs.sort((a, b) => a.window - b.window).map((r) => [r.window, r[metric]]),
    }));
    return {
      tooltip: { trigger: "axis" },
      legend: { type: "scroll", top: 0, textStyle: { color: "#8b949e" } },
      grid: { left: 50, right: 24, top: 40, bottom: 40 },
      xAxis: { type: "value", name: "window (samples)", min: Math.min(...metrics.windows), max: Math.max(...metrics.windows) },
      yAxis: { type: "value", name: metric.toUpperCase(), min: 0, max: 1 },
      series,
    };
  }, [metrics, metric]);
  return (
    <div className="panel">
      <h2>Accuracy vs observation window</h2>
      <p className="desc">How detection quality changes as the window shrinks 50 → 10 (Q2).</p>
      <div className="controls">
        <label>Metric:</label>
        <select value={metric} onChange={(e) => setMetric(e.target.value)}>
          <option value="vus_pr">VUS-PR</option>
          <option value="f1">F1</option>
          <option value="mcc">MCC</option>
          <option value="latency">Detection latency</option>
        </select>
      </div>
      <EChart option={option} />
    </div>
  );
}

function Pareto({ metrics, selection }) {
  const option = useMemo(() => {
    const pts = (selection?.per_detector_best || []).filter((p) => p.us_per_sample != null);
    const ok = pts.filter((p) => p.budget_ok);
    const no = pts.filter((p) => !p.budget_ok);
    const mk = (arr, color) => ({
      type: "scatter", symbolSize: 16,
      itemStyle: { color },
      label: { show: true, formatter: (d) => d.data[2], position: "top", color: "#8b949e", fontSize: 10 },
      data: arr.map((p) => [p.us_per_sample, p.intel, p.detector + " w" + p.window]),
    });
    const front = (selection?.pareto_front || []).slice().sort((a, b) => a.us - b.us);
    return {
      tooltip: { formatter: (d) => `${d.data[2]}<br/>cost ${fmt(d.data[0])} µs<br/>intel ${fmt(d.data[1])}` },
      grid: { left: 56, right: 24, top: 30, bottom: 50 },
      xAxis: { type: "log", name: "µs per sample (log)", nameLocation: "middle", nameGap: 30 },
      yAxis: { type: "value", name: "intelligence", min: 0, max: 1 },
      series: [
        { name: "Pareto frontier", type: "line", data: front.map((p) => [p.us, p.intel]),
          lineStyle: { type: "dashed", color: "#58a6ff" }, symbol: "none", z: 1 },
        { name: "within budget", ...mk(ok, "#3fb950"), z: 3 },
        { name: "over budget", ...mk(no, "#f85149"), z: 2 },
      ],
      legend: { top: 0, textStyle: { color: "#8b949e" }, data: ["within budget", "over budget"] },
    };
  }, [selection]);
  return (
    <div className="panel">
      <h2>Intelligence vs cost (Pareto)</h2>
      <p className="desc">Each detector at its best window. Green = within the &lt;100 µs / &lt;100 byte budget. Frontier = non-dominated trade-offs (Q3/Q5).</p>
      <EChart option={option} height={480} />
    </div>
  );
}

function Heatmap({ metrics }) {
  const option = useMemo(() => {
    const rows = metrics.agg_detector_window_type;
    const types = metrics.anomaly_types;
    const dets = metrics.detectors;
    const best = {};
    rows.forEach((r) => {
      const k = r.detector + "|" + r.anomaly_type;
      if (!(k in best) || r.vus_pr > best[k]) best[k] = r.vus_pr;
    });
    const data = [];
    dets.forEach((d, yi) => types.forEach((t, xi) => {
      const v = best[d + "|" + t];
      if (v !== undefined) data.push([xi, yi, Number(v.toFixed(3))]);
    }));
    return {
      tooltip: { formatter: (p) => `${dets[p.data[1]]} · ${types[p.data[0]]}<br/>VUS-PR ${p.data[2]}` },
      grid: { left: 110, right: 24, top: 20, bottom: 60 },
      xAxis: { type: "category", data: types, axisLabel: { rotate: 20 } },
      yAxis: { type: "category", data: dets },
      visualMap: { min: 0, max: 1, calculable: true, orient: "horizontal", left: "center", bottom: 10,
        inRange: { color: ["#161b22", "#1f6feb", "#3fb950"] }, textStyle: { color: "#8b949e" } },
      series: [{ type: "heatmap", data, label: { show: true, color: "#e6edf3", fontSize: 10 } }],
    };
  }, [metrics]);
  return (
    <div className="panel">
      <h2>VUS-PR by detector × anomaly type</h2>
      <p className="desc">Best window per cell — drives the condition→algorithm mapping (Q4).</p>
      <EChart option={option} height={520} />
    </div>
  );
}

function CostBudget({ metrics }) {
  const [sortKey, setSortKey] = useState("c_us_per_sample");
  const windows = metrics.windows;
  const [win, setWin] = useState(windows.includes(20) ? 20 : windows[0]);
  const rows = useMemo(() => {
    const r = metrics.cost.filter((c) => c.window === win);
    const get = (x) => (x[sortKey] == null ? Infinity : x[sortKey]);
    return r.slice().sort((a, b) => get(a) - get(b));
  }, [metrics, win, sortKey]);
  const budget = metrics.budget;
  const cell = (v, d = 3) => <td className="num">{fmt(v, d)}</td>;
  return (
    <div className="panel">
      <h2>Per-sample cost & memory footprint</h2>
      <p className="desc">Authoritative C measurements with the Python cross-check. Budget is a hard gate (Q3).</p>
      <div className="controls">
        <label>Window:</label>
        <select value={win} onChange={(e) => setWin(Number(e.target.value))}>
          {windows.map((w) => <option key={w} value={w}>{w}</option>)}
        </select>
        <span className="badge">budget: &lt; {budget.max_us} µs · &lt; {budget.max_bytes} bytes</span>
      </div>
      <table>
        <thead>
          <tr>
            <th onClick={() => setSortKey("detector")}>Detector</th>
            <th onClick={() => setSortKey("c_us_per_sample")}>C µs/sample</th>
            <th onClick={() => setSortKey("py_us_per_sample")}>Python µs/sample</th>
            <th onClick={() => setSortKey("c_state_bytes")}>State bytes</th>
            <th>Time ✓</th><th>Mem ✓</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const us = c.c_us_per_sample ?? c.py_us_per_sample;
            const by = c.c_state_bytes ?? c.state_bytes;
            const tOk = us != null && us < budget.max_us;
            const mOk = by != null && by < budget.max_bytes;
            return (
              <tr key={c.detector}>
                <td><b>{c.detector}</b></td>
                {cell(c.c_us_per_sample, 4)}{cell(c.py_us_per_sample, 3)}
                <td className="num">{by ?? "—"}</td>
                <td><span className={"pill " + (tOk ? "ok" : "no")}>{tOk ? "✓" : "✗"}</span></td>
                <td><span className={"pill " + (mOk ? "ok" : "no")}>{mOk ? "✓" : "✗"}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const { loading, error, metrics, selection } = useData();
  const [tab, setTab] = useState(TABS[0]);
  if (loading) return <div className="app"><div className="loading">Loading results…</div></div>;
  if (error || !metrics) return (
    <div className="app"><div className="error">
      Could not load results. Run the pipeline first:<br />
      <code>powershell -NoProfile -File scripts\run_all.ps1</code><br />
      then copy results/metrics.json + selection.json into dashboard/public/data/.
      <br /><br />{error}
    </div></div>
  );
  return (
    <div className="app">
      <header>
        <h1>Lightweight Time-Series Anomaly Detection — Network Telemetry</h1>
        <p>Phase 4 · empirical comparison of {metrics.detectors.length} streaming detectors under the on-device budget</p>
      </header>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t} className={"tab" + (t === tab ? " active" : "")} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === "Overview" && <Overview metrics={metrics} selection={selection} />}
      {tab === "Accuracy vs Window" && <AccuracyVsWindow metrics={metrics} />}
      {tab === "Intelligence vs Cost" && <Pareto metrics={metrics} selection={selection} />}
      {tab === "Anomaly-type map" && <Heatmap metrics={metrics} />}
      {tab === "Cost & Budget" && <CostBudget metrics={metrics} />}
      <footer>Phase 4 · short-window (10–50) on-device telemetry analytics · budget &lt; 100 µs / &lt; 100 bytes</footer>
    </div>
  );
}
