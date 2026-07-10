import { PHASE1 } from '../content/phases.js'
import { CONSTRAINTS } from '../content/theory.js'
import PhaseNav from '../components/PhaseNav.jsx'

const CAT_COLOR = {
  statistical: 'var(--red)', smoothing: 'var(--purple)', 'change-point': 'var(--cyan)',
  'state-space': 'var(--amber)', pattern: 'var(--green)', forecasting: 'var(--accent)', segmentation: 'var(--fg-subtle)',
}
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

export default function Phase1() {
  const kept = PHASE1.studied.filter((s) => s.verdict === 'kept')
  const cut = PHASE1.studied.filter((s) => s.verdict === 'cut')
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 1 · algorithm study</div>
        <h1>15 candidates in, <span className="hero-underline">6 survivors out</span></h1>
        <p>{PHASE1.goal}</p>
      </div>

      <div className="grid g4">
        <Stat n="15" l="Algorithms studied" />
        <Stat n="6" l="Carried to Phase 2" cls="green" />
        <Stat n="9" l="Rejected on theory" cls="accent" />
        <Stat n="10 to 50" l="Samples · the binding window" />
      </div>

      <div className="section-title">The on-device budget every algorithm was judged against</div>
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

      <div className="section-title">The six we kept, and why each one earned its place</div>
      <div className="grid g3">
        {PHASE1.selectedRoles.map((a) => (
          <div className="card" key={a.name}>
            <span className="mono" style={{ fontWeight: 600, fontSize: 15 }}>{a.name}</span>
            <p className="desc" style={{ marginTop: 8 }}>{a.role}</p>
          </div>
        ))}
      </div>

      <div className="section-title">Full screening: all 15 algorithms, every verdict</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>algorithm</th><th>family</th><th style={{ textAlign: 'center' }}>verdict</th><th>reason</th></tr></thead>
          <tbody>
            {[...kept, ...cut].map((a) => (
              <tr key={a.name} className={a.verdict === 'kept' ? 'hl' : ''}>
                <td className="mono" style={{ fontWeight: 600 }}>{a.name}</td>
                <td><span className="dot" style={{ background: CAT_COLOR[a.cat], marginRight: 7 }} /><span style={{ color: 'var(--fg-muted)', fontSize: 12 }}>{cap(a.cat)}</span></td>
                <td style={{ textAlign: 'center' }}>{a.verdict === 'kept'
                  ? <span className="badge ok">Keep</span>
                  : <span className="badge no">Cut</span>}</td>
                <td style={{ color: 'var(--fg-muted)', whiteSpace: 'normal' }}>{a.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">What the family labels mean</div>
      <div className="card">
        <div className="grid g2" style={{ gap: 10 }}>
          {PHASE1.familyLegend.map((f) => (
            <div key={f.cat} style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
              <span className="dot" style={{ background: CAT_COLOR[f.cat], flex: 'none', position: 'relative', top: 4 }} />
              <div style={{ fontSize: 13 }}>
                <b>{cap(f.cat)}</b><span style={{ color: 'var(--fg-muted)' }}>: {f.d}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="section-title">How the survivors cover the network conditions</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>network condition</th><th>primary detector</th><th>supporting</th></tr></thead>
          <tbody>
            {PHASE1.coverage.map((r) => (
              <tr key={r.cond}>
                <td style={{ fontWeight: 600 }}>{r.cond}</td>
                <td className="mono" style={{ color: 'var(--accent)' }}>{r.primary}</td>
                <td className="mono" style={{ color: 'var(--fg-muted)' }}>{r.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">Why these six made the cut</div>
      <div className="callout" style={{ borderLeftColor: 'var(--cyan)' }}>{PHASE1.justification}</div>

      <PhaseNav />
    </div>
  )
}

const Stat = ({ n, l, cls }) => (
  <div className="card stat accent-top">
    <div className={'n ' + (cls || '')}>{n}</div>
    <div className="l">{l}</div>
  </div>
)
