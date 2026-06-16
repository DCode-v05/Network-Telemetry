import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { C, base, AXIS, RAMP_F1, RAMP_RATE, alpha, FONT_MONO } from "../theme.js";
import {
  heatmap, meanByDetAnom, metricVsWindow, latency, radar, atWindow,
} from "../lib/transform.js";
import { Segmented, SegLabel } from "./ui.jsx";

const EH = 380; // default chart height

function Chart({ option, height = EH }) {
  return (
    <ReactECharts
      option={option}
      notMerge
      lazyUpdate
      style={{ height, width: "100%" }}
      opts={{ renderer: "canvas" }}
    />
  );
}

const lab = (meta, d) => meta.det_labels[d] ?? d;
const alab = (meta, a) => meta.anomaly_labels[a] ?? a;
const col = (meta, d) => meta.colors[d] ?? "#888";

/* ───────────────────────── Performance Matrix (heatmap) ───────────────── */
export function PerfMatrix({ rows, meta, dets }) {
  const [metric, setMetric] = useState("detection_rate");
  const [w, setW] = useState(meta.window_sizes[0]);

  const metrics = [
    { value: "detection_rate", label: "DET RATE" },
    { value: "tpr_mean", label: "TPR" },
    { value: "f1_mean", label: "F1" },
    { value: "precision_mean", label: "PRECISION" },
    { value: "fpr_mean", label: "FPR" },
  ];
  const ramp = metric === "fpr_mean" ? RAMP_RATE.slice().reverse()
    : metric === "detection_rate" || metric === "tpr_mean" ? RAMP_RATE : RAMP_F1;

  const { data, max } = useMemo(
    () => heatmap(rows, metric, w, dets, meta.anomaly_types),
    [rows, metric, w, dets, meta.anomaly_types]
  );
  const vmax = Math.max(0.0001, Math.ceil(max * 20) / 20);
  const yLabels = dets.map((d) => lab(meta, d));
  const xLabels = meta.anomaly_types.map((a) => alab(meta, a));

  const option = base({
    grid: { left: 8, right: 8, top: 10, bottom: 60, containLabel: true },
    tooltip: {
      ...base().tooltip,
      formatter: (p) => {
        const d = yLabels[p.value[1]], a = xLabels[p.value[0]];
        return `<b style="color:${C.mint}">${d}</b><br/>${a}<br/>${metrics.find(m=>m.value===metric).label}: <b>${p.value[2].toFixed(3)}</b>`;
      },
    },
    xAxis: { type: "category", data: xLabels, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft, fontWeight: 600 }, splitLine: { show: false } },
    yAxis: { type: "category", data: yLabels, inverse: true, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft }, splitLine: { show: false } },
    visualMap: {
      min: 0, max: vmax, calculable: false, show: true, orient: "horizontal",
      left: "center", bottom: 0, itemWidth: 12, itemHeight: 120,
      text: ["high", "low"], textStyle: { color: C.muted, fontFamily: FONT_MONO, fontSize: 10 },
      inRange: { color: ramp },
    },
    series: [{
      type: "heatmap", data,
      label: {
        show: true, fontFamily: FONT_MONO, fontSize: 11, fontWeight: 600,
        formatter: (p) => (p.value[2] >= 0.0005 ? p.value[2].toFixed(2) : "·"),
        color: "rgba(232,238,251,0.92)",
      },
      itemStyle: { borderColor: C.ink, borderWidth: 3, borderRadius: 6 },
      emphasis: { itemStyle: { borderColor: C.mint, borderWidth: 2 } },
    }],
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Performance Matrix · Window {w}</span>
        <SegLabel>metric</SegLabel>
        <Segmented options={metrics} value={metric} onChange={setMetric} />
        <SegLabel>window</SegLabel>
        <Segmented options={meta.window_sizes.map((x) => ({ value: x, label: String(x) }))} value={w} onChange={setW} variant="amber" />
      </div>
      <Chart option={option} height={Math.max(360, dets.length * 46 + 120)} />
    </>
  );
}

/* ───────────────────────── TPR / FPR grouped bars ─────────────────────── */
export function RateBars({ rows, meta, dets }) {
  const [metric, setMetric] = useState("tpr_mean");
  const series = useMemo(() => meanByDetAnom(rows, metric, dets, meta.anomaly_types), [rows, metric, dets, meta.anomaly_types]);
  const xLabels = meta.anomaly_types.map((a) => alab(meta, a));

  const option = base({
    legend: {
      type: "scroll", bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 },
      icon: "roundRect", itemWidth: 11, itemHeight: 11,
    },
    grid: { left: 50, right: 20, top: 18, bottom: 56, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: xLabels, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft, fontWeight: 600 } },
    yAxis: { type: "value", min: 0, max: metric === "fpr_mean" ? undefined : 1, name: metric === "fpr_mean" ? "FPR" : "TPR", ...AXIS },
    series: series.map((s) => ({
      name: lab(meta, s.detector), type: "bar",
      data: s.values, itemStyle: { color: col(meta, s.detector), borderRadius: [3, 3, 0, 0] },
      emphasis: { focus: "series" },
      markLine: metric === "fpr_mean" && s.detector === dets[0] ? {
        symbol: "none", silent: true,
        lineStyle: { color: C.alarm, type: "dashed", width: 1.4 },
        label: { formatter: "FPR target 0.05", color: C.alarm, fontFamily: FONT_MONO, fontSize: 10 },
        data: [{ yAxis: 0.05 }],
      } : undefined,
    })),
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">TPR vs FPR · averaged across windows</span>
        <SegLabel>metric</SegLabel>
        <Segmented options={[{ value: "tpr_mean", label: "TPR" }, { value: "fpr_mean", label: "FPR" }]} value={metric} onChange={setMetric} />
      </div>
      <Chart option={option} height={420} />
    </>
  );
}

