import { useEffect, useMemo, useRef, useState } from 'react'
import PhaseNav from '../components/PhaseNav.jsx'
import { ZScore, MAD, EWMA, CUSUM, ConfirmationGate, TwoLayerEnsemble } from '../lib/phaseDetectors.js'
import { makeStream, scoreAlerts } from '../lib/phaseData.js'
import { PHASE3 } from '../content/phases.js'

const BASES = { MAD: () => new MAD(20, 3.5), ZScore: () => new ZScore(20, 3.0), EWMA: () => new EWMA(0.2, 3.5), CUSUM: () => new CUSUM(0.5, 3.5) }
const ATYPES = [{ key: 'burst', name: 'Burst' }, { key: 'transient', name: 'Transient' }, { key: 'rate_shift', name: 'Rate shift' }, { key: 'gradual_drift', name: 'Gradual drift' }]

export default function Phase3Live() {
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 3 · live lab</div>
        <h1>Watch the gate <span className="hero-underline">kill false alarms</span></h1>
      </div>

      <Phase3Lab />

      <div className="section-title">Why this pushed us to Phase 4</div>
      <div className="callout" style={{ borderLeftColor: 'var(--purple)' }}>{PHASE3.justification}</div>

      <PhaseNav />
    </div>
  )
}

// ------------------------------- live lab -----------------------------------
function Phase3Lab() {
  const [base, setBase] = useState('MAD')
  const [atype, setAtype] = useState('burst')
  const [seed, setSeed] = useState(2)
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(true)
  const iRef = useRef(0)

  const stream = useMemo(() => makeStream(atype, { seed }), [atype, seed])
  const N = stream.values.length
  const tracks = useMemo(() => {
    const raw = BASES[base](); const gated = new ConfirmationGate(BASES[base](), 2); const ens = new TwoLayerEnsemble(20)
    const rawA = [], gatA = [], ensA = []
    for (const x of stream.values) { rawA.push(raw.update(x).alert); gatA.push(gated.update(x).alert); ensA.push(ens.update(x).alert) }
    return [
      { key: `${base}`, alerts: rawA, color: 'var(--red)' },
      { key: `Gated${base}`, alerts: gatA, color: 'var(--green)' },
      { key: 'TwoLayerEnsemble', alerts: ensA, color: 'var(--purple)' },
    ]
  }, [stream, base])

  useEffect(() => { iRef.current = 0; setIdx(0); setPlaying(true) }, [base, atype, seed])
  useEffect(() => {
    if (!playing) return
    const step = Math.max(1, Math.round(N / 110))
    const id = setInterval(() => { const i = Math.min(N, iRef.current + step); iRef.current = i; setIdx(i); if (i >= N) setPlaying(false) }, 30)
    return () => clearInterval(id)
  }, [playing, N])

  const scored = tracks.map((t) => ({ ...t, s: scoreAlerts(t.alerts.map((a, i) => (i < idx ? a : false)), stream.event, stream.labels) }))
  const done = idx >= N
  const rawFP = scored[0].s.fp, gatFP = scored[1].s.fp

  return (
    <div>
      <div className="deck-row">
        <div className="grp"><span className="lbl">base detector</span>
          <div className="seg">{Object.keys(BASES).map((b) => <button key={b} className={base === b ? 'on' : ''} onClick={() => setBase(b)}>{b}</button>)}</div>
        </div>
        <div className="grp"><span className="lbl">anomaly</span>
          <div className="seg">{ATYPES.map((t) => <button key={t.key} className={atype === t.key ? 'on' : ''} onClick={() => setAtype(t.key)}>{t.name}</button>)}</div>
        </div>
        <div className="grp">
          <button className="btn primary" onClick={() => { if (done) { iRef.current = 0; setIdx(0) } setPlaying(!playing) }}>{playing ? '❙❙ Pause' : done ? '⟲ Replay' : '▶ Play'}</button>
          <button className="btn" onClick={() => setSeed((s) => s + 1)}>Re-roll</button>
        </div>
        <div className="grp" style={{ marginLeft: 'auto' }}><span className={'rec ' + (playing ? 'live' : done ? 'done' : '')}><span className="d" />{playing ? 'STREAMING' : done ? 'COMPLETE' : 'READY'} · {idx}/{N}</span></div>
      </div>

      <div className="card pad0" style={{ marginBottom: 14 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--fg-muted)' }} className="mono">live reproduction · generated data · anomaly region shaded · each row = one detector's alerts</div>
        <div style={{ padding: '10px 14px' }}>
          {scored.map((t) => (
            <div key={t.key} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 120px', gap: 12, alignItems: 'center', padding: '6px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5 }}><span className="dot" style={{ background: t.color }} /><span className="mono" style={{ fontWeight: 600 }}>{t.key}</span></div>
              <AlertRaster alerts={t.alerts} idx={idx} N={N} event={stream.event} color={t.color} />
              <div className="mono" style={{ fontSize: 12, textAlign: 'right' }}>
                {t.s.caught ? <span style={{ color: 'var(--green)' }}>caught</span> : <span style={{ color: 'var(--red)' }}>missed</span>}
                <span style={{ color: t.s.fp > 3 ? 'var(--red)' : 'var(--fg-muted)' }}> · {t.s.fp} FP</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="callout" style={{ borderLeftColor: 'var(--green)' }}>
        <b>Confirmation gate:</b> in this run, <span className="mono">{base}</span> fired <b style={{ color: 'var(--red)' }}>{rawFP}</b> false alarm{rawFP === 1 ? '' : 's'} on clean noise.
        {' '}<span className="mono">Gated{base}</span> cut that to <b style={{ color: 'var(--green)' }}>{gatFP}</b> by asking for two alarms in a row, so the stray single ticks never survive but the real anomaly does.
      </div>
    </div>
  )
}

function AlertRaster({ alerts, idx, N, event, color }) {
  return (
    <svg viewBox={`0 0 ${N} 20`} preserveAspectRatio="none" style={{ width: '100%', height: 18, display: 'block', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--bg-subtle)' }}>
      <rect x={event[0]} y={0} width={Math.max(1, event[1] - event[0] + 1)} height={20} fill="var(--fg)" opacity="0.08" />
      {alerts.map((a, i) => (a && i < idx ? <line key={i} x1={i + 0.5} x2={i + 0.5} y1={2} y2={18} stroke={color} strokeWidth={1.4} vectorEffect="non-scaling-stroke" /> : null))}
    </svg>
  )
}
