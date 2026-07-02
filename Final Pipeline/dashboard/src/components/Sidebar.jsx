import { NavLink } from 'react-router-dom'
import { IcOverview, IcTheory, IcArch, IcLive, IcEval, IcSun, IcMoon, IcMonitor } from './Icons.jsx'

const NAV = [
  { to: '/', label: 'Overview', Icon: IcOverview, end: true },
  { to: '/theory', label: 'Problem & Theory', Icon: IcTheory },
  { to: '/architecture', label: 'Architecture', Icon: IcArch },
  { to: '/live', label: 'Live Pipeline', Icon: IcLive },
  { to: '/evaluation', label: 'Evaluation', Icon: IcEval },
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
          <div className="name">Unified</div>
          <div className="sub">96-byte detector</div>
        </div>
      </div>

      <div className="nav-label">Explore</div>
      {NAV.map(({ to, label, Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}>
          <span className="ico"><Icon /></span>
          {label}
        </NavLink>
      ))}

      <div className="side-foot">
        <button className="icon-btn" onClick={cycle} title={`theme: ${pref} (click to change)`}>
          <TIcon size={16} />
        </button>
      </div>
    </aside>
  )
}
