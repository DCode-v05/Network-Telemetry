import React from "react";
import data from "./data.json";
import { Reveal, CountUp } from "./components/ui.jsx";
import {
  PerfMatrix, RateBars, TrendLines, LatencyBars, RadarProfile,
} from "./components/charts.jsx";
import { detectorsPresent } from "./lib/transform.js";

const meta = data.meta;
const dets = detectorsPresent(data.aggregated, meta.detector_order);
const alab = (a) => meta.anomaly_labels[a] ?? a;
const dlab = (d) => meta.det_labels[d] ?? d;
const dcol = (d) => meta.colors[d] ?? "#888";

const NAV = [
  ["roster", "Detectors"],
  ["matrix", "Matrix"],
  ["rates", "TPR/FPR"],
  ["trend", "Trend"],
  ["latency", "Latency"],
  ["radar", "Radar"],
];

function Mark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#34e5b0" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M2 12h3l2-7 4 16 3-11 2 5h6" />
    </svg>
  );
}

function TopBar() {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="mark"><Mark /></span>
        <span className="titles">
          <b>Signal Lab</b>
          <span>Phase 02 · Benchmark</span>
        </span>
      </div>
      <nav className="topnav">
        {NAV.map(([id, l]) => <a key={id} href={`#${id}`}>{l}</a>)}
      </nav>
      <span className="live-chip"><span className="dot" /> {meta.dataset}</span>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero">
      <Reveal className="eyebrow" as="div">Lightweight on-switch anomaly detection</Reveal>
      <Reveal as="h1" delay={80}>
        Six detectors,<br />one <span className="accent">signal grid.</span>
      </Reveal>
      <Reveal as="p" className="lede" delay={160}>
        {meta.subtitle}. Each detector is swept across four
        anomaly classes and four sliding-window sizes, then scored on detection
        rate, true/false-positive balance, latency, and overall capability —
        the empirical case for the Phase 3 ensemble.
      </Reveal>
      <Reveal className="specbar" delay={240}>
        <span className="spec-pill"><b>{data.kpis.n_detectors}</b> detectors</span>
        <span className="spec-pill"><b>{data.kpis.n_anomalies}</b> anomaly types</span>
        <span className="spec-pill"><b>{data.kpis.n_windows}</b> window sizes</span>
        <span className="spec-pill"><b>{data.kpis.n_trials}</b> trials each</span>
        <span className="spec-pill">primary signal <b>n_bytes</b></span>
      </Reveal>
    </section>
  );
}

function Kpis() {
  const k = data.kpis;
  const cards = [
    { label: "Evaluation Runs", glow: "rgba(52,229,176,0.16)",
      value: <CountUp value={k.total_runs} />,
      sub: <>{k.n_detectors} det · {k.n_anomalies} anom · {k.n_windows} win · {k.n_trials} trials</> },
    { label: "Peak Detection Rate", glow: "rgba(69,200,255,0.16)",
      value: <><CountUp value={k.top_detection_rate.value * 100} decimals={1} /><span className="unit">%</span></>,
      sub: <><span className="chip" style={{ background: dcol(k.top_detection_rate.detector) }} />{dlab(k.top_detection_rate.detector)}</> },
    { label: "Lowest False-Alarm", glow: "rgba(245,176,66,0.16)",
      value: <CountUp value={k.cleanest.value} decimals={3} />,
      sub: <><span className="chip" style={{ background: dcol(k.cleanest.detector) }} />{dlab(k.cleanest.detector)} · mean FPR</> },
    { label: "Best F1 Cell", glow: "rgba(140,124,255,0.16)",
      value: <CountUp value={k.best_f1.value} decimals={3} />,
      sub: <><span className="chip" style={{ background: dcol(k.best_f1.detector) }} />{dlab(k.best_f1.detector)} · {alab(k.best_f1.anomaly)} · w{k.best_f1.window}</> },
  ];
  return (
    <div className="kpi-grid">
      {cards.map((c, i) => (
        <Reveal key={c.label} className="kpi" delay={i * 90} style={{ "--kpi-glow": c.glow }}>
          <div className="k-label">{c.label}</div>
          <div className="k-value">{c.value}</div>
          <div className="k-sub">{c.sub}</div>
        </Reveal>
      ))}
    </div>
  );
}

function Section({ id, num, title, desc, children }) {
  return (
    <section className="section" id={id}>
      <Reveal className="section-head">
        <div className="num">{num}</div>
        <h2>{title}</h2>
        {desc && <p>{desc}</p>}
      </Reveal>
      <Reveal delay={80}>{children}</Reveal>
    </section>
  );
}

