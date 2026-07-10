import { useJson } from '../lib/useJson.js'
import PhaseNav from '../components/PhaseNav.jsx'
import LivePipeline from './LivePipeline.jsx'

const fmt = (x, d = 1) => (x == null ? '·' : Number(x).toFixed(d))

export default function FinalPipeline() {
  const { data } = useJson(['data/c_results.json'])
  const c = data?.[0]
  const ns = c?.bench?.rows?.[0]?.ns_per_sample
  const bytes = c?.bench?.state_bytes ?? 96

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">final pipeline · the deliverable</div>
        <h1>One 96-byte unit, <span className="hero-underline">running live</span>.</h1>
        <p>This is where the journey ends: the winning <span className="mono">unified</span> detector, pulled out into
          a self-contained package with a live dashboard and real network capture. This is the thing that would actually
          run on the switch.</p>
      </div>

      <div className="grid g3">
        <Stat n={bytes} u="bytes" l="on-device state · < 100 budget" cls="green" />
        <Stat n={ns ? fmt(ns, 0) : '~55'} u="ns/sample" l="measured in C · < 100 µs budget" cls="green" />
        <Stat n="4" u="types" l="one unit covers all four" />
      </div>

      <div className="section-title">Live demo · the pipeline on real telemetry</div>
      <p className="desc" style={{ margin: '-6px 0 14px' }}>
        The same 96-byte unit, now scoring your device's live network throughput, or ping latency to any IPv4 host you
        type in, one sample at a time. You'll need the engine server running (<span className="mono">python server.py</span>).
      </p>
      <LivePipeline embed defaultInput="clean" />

      <PhaseNav />
    </div>
  )
}

const Stat = ({ n, u, l, cls }) => (
  <div className="card stat accent-top"><div className={'n ' + (cls || '')}>{n}{u && <small> {u}</small>}</div><div className="l">{l}</div></div>
)
