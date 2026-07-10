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

// one-line "what it is" for every detector name across the three phases (#6)
const DESC = {
  // Phase 2 / 3 — single
  ZScore: 'Rolling z-score (Welford) — point spikes',
  MAD: 'Median-absolute-deviation robust z — heavy-tailed spikes',
  EWMA: 'Exp-weighted moving-average control chart — level shifts',
  CUSUM: 'Cumulative-sum change detector — sustained shifts',
  PageHinkley: 'Page-Hinkley test — gradual drift',
  SlidingWindow: 'Sliding-window mean threshold — baseline',
  // Phase 3 — gated
  GatedZScore: 'Z-score + confirmation gate — fewer false positives',
  GatedMAD: 'MAD + confirmation gate — fewer false positives',
  GatedEWMA: 'EWMA + confirmation gate — fewer false positives',
  GatedCUSUM: 'CUSUM + confirmation gate — fewer false positives',
  // Phase 3 — ensemble
  Spike_AND: 'AND-vote of spike detectors — high precision',
  Spike_OR: 'OR-vote of spike detectors — high recall',
  Sustained_OR: 'OR-vote of change detectors — sustained shifts',
  TwoLayerEnsemble: 'Spike + sustained layers combined',
  // Phase 4 — production registry
  ewma_z: 'EWMA control-chart z-score',
  robust_z: 'Robust (MAD) z-score',
  hampel: 'Hampel identifier — robust outliers',
  cusum: 'CUSUM change detector',
  page_hinkley: 'Page-Hinkley drift test',
  ewmv_adaptive: 'Adaptive EWMA + variance control',
  deriv: 'First-difference derivative — Pareto-cheapest single',
  acf_periodicity: 'Autocorrelation-drop — periodicity loss',
  heavy_baseline: 'Heavy-tailed baseline model',
  layered: 'Layered spike + drift detector',
  voting: 'Voting ensemble (all four types)',
  cascade: 'Cascade ensemble',
  ewma_z_hold: 'EWMA-z with anomaly-aware HOLD baseline',
  ewmv_hold: 'EWMV with HOLD baseline',
  cusum_gated: 'CUSUM + confirmation gate',
  page_hinkley_gated: 'Page-Hinkley + confirmation gate',
  ewmv_gated: 'EWMV + confirmation gate',
  ewmv_hold_gated: 'EWMV-HOLD + confirmation gate',
  acf_gated: 'Gated ACF periodicity head',
  unified: 'THREE heads (derivative + EWMA + gated-ACF), MAX-fused — all four types in 96 B',
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
        <h1>From {d.counts.total} detectors to <span className="hero-underline">one winner</span></h1>
        <p>Four empirical phases evaluated <b>{d.counts.total} detectors</b> in total — Phase 2's {d.counts.phase2} single
          detectors, Phase 3's {d.counts.phase3} gated/ensemble variants, and Phase 4's fresh field of {d.counts.phase4}
          behind a hard budget gate — to select a single on-device winner: <b className="mono">unified</b>.</p>
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
      <PhaseHead n="2" title="Single-detector benchmark" sub={`${d.counts.phase2} single detectors · event detection rate by anomaly type — no single detector combines full coverage with a low false-alarm rate`} />
      <PhaseTypeTable rows={d.phase2} />
      <p className="desc" style={{ marginTop: 8 }}>
        <b>Why detection rate, not F1?</b> These are rare <i>point</i> anomalies — a handful of anomalous samples
        against thousands of normal ones — so sample-level precision floors near 0.1 % and sample-F1 collapses to
        ~0.01 for <i>every</i> detector, an uninformative number. The measure that carries signal is whether each
        anomaly <i>window</i> is flagged at all (event detection rate, shown above), read together with the
        false-positive rate.
      </p>

      {/* ---- Phase 2 -> Phase 3 justification ---- */}
      <div className="callout" style={{ marginTop: 14, borderLeftColor: 'var(--purple)' }}>
        <b>Why move Phase 2 → Phase 3?</b> Phase 2 exposes a tension: the detectors that catch everything do it by
        alerting constantly. <span className="mono">MAD</span> reaches <b>1.00</b> detection on spikes and transients
        but at a <b>~14.6 % FPR</b>, and <span className="mono">EWMA</span> sits near <b>~20 % FPR</b>. High recall
        <i> or</i> low false alarms — not both. Phase 3 adds a <b>confirmation gate</b> (fire only when an anomaly
        persists) and <b>ensembles</b> (vote across detectors), which cut false positives sharply while holding
        detection: <span className="mono">GatedZScore 5.1 % → 0.7 % FPR</span>,
        <span className="mono"> GatedMAD 14.6 % → 5.6 %</span>. The gated MAD / Z-Score family carries forward.
      </div>

      {/* ---- Phase 3 ---- */}
      <PhaseHead n="3" title="Confirmation-gated ensemble" sub={`${d.counts.phase3} detectors: 6 single + 4 gated + 4 ensemble · gating holds detection while cutting false positives`} />
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

      {/* ---- Full catalogue: every one of the 40 detectors, named (#6) ---- */}
      <PhaseHead title={`Full detector catalogue — all ${d.counts.total}`} sub="exactly which detectors were evaluated in each phase, and what each one is" />
      <div className="grid g3">
        <CatalogueCol n="2" title="Single-detector benchmark" names={d.phase2.map((r) => r.detector)} />
        <CatalogueCol n="3" title="Gated + ensemble" names={d.phase3.map((r) => r.detector)} />
        <CatalogueCol n="4" title="Production field" names={d.phase4.map((r) => r.detector)} winner="unified" />
      </div>
      <p className="desc" style={{ marginTop: 8 }}>
        {d.counts.phase2} + {d.counts.phase3} + {d.counts.phase4} = <b>{d.counts.total} detectors</b> evaluated in total.
        <span className="mono"> unified</span> (Phase 4) is the selected winner — one of the {d.counts.total}, not a
        separate entry.
      </p>
    </div>
  )
}

function CatalogueCol({ n, title, names, winner }) {
  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ width: 22, height: 22, borderRadius: 6, background: 'var(--accent)', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: 12, flex: 'none' }}>{n}</span>
        <span style={{ fontWeight: 600, fontSize: 13.5 }}>Phase {n} · {title}</span>
        <span style={{ marginLeft: 'auto', color: 'var(--fg-subtle)', fontSize: 12 }}>{names.length}</span>
      </div>
      <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'grid', gap: 7 }}>
        {names.map((nm, i) => (
          <li key={nm} style={{ display: 'grid', gridTemplateColumns: '18px 1fr', gap: 8, alignItems: 'baseline' }}>
            <span className="mono" style={{ color: 'var(--fg-subtle)', fontSize: 11 }}>{i + 1}</span>
            <span>
              <span className="mono" style={{ fontWeight: 600, fontSize: 12.5, color: nm === winner ? 'var(--accent)' : 'var(--fg)' }}>
                {nm}{nm === winner && <span className="badge accent" style={{ marginLeft: 6 }}>winner</span>}
              </span>
              <div className="desc" style={{ fontSize: 11.5, marginTop: 1 }}>{DESC[nm] || '—'}</div>
            </span>
          </li>
        ))}
      </ol>
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
  // headline metric = event-level DETECTION RATE per anomaly type (sample-F1 is
  // uninformative for rare point anomalies -- see the note under Phase 2)
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
                const v = r.by_type_det?.[t]
                const win = v != null && v === colMax[t]
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
