import { NavLink } from 'react-router-dom'
import { IcOverview, IcTheory, IcEval, IcLive, IcChip, IcArch, IcSun, IcMoon, IcMonitor } from './Icons.jsx'

const NAV = [
  { to: '/', label: 'Overview', Icon: IcOverview, end: true },
  { to: '/problem', label: 'Problem Statement', Icon: IcTheory },
  { to: '/phase1', label: 'Phase 1 · Study', Icon: IcEval },
  { to: '/phase2', label: 'Phase 2 · Benchmark', Icon: IcLive },
  {
    to: '/phase3', label: 'Phase 3 · Ensemble', Icon: IcChip,
    children: [
      { to: '/phase3/evaluators', label: 'Evaluators' },
      { to: '/phase3/architecture', label: 'Architecture' },
      { to: '/phase3/live', label: 'Live Lab' },
    ],
  },
  {
    to: '/phase4', label: 'Phase 4 · Selection', Icon: IcArch,
    children: [
      { to: '/phase4/evaluators', label: 'Evaluators' },
      { to: '/phase4/architecture', label: 'Architecture' },
      { to: '/phase4/live', label: 'Live Lab' },
    ],
  },
  { to: '/catalogue', label: 'Detector Catalogue', Icon: IcEval },
]

export default function Sidebar({ theme }) {
  const { pref, cycle } = theme
  const TIcon = pref === 'dark' ? IcMoon : pref === 'light' ? IcSun : IcMonitor
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="mark">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 12h4l2-7 4 14 3-9 2 4h5" />
          </svg>
        </div>
        <div>
          <div className="name">Network TSAD</div>
        </div>
      </div>

      <div className="nav-label">The journey</div>
      {NAV.map(({ to, label, Icon, end, children }) => (
        <div key={to}>
          <NavLink to={to} end={end} className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}>
            <span className="ico"><Icon /></span>
            {label}
          </NavLink>
          {children && (
            <div className="nav-sub">
              {children.map((c) => (
                <NavLink key={c.to} to={c.to} className={({ isActive }) => 'nav-subitem' + (isActive ? ' active' : '')}>
                  {c.label}
                </NavLink>
              ))}
            </div>
          )}
        </div>
      ))}

      <div className="side-foot">
        <button className="icon-btn" onClick={cycle} title={`theme: ${pref} (click to change)`}>
          <TIcon size={16} />
        </button>
      </div>
    </aside>
  )
}