/* ───────────────────────── Metric vs Window (lines) ───────────────────── */
export function TrendLines({ rows, meta, dets }) {
  const [anom, setAnom] = useState(meta.anomaly_types[0]);
  const [metric, setMetric] = useState("detection_rate");
  const series = useMemo(
    () => metricVsWindow(rows, metric, anom, dets, meta.window_sizes),
    [rows, metric, anom, dets, meta.window_sizes]
  );

  const option = base({
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    grid: { left: 50, right: 24, top: 18, bottom: 56, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis" },
    xAxis: { type: "category", data: meta.window_sizes, name: "Window", boundaryGap: false, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft } },
    yAxis: { type: "value", min: 0, max: metric === "fpr_mean" ? undefined : 1, ...AXIS },
    series: series.map((s) => ({
      name: lab(meta, s.detector), type: "line", smooth: true,
      data: s.points, connectNulls: true,
      symbol: "circle", symbolSize: 7,
      lineStyle: { color: col(meta, s.detector), width: 2.5 },
      itemStyle: { color: col(meta, s.detector), borderColor: C.ink, borderWidth: 1.5 },
      emphasis: { focus: "series" },
      areaStyle: { color: alpha(col(meta, s.detector), 0.05) },
    })),
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Metric vs Window Size</span>
        <SegLabel>metric</SegLabel>
        <Segmented options={[{ value: "detection_rate", label: "DET" }, { value: "tpr_mean", label: "TPR" }, { value: "f1_mean", label: "F1" }]} value={metric} onChange={setMetric} />
        <SegLabel>anomaly</SegLabel>
        <Segmented options={meta.anomaly_types.map((a) => ({ value: a, label: alab(meta, a).toUpperCase() }))} value={anom} onChange={setAnom} variant="amber" />
      </div>
      <Chart option={option} height={420} />
    </>
  );
}

/* ───────────────────────── Latency bars ───────────────────────────────── */
export function LatencyBars({ rows, meta, dets }) {
  const [anom, setAnom] = useState(meta.anomaly_types[0]);
  const data = useMemo(() => {
    const all = latency(rows, dets, [anom]);
    return all.sort((a, b) => a.value - b.value);
  }, [rows, dets, anom]);

  const option = base({
    grid: { left: 10, right: 60, top: 12, bottom: 36, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (ps) => { const p = ps[0]; return `<b style="color:${C.mint}">${p.name}</b><br/>latency: <b>${p.value.toFixed(2)}</b> samples`; } },
    xAxis: { type: "value", name: "samples after onset", ...AXIS },
    yAxis: { type: "category", data: data.map((d) => lab(meta, d.detector)), ...AXIS,
      axisLabel: { ...AXIS.axisLabel, color: C.textSoft } },
    series: [{
      type: "bar", data: data.map((d) => ({ value: d.value, itemStyle: { color: col(meta, d.detector), borderRadius: [0, 4, 4, 0] } })),
      barWidth: "56%",
      label: { show: true, position: "right", color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11, formatter: (p) => p.value.toFixed(2) },
    }],
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Detection Latency · lower is faster</span>
        <SegLabel>anomaly</SegLabel>
        <Segmented options={meta.anomaly_types.map((a) => ({ value: a, label: alab(meta, a).toUpperCase() }))} value={anom} onChange={setAnom} variant="amber" />
      </div>
      <Chart option={option} height={Math.max(300, data.length * 46 + 80)} />
    </>
  );
}

/* ───────────────────────── Radar capability profile ───────────────────── */
export function RadarProfile({ rows, meta, dets }) {
  const { norm, raw, axes } = useMemo(() => radar(rows, dets), [rows, dets]);
  // label → detector short, so the tooltip can resolve raw values reliably.
  const byLabel = useMemo(() => {
    const m = {};
    dets.forEach((d) => { m[lab(meta, d)] = d; });
    return m;
  }, [dets, meta]);

  const option = base({
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    tooltip: { ...base().tooltip,
      formatter: (p) => {
        const d = byLabel[p.name] ?? p.name;
        const r = raw[d] || [];
        return `<b style="color:${col(meta, d)}">${p.name}</b><br/>` +
          axes.map((ax, i) => `${ax}: <b>${(r[i] ?? 0).toFixed(3)}</b>`).join("<br/>");
      } },
    radar: {
      indicator: axes.map((a) => ({ name: a, max: 1 })),
      shape: "polygon", splitNumber: 4, center: ["50%", "52%"], radius: "66%",
      axisName: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 },
      splitLine: { lineStyle: { color: C.grid } },
      splitArea: { areaStyle: { color: ["rgba(120,175,255,0.02)", "rgba(120,175,255,0.05)"] } },
      axisLine: { lineStyle: { color: C.line } },
    },
    series: [{
      type: "radar",
      data: dets.map((d) => ({
        name: lab(meta, d), value: norm[d],
        lineStyle: { color: col(meta, d), width: 2 },
        itemStyle: { color: col(meta, d) },
        areaStyle: { color: alpha(col(meta, d), 0.12) },
      })),
      emphasis: { lineStyle: { width: 4 }, areaStyle: { opacity: 0.3 } },
    }],
  });

  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Capability Profile · normalised 0–1 across detectors</span>
      </div>
      <Chart option={option} height={460} />
    </>
  );
}
