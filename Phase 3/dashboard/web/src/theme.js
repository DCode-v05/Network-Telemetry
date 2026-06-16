
export const C = {
  ink: "#0b0906",
  text: "#f4eddd",
  textSoft: "#cdbfa3",
  muted: "#8c7d63",
  faint: "#5e533f",
  line: "rgba(244,193,82,0.14)",
  grid: "rgba(244,193,82,0.07)",
  gold: "#f4c152",
  rose: "#e0457b",
  teal: "#7bc8b7",
  blue: "#6fa8dc",
  alarm: "#ff6b5e",
};

export const FONT_MONO = "JetBrains Mono, ui-monospace, monospace";
export const FONT_BODY = "Hanken Grotesk, system-ui, sans-serif";

export const RAMP_F1 = [
  "#1a1206", "#3a2a0c", "#6b4a14", "#a06f1c", "#cf9a2c", "#f4c152", "#ffe49a",
];
export const RAMP_RATE = [
  "#3a0d18", "#7a1f24", "#b9542a", "#d9952f", "#cabd4a", "#9bc88c", "#7bc8b7",
];

export function base(extra = {}) {
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: FONT_BODY, color: C.textSoft },
    grid: { left: 56, right: 24, top: 28, bottom: 48, containLabel: true },
    tooltip: {
      backgroundColor: "rgba(11,9,6,0.95)",
      borderColor: C.line, borderWidth: 1, padding: [10, 12],
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
  nameTextStyle: { color: C.faint, fontFamily: FONT_MONO, fontSize: 11 },
};

export function alpha(hex, a) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}
