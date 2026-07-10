import PhaseNav from '../components/PhaseNav.jsx'
import { PHASE3 } from '../content/phases.js'

export default function Phase3Architecture() {
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 3 · architecture</div>
        <h1>Gate first, <span className="hero-underline">then let them vote</span></h1>
        <p>Here is how the fourteen detectors are wired together. Every raw detector is wrapped in a confirmation gate, the gated detectors fan out into two specialised layers, and those two layers are combined into a single confirmed alert.</p>
      </div>

      <div className="section-title">Step 1 · the confirmation gate</div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{PHASE3.gate.title}</div>
        <p className="desc">{PHASE3.gate.how}</p>
      </div>

      <div className="section-title">Step 2 · how it all connects</div>
      <EnsembleDiagram />

      <div className="section-title">Step 3 · what each layer is for</div>
      <div className="grid g3">
        {PHASE3.layers.map((l) => (
          <div className="card" key={l.name}>
            <div style={{ fontWeight: 600, marginBottom: 3 }}>{l.name}</div>
            <div className="mono" style={{ fontSize: 12, color: 'var(--fg-muted)', marginBottom: 7 }}>vote mode · {l.mode} · {l.members}</div>
            <p className="desc">{l.why}</p>
          </div>
        ))}
      </div>

      <PhaseNav />
    </div>
  )
}

// -------- the two-layer ensemble diagram --------
function EnsembleDiagram() {
  const Arrow = ({ label }) => (
    <div className="arrow-v">{label && <span className="lab">{label}</span>}
      <svg width="30" height="38" viewBox="0 0 30 38" fill="none"><line x1="15" y1="2" x2="15" y2="26" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" /><path d="M15 37 L7 24 L23 24 Z" fill="currentColor" /></svg>
    </div>
  )
  const Layer = ({ title, mode, members, color }) => (
    <div className="head-card" style={{ '--hc': color }}>
      <div className="hh">{title}</div>
      <div className="st">vote mode · <b style={{ color }}>{mode}</b></div>
      <div className="fx">{members}</div>
    </div>
  )
  return (
    <div className="dgm" style={{ marginBottom: 8 }}>
      <div className="dgm-box"><div className="t">telemetry sample&nbsp;&nbsp;<span style={{ color: 'var(--accent)' }}>x</span></div><div className="s">each raw detector wrapped in a confirmation gate (n = 2)</div></div>
      <Arrow label="fan out to two specialised layers" />
      <div className="heads-group">
        <div className="hg-label">two voting layers · each member is a gated Phase-2 detector</div>
        <div className="heads-cols" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <Layer title="Spike layer" mode="AND · both must agree" members="GatedMAD ∧ GatedZScore" color="var(--red)" />
          <Layer title="Sustained layer" mode="OR · whichever fires first" members="GatedEWMA ∨ GatedCUSUM" color="var(--purple)" />
        </div>
      </div>
      <Arrow label="OR-fuse the two layers" />
      <div className="dgm-box fusion"><div className="t">alert = Spike ∨ Sustained</div></div>
      <Arrow />
      <div className="dgm-box output"><div className="t">◆ confirmed anomaly</div></div>
    </div>
  )
}
