import { useState } from 'react'
import { useJson } from '../lib/useJson.js'

const ATYPE_COLOR = { spike: 'var(--red)', transient: 'var(--amber)', drift: 'var(--purple)', periodicity: 'var(--cyan)', real: 'var(--cyan)' }
const KIND_COLOR = { single: 'var(--fg-muted)', gated: 'var(--cyan)', ensemble: 'var(--purple)' }
const P2_TYPES = ['burst', 'rate_shift', 'gradual_drift', 'transient']
const fmt = (x, d = 3) => (x == null ? '—' : Number(x).toFixed(d))
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

const PHASE1 = {
  studied: 15, rejected: 9,
  selected: [
    { name: 'Z-Score', role: 'baseline spike detector · O(1) via Welford' },
    { name: 'MAD', role: 'robust spike detector for heavy-tailed traffic' },
    { name: 'EWMA', role: 'control-chart baseline + shift detection' },
    { name: 'CUSUM', role: 'change-point / sustained rate-shift' },
    { name: 'Page-Hinkley', role: 'gradual drift detection' },
    { name: 'Sliding-Window', role: 'feature-extraction primitive' },
  ],
  rejectedList: ['ADWIN', 'DDM', 'Kalman Filter', 'Matrix Profile', 'Spectral Residual', 'SAX', 'ARIMA', 'PELT', 'Binary Segmentation'],
}

const FINDINGS = [
  { p: 'Phase 2', t: 'No single detector wins every anomaly type — MAD/Z-Score lead on spikes, EWMA/CUSUM/PH on sustained changes. That motivated combining them.' },
  { p: 'Phase 3', t: 'Confirmation gating cuts false positives sharply (e.g. MAD FPR 14.6 % → 5.6 %, Z-Score 5.1 % → 0.7 %) while keeping recall within ~4 pts of the best single.' },
  { p: 'Phase 4', t: 'Memory — not compute — is the binding constraint: every detector runs far under 100 µs, but window-buffer detectors blow the 100-byte budget at large windows.' },
  { p: 'Winner', t: 'unified is the only budget-passing detector covering all four types (highest VUS-PR, 96 B). deriv wins the single-detector Pareto front (cheapest + accurate) but only targets spikes/transients.' },
]

