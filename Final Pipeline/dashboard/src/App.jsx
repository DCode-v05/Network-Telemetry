import { useEffect } from 'react'
import { Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar.jsx'
import { useTheme } from './theme.js'
import Overview from './pages/Overview.jsx'
import Theory from './pages/Theory.jsx'
import Phase1 from './pages/Phase1.jsx'
import Phase2 from './pages/Phase2.jsx'
import Phase3Evaluators from './pages/Phase3Evaluators.jsx'
import Phase3Architecture from './pages/Phase3Architecture.jsx'
import Phase3Live from './pages/Phase3Live.jsx'
import Phase4Evaluators from './pages/Phase4Evaluators.jsx'
import Phase4Architecture from './pages/Phase4Architecture.jsx'
import FinalPipeline from './pages/FinalPipeline.jsx'
import Catalogue from './pages/Catalogue.jsx'

const TITLES = {
  '/': 'Overview', '/problem': 'Problem Statement',
  '/phase1': 'Phase 1 · Algorithm Study', '/phase2': 'Phase 2 · Benchmark',
  '/phase3/evaluators': 'Phase 3 · Evaluators',
  '/phase3/architecture': 'Phase 3 · Architecture',
  '/phase3/live': 'Phase 3 · Live Lab',
  '/phase4/evaluators': 'Phase 4 · Evaluators',
  '/phase4/architecture': 'Phase 4 · Architecture',
  '/phase4/live': 'Phase 4 · Live Lab',
  '/catalogue': 'Detector Catalogue',
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
          <span className="crumb">Network TSAD&nbsp;/&nbsp;<b>{title}</b></span>
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
        <Route path="problem" element={<Theory />} />
        <Route path="phase1" element={<Phase1 />} />
        <Route path="phase2" element={<Phase2 />} />
        <Route path="phase3" element={<Navigate to="/phase3/evaluators" replace />} />
        <Route path="phase3/evaluators" element={<Phase3Evaluators />} />
        <Route path="phase3/architecture" element={<Phase3Architecture />} />
        <Route path="phase3/live" element={<Phase3Live />} />
        <Route path="phase4" element={<Navigate to="/phase4/evaluators" replace />} />
        <Route path="phase4/evaluators" element={<Phase4Evaluators />} />
        <Route path="phase4/architecture" element={<Phase4Architecture />} />
        <Route path="phase4/live" element={<FinalPipeline />} />
        <Route path="catalogue" element={<Catalogue />} />
        <Route path="final" element={<Navigate to="/phase4/live" replace />} />
      </Route>
    </Routes>
  )
}
