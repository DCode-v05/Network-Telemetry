
export const fmtAnom = (a, labels) => labels?.[a] ?? a;

export function detectorsPresent(rows, order) {
  const set = new Set(rows.map((r) => r.detector));
  return order.filter((d) => set.has(d));
}

export const atWindow = (rows, w) => rows.filter((r) => r.window_size === w);

export function heatmap(rows, metric, w, dets, anomalies) {
  const sub = atWindow(rows, w);
  const data = [];
  let max = 0;
  dets.forEach((d, ri) => {
    anomalies.forEach((at, ci) => {
      const cell = sub.find((r) => r.detector === d && r.anomaly_type === at);
      const v = cell ? Number(cell[metric] ?? 0) : 0;
      max = Math.max(max, v);
      data.push([ci, ri, v]);
    });
  });
  return { data, max };
}

export function meanByDetAnom(rows, metric, dets, anomalies) {
  const acc = {};
  rows.forEach((r) => {
    const k = r.detector + "|" + r.anomaly_type;
    (acc[k] ??= []).push(Number(r[metric] ?? 0));
  });
  const mean = (arr) => (arr && arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);
  return dets.map((d) => ({
    detector: d,
    values: anomalies.map((at) => mean(acc[d + "|" + at])),
  }));
}

export function metricVsWindow(rows, metric, anomaly, dets, windows) {
  const sub = rows.filter((r) => r.anomaly_type === anomaly);
  return dets.map((d) => ({
    detector: d,
    points: windows.map((w) => {
      const cell = sub.find((r) => r.detector === d && r.window_size === w);
      return cell ? Number(cell[metric] ?? 0) : null;
    }),
  }));
}

export function latency(rows, dets, anomalies) {
  const acc = {};
  rows.forEach((r) => {
    const lat = Number(r.avg_detection_latency);
    if (lat < 0) return;
    const k = r.detector + "|" + r.anomaly_type;
    (acc[k] ??= []).push(lat);
  });
  const out = [];
  anomalies.forEach((at) => {
    dets.forEach((d) => {
      const arr = acc[d + "|" + at];
      if (arr && arr.length) {
        out.push({
          detector: d,
          anomaly: at,
          value: arr.reduce((a, b) => a + b, 0) / arr.length,
        });
      }
    });
  });
  return out;
}

export function radar(rows, dets) {
  const COLS = ["f1_mean", "tpr_mean", "precision_mean", "detection_rate", "fpr_mean"];
  const raw = {};
  dets.forEach((d) => {
    const sub = rows.filter((r) => r.detector === d);
    const vals = COLS.map((c) => {
      const xs = sub.map((r) => Number(r[c] ?? 0));
      return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
    });
    vals[4] = 1 - vals[4];
    raw[d] = vals;
  });
  const mins = COLS.map((_, i) => Math.min(...dets.map((d) => raw[d][i])));
  const maxs = COLS.map((_, i) => Math.max(...dets.map((d) => raw[d][i])));
  const norm = (d) => raw[d].map((v, i) => (v - mins[i]) / Math.max(maxs[i] - mins[i], 1e-9));
  return { raw, norm, axes: ["F1", "TPR", "Precision", "Det. Rate", "Low FPR"] };
}
