// Shared visual constants + ECharts base options for the Signal Lab theme.

export const C = {
  ink: "#05070e",
  text: "#e8eefb",
  textSoft: "#aebbd4",
  muted: "#6c7a96",
  faint: "#475068",
  line: "rgba(120,175,255,0.12)",
  grid: "rgba(120,175,255,0.07)",
  mint: "#34e5b0",
  amber: "#f5b042",
  cyan: "#45c8ff",
  violet: "#8c7cff",
  alarm: "#ff5a6a",
  panel: "#0c1322",
};

export const FONT_MONO = "JetBrains Mono, ui-monospace, monospace";
export const FONT_BODY = "Hanken Grotesk, system-ui, sans-serif";

// Heatmap colour ramps (low → high)
export const RAMP_F1 = [
  "#0a1020", "#0e2b35", "#0f4a47", "#13784f", "#27a85f", "#7fd86a", "#d7f59a",
];
export const RAMP_RATE = [
  "#3a0d18", "#7a1f24", "#b9542a", "#d9952f", "#a9c64a", "#4fb96a", "#34e5b0",
];

// Base layout shared by every chart
export function base(extra = {}) {
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: FONT_BODY, color: C.textSoft },
    grid: { left: 56, right: 24, top: 28, bottom: 48, containLabel: true },
    tooltip: {
      backgroundColor: "rgba(8,12,22,0.94)",
      borderColor: C.line,
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: C.text, fontFamily: FONT_MONO, fontSize: 12 },
      extraCssText: "backdrop-filter: blur(8px); border-radius:10px; box-shadow:0 18px 40px -20px #000;",
    },
    ...extra,
  };
}

export const AXIS = {
  axisLine: { lineStyle: { color: C.line } },
  axisTick: { show: false },
  axisLabel: { color: C.muted, fontFamily: FONT_MONO, fontSize: 11 },
  splitLine: { lineStyle: { color: C.grid } },
  nameTextStyle: { color: C.faint, fontFamily: FONT_MONO, fontSize: 11, fontWeight: 500 },
};

// Add alpha to a hex colour
export function alpha(hex, a) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}
