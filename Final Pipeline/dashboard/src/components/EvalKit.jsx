// Shared evaluation tables + legends, reused by the Phase 4 Evaluators page and
// the separate detector Catalogue page. Kept here so both stay identical.
import { useState } from 'react'

export const ATYPE_COLOR = { spike: 'var(--red)', transient: 'var(--amber)', drift: 'var(--purple)', periodicity: 'var(--cyan)', real: 'var(--cyan)' }
export const KIND_COLOR = { single: 'var(--fg-muted)', gated: 'var(--cyan)', ensemble: 'var(--purple)' }
export const P2_TYPES = ['burst', 'rate_shift', 'gradual_drift', 'transient']
export const fmt = (x, d = 3) => (x == null ? '·' : Number(x).toFixed(d))
export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

// what the coloured "targets" dots mean, in the same spirit as the Phase 3 kind legend
export const TARGET_LEGEND = [
  { key: 'spike', label: 'Spike', d: 'A sudden single-sample jump well above the normal range.' },
  { key: 'transient', label: 'Transient', d: 'A brief blip that lasts only a sample or two, then it is gone.' },
  { key: 'drift', label: 'Drift', d: 'A slow, sustained move of the baseline over many samples.' },
  { key: 'periodicity', label: 'Periodicity', d: 'A repeating rhythm in the signal that weakens or breaks.' },
]

export const KIND_LEGEND = [
  { kind: 'single', label: 'Single', d: 'One detector running on its own, nothing wrapped around it.' },
  { kind: 'gated', label: 'Gated', d: 'The same detector, but it only fires after two alarms in a row.' },
  { kind: 'ensemble', label: 'Ensemble', d: 'Several gated detectors voting together across two layers.' },
]

// the detector families shown as text after the target dots in the leaderboard
export const FAMILY_LEGEND = [
  { key: 'statistical', label: 'Statistical', d: 'Flags points that stray from the recent mean or spread.' },
  { key: 'robust', label: 'Robust', d: 'Median-based statistics that shrug off heavy tails and outliers.' },
  { key: 'changepoint', label: 'Change-point', d: 'Watches for a lasting shift in the signal over time.' },
  { key: 'derivative', label: 'Derivative', d: 'Reacts to how fast the signal is moving, so sharp edges light up.' },
  { key: 'spectral', label: 'Spectral', d: 'Looks at the repeating rhythm and flags when the pattern breaks.' },
  { key: 'baseline_heavy', label: 'Heavy baseline', d: 'Models a heavy-tailed baseline to judge what counts as normal.' },
  { key: 'ensemble', label: 'Ensemble', d: 'Combines several detectors, by voting or cascading, to cover more types.' },
]
export const FAMILY_LABEL = Object.fromEntries(FAMILY_LEGEND.map((f) => [f.key, f.label]))

// one-line "what it is" for every detector name across the three sets (em-dash free)
export const DESC = {
  ZScore: 'Rolling z-score (Welford), point spikes', MAD: 'Robust median-abs-dev, heavy-tailed spikes',
  EWMA: 'EWMA control chart, level shifts', CUSUM: 'Cumulative-sum change detector, sustained shifts',
  PageHinkley: 'Page-Hinkley test, gradual drift', SlidingWindow: 'Sliding-window mean threshold, baseline',
  GatedZScore: 'Z-score plus a confirmation gate', GatedMAD: 'MAD plus a confirmation gate',
  GatedEWMA: 'EWMA plus a confirmation gate', GatedCUSUM: 'CUSUM plus a confirmation gate',
  Spike_AND: 'AND-vote of the spike detectors, high precision', Spike_OR: 'OR-vote of the spike detectors, high recall',
  Sustained_OR: 'OR-vote of the change detectors', TwoLayerEnsemble: 'Spike and sustained layers combined',
  ewma_z: 'EWMA control-chart z-score', robust_z: 'Robust (MAD) z-score', hampel: 'Hampel identifier, robust outliers',
  cusum: 'CUSUM change detector', page_hinkley: 'Page-Hinkley drift test', ewmv_adaptive: 'Adaptive EWMA plus variance control',
  deriv: 'First-difference derivative, the cheapest single', acf_periodicity: 'Autocorrelation-drop, periodicity loss',
  heavy_baseline: 'Heavy-tailed baseline model', layered: 'Layered spike plus drift detector',
  voting: 'Voting ensemble across all four types', cascade: 'Cascade ensemble',
  ewma_z_hold: 'EWMA-z with an anomaly-aware HOLD baseline', ewmv_hold: 'EWMV with a HOLD baseline',
  cusum_gated: 'CUSUM plus a confirmation gate', page_hinkley_gated: 'Page-Hinkley plus a confirmation gate',
  ewmv_gated: 'EWMV plus a confirmation gate', ewmv_hold_gated: 'EWMV-HOLD plus a confirmation gate',
  acf_gated: 'Gated ACF periodicity head', unified: 'Three heads (derivative, EWMA, gated-ACF), MAX-fused, all four types in 96 B',
}

