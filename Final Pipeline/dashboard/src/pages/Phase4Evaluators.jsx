import { useJson } from '../lib/useJson.js'
import PhaseNav from '../components/PhaseNav.jsx'
import { PHASE4 } from '../content/phases.js'
import { Leaderboard, TargetsLegend, FamilyLegend, Stat } from '../components/EvalKit.jsx'

export default function Phase4Evaluators() {
  const { loading, error, data } = useJson(['data/evaluation.json'])
  if (loading) return <div className="page"><div className="loading">loading evaluation…</div></div>
  if (error) return <div className="page"><div className="error">missing <code>evaluation.json</code>, run <code>python python/export_eval.py</code></div></div>
  const d = data[0]
  const overall = d.recommended.overall.detector
  const budgetPass = d.phase4.filter((r) => r.budget_ok).length

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 4 · evaluators</div>
        <h1>Accuracy vs. cost, <span className="hero-underline">one winner</span></h1>
        <p>{PHASE4.goal}</p>
      </div>

      <div className="grid g4">
        <Stat n="20" l="Detectors screened" />
        <Stat n={`${budgetPass}/20`} l="Pass < 100 µs & < 100 B" cls="green" />
        <Stat n="unified" l="Selected detector" cls="accent" mono />
        <Stat n="0.93" l="unified F1 score" />
      </div>

      <div className="section-title">The deciding leaderboard · 20 detectors × best window</div>
      <Leaderboard rows={d.phase4} overall={overall} minimal />
      <TargetsLegend />
      <FamilyLegend />

      <PhaseNav />
    </div>
  )
}
