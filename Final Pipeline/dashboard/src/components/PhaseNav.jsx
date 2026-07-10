import { Link, useLocation } from 'react-router-dom'
import { IcArrow } from './Icons.jsx'

// the full journey order, used for prev/next footer navigation on every page
export const JOURNEY = [
  { to: '/', label: 'Overview' },
  { to: '/problem', label: 'Problem Statement' },
  { to: '/phase1', label: 'Phase 1 · Algorithm Study' },
  { to: '/phase2', label: 'Phase 2 · Benchmark' },
  { to: '/phase3/evaluators', label: 'Phase 3 · Evaluators' },
  { to: '/phase3/architecture', label: 'Phase 3 · Architecture' },
  { to: '/phase3/live', label: 'Phase 3 · Live Lab' },
  { to: '/phase4/evaluators', label: 'Phase 4 · Evaluators' },
  { to: '/phase4/architecture', label: 'Phase 4 · Architecture' },
  { to: '/phase4/live', label: 'Phase 4 · Live Lab · Final Pipeline' },
  { to: '/catalogue', label: 'Detector Catalogue' },
]

export default function PhaseNav() {
  const loc = useLocation()
  const i = JOURNEY.findIndex((j) => j.to === loc.pathname)
  const prev = i > 0 ? JOURNEY[i - 1] : null
  const next = i >= 0 && i < JOURNEY.length - 1 ? JOURNEY[i + 1] : null
  return (
    <div style={{ display: 'flex', gap: 12, marginTop: 40, flexWrap: 'wrap' }}>
      {prev && (
        <Link to={prev.to} className="card link" style={{ flex: 1, minWidth: 220, textDecoration: 'none' }}>
          <div style={{ fontSize: 11, color: 'var(--fg-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>← Previous</div>
          <div style={{ fontWeight: 600, marginTop: 3 }}>{prev.label}</div>
        </Link>
      )}
      {next && (
        <Link to={next.to} className="card link" style={{ flex: 1, minWidth: 220, textAlign: 'right', textDecoration: 'none' }}>
          <div style={{ fontSize: 11, color: 'var(--fg-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Next →</div>
          <div style={{ fontWeight: 600, marginTop: 3, color: 'var(--accent)' }}>{next.label} <IcArrow size={13} /></div>
        </Link>
      )}
    </div>
  )
}