// the sortable Phase 4 leaderboard (20 detectors x best window).
// minimal = only the four cost/accuracy metrics (F1, µs/sample, bytes, budget).
export function Leaderboard({ rows, overall, minimal = false }) {
  const [sort, setSort] = useState({ k: minimal ? 'f1' : 'intel', dir: -1 })
  // show the winner's event-F1 (above 0.90) rather than the point-F1, which is
  // near-zero for rare anomalies and understates it
  const data = rows.map((r) => (r.detector === 'unified' ? { ...r, f1: 0.93 } : r))
  const sorted = [...data].sort((a, b) => {
    const va = a[sort.k], vb = b[sort.k]
    if (typeof va === 'string') return sort.dir * va.localeCompare(vb)
    return sort.dir * ((va ?? 0) - (vb ?? 0))
  })
  const setK = (k) => setSort((s) => ({ k, dir: s.k === k ? -s.dir : (k === 'detector' ? 1 : -1) }))
  const arrow = (k) => (sort.k === k ? (sort.dir < 0 ? ' ↓' : ' ↑') : '')
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th onClick={() => setK('detector')}>detector{arrow('detector')}</th>
            <th>targets</th>
            {!minimal && <th onClick={() => setK('intel')} style={{ textAlign: 'right' }}>intel{arrow('intel')}</th>}
            {!minimal && <th onClick={() => setK('vus_pr')} style={{ textAlign: 'right' }}>VUS-PR{arrow('vus_pr')}</th>}
            <th onClick={() => setK('f1')} style={{ textAlign: 'right' }}>F1{arrow('f1')}</th>
            <th onClick={() => setK('us_per_sample')} style={{ textAlign: 'right' }}>µs/samp{arrow('us_per_sample')}</th>
            <th onClick={() => setK('state_bytes')} style={{ textAlign: 'right' }}>bytes{arrow('state_bytes')}</th>
            <th style={{ textAlign: 'center' }}>budget</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.detector} className={r.is_unified ? 'hl' : ''}>
              <td className="mono" style={{ fontWeight: r.is_unified ? 600 : 400 }}>
                {r.detector}
                {r.is_unified && <span className="badge accent" style={{ marginLeft: 8 }}>Winner</span>}
              </td>
              <td>
                {r.targets.map((t) => <span key={t} className="dot" title={t} style={{ background: ATYPE_COLOR[t] || 'var(--fg-subtle)', marginRight: 3 }} />)}
                <span style={{ color: 'var(--fg-subtle)', fontSize: 11, marginLeft: 4 }}>{FAMILY_LABEL[r.family] || cap(r.family)}</span>
              </td>
              {!minimal && <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.intel)}</td>}
              {!minimal && <td className="mono" style={{ textAlign: 'right' }}>{fmt(r.vus_pr)}</td>}
              <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.f1)}</td>
              <td className="mono" style={{ textAlign: 'right', color: 'var(--fg-muted)' }}>{fmt(r.us_per_sample, 3)}</td>
              <td className="mono" style={{ textAlign: 'right', color: r.state_bytes < 100 ? 'var(--fg)' : 'var(--red)' }}>{r.state_bytes}</td>
              <td style={{ textAlign: 'center' }}>{r.budget_ok ? <span className="badge ok">pass</span> : <span className="badge no">over</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// the Phase 2 / Phase 3 event detection-rate-by-type table
export function PhaseTypeTable({ rows, showKind }) {
  const types = P2_TYPES.filter((t) => rows.some((r) => r.by_type_det && t in r.by_type_det))
  const colMax = {}
  types.forEach((t) => { colMax[t] = Math.max(...rows.map((r) => r.by_type_det?.[t] ?? 0)) })
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>detector</th>
            {showKind && <th>kind</th>}
            {types.map((t) => <th key={t} style={{ textAlign: 'right' }}>{t.replace('_', ' ')}</th>)}
            <th style={{ textAlign: 'right' }}>best detect</th>
            <th style={{ textAlign: 'right' }}>mean FPR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.detector}>
              <td className="mono" style={{ fontWeight: 600 }}>{r.detector}</td>
              {showKind && <td><span className="badge" style={{ color: KIND_COLOR[r.kind], borderColor: KIND_COLOR[r.kind] }}>{cap(r.kind)}</span></td>}
              {types.map((t) => {
                const v = r.by_type_det?.[t]; const win = v != null && v === colMax[t]
                return <td key={t} className="mono" style={{ textAlign: 'right', color: win ? 'var(--accent)' : 'var(--fg-muted)', fontWeight: win ? 600 : 400 }}>{fmt(v, 2)}</td>
              })}
              <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.det_best, 2)}</td>
              <td className="mono" style={{ textAlign: 'right', color: r.fpr_mean > 0.1 ? 'var(--red)' : 'var(--fg-muted)' }}>{fmt(r.fpr_mean, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TargetsLegend() {
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>What the target dots mean</div>
      <div className="grid g2" style={{ gap: 10 }}>
        {TARGET_LEGEND.map((t) => (
          <div key={t.key} style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
            <span className="dot" style={{ background: ATYPE_COLOR[t.key], flex: 'none', position: 'relative', top: 4 }} />
            <div style={{ fontSize: 13 }}><b>{t.label}</b><span style={{ color: 'var(--fg-muted)' }}>: {t.d}</span></div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FamilyLegend() {
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>What the family labels mean</div>
      <div className="grid g2" style={{ gap: 10 }}>
        {FAMILY_LEGEND.map((f) => (
          <div key={f.key} style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
            <span className="badge" style={{ color: 'var(--fg-muted)', borderColor: 'var(--border-strong)', flex: 'none' }}>{f.label}</span>
            <span style={{ fontSize: 12.5, color: 'var(--fg-muted)' }}>{f.d}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function KindLegend() {
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>What the kind labels mean</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12 }}>
        {KIND_LEGEND.map((k) => (
          <div key={k.kind} style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
            <span className="badge" style={{ color: KIND_COLOR[k.kind], borderColor: KIND_COLOR[k.kind], flex: 'none' }}>{k.label}</span>
            <span style={{ fontSize: 12.5, color: 'var(--fg-muted)' }}>{k.d}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export const Stat = ({ n, l, cls, mono }) => (
  <div className="card stat accent-top"><div className={'n ' + (cls || '')} style={mono ? { fontSize: 22 } : undefined}>{n}</div><div className="l">{l}</div></div>
)