export default function Evaluation() {
  const { loading, error, data } = useJson(['data/evaluation.json'])
  const [sort, setSort] = useState({ k: 'intel', dir: -1 })
  if (loading) return <div className="page"><div className="loading">loading evaluation…</div></div>
  if (error) return <div className="page"><div className="error">missing <code>evaluation.json</code> — run <code>python python/export_eval.py</code></div></div>
  const d = data[0]
  const rec = d.recommended
  const overall = rec.overall.detector
  const budgetPass = d.phase4.filter((r) => r.budget_ok).length

  const rows = [...d.phase4].sort((a, b) => {
    const va = a[sort.k], vb = b[sort.k]
    if (typeof va === 'string') return sort.dir * va.localeCompare(vb)
    return sort.dir * ((va ?? 0) - (vb ?? 0))
  })
  const setK = (k) => setSort((s) => ({ k, dir: s.k === k ? -s.dir : (k === 'detector' ? 1 : -1) }))
  const arrow = (k) => (sort.k === k ? (sort.dir < 0 ? ' ↓' : ' ↑') : '')

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">evaluation · {d.counts.total} detectors · 4 phases</div>
        <h1>From 15 candidates to <span className="hero-underline">one winner</span></h1>
        <p>Phase 1 selected 6 algorithms from theory; Phase 2 benchmarked them; Phase 3 added gated/ensemble
          variants; Phase 4 screened a fresh field of 20 on intelligence-vs-cost behind a hard budget gate.</p>
      </div>

      <div className="grid g4">
        <Stat n={d.counts.total} l="detectors evaluated (all phases)" />
        <Stat n="4" l="empirical phases" />
        <Stat n={`${budgetPass}/20`} l="pass < 100 µs & < 100 B (Phase 4)" />
        <Stat n="unified" l="selected on-device detector" mono cls="accent" />
      </div>

      {/* ---- Phase 1 ---- */}
      <PhaseHead n="1" title="Algorithm study" sub="15 lightweight time-series techniques analysed against the on-device budget → 6 carried forward" />
      <div className="grid g3">
        {PHASE1.selected.map((a) => (
          <div className="card" key={a.name}>
            <span className="mono" style={{ fontWeight: 600, fontSize: 15 }}>{a.name}</span>
            <p className="desc" style={{ marginTop: 8 }}>{a.role}</p>
          </div>
        ))}
      </div>
      <div className="callout" style={{ marginTop: 12 }}>
        <b>{PHASE1.rejected} rejected</b> on memory / compute / history-length grounds:{' '}
        <span className="mono" style={{ fontSize: 12 }}>{PHASE1.rejectedList.join(' · ')}</span>.
      </div>

      {/* ---- Phase 2 ---- */}
      <PhaseHead n="2" title="Single-detector benchmark" sub="6 detectors on real CESNET traffic · best F1 by anomaly type (no single detector wins all)" />
      <PhaseTypeTable rows={d.phase2} />

      {/* ---- Phase 3 ---- */}
      <PhaseHead n="3" title="Confirmation-gated ensemble" sub="14 detectors: 6 single + 4 gated + 4 ensemble · gating cuts false positives" />
      <PhaseTypeTable rows={d.phase3} showKind />

      {/* ---- Phase 4 ---- */}
      <PhaseHead n="4" title="Production selection" sub="20 detectors × best window · intelligence-vs-cost behind the hard budget gate — the deciding leaderboard" />
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th onClick={() => setK('detector')}>detector{arrow('detector')}</th>
              <th>targets</th>
              <th onClick={() => setK('intel')} style={{ textAlign: 'right' }}>intel{arrow('intel')}</th>
              <th onClick={() => setK('vus_pr')} style={{ textAlign: 'right' }}>VUS-PR{arrow('vus_pr')}</th>
              <th onClick={() => setK('f1')} style={{ textAlign: 'right' }}>F1{arrow('f1')}</th>
              <th onClick={() => setK('us_per_sample')} style={{ textAlign: 'right' }}>µs/samp{arrow('us_per_sample')}</th>
              <th onClick={() => setK('state_bytes')} style={{ textAlign: 'right' }}>bytes{arrow('state_bytes')}</th>
              <th style={{ textAlign: 'center' }}>budget</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.detector} className={r.is_unified ? 'hl' : ''}>
                <td className="mono" style={{ fontWeight: r.is_unified || r.detector === overall ? 600 : 400 }}>
                  {r.detector}
                  {r.is_unified && <span className="badge accent" style={{ marginLeft: 8 }}>winner</span>}
                  {r.detector === overall && <span className="badge" style={{ marginLeft: 8 }}>best single</span>}
                </td>
                <td>
                  {r.targets.map((t) => <span key={t} className="dot" title={t} style={{ background: ATYPE_COLOR[t] || 'var(--fg-subtle)', marginRight: 3 }} />)}
                  <span style={{ color: 'var(--fg-subtle)', fontSize: 11, marginLeft: 4 }}>{cap(r.family)}</span>
                </td>
                <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.intel)}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{fmt(r.vus_pr)}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{fmt(r.f1)}</td>
                <td className="mono" style={{ textAlign: 'right', color: 'var(--fg-muted)' }}>{fmt(r.us_per_sample, 3)}</td>
                <td className="mono" style={{ textAlign: 'right', color: r.state_bytes < 100 ? 'var(--fg)' : 'var(--red)' }}>{r.state_bytes}</td>
                <td style={{ textAlign: 'center' }}>{r.budget_ok ? <span className="badge ok">pass</span> : <span className="badge no">over</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="desc" style={{ marginTop: 8 }}>
        intel = 0.45·VUS-PR + 0.30·F1 + 0.15·MCC + 0.10·latency-score. Click a column to sort. Colored dots = the
        anomaly types each detector is designed to catch.
      </p>

      {/* ---- Findings ---- */}
      <PhaseHead title="Findings" sub="what each phase taught us — and why unified was chosen" />
      <div className="grid g2">
        {FINDINGS.map((f) => (
          <div className="card" key={f.p}>
            <span className="badge accent">{f.p}</span>
            <p className="desc" style={{ marginTop: 8 }}>{f.t}</p>
          </div>
        ))}
      </div>

      <div className="section-title">Condition → best detector (per anomaly type)</div>
      <div className="grid g4">
        {Object.entries(d.condition_to_algorithm).map(([atype, w]) => (
          <div className="card" key={atype}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="dot" style={{ background: ATYPE_COLOR[atype] || 'var(--fg-subtle)' }} />
              <span style={{ textTransform: 'capitalize', fontWeight: 600 }}>{atype}</span>
            </div>
            <div className="mono" style={{ fontSize: 18, marginTop: 8 }}>{w.detector}</div>
            <div className="desc mono" style={{ fontSize: 12, marginTop: 4 }}>VUS {fmt(w.vus_pr, 2)} · F1 {fmt(w.f1, 2)} · w{w.window}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

const Stat = ({ n, l, cls, mono }) => (
  <div className="card stat">
    <div className={'n ' + (cls || '')} style={mono ? { fontSize: 22 } : undefined}>{n}</div>
    <div className="l">{l}</div>
  </div>
)

function PhaseHead({ n, title, sub }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '34px 0 14px' }}>
      {n && <span style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent)', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: 14, flex: 'none' }}>{n}</span>}
      <div>
        <div style={{ fontWeight: 600, fontSize: 16 }}>{n ? `Phase ${n} · ` : ''}{title}</div>
        <div className="desc" style={{ fontSize: 12.5 }}>{sub}</div>
      </div>
    </div>
  )
}

function PhaseTypeTable({ rows, showKind }) {
  const types = P2_TYPES.filter((t) => rows.some((r) => r.by_type && t in r.by_type))
  const colMax = {}
  types.forEach((t) => { colMax[t] = Math.max(...rows.map((r) => r.by_type?.[t] ?? 0)) })
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>detector</th>
            {showKind && <th>kind</th>}
            {types.map((t) => <th key={t} style={{ textAlign: 'right' }}>{t.replace('_', ' ')}</th>)}
            <th style={{ textAlign: 'right' }}>best F1</th>
            <th style={{ textAlign: 'right' }}>mean FPR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.detector}>
              <td className="mono" style={{ fontWeight: 600 }}>{r.detector}</td>
              {showKind && <td><span className="badge" style={{ color: KIND_COLOR[r.kind], borderColor: KIND_COLOR[r.kind] }}>{cap(r.kind)}</span></td>}
              {types.map((t) => {
                const v = r.by_type?.[t]
                const win = v != null && v === colMax[t]
                return <td key={t} className="mono" style={{ textAlign: 'right', color: win ? 'var(--accent)' : 'var(--fg-muted)', fontWeight: win ? 600 : 400 }}>{fmt(v)}</td>
              })}
              <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.f1_best)}</td>
              <td className="mono" style={{ textAlign: 'right', color: 'var(--fg-muted)' }}>{fmt(r.fpr_mean)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
