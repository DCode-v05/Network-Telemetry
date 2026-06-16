import React from "react";
import data from "./data.json";
import { Reveal, CountUp } from "./components/ui.jsx";
import { PerfMatrix, RateBars, LatencyBars, RadarProfile } from "./components/charts.jsx";
import { GateEffect, EnsembleVsBest, PhaseCompare } from "./components/ensemble.jsx";
import { detectorsPresent } from "./lib/transform.js";

const meta = data.meta;
const dets = detectorsPresent(data.aggregated, meta.detector_order);
const alab = (a) => meta.anomaly_labels[a] ?? a;
const dlab = (d) => meta.det_labels[d] ?? d;
const dcol = (d) => meta.colors[d] ?? "#888";

const NAV = [
  ["arch", "Architecture"],
  ["gate", "Gate"],
  ["ensemble", "Ensemble"],
  ["compare", "Phase 2↔3"],
  ["matrix", "Matrix"],
  ["board", "Leaderboard"],
];

function Mark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#f4c152" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2v6M12 22v-6M4.9 7l4.2 2.5M19.1 17l-4.2-2.5M4.9 17l4.2-2.5M19.1 7l-4.2 2.5" />
      <circle cx="12" cy="12" r="2.4" />
    </svg>
  );
}

function TopBar() {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="mark"><Mark /></span>
        <span className="titles"><b>Ensemble Command</b><span>Phase 03 · Fusion</span></span>
      </div>
      <nav className="topnav">{NAV.map(([id, l]) => <a key={id} href={`#${id}`}>{l}</a>)}</nav>
      <span className="live-chip"><span className="dot" /> {meta.dataset}</span>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero">
      <Reveal className="eyebrow" as="div">Confirmation-gated two-layer ensemble</Reveal>
      <Reveal as="h1" delay={80}>Two layers,<br /><span className="accent">one verdict.</span></Reveal>
      <Reveal as="p" className="lede" delay={160}>
        Phase 2 proved no single detector wins everywhere. Phase 3 answers with a
        confirmation-gated ensemble — a high-precision spike layer (MAD ∧ Z-Score)
        in union with a high-recall sustained layer (EWMA ∨ CUSUM), each child
        wrapped in an {meta.confirmation_n}-of-{meta.confirmation_n} gate that
        suppresses singleton false alarms before they ever fire.
      </Reveal>
      <Reveal className="specbar" delay={240}>
        <span className="spec-pill"><b>{data.kpis.n_detectors}</b> detectors</span>
        <span className="spec-pill"><b>6</b> base · <b>4</b> gated · <b>4</b> ensemble</span>
        <span className="spec-pill"><b>{data.kpis.n_anomalies}</b> anomaly types</span>
        <span className="spec-pill"><b>{data.kpis.total_runs.toLocaleString()}</b> runs</span>
      </Reveal>
    </section>
  );
}

