import { useState } from 'react'
import { useJson } from '../lib/useJson.js'
import PhaseNav from '../components/PhaseNav.jsx'
import { Leaderboard, PhaseTypeTable, TargetsLegend, FamilyLegend, KindLegend } from '../components/EvalKit.jsx'

const SETS = [
  { id: 'phase2', n: '2', title: 'Single Detector', blurb: 'The six survivors from Phase 1, each running on its own.' },
  { id: 'phase3', n: '3', title: 'Gated and Ensemble', blurb: 'The six singles, plus four gated versions and four ensembles.' },
  { id: 'phase4', n: '4', title: 'On-Device Selection', blurb: 'A fresh field of twenty candidates, judged behind the budget gate.' },
]

export default function Catalogue() {
  const { loading, error, data } = useJson(['data/evaluation.json'])
  const [set, setSet] = useState('phase2')
  if (loading) return <div className="page"><div className="loading">loading evaluation…</div></div>
  if (error) return <div className="page"><div className="error">missing <code>evaluation.json</code>, run <code>python python/export_eval.py</code></div></div>
  const d = data[0]
  const overall = d.recommended.overall.detector
  const rowsBySet = { phase2: d.phase2, phase3: d.phase3, phase4: d.phase4 }
  const activeRows = rowsBySet[set]
  const activeSet = SETS.find((s) => s.id === set)

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">detector catalogue</div>
        <h1>Every detector we evaluated, <span className="hero-underline">all {d.counts.total}</span></h1>
        <p>Across the four-phase study we evaluated {d.counts.total} detectors in three sets: {d.counts.phase2} in Phase 2, {d.counts.phase3} in Phase 3, and {d.counts.phase4} in Phase 4. Pick a set to list the detectors in it and open the exact results table from that phase.</p>
      </div>

      {/* pick a set */}
      <div className="grid g3" style={{ marginBottom: 16 }}>
        {SETS.map((s) => {
          const on = set === s.id
          return (
            <button type="button" key={s.id} onClick={() => setSet(s.id)} className="card"
              style={{ cursor: 'pointer', textAlign: 'left', width: '100%', font: 'inherit', color: 'inherit', ...(on ? { borderColor: 'var(--accent)', background: 'var(--bg-hover)' } : {}) }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ width: 24, height: 24, borderRadius: 6, background: on ? 'var(--accent)' : 'var(--fg-subtle)', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: 12, flex: 'none' }}>{s.n}</span>
                <span style={{ fontWeight: 600 }}>Phase {s.n}</span>
                <span className="badge" style={{ marginLeft: 'auto' }}>{rowsBySet[s.id].length}</span>
              </div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{s.title}</div>
              <p className="desc" style={{ fontSize: 12 }}></p>
            </button>
          )
        })}
      </div>

      {/* the selected set: the detector list, then its results table */}
      <div className="section-title">Phase {activeSet.n} · {activeSet.title} · {activeRows.length} detectors</div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {activeRows.map((r) => {
            const win = r.detector === 'unified'
            return (
              <span key={r.detector} className="mono" style={{
                fontSize: 12.5, fontWeight: 600, padding: '5px 11px', borderRadius: 7,
                border: '1px solid ' + (win ? 'var(--accent)' : 'var(--border)'),
                background: 'var(--bg-subtle)', color: win ? 'var(--accent)' : 'var(--fg-muted)',
              }}>{r.detector}</span>
            )
          })}
        </div>
      </div>

      {set === 'phase4'
        ? (<><Leaderboard rows={activeRows} overall={overall} /><TargetsLegend /><FamilyLegend /></>)
        : (<><PhaseTypeTable rows={activeRows} showKind={set === 'phase3'} />{set === 'phase3' && <KindLegend />}</>)}

      <PhaseNav />
    </div>
  )
}
