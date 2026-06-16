import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { C, base, AXIS, RAMP_F1, RAMP_RATE, alpha, FONT_MONO } from "../theme.js";
import { heatmap, meanByDetAnom, latency, radar } from "../lib/transform.js";
import { Segmented, SegLabel } from "./ui.jsx";

function Chart({ option, height = 380 }) {
  return (
    <ReactECharts option={option} notMerge lazyUpdate
      style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} />
  );
}

const lab = (meta, d) => meta.det_labels[d] ?? d;
const alab = (meta, a) => meta.anomaly_labels[a] ?? a;
const col = (meta, d) => meta.colors[d] ?? "#888";

const GROUPS = [
  { value: "all", label: "ALL" },
  { value: "individual", label: "BASE" },
  { value: "gated", label: "GATED" },
  { value: "ensemble", label: "ENSEMBLE" },
];
function filterGroup(dets, meta, g) {
  if (g === "all") return dets;
  return dets.filter((d) => (meta.det_group[d] ?? "individual") === g);
}

/* ───────────────────────── Performance Matrix ─────────────────────────── */
export function PerfMatrix({ rows, meta, dets }) {
  const [metric, setMetric] = useState("detection_rate");
  const [w, setW] = useState(meta.window_sizes[0]);
  const metrics = [
    { value: "detection_rate", label: "DET RATE" },
    { value: "tpr_mean", label: "TPR" },
    { value: "fpr_mean", label: "FPR" },
    { value: "f1_mean", label: "F1" },
    { value: "precision_mean", label: "PRECISION" },
  ];
  const ramp = metric === "fpr_mean" ? RAMP_RATE.slice().reverse()
    : metric === "detection_rate" || metric === "tpr_mean" ? RAMP_RATE : RAMP_F1;
  const { data, max } = useMemo(() => heatmap(rows, metric, w, dets, meta.anomaly_types),
    [rows, metric, w, dets, meta.anomaly_types]);
  const vmax = Math.max(0.0001, Math.ceil(max * 20) / 20);
  const yLabels = dets.map((d) => lab(meta, d));
  const xLabels = meta.anomaly_types.map((a) => alab(meta, a));

  const option = base({
    grid: { left: 8, right: 8, top: 10, bottom: 64, containLabel: true },
    tooltip: { ...base().tooltip, formatter: (p) =>
      `<b style="color:${C.gold}">${yLabels[p.value[1]]}</b><br/>${xLabels[p.value[0]]}<br/>` +
      `${metrics.find(m => m.value === metric).label}: <b>${p.value[2].toFixed(3)}</b>` },
    xAxis: { type: "category", data: xLabels, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft, fontWeight: 600 }, splitLine: { show: false } },
    yAxis: { type: "category", data: yLabels, inverse: true, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft }, splitLine: { show: false } },
    visualMap: { min: 0, max: vmax, calculable: false, orient: "horizontal", left: "center", bottom: 4,
      itemWidth: 12, itemHeight: 120, text: ["high", "low"],
      textStyle: { color: C.muted, fontFamily: FONT_MONO, fontSize: 10 }, inRange: { color: ramp } },
    series: [{
      type: "heatmap", data,
      label: { show: true, fontFamily: FONT_MONO, fontSize: 10.5, fontWeight: 600,
        formatter: (p) => (p.value[2] >= 0.0005 ? p.value[2].toFixed(2) : "·"), color: "rgba(244,237,221,0.92)" },
      itemStyle: { borderColor: C.ink, borderWidth: 3, borderRadius: 5 },
      emphasis: { itemStyle: { borderColor: C.gold, borderWidth: 2 } },
    }],
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Performance Matrix{meta.window_sizes.length > 1 ? ` · Window ${w}` : " · all 14 detectors"}</span>
        <SegLabel>metric</SegLabel>
        <Segmented options={metrics} value={metric} onChange={setMetric} />
        {meta.window_sizes.length > 1 && (<>
          <SegLabel>window</SegLabel>
          <Segmented options={meta.window_sizes.map((x) => ({ value: x, label: String(x) }))} value={w} onChange={setW} variant="rose" />
        </>)}
      </div>
      <Chart option={option} height={Math.max(420, dets.length * 38 + 120)} />
    </>
  );
}