function Kpis() {
  const k = data.kpis;
  const cards = [
    { label: "Mean Gate FP Cut", glow: "rgba(244,193,82,0.18)",
      value: <><CountUp value={(k.mean_gate_fp_reduction ?? 0) * 100} decimals={1} /><span className="unit">%</span></>,
      sub: <>peak {dlab(k.best_gate.family)} · {Math.round((k.best_gate.value ?? 0) * 100)}%</> },
    { label: "Ensemble Recall (TPR)", glow: "rgba(123,200,183,0.18)",
      value: <CountUp value={k.ensemble_tpr ?? 0} decimals={3} />,
      sub: <>union of both layers</> },
    { label: "Ensemble False-Alarm", glow: "rgba(224,69,123,0.18)",
      value: <CountUp value={k.ensemble_fpr ?? 0} decimals={3} />,
      sub: <>precision is the trade-off</> },
    { label: "Evaluation Runs", glow: "rgba(111,168,220,0.16)",
      value: <CountUp value={k.total_runs} />,
      sub: <>{k.n_detectors} det · {k.n_anomalies} anom · {k.n_trials} trials</> },
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

function Gate({ d }) {
  return (
    <span className="gate">
      <span className="swatch" style={{ background: dcol(d) }} />
      {dlab(d)}<span className="n">n={meta.confirmation_n}</span>
    </span>
  );
}

function Architecture() {
  return (
    <Section id="arch" num="// 01 — Architecture" title="The two-layer ensemble"
      desc="Every base detector is wrapped in a confirmation gate, then fused. Layer 1 votes AND for corroborated spikes; Layer 2 votes OR so either change-point detector can lock onto a sustained shift. The top level takes their union.">
      <div className="panel">
        <div className="arch">
          <div className="node">Sliding-window stream · n_bytes</div>
          <div className="conn" />
          <div className="layers">
            <div className="layer" style={{ "--lc": dcol("Spike_AND") }}>
              <div className="l-tag">Layer 1 · Spike</div>
              <div className="l-name">High precision</div>
              <div className="l-rule">GatedMAD <b>∧</b> GatedZScore</div>
              <div className="gate-row"><Gate d="GatedMAD" /><Gate d="GatedZScore" /></div>
            </div>
            <div className="layer" style={{ "--lc": dcol("Sustained_OR") }}>
              <div className="l-tag">Layer 2 · Sustained</div>
              <div className="l-name">High recall</div>
              <div className="l-rule">GatedEWMA <b>∨</b> GatedCUSUM</div>
              <div className="gate-row"><Gate d="GatedEWMA" /><Gate d="GatedCUSUM" /></div>
            </div>
          </div>
          <div className="conn" />
          <div className="op">Layer 1 ∨ Layer 2</div>
          <div className="conn" />
          <div className="fusion"><span style={{ width: 9, height: 9, borderRadius: 2, background: "#1a1206" }} />Two-Layer Ensemble · alarm</div>
        </div>
      </div>
    </Section>
  );
}

function Winners() {
  const w = data.winners;
  return (
    <Section id="winners" num="// 05 — Headline" title="Best base detector per anomaly"
      desc="The Phase 2 finding the ensemble is built to beat: no single detector dominates every anomaly class. Ranked by mean F1 among the six base detectors.">
      <div className="cards">
        {meta.anomaly_types.map((at, i) => {
          const win = w[at]; if (!win) return null;
          return (
            <Reveal key={at} className="card" delay={i * 70} style={{ "--c": dcol(win.detector) }}>
              <span className="glow" />
              <div className="c-eyebrow">{alab(at)}</div>
              <div className="c-title">{dlab(win.detector)}</div>
              <div className="c-stats">
                <div className="c-stat"><div className="sv">{win.f1.toFixed(3)}</div><div className="sl">F1</div></div>
                <div className="c-stat"><div className="sv">{win.tpr.toFixed(2)}</div><div className="sl">TPR</div></div>
                <div className="c-stat"><div className="sv">{win.fpr.toFixed(3)}</div><div className="sl">FPR</div></div>
              </div>
            </Reveal>
          );
        })}
      </div>
    </Section>
  );
}

function Leaderboard() {
  return (
    <Section id="board" num="// 09 — Leaderboard" title="All 14 detectors, ranked by false-alarm rate"
      desc="Mean across anomaly types. Gated and ensemble rows are the Phase 3 additions; the gates push the cleanest detectors to the top.">
      <div className="panel">
        <div className="lb-wrap">
          <table className="lb">
            <thead><tr>
              <th>Detector</th><th>Group</th><th>Det Rate</th><th>TPR</th><th>FPR</th><th>Precision</th>
            </tr></thead>
            <tbody>
              {data.leaderboard.map((r) => (
                <tr key={r.detector}>
                  <td><span className="det"><span className="sw" style={{ background: dcol(r.detector) }} />{dlab(r.detector)}</span></td>
                  <td><span className={`grp ${r.group}`}>{r.group}</span></td>
                  <td className="num">{(r.det_rate ?? 0).toFixed(3)}</td>
                  <td className="num">{(r.tpr ?? 0).toFixed(3)}</td>
                  <td className="num best">{(r.fpr ?? 0).toFixed(3)}</td>
                  <td className="num">{(r.precision ?? 0).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}

function Footer() {
  return (
    <footer className="foot">
      <div className="brand-min"><span className="mark" style={{ width: 26, height: 26 }}><Mark /></span>
        Phase 3 · Two-Layer Ensemble Anomaly Detection</div>
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
        <Architecture />

        <Section id="gate" num="// 02 — The gate" title="What the confirmation gate buys"
          desc={`Requiring ${meta.confirmation_n} consecutive child alarms eliminates a large share of singleton false positives while retaining most true detections. Gold = false positives removed; teal = true positives kept.`}>
          <div className="panel"><GateEffect data={data} meta={meta} /></div>
        </Section>

        <Section id="ensemble" num="// 03 — Fusion" title="Ensemble vs the best single detector"
          desc="Per anomaly type, the union of both layers lifts recall well above any single detector — at a higher false-positive cost. Toggle the metric to see the trade made.">
          <div className="panel"><EnsembleVsBest data={data} meta={meta} /></div>
        </Section>

        {data.phase_compare?.length ? (
          <Section id="compare" num="// 04 — Lineage" title="Phase 2 → Phase 3"
            desc="The Phase 2 per-anomaly champion next to the Phase 3 ensemble, measured the same way, on the same data, with the same seeds.">
            <div className="panel"><PhaseCompare data={data} meta={meta} /></div>
          </Section>
        ) : null}

        <Winners />

        <Section id="matrix" num="// 06 — Matrix" title="The full 14-detector grid"
          desc="Every detector × anomaly cell. Switch metrics to read detection rate, true/false-positive rates, precision or F1 across base, gated and ensemble detectors at once.">
          <div className="panel"><PerfMatrix rows={data.aggregated} meta={meta} dets={dets} /></div>
        </Section>

        <Section id="rates" num="// 07 — Trade-off" title="True vs false positive rate"
          desc="Grouped by anomaly type. Filter to base, gated or ensemble detectors — the dashed line marks the 5% acceptable FPR.">
          <div className="panel"><RateBars rows={data.aggregated} meta={meta} dets={dets} /></div>
        </Section>

        <div className="grid-2" style={{ marginTop: "clamp(2.5rem,6vw,4.5rem)" }}>
          <section className="section" id="latency" style={{ marginTop: 0 }}>
            <Reveal className="section-head">
              <div className="num">
              <p>Samples between anomaly onset and first alarm, for trials that detected.</p>
            </Reveal>
            <Reveal delay={80}><div className="panel"><LatencyBars rows={data.aggregated} meta={meta} dets={dets} /></div></Reveal>
          </section>
          <section className="section" style={{ marginTop: 0 }}>
            <Reveal className="section-head">
              <div className="num">
              <p>Normalised 0–1 across F1, TPR, Precision, Detection Rate, Low-FPR. Filter by detector group.</p>
            </Reveal>
            <Reveal delay={80}><div className="panel"><RadarProfile rows={data.aggregated} meta={meta} dets={dets} /></div></Reveal>
          </section>
        </div>

        <Leaderboard />
      </main>
      <Footer />
    </>
  );
}
