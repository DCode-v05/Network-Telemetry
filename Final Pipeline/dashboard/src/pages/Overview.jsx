import { Link } from 'react-router-dom'
import { useJson } from '../lib/useJson.js'
import { IcTheory, IcEval, IcLive, IcChip, IcArch, IcCode, IcArrow } from '../components/Icons.jsx'

const JOURNEY = [
  { to: '/problem', Icon: IcTheory, c: 'var(--cyan)', t: 'Problem Statement', d: 'What it takes to run detection on a switch’s little ARM processor: under 100 µs, under 100 bytes, and only 10 to 50 samples to work with. Plus the four kinds of anomaly we’re after.' },
  { to: '/phase1', Icon: IcEval, c: 'var(--cyan)', t: 'Phase 1 · Algorithm Study', d: 'We put 15 classic algorithms up against the budget on paper. Six made it through, and nine were ruled out before we ran a single test.' },
  { to: '/phase2', Icon: IcLive, c: 'var(--amber)', t: 'Phase 2 · Benchmark', d: 'A 2,880-run benchmark of the six on real traffic, where it turns out no single one catches everything. Try the live six-detector lab.' },
  { to: '/phase3', Icon: IcChip, c: 'var(--purple)', t: 'Phase 3 · Gated Ensemble', d: 'A confirmation gate and two voting layers cut false alarms by 50 to 85%. Watch the gate do its thing, live.' },
  { to: '/phase4/evaluators', Icon: IcArch, c: 'var(--accent)', t: 'Phase 4 · Selection', d: 'Twenty detectors judged on smarts and cost at once, behind a hard budget gate, and how unified came out on top. With a live demo.' },
  { to: '/phase4/live', Icon: IcCode, c: 'var(--green)', t: 'Final Pipeline', d: 'The 96-byte result you can actually ship: identical in Python, C and JS with zero drift, plus live capture of real network telemetry.' },
]

export default function Overview() {
  const { data } = useJson(['data/c_results.json', 'data/evaluation.json'])
  const c = data?.[0]
  const ns = c?.bench?.rows?.[0]?.ns_per_sample
  const total = data?.[1]?.counts?.total

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">on-device streaming anomaly detection · a four-phase journey</div>
        <h1>From 15 algorithms<br /><span className="hero-underline">to one 96-byte detector.</span></h1>
        <p>
          Here’s the whole story of a small research project. We sift through the classic techniques, benchmark the ones
          that survive, combine them, and finally land on a single streaming detector that catches spikes, drift,
          periodicity loss and transients right on a network switch. And it does all of that inside a hard budget of
          under 100 microseconds and under 100 bytes per metric. The site walks you through it phase by phase, with
          something live to play with at each step.
        </p>
      </div>

      <div className="grid g4">
        <Stat n="4" u="phases" top />
        <Stat n={total || '40'} u="detectors" cls="accent" top />
        <Stat n="96" u="bytes" cls="green" top />
        <Stat n={ns ? ns.toFixed(0) : '~55'} u="ns/sample" cls="green" top />
      </div>

      <div className="section-title">Walk the journey</div>
      <div className="grid g2">
        {JOURNEY.map(({ to, Icon, c, t, d }) => (
          <Link key={to} to={to} className="card link">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
              <span className="icon-tile" style={{ background: `color-mix(in srgb, ${c} 14%, transparent)`, color: c }}><Icon size={19} /></span>
              <h3 style={{ margin: 0, fontSize: 15 }}>{t}</h3>
              <span style={{ marginLeft: 'auto', color: 'var(--fg-subtle)' }}><IcArrow size={16} /></span>
            </div>
            <p className="desc">{d}</p>
          </Link>
        ))}
      </div>

    </div>
  )
}

const Stat = ({ n, u, l, cls, top }) => (
  <div className={'card stat' + (top ? ' accent-top' : '')}>
    <div className={'n ' + (cls || '')}>{n}{u && <small> {u}</small>}</div>
    {l && <div className="l">{l}</div>}
  </div>
)
