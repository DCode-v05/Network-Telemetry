import { Link } from 'react-router-dom'
import { useJson } from '../lib/useJson.js'
import { IcTheory, IcArch, IcLive, IcEval, IcArrow } from '../components/Icons.jsx'

const CARDS = [
  { to: '/theory', Icon: IcTheory, c: 'var(--cyan)', t: 'Problem & Theory', d: 'The on-device constraint, and the four anomaly types explained.' },
  { to: '/architecture', Icon: IcArch, c: 'var(--purple)', t: 'Architecture', d: 'Three heads, one 96-byte state block, and which head catches what.' },
  { to: '/live', Icon: IcLive, c: 'var(--green)', t: 'Live Pipeline', d: 'Stream a signal through the detector in Python, C, or JS — sample by sample.' },
  { to: '/evaluation', Icon: IcEval, c: 'var(--accent)', t: 'Evaluation', d: '40 detectors across 3 phases — and why unified was chosen.' },
]

export default function Overview() {
  const { data } = useJson(['data/c_results.json', 'data/evaluation.json'])
  const c = data?.[0]
  const evalD = data?.[1]
  const ns = c?.bench?.rows?.[0]?.ns_per_sample
  const uni = evalD?.recommended?.best_combined

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">on-device streaming anomaly detection</div>
        <h1>One 96-byte detector.<br /><span className="hero-underline">Four anomaly types.</span></h1>
        <p>
          A single streaming unit that catches spikes, drift, periodicity loss, and transients on a network
          switch's control-plane processor — inside a hard budget of &lt; 100 microseconds and &lt; 100 bytes
          per metric. The same algorithm runs identically in Python, C, and in your browser.
        </p>
      </div>

      <div className="grid g4">
        <Stat n="96" u="bytes" l="on-device state · < 100 budget" cls="green" top />
        <Stat n={ns ? ns.toFixed(0) : '~55'} u="ns/sample" l="measured in C · < 100 µs budget" cls="green" top />
        <Stat n="0.0" u="Δ" l="Python = C = JS parity" cls="accent" top />
        <Stat n="40" u="→ 1" l="detectors evaluated → winner" top />
      </div>

      <div className="section-title">Explore the demo</div>
      <div className="grid g2">
        {CARDS.map(({ to, Icon, c, t, d }) => (
          <Link key={to} to={to} className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
              <span className="icon-tile" style={{ background: `color-mix(in srgb, ${c} 14%, transparent)`, color: c }}><Icon size={19} /></span>
              <h3 style={{ margin: 0, fontSize: 15 }}>{t}</h3>
              <span style={{ marginLeft: 'auto', color: 'var(--fg-subtle)' }}><IcArrow size={16} /></span>
            </div>
            <p className="desc">{d}</p>
          </Link>
        ))}
      </div>

      {uni && (
        <div className="card" style={{ marginTop: 14, borderColor: 'color-mix(in srgb, var(--accent) 35%, var(--border))', background: 'color-mix(in srgb, var(--accent) 4%, var(--bg-elevated))' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span className="badge accent">winner</span>
            <h3 style={{ margin: 0 }}>unified</h3>
          </div>
          <p className="desc">
            Highest VUS-PR (<b className="mono">{uni.vus_pr?.toFixed(2)}</b>) of any budget-passing detector,
            covering all four anomaly types in just <b className="mono">96 bytes</b>. See the full 40-detector
            comparison on the <Link to="/evaluation" style={{ color: 'var(--accent)' }}>Evaluation</Link> page.
          </p>
        </div>
      )}
    </div>
  )
}

const Stat = ({ n, u, l, cls, top }) => (
  <div className={'card stat' + (top ? ' accent-top' : '')}>
    <div className={'n ' + (cls || '')}>{n}{u && <small> {u}</small>}</div>
    <div className="l">{l}</div>
  </div>
)
