import { useEffect } from 'react'
import { Routes, Route, Outlet, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar.jsx'
import { useTheme } from './theme.js'
import Overview from './pages/Overview.jsx'
import Theory from './pages/Theory.jsx'
import Architecture from './pages/Architecture.jsx'
import LivePipeline from './pages/LivePipeline.jsx'
import Evaluation from './pages/Evaluation.jsx'

const TITLES = {
  '/': 'Overview', '/theory': 'Problem & Theory', '/architecture': 'Architecture',
  '/live': 'Live Pipeline', '/evaluation': 'Evaluation',
}

function Layout({ theme }) {
  const loc = useLocation()
  const title = TITLES[loc.pathname] || 'Unified'
  // reset scroll to top on every route change (both window- and container-scroll)
  useEffect(() => {
    window.scrollTo(0, 0)
    document.querySelector('.content')?.scrollTo(0, 0)
  }, [loc.pathname])
  return (
    <div className="shell">
      <Sidebar theme={theme} />
      <div className="content">
        <div className="topbar">
          <span className="crumb">Unified&nbsp;/&nbsp;<b>{title}</b></span>
          <span className="spacer" />
        </div>
        <Outlet context={{ theme }} />
      </div>
    </div>
  )
}

export default function App() {
  const theme = useTheme()
  return (
    <Routes>
      <Route element={<Layout theme={theme} />}>
        <Route index element={<Overview />} />
        <Route path="theory" element={<Theory />} />
        <Route path="architecture" element={<Architecture />} />
        <Route path="live" element={<LivePipeline />} />
        <Route path="evaluation" element={<Evaluation />} />
      </Route>
    </Routes>
  )
}
