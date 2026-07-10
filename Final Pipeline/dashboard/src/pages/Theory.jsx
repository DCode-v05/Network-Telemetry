import { PROBLEM, CONSTRAINTS, ANOMALIES, shapeFor } from '../content/theory.js'
import PhaseNav from '../components/PhaseNav.jsx'

function Spark({ points, color }) {
  const n = points.length
  const min = Math.min(...points), max = Math.max(...points)
  const rng = max - min || 1
  const W = 240, H = 44
  const d = points.map((v, i) => `${(i / (n - 1)) * W},${H - ((v - min) / rng) * (H - 6) - 3}`).join(' ')
  return (
    <div className="spark sparkbox">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height: H, width: '100%' }}>
        <polyline points={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

export default function Theory() {
  return (
    <div className="page">
      <div className="page-head">
        <div className="eyebrow">problem statement</div>
        <h1>Intelligence at the edge, on a byte budget</h1>
        <p>Here's why you'd want the detection running on the device itself, what makes that so hard, and the four kinds of anomaly it has to catch.</p>
      </div>

      <div className="prose">
        {PROBLEM.map((p, i) => <p key={i}>{p}</p>)}
      </div>

      <div className="section-title">Server analytics vs. on-device</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>constraint</th><th>typical server analytics</th><th>on-device requirement</th></tr></thead>
          <tbody>
            {CONSTRAINTS.map((r) => (
              <tr key={r.k}>
                <td style={{ fontWeight: 600 }}>{r.k}</td>
                <td style={{ color: 'var(--fg-muted)' }}>{r.server}</td>
                <td className="mono" style={{ color: 'var(--accent)' }}>{r.device}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">The four anomaly types</div>
      <div className="grid g2">
        {ANOMALIES.map((a) => (
          <div className="card" key={a.key}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 4 }}>
              <span className="dot" style={{ background: a.color, width: 10, height: 10 }} />
              <h3 style={{ margin: 0 }}>{a.name}</h3>
            </div>
            <Spark points={shapeFor(a.key)} color={a.color} />
            <p className="desc" style={{ marginTop: 8 }}><strong style={{ color: 'var(--fg)' }}>{a.def}</strong></p>
            <p className="desc" style={{ marginTop: 8 }}>{a.detail}</p>
          </div>
        ))}
      </div>

      <div className="callout" style={{ marginTop: 22 }}>
        <b>Why the four types matter:</b> no single classic detector covers all of them. Spikes and transients need a
        view of how fast things are changing, drift needs a view of the overall level, and periodicity needs a view of
        the rhythm.
      </div>

      <PhaseNav />
    </div>
  )
}
