import { useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import EChart, { themeColors } from '../components/EChart.jsx'
import PhaseNav from '../components/PhaseNav.jsx'
import { useJson } from '../lib/useJson.js'
import { SINGLE_DEFS } from '../lib/phaseDetectors.js'
import { makeStream, scoreAlerts } from '../lib/phaseData.js'
import { PHASE2 } from '../content/phases.js'

const P2_TYPES = ['burst', 'rate_shift', 'gradual_drift', 'transient']
const ATYPES = [{ key: 'burst', name: 'Burst' }, { key: 'transient', name: 'Transient' }, { key: 'rate_shift', name: 'Rate shift' }, { key: 'gradual_drift', name: 'Gradual drift' }]
const fmt = (x, d = 2) => (x == null ? '·' : Number(x).toFixed(d))

export default function Phase2() {
  const { theme } = useOutletContext()
  const { data } = useJson(['data/evaluation.json'])
  const evalD = data?.[0]
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">phase 2 · single-detector benchmark</div>
        <h1>No single detector <span className="hero-underline">wins every type</span></h1>
        <p>{PHASE2.goal}</p>
      </div>

      <div className="grid g4">
        <Stat n="6" l="Detectors benchmarked" />
        <Stat n="4" l="Anomaly types" />
        <Stat n="2,880" l="Trials swept" />
        <Stat n="30" l="Repeats per cell" />
      </div>

      <div className="section-title">How the benchmark ran</div>
      <div className="grid g2">
        {PHASE2.method.map((m) => (
          <div className="card" key={m.k}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{m.k}</div>
            <p className="desc">{m.v}</p>
          </div>
        ))}
      </div>

      <div className="section-title">Live reproduction</div>
      <Phase2Lab theme={theme} />

      <div className="section-title">What the full 2,880-trial sweep found</div>
      <div className="grid g2">
        {PHASE2.findings.map((f, i) => (
          <div className="card" key={i}><p className="desc">{f}</p></div>
        ))}
      </div>

      {evalD && (
        <>
          <div className="section-title">Event detection-rate by anomaly type (real results)</div>
          <DetTable rows={evalD.phase2} />
        </>
      )}

      <PhaseNav />
    </div>
  )
}

