import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { C, base, AXIS, FONT_MONO } from "../theme.js";
import { Segmented, SegLabel } from "./ui.jsx";

function Chart({ option, height = 400 }) {
  return (
    <ReactECharts option={option} notMerge lazyUpdate
      style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} />
  );
}
const alab = (meta, a) => meta.anomaly_labels[a] ?? a;
const col = (meta, d) => meta.colors[d] ?? "#888";

export function GateEffect({ data, meta }) {
  const families = data.gate_fp.map((g) => g.family);
  const fpRed = data.gate_fp.map((g) => (g.fp_reduction_pct ?? 0) * 100);
  const tpRet = data.gate_fp.map((g) => (g.tp_retention_pct ?? 0) * 100);

  const option = base({
    legend: { bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    grid: { left: 10, right: 56, top: 14, bottom: 48, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" },
      valueFormatter: (v) => `${v.toFixed(1)}%` },
    xAxis: { type: "value", max: 100, name: "percent", ...AXIS, axisLabel: { ...AXIS.axisLabel, formatter: "{value}%" } },
    yAxis: { type: "category", data: families.map((f) => meta.det_labels[f] ?? f), inverse: true, ...AXIS,
      axisLabel: { ...AXIS.axisLabel, color: C.textSoft } },
    series: [
      { name: "False positives eliminated", type: "bar", data: fpRed, barWidth: "34%",
        itemStyle: { color: C.gold, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: C.gold, fontFamily: FONT_MONO, fontSize: 11, formatter: (p) => `${p.value.toFixed(0)}%` } },
      { name: "True positives retained", type: "bar", data: tpRet, barWidth: "34%",
        itemStyle: { color: C.teal, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: C.teal, fontFamily: FONT_MONO, fontSize: 11, formatter: (p) => `${p.value.toFixed(0)}%` } },
    ],
  });
  return (
    <>
      <div className="panel-bar"><span className="p-title">Confirmation gate (n={meta.confirmation_n}) · FP cut vs TP kept</span></div>
      <Chart option={option} height={Math.max(300, families.length * 64 + 90)} />
    </>
  );
}

export function EnsembleVsBest({ data, meta }) {
  const [metric, setMetric] = useState("tpr");
  const rows = data.ensemble_vs_best;
  const keyBest = { tpr: "best_tpr", fpr: "best_fpr", f1: "best_f1" }[metric];
  const keyEns = { tpr: "ensemble_tpr", fpr: "ensemble_fpr", f1: "ensemble_f1" }[metric];
  const x = rows.map((r) => alab(meta, r.anomaly_type));

  const option = base({
    legend: { bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    grid: { left: 50, right: 20, top: 30, bottom: 50, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: x, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft, fontWeight: 600 } },
    yAxis: { type: "value", min: 0, max: metric === "f1" ? undefined : 1, ...AXIS },
    series: [
      { name: "Best individual", type: "bar", data: rows.map((r) => r[keyBest]), barWidth: "30%",
        itemStyle: { color: "#9a86d8", borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: "top", color: C.muted, fontFamily: FONT_MONO, fontSize: 10,
          formatter: (p) => rows[p.dataIndex].best_name } },
      { name: "Two-Layer Ensemble", type: "bar", data: rows.map((r) => r[keyEns]), barWidth: "30%",
        itemStyle: { color: C.gold, borderRadius: [3, 3, 0, 0] } },
      metric === "fpr" ? { name: "FPR target", type: "line", data: x.map(() => 0.05), symbol: "none",
        lineStyle: { color: C.alarm, type: "dashed", width: 1.4 } } : null,
    ].filter(Boolean),
  });
  return (
    <>
      <div className="panel-bar">
        <span className="p-title">Ensemble vs best single detector</span>
        <SegLabel>metric</SegLabel>
        <Segmented options={[{ value: "tpr", label: "TPR" }, { value: "fpr", label: "FPR" }, { value: "f1", label: "F1" }]} value={metric} onChange={setMetric} />
      </div>
      <Chart option={option} height={420} />
    </>
  );
}

export function PhaseCompare({ data, meta }) {
  const rows = data.phase_compare;
  if (!rows || !rows.length) return null;
  const x = rows.map((r) => alab(meta, r.anomaly_type));
  const option = base({
    legend: { bottom: 0, textStyle: { color: C.textSoft, fontFamily: FONT_MONO, fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
    grid: { left: 50, right: 20, top: 30, bottom: 50, containLabel: true },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: x, ...AXIS, axisLabel: { ...AXIS.axisLabel, color: C.textSoft, fontWeight: 600 } },
    yAxis: { type: "value", name: "mean F1", ...AXIS },
    series: [
      { name: "Phase 2 best individual", type: "bar", data: rows.map((r) => r.phase2_f1), barWidth: "30%",
        itemStyle: { color: "#9a86d8", borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: "top", color: C.muted, fontFamily: FONT_MONO, fontSize: 10, formatter: (p) => rows[p.dataIndex].phase2_winner } },
      { name: "Phase 3 ensemble", type: "bar", data: rows.map((r) => r.phase3_ensemble_f1), barWidth: "30%",
        itemStyle: { color: C.gold, borderRadius: [3, 3, 0, 0] } },
    ],
  });
  return (
    <>
      <div className="panel-bar"><span className="p-title">Phase 2 best individual vs Phase 3 ensemble · F1</span></div>
      <Chart option={option} height={420} />
    </>
  );
}
