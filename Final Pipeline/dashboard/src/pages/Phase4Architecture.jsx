import PhaseNav from '../components/PhaseNav.jsx'
import Architecture from './Architecture.jsx'
import { PHASE4 } from '../content/phases.js'

export default function Phase4Architecture() {
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 4 · architecture</div>
        <h1>Three heads, one 96-byte state, <span className="hero-underline">MAX-fused</span></h1>
        <p>The winning detector is a single unit with three specialised heads that all share one 96-byte block of state. Every sample flows through that shared state into the three heads, and the final score is simply the largest of the three.</p>
      </div>

      <Architecture embed />


      <PhaseNav />
    </div>
  )
}