function Roster() {
  return (
    <Section id="roster" num="// 00 — Roster" title="The six finalists"
      desc="Each detector conforms to a shared DetectorBase contract and runs on an O(1) sliding-window buffer — under 100 bytes of state, sub-100µs updates.">
      <div className="winners">
        {dets.map((d, i) => (
          <Reveal key={d} className="win-card" delay={i * 60} style={{ "--win-c": dcol(d) }}>
            <span className="glow" />
            <div className="w-anom">Detector</div>
            <div className="w-det">{dlab(d)}</div>
            <p style={{ fontSize: "0.8rem", color: "var(--text-soft)", lineHeight: 1.5 }}>
              {meta.det_blurb[d]}
            </p>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}

function Winners() {
  const w = data.winners;
  return (
    <Section id="winners" num="// 01 — Headline" title="Best detector per anomaly class"
      desc="No single detector wins everywhere — the core Phase 2 finding. Ranked by mean F1 across all window sizes for each anomaly type.">
      <div className="winners">
        {meta.anomaly_types.map((at, i) => {
          const win = w[at];
          if (!win) return null;
          return (
            <Reveal key={at} className="win-card" delay={i * 70} style={{ "--win-c": dcol(win.detector) }}>
              <span className="glow" />
              <div className="w-anom">{alab(at)}</div>
              <div className="w-det">{dlab(win.detector)}</div>
              <div className="w-stats">
                <div className="w-stat"><div className="sv">{win.f1.toFixed(3)}</div><div className="sl">F1</div></div>
                <div className="w-stat"><div className="sv">{win.tpr.toFixed(2)}</div><div className="sl">TPR</div></div>
                <div className="w-stat"><div className="sv">{win.fpr.toFixed(3)}</div><div className="sl">FPR</div></div>
              </div>
            </Reveal>
          );
        })}
      </div>
    </Section>
  );
}

function Footer() {
  return (
    <footer className="foot">
      <div className="brand-min"><span className="mark" style={{ width: 26, height: 26 }}><Mark /></span>
        Phase 2 · Network Telemetry Anomaly Detection</div>
      <div>HP CPP Internship · <b>{meta.dataset}</b> · generated {meta.generated}</div>
    </footer>
  );
}

export default function App() {
  return (
    <>
      <TopBar />
      <Hero />
      <Kpis />
      <main>
        <Roster />
        <Winners />

        <Section id="matrix" num="// 02 — Matrix"
          title="Performance across the full grid"
          desc="Every detector × anomaly cell at a chosen window size. Switch metrics to read detection rate, true/false-positive rates, precision, or F1. Values are annotated on each tile.">
          <div className="panel"><PerfMatrix rows={data.aggregated} meta={meta} dets={dets} /></div>
        </Section>

        <Section id="rates" num="// 03 — Trade-off"
          title="True-positive vs false-positive rate"
          desc="Grouped by anomaly type, averaged across window sizes. Toggle to FPR to see the false-alarm cost — the dashed line marks the 5% acceptable threshold.">
          <div className="panel"><RateBars rows={data.aggregated} meta={meta} dets={dets} /></div>
        </Section>

        <Section id="trend" num="// 04 — Sensitivity"
          title="How window size moves the needle"
          desc="Detector response as the sliding-window grows from 10 to 50 samples, per anomaly type. Larger windows stabilise statistics but slow reaction.">
          <div className="panel"><TrendLines rows={data.aggregated} meta={meta} dets={dets} /></div>
        </Section>

        <div className="grid-2" style={{ marginTop: "clamp(2.5rem,6vw,4.5rem)" }}>
          <section className="section" id="latency" style={{ marginTop: 0 }}>
            <Reveal className="section-head">
              <div className="num">// 05 — Speed</div>
              <h2>Detection latency</h2>
              <p>Samples elapsed between anomaly onset and first alarm, for trials that detected.</p>
            </Reveal>
            <Reveal delay={80}><div className="panel"><LatencyBars rows={data.aggregated} meta={meta} dets={dets} /></div></Reveal>
          </section>
          <section className="section" id="radar" style={{ marginTop: 0 }}>
            <Reveal className="section-head">
              <div className="num">// 06 — Profile</div>
              <h2>Capability radar</h2>
              <p>Normalised 0–1 across F1, TPR, Precision, Detection Rate and Low-FPR. Bigger area = stronger all-rounder.</p>
            </Reveal>
            <Reveal delay={80}><div className="panel"><RadarProfile rows={data.aggregated} meta={meta} dets={dets} /></div></Reveal>
          </section>
        </div>
      </main>
      <Footer />
    </>
  );
}