// ---------------------------------------------------------------- live lab ----
function Phase2Lab({ theme }) {
  const [atype, setAtype] = useState('transient')
  const [win, setWin] = useState(20)
  const [seed, setSeed] = useState(118)   // a seed where no single detector catches all four types
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(true)
  const iRef = useRef(0)

  const stream = useMemo(() => makeStream(atype, { seed }), [atype, seed])
  const N = stream.values.length
  const results = useMemo(
    () => SINGLE_DEFS.map((def) => {
      const det = def.make(win)
      const alerts = stream.values.map((x) => det.update(x).alert)
      return { def, alerts }
    }),
    [stream, win]
  )

  // reset + autoplay on any control change
  useEffect(() => { iRef.current = 0; setIdx(0); setPlaying(true) }, [atype, win, seed])
  useEffect(() => {
    if (!playing) return
    const step = Math.max(1, Math.round(N / 110))
    const id = setInterval(() => {
      const i = Math.min(N, iRef.current + step)
      iRef.current = i; setIdx(i)
      if (i >= N) setPlaying(false)
    }, 30)
    return () => clearInterval(id)
  }, [playing, N])

  const scored = results.map((r) => ({
    ...r,
    s: scoreAlerts(r.alerts.map((a, i) => (i < idx ? a : false)), stream.event, stream.labels),
  }))
  const board = scored   // fixed detector order (spike family, then change family); do not reorder by caught
  const done = idx >= N
  const caughtBy = done ? scored.filter((r) => r.s.caught).map((r) => r.def.key) : []
  const missedBy = done ? scored.filter((r) => !r.s.caught).map((r) => r.def.key) : []

  const option = useMemo(() => signalOption(stream, idx, theme.resolved), [stream, idx, theme.resolved])

  return (
    <div>
      <div className="deck-row">
        <div className="grp"><span className="lbl">anomaly type</span>
          <div className="seg">{ATYPES.map((t) => <button key={t.key} className={atype === t.key ? 'on' : ''} onClick={() => setAtype(t.key)}>{t.name}</button>)}</div>
        </div>
        <div className="grp"><span className="lbl">window</span>
          <div className="seg">{[10, 20, 30, 50].map((w) => <button key={w} className={w === win ? 'on' : ''} onClick={() => setWin(w)}>{w}</button>)}</div>
        </div>
        <div className="grp">
          <button className="btn primary" onClick={() => { if (done) { iRef.current = 0; setIdx(0) } setPlaying(!playing) }}>{playing ? '❙❙ Pause' : done ? '⟲ Replay' : '▶ Play'}</button>
          <button className="btn" onClick={() => setSeed((s) => s + 1)}>Re-roll</button>
        </div>
        <div className="grp" style={{ marginLeft: 'auto' }}>
          <span className={'rec ' + (playing ? 'live' : done ? 'done' : '')}><span className="d" />{playing ? 'STREAMING' : done ? 'COMPLETE' : 'READY'} · {idx}/{N}</span>
        </div>
      </div>

      <div className="card pad0" style={{ marginBottom: 14 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--fg-muted)' }} className="mono">
          Phase 2
        </div>
        <div style={{ padding: 8 }}><EChart option={option} height={200} themeKey={theme.resolved} /></div>
        <div style={{ padding: '4px 14px 14px' }}>
          {board.map((r) => (
            <div key={r.def.key} style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 12, alignItems: 'center', padding: '6px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5 }}>
                <span className="dot" style={{ background: r.def.color }} />
                <span className="mono" style={{ fontWeight: 600 }}>{r.def.key}</span>
              </div>
              <AlertRaster alerts={r.alerts} idx={idx} N={N} event={stream.event} color={r.def.color} />
            </div>
          ))}
        </div>
      </div>

      <div className="tbl-wrap" style={{ marginBottom: 14 }}>
        <table className="tbl">
          <thead><tr><th>detector</th><th>family</th><th style={{ textAlign: 'center' }}>caught?</th><th style={{ textAlign: 'right' }}>latency (samp)</th><th style={{ textAlign: 'right' }}>false alarms</th></tr></thead>
          <tbody>
            {board.map((r) => (
              <tr key={r.def.key}>
                <td className="mono" style={{ fontWeight: 600 }}><span className="dot" style={{ background: r.def.color, marginRight: 8 }} />{r.def.key}</td>
                <td style={{ color: 'var(--fg-muted)', fontSize: 12 }}>{r.def.family === 'spike' ? 'Spike / instant' : 'Sustained / change'}</td>
                <td style={{ textAlign: 'center' }}>{r.s.caught ? <span className="badge ok">Caught</span> : <span className="badge no">Missed</span>}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{r.s.caught ? r.s.latency : '·'}</td>
                <td className="mono" style={{ textAlign: 'right', color: r.s.fp > 3 ? 'var(--red)' : 'var(--fg-muted)' }}>{r.s.fp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>What the family labels mean</div>
        <div className="grid g2" style={{ gap: 10 }}>
          <div style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
            <span className="dot" style={{ background: 'var(--red)', flex: 'none', position: 'relative', top: 4 }} />
            <div style={{ fontSize: 13 }}><b>Spike / instant</b><span style={{ color: 'var(--fg-muted)' }}>: reacts to a single large deviation right away, so it fires the moment a spike or transient shows up (Z-Score, MAD, Sliding-Window).</span></div>
          </div>
          <div style={{ display: 'flex', gap: 9, alignItems: 'baseline' }}>
            <span className="dot" style={{ background: 'var(--purple)', flex: 'none', position: 'relative', top: 4 }} />
            <div style={{ fontSize: 13 }}><b>Sustained / change</b><span style={{ color: 'var(--fg-muted)' }}>: builds up evidence over several samples to catch a lasting shift or drift, slower but steadier (EWMA, CUSUM, Page-Hinkley).</span></div>
          </div>
        </div>
      </div>

      {done && (
        <div className="callout" style={{ borderLeftColor: caughtBy.length && missedBy.length ? 'var(--amber)' : 'var(--green)' }}>
          <b>Result:</b> caught by <span className="mono" style={{ color: 'var(--green)' }}>{caughtBy.join(', ') || 'none'}</span>
          {missedBy.length > 0 && <> · missed by <span className="mono" style={{ color: 'var(--red)' }}>{missedBy.join(', ')}</span></>}.
          {' '}
        </div>
      )}
    </div>
  )
}

function AlertRaster({ alerts, idx, N, event, color }) {
  return (
    <svg viewBox={`0 0 ${N} 20`} preserveAspectRatio="none" style={{ width: '100%', height: 18, display: 'block', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--bg-subtle)' }}>
      <rect x={event[0]} y={0} width={Math.max(1, event[1] - event[0] + 1)} height={20} fill="var(--fg)" opacity="0.08" />
      {alerts.map((a, i) => (a && i < idx
        ? <line key={i} x1={i + 0.5} x2={i + 0.5} y1={2} y2={18} stroke={color} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
        : null))}
    </svg>
  )
}

function signalOption(stream, idx, themeKey) {
  const t = themeColors()
  const N = stream.values.length
  const data = []
  for (let i = 0; i < Math.min(idx, N); i++) data.push([i, stream.values[i]])
  return {
    animation: false, backgroundColor: 'transparent',
    grid: { left: 46, right: 14, top: 10, bottom: 24 },
    tooltip: {
      trigger: 'axis', backgroundColor: t.bg, borderColor: t.border, textStyle: { color: t.fg, fontSize: 11 },
      formatter: (ps) => {
        const p = ps && ps[0]
        if (!p) return ''
        const i = p.data[0], v = p.data[1]
        const inAnom = stream.labels[i] === 1
        return `sample <b>${i}</b> of ${N - 1}<br/>value <b>${Number(v).toFixed(2)}</b>`
          + (inAnom ? `<br/><span style="color:${t.amber}">● injected anomaly</span>` : `<br/><span style="color:${t.subtle}">normal</span>`)
      },
    },
    xAxis: { type: 'value', min: 0, max: N - 1, name: 'sample', nameLocation: 'middle', nameGap: 22, nameTextStyle: { color: t.subtle, fontSize: 10 }, axisLine: { lineStyle: { color: t.border } }, axisLabel: { color: t.subtle }, splitLine: { show: false } },
    yAxis: { type: 'value', scale: true, name: 'value', nameTextStyle: { color: t.subtle, fontSize: 10 }, axisLine: { lineStyle: { color: t.border } }, axisLabel: { color: t.subtle }, splitLine: { lineStyle: { color: t.border, opacity: 0.5 } } },
    series: [{
      type: 'line', data, showSymbol: false, sampling: 'lttb', lineStyle: { width: 1.3, color: t.accent },
      markArea: { silent: true, itemStyle: { color: t.amber, opacity: 0.1 }, data: [[{ xAxis: stream.event[0] }, { xAxis: stream.event[1] }]] },
      markLine: idx > 0 && idx < N ? { silent: true, symbol: 'none', lineStyle: { color: t.accent, width: 1, opacity: 0.5 }, data: [{ xAxis: Math.min(idx, N - 1) }] } : undefined,
    }],
  }
}

function DetTable({ rows }) {
  const types = P2_TYPES.filter((ty) => rows.some((r) => r.by_type_det && ty in r.by_type_det))
  const colMax = {}
  types.forEach((ty) => { colMax[ty] = Math.max(...rows.map((r) => r.by_type_det?.[ty] ?? 0)) })
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr>
          <th>detector</th>
          {types.map((ty) => <th key={ty} style={{ textAlign: 'right' }}>{ty.replace('_', ' ')}</th>)}
          <th style={{ textAlign: 'right' }}>best detect</th>
          <th style={{ textAlign: 'right' }}>mean FPR</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.detector}>
              <td className="mono" style={{ fontWeight: 600 }}>{r.detector}</td>
              {types.map((ty) => {
                const v = r.by_type_det?.[ty]; const win = v != null && v === colMax[ty]
                return <td key={ty} className="mono" style={{ textAlign: 'right', color: win ? 'var(--accent)' : 'var(--fg-muted)', fontWeight: win ? 600 : 400 }}>{fmt(v)}</td>
              })}
              <td className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(r.det_best)}</td>
              <td className="mono" style={{ textAlign: 'right', color: r.fpr_mean > 0.1 ? 'var(--red)' : 'var(--fg-muted)' }}>{fmt(r.fpr_mean, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const Stat = ({ n, l, cls }) => (
  <div className="card stat accent-top"><div className={'n ' + (cls || '')}>{n}</div><div className="l">{l}</div></div>
)
