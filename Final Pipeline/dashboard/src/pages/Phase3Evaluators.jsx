import PhaseNav from '../components/PhaseNav.jsx'
import { useJson } from '../lib/useJson.js'
import { PHASE3 } from '../content/phases.js'

const fmt = (x, d = 2) => (x == null ? '·' : Number(x).toFixed(d))
const KIND_COLOR = { single: 'var(--fg-muted)', gated: 'var(--cyan)', ensemble: 'var(--purple)' }
const P2_TYPES = ['burst', 'rate_shift', 'gradual_drift', 'transient']
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

// legend for the "kind" column, in the same spirit as the Phase 2 family legend
const KIND_LEGEND = [
  { kind: 'single', label: 'Single', d: 'One of the six Phase 2 detectors running on its own, with nothing wrapped around it. This is the baseline the rest have to beat.' },
  { kind: 'gated', label: 'Gated', d: 'The same detector, but it only fires after two alarms in a row. A one off noise blip gets dropped, while a real anomaly still passes through.' },
  { kind: 'ensemble', label: 'Ensemble', d: 'Several gated detectors voting together across two layers, so a sudden spike and a slow shift are both covered at once.' },
]

export default function Phase3Evaluators() {
  const { data } = useJson(['data/evaluation.json'])
  const evalD = data?.[0]
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 3 · evaluators</div>
        <h1>Combine them, <span className="hero-underline">gate the noise</span></h1>
        <p>{PHASE3.goal}</p>
      </div>

      <div className="grid g4">
        <Stat n="14" l="Detectors evaluated" />
        <Stat n="N=2" l="Confirmation gate" cls="accent" />
        <Stat n="86%" l="False alarms cut on Z-Score" cls="green" />
        <Stat n="2" l="Voting layers" />
      </div>

      <div className="section-title">What Phase 3 proved</div>
      <div className="grid g2">
        {PHASE3.findings.map((f, i) => <div className="card" key={i}><p className="desc">{f}</p></div>)}
      </div>

      <div className="section-title">False alarms before and after gating (real results)</div>
      <div className="card">
        <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 12, color: 'var(--fg-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 11, height: 11, borderRadius: 3, background: 'color-mix(in srgb, var(--red) 30%, transparent)', border: '1px solid var(--border)', flex: 'none' }} />Before gating (left)</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 11, height: 11, borderRadius: 3, background: 'var(--green)', flex: 'none' }} />After gating (right)</span>
        </div>
        {PHASE3.fprReduction.map((r) => (
          <div key={r.det} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 150px', gap: 12, alignItems: 'center', padding: '7px 0' }}>
            <span className="mono" style={{ fontWeight: 600 }}>{r.det}</span>
            <div style={{ position: 'relative', height: 20, background: 'var(--bg-subtle)', borderRadius: 5, border: '1px solid var(--border)', overflow: 'hidden' }}>
              {/* full "before" bar (red) anchored left; the green "after" chunk sits at its right end, so red = before on the left, green = after on the right */}
              <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(100, r.before * 4)}%`, background: 'color-mix(in srgb, var(--red) 30%, transparent)' }} />
              <div style={{ position: 'absolute', left: `${Math.min(100, (r.before - r.after) * 4)}%`, top: 0, bottom: 0, width: `${Math.min(100, r.after * 4)}%`, background: 'var(--green)' }} />
            </div>
            <span className="mono" style={{ fontSize: 12.5, color: 'var(--fg-muted)' }}>{r.before}% → <b style={{ color: 'var(--green)' }}>{r.after}%</b></span>
          </div>
        ))}
      </div>

      {evalD && (
        <>
          <div className="section-title">All 14 detectors · detection rate by type (real results)</div>
          <DetTable rows={evalD.phase3} />
          <div className="card" style={{ marginTop: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>What the kind labels mean</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
              {KIND_LEGEND.map((k) => (
                <div key={k.kind} style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
                  <span className="badge" style={{ color: KIND_COLOR[k.kind], borderColor: KIND_COLOR[k.kind], flex: 'none' }}>{k.label}</span>
                  <span style={{ fontSize: 12.5, color: 'var(--fg-muted)' }}>{k.d}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <PhaseNav />
    </div>
  )
}

function DetTable({ rows }) {
  const types = P2_TYPES.filter((ty) => rows.some((r) => r.by_type_det && ty in r.by_type_det))
  const colMax = {}
  types.forEach((ty) => { colMax[ty] = Math.max(...rows.map((r) => r.by_type_det?.[ty] ?? 0)) })
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr><th>detector</th><th>kind</th>{types.map((ty) => <th key={ty} style={{ textAlign: 'right' }}>{ty.replace('_', ' ')}</th>)}<th style={{ textAlign: 'right' }}>best detect</th><th style={{ textAlign: 'right' }}>mean FPR</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.detector}>
              <td className="mono" style={{ fontWeight: 600 }}>{r.detector}</td>
              <td><span className="badge" style={{ color: KIND_COLOR[r.kind], borderColor: KIND_COLOR[r.kind] }}>{cap(r.kind)}</span></td>
              {types.map((ty) => { const v = r.by_type_det?.[ty]; const win = v != null && v === colMax[ty]; return <td key={ty} className="mono" style={{ textAlign: 'right', color: win ? 'var(--accent)' : 'var(--fg-muted)', fontWeight: win ? 600 : 400 }}>{fmt(v)}</td> })}
              <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.det_best)}</td>
              <td className="mono" style={{ textAlign: 'right', color: r.fpr_mean > 0.1 ? 'var(--red)' : 'var(--fg-muted)' }}>{fmt(r.fpr_mean, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const Stat = ({ n, l, cls }) => (<div className="card stat accent-top"><div className={'n ' + (cls || '')}>{n}</div><div className="l">{l}</div></div>)