/* ───────────────────────── Rate bars (group filtered) ─────────────────── */
export function RateBars({ rows, meta, dets }) {
  const [metric, setMetric] = useState("tpr_mean");
  const [grp, setGrp] = useState("all");
  const shown = filterGroup(dets, meta, grp);
  const series = useMemo(() => meanByDetAnom(rows, metric, shown, meta.anomaly_types),
    [rows, metric, shown, meta.anomaly_types]);
  const xLabels = meta.anomaly_types.map((a) => alab(meta, a));

  const option = base({
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    grid: { left: 50, right: 20, top: 18, bottom: 56, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: xLabels, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft, fontWeight: 600 } },
    yAxis: { type: "value", min: 0, max: metric === "fpr_mean" ? undefined : 1, name: metric === "fpr_mean" ? "FPR" : "TPR", ...AXIS },
    series: series.map((s) => ({
      name: lab(meta, s.detector), type: "bar", data: s.values,
      itemStyle: { color: col(meta, s.detector), borderRadius: [3, 3, 0, 0] }, emphasis: { focus: "series" },
      markLine: metric === "fpr_mean" && s.detector === shown[0] ? {
        symbol: "none", silent: true, lineStyle: { color: C.alarm, type: "dashed", width: 1.4 },
        label: { formatter: "FPR 0.05", color: C.alarm, fontFamily: FONT_MONO, fontSize: 10 }, data: [{ yAxis: 0.05 }],
      } : undefined,
    })),
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">TPR vs FPR by anomaly</span>
        <SegLabel>metric</SegLabel>
        <Segmented options={[{ value: "tpr_mean", label: "TPR" }, { value: "fpr_mean", label: "FPR" }]} value={metric} onChange={setMetric} />
        <SegLabel>group</SegLabel>
        <Segmented options={GROUPS} value={grp} onChange={setGrp} variant="rose" />
      </div>
      <Chart option={option} height={440} />
    </>
  );
}

/* ───────────────────────── Latency bars ───────────────────────────────── */
export function LatencyBars({ rows, meta, dets }) {
  const [anom, setAnom] = useState(meta.anomaly_types[0]);
  const data = useMemo(() => latency(rows, dets, [anom]).sort((a, b) => a.value - b.value),
    [rows, dets, anom]);
  const option = base({
    grid: { left: 10, right: 60, top: 12, bottom: 36, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (ps) => { const p = ps[0]; return `<b style="color:${C.gold}">${p.name}</b><br/>latency: <b>${p.value.toFixed(2)}</b> samples`; } },
    xAxis: { type: "value", name: "samples after onset", ...AXIS },
    yAxis: { type: "category", data: data.map((d) => lab(meta, d.detector)), ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft } },
    series: [{ type: "bar", data: data.map((d) => ({ value: d.value, itemStyle: { color: col(meta, d.detector), borderRadius: [0, 4, 4, 0] } })),
      barWidth: "58%", label: { show: true, position: "right", color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11, formatter: (p) => p.value.toFixed(2) } }],
  });
  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Detection Latency · lower is faster</span>
        <SegLabel>anomaly</SegLabel>
        <Segmented options={meta.anomaly_types.map((a) => ({ value: a, label: alab(meta, a).toUpperCase() }))} value={anom} onChange={setAnom} variant="rose" />
      </div>
      <Chart option={option} height={Math.max(320, data.length * 30 + 80)} />
    </>
  );
}

/* ───────────────────────── Radar (group filtered) ─────────────────────── */
export function RadarProfile({ rows, meta, dets }) {
  const [grp, setGrp] = useState("ensemble");
  const shown = filterGroup(dets, meta, grp);
  const { norm, raw, axes } = useMemo(() => radar(rows, dets), [rows, dets]);
  const byLabel = useMemo(() => { const m = {}; dets.forEach((d) => { m[lab(meta, d)] = d; }); return m; }, [dets, meta]);

  const option = base({
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    tooltip: { ...base().tooltip, formatter: (p) => {
      const d = byLabel[p.name] ?? p.name; const r = raw[d] || [];
      return `<b style="color:${col(meta, d)}">${p.name}</b><br/>` + axes.map((ax, i) => `${ax}: <b>${(r[i] ?? 0).toFixed(3)}</b>`).join("<br/>");
    } },
    radar: { indicator: axes.map((a) => ({ name: a, max: 1 })), shape: "polygon", splitNumber: 4, center: ["50%", "52%"], radius: "64%",
      axisName: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, splitLine: { lineStyle: { color: C.grid } },
      splitArea: { areaStyle: { color: ["rgba(244,193,82,0.02)", "rgba(244,193,82,0.05)"] } }, axisLine: { lineStyle: { color: C.line } } },
    series: [{ type: "radar", data: shown.map((d) => ({ name: lab(meta, d), value: norm[d],
      lineStyle: { color: col(meta, d), width: 2 }, itemStyle: { color: col(meta, d) }, areaStyle: { color: alpha(col(meta, d), 0.12) } })),
      emphasis: { lineStyle: { width: 4 }, areaStyle: { opacity: 0.3 } } }],
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Capability Profile · normalised</span>
        <SegLabel>group</SegLabel>
        <Segmented options={GROUPS} value={grp} onChange={setGrp} variant="rose" />
      </div>
      <Chart option={option} height={470} />
    </>
  );
}
