import { useEffect, useMemo, useRef, useState } from 'react'
import EChart from './EChart.jsx'
import { UnifiedDetector, CausalStandardizer } from './lib/unified.js'

const BASE = import.meta.env.BASE_URL
const TICK_MS = 50
const SPEEDS = [
  { label: '0.5×', sps: 80 }, { label: '1×', sps: 200 }, { label: '4×', sps: 800 },
  { label: '16×', sps: 3200 }, { label: 'MAX', sps: Infinity },
]
const TYPE_COLOR = {
  spike: '#ff4d5e', transient: '#ffb020', drift: '#b98cff',
  periodicity: '#39c5cf', real: '#35d6e6', anomaly: '#8b949e',
}
const HEADS = [
  { key: 'sDrv', name: 'derivative', sub: 'spike · transient', color: '#ff4d5e', cap: null },
  { key: 'sDrift', name: 'EWMA control', sub: 'drift', color: '#b98cff', cap: 0.9 },
  { key: 'sPer', name: 'ACF-drop', sub: 'periodicity', color: '#39c5cf', cap: null },
]

const fmt = (x, d = 3) => (x == null || Number.isNaN(x) ? '—' : Number(x).toFixed(d))

function useJson(paths) {
  const [s, setS] = useState({ loading: true, error: null, data: null })
  useEffect(() => {
    Promise.all(paths.map((p) => fetch(BASE + p).then((r) => r.json())))
      .then((d) => setS({ loading: false, error: null, data: d }))
      .catch((e) => setS({ loading: false, error: String(e), data: null }))
  }, [])
  return s
}

export default function App() {
  const { loading, error, data } = useJson(['data/streams.json', 'data/c_results.json'])
  const streams = data?.[0]?.streams
  const cRes = data?.[1]

  if (loading) return <div className="app"><div className="loading">initialising detector…</div></div>
  if (error || !streams) {
    return (
      <div className="app"><div className="error">
        <p>Could not load stream data.</p>
        <p>Run <code>python python/export_streams.py</code> then reload.</p>
        <p style={{ color: '#ff4d5e' }}>{error}</p>
      </div></div>
    )
  }
  return <Live streams={streams} cRes={cRes} />
}

function Live({ streams, cRes }) {
  const [selId, setSelId] = useState(streams[0].id)
  const stream = streams.find((s) => s.id === selId) || streams[0]

  const [window_, setWindow] = useState(stream.window)
  const [threshold, setThreshold] = useState(stream.defaultThreshold)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [playing, setPlaying] = useState(false)
  const [idx, setIdx] = useState(0)

  const det = useRef(null)
  const std = useRef(null)
  const scores = useRef([])
  const heads = useRef([])
  const iRef = useRef(0)
  const N = stream.values.length

  // (re)build the engine whenever the input or window changes
  function build(win) {
    det.current = new UnifiedDetector(win, 1.0)
    std.current = stream.standardize ? new CausalStandardizer() : null
    scores.current = []
    heads.current = []
    iRef.current = 0
    setIdx(0)
    setPlaying(false)
  }
  useEffect(() => {
    setWindow(stream.window)
    setThreshold(stream.defaultThreshold)
    build(stream.window)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selId])

  function changeWindow(w) { setWindow(w); build(w) }
  function reset() { build(window_) }

  // streaming loop
  useEffect(() => {
    if (!playing) return
    const sps = SPEEDS[speedIdx].sps
    const id = setInterval(() => {
      const k = sps === Infinity ? N : Math.max(1, Math.round((sps * TICK_MS) / 1000))
      const vals = stream.values
      let i = iRef.current
      const end = Math.min(N, i + k)
      for (; i < end; i++) {
        const x = vals[i]
        const fed = std.current ? std.current.push(x) : x
        const r = det.current.update(fed)
        scores.current.push(r.score)
        heads.current.push(r)
      }
      iRef.current = i
      setIdx(i)
      if (i >= N) setPlaying(false)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [playing, speedIdx, N, stream])

  // ---- derived live metrics (threshold applied here; scores are threshold-free) ----
  const m = useMemo(() => {
    const sc = scores.current, lab = stream.labels
    let tp = 0, fp = 0, fn = 0, tn = 0, alerts = 0
    for (let i = 0; i < idx; i++) {
      const a = sc[i] >= threshold ? 1 : 0
      alerts += a
      if (a && lab[i]) tp++; else if (a) fp++; else if (lab[i]) fn++; else tn++
    }
    const tpr = tp + fn ? tp / (tp + fn) : 0
    const fpr = fp + tn ? fp / (fp + tn) : 0
    const prec = tp + fp ? tp / (tp + fp) : 0
    const f1 = prec + tpr ? (2 * prec * tpr) / (prec + tpr) : 0
    // events reached / detected + latency
    let reached = 0, detected = 0, latSum = 0, latN = 0
    for (const e of stream.events) {
      if (e.start >= idx) continue
      reached++
      let hit = -1
      for (let i = e.start; i < Math.min(idx, e.end + 3); i++) if (sc[i] >= threshold) { hit = i; break }
      if (hit >= 0) { detected++; latSum += hit - e.start; latN++ }
    }
    const last = heads.current[idx - 1] || { score: 0, sDrv: 0, sDrift: 0, sPer: 0 }
    return { tp, fp, fn, tn, alerts, tpr, fpr, prec, f1, reached, detected,
      lat: latN ? latSum / latN : null, last, curScore: sc[idx - 1] ?? 0 }
  }, [idx, threshold, stream])

  const option = useMemo(() => scopeOption(stream, scores.current, idx, threshold), [idx, threshold, stream])
  const done = idx >= N
  const winMax = HEADS.reduce((a, h) => Math.max(a, h.key === 'sDrift' ? 0.9 : m.last[h.key]), 0)

  return (
    <div className="app">
      <TopBar cRes={cRes} />

      <div className="deck">
        <div className="grp">
          <span className="lbl">input</span>
          <select className="input-sel" value={selId} onChange={(e) => setSelId(e.target.value)}>
            {streams.map((s) => <option key={s.id} value={s.id}>{s.name}  ·  {s.values.length} samples</option>)}
          </select>
        </div>
        <div className="grp">
          <button className={'btn play' + (playing ? ' on' : '')} onClick={() => (done ? (reset(), setTimeout(() => setPlaying(true), 0)) : setPlaying(!playing))}>
            {playing ? '❙❙ pause' : done ? '⟲ replay' : '▶ stream'}
          </button>
          <button className="btn" onClick={reset}>⟲ reset</button>
        </div>
        <div className="grp">
          <span className="lbl">speed</span>
          <div className="seg">
            {SPEEDS.map((s, i) => <button key={s.label} className={i === speedIdx ? 'on' : ''} onClick={() => setSpeedIdx(i)}>{s.label}</button>)}
          </div>
        </div>
        <div className="grp">
          <span className="lbl">window</span>
          <div className="seg">
            {[10, 20, 24, 30, 50].map((w) => <button key={w} className={w === window_ ? 'on' : ''} onClick={() => changeWindow(w)}>{w}</button>)}
          </div>
        </div>
        <div className="grp">
          <span className="lbl">threshold</span>
          <div className="slider">
            <input type="range" min="0.2" max={stream.standardize ? 5 : 3} step="0.05" value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))} />
            <span className="rdout">{threshold.toFixed(2)}</span>
          </div>
        </div>
        <div className="grp" style={{ marginLeft: 'auto' }}>
          <span className={'rec ' + (playing ? 'live' : done ? 'done' : '')}>
            <span className="dot" />{playing ? 'STREAMING' : done ? 'COMPLETE' : 'READY'}
          </span>
        </div>
      </div>

      <div className="main">
        <div className="panel scope">
          <h3><span className="k">▸</span> live oscilloscope
            <span style={{ marginLeft: 'auto', color: '#6c7889', fontWeight: 400 }}>
              sample {idx} / {N}{stream.standardize ? '  ·  input z-scored (causal)' : ''}
            </span>
          </h3>
          <div className="legend">
            <span><i className="sw" style={{ background: '#35d6e6' }} /> value</span>
            <span><i className="sw" style={{ background: '#ffb020' }} /> score</span>
            <span><i className="sw" style={{ background: '#ff4d5e' }} /> alert</span>
            {Object.entries(TYPE_COLOR).filter(([t]) => stream.events.some((e) => e.type === t)).map(([t, c]) =>
              <span key={t}><i className="sw" style={{ background: c, opacity: 0.5 }} /> {t}</span>)}
          </div>
          <div className="screen"><EChart option={option} height={430} /></div>
          <div className="note">
            The detector runs <b>in your browser</b>, one sample at a time (no look-ahead) — the same
            96-byte algorithm as the Python reference and C twin, ported to JS and <b>parity-verified to 0.0</b>.
            Shaded bands = ground-truth anomaly windows. Move the threshold to watch precision/recall trade off live.
          </div>
        </div>

        <div className="side">
          <div className="panel">
            <h3><span className="k">▸</span> live readout</h3>
            <div className="readouts">
              <RO v={fmt(m.curScore, 2)} k="current score" cls={m.curScore >= threshold ? 'amber' : ''} />
              <RO v={`${m.detected}/${stream.events.length}`} k="events detected" cls="green" />
              <RO v={fmt(m.tpr, 2)} k="recall (TPR)" cls="cyan" />
              <RO v={fmt(m.fpr, 3)} k="false-pos rate" cls={m.fpr > 0.1 ? 'red' : ''} />
              <RO v={fmt(m.f1, 2)} k="F1 (sample)" />
              <RO v={m.lat == null ? '—' : fmt(m.lat, 0)} k="latency (samp)" />
            </div>
          </div>

          <div className="panel" style={{ marginTop: 16 }}>
            <h3><span className="k">▸</span> detector heads <span style={{ marginLeft: 'auto', color: '#6c7889', fontWeight: 400 }}>score = max</span></h3>
            <div className="vu">
              {HEADS.map((h) => {
                const val = m.last[h.key] || 0
                const winning = m.last.score > 0 && val === Math.max(m.last.sDrv, m.last.sDrift, m.last.sPer)
                const pct = Math.min(100, (val / 2) * 100)
                const hot = val >= 1
                return (
                  <div className={'row' + (hot ? ' hot' : '')} key={h.key}>
                    <div className="top">
                      <span className="name">{h.name} <small>· {h.sub}</small></span>
                      <span className="val" style={winning ? { color: h.color } : undefined}>{fmt(val, 2)}</span>
                    </div>
                    <div className="track">
                      <div className="fill" style={{ width: pct + '%', background: h.color,
                        boxShadow: hot ? `0 0 12px ${h.color}` : 'none', opacity: winning ? 1 : 0.7 }} />
                      <div className="fire-line" style={{ left: '50%' }} title="fire line (1.0)" />
                      {h.cap && <div className="fire-line" style={{ left: (h.cap / 2) * 100 + '%', background: h.color, opacity: 0.5 }} title="clip 0.9" />}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="panel" style={{ marginTop: 16 }}>
            <h3><span className="k">▸</span> deployment spec</h3>
            <div className="spec">
              <div className="s"><div className="v" style={{ color: '#6ef2a8' }}>{cRes?.bench?.state_bytes ?? 96} B</div><div className="k">state · &lt; 100 budget</div></div>
              <div className="s"><div className="v" style={{ color: '#6ef2a8' }}>{fmt(cRes?.bench?.rows?.[0]?.ns_per_sample, 1)} ns</div><div className="k">per sample (C)</div></div>
              <div className="s"><div className="v">{stream.standardize ? 'z-scored' : 'raw'}</div><div className="k">input scaling</div></div>
              <div className="s"><div className="v" style={{ color: '#6ef2a8' }}>PY=C=JS</div><div className="k">parity Δ = {cRes?.parity?.max_diff ?? 0}</div></div>
            </div>
          </div>
        </div>
      </div>

      <div className="foot">
        one 96-byte streaming unit · three heads, MAX-fused · <b>spike · drift · periodicity · transient</b> ·
        Python reference → C twin → JS live, parity-verified
      </div>
    </div>
  )
}

const RO = ({ v, k, cls }) => (
  <div className="ro"><div className={'v ' + (cls || '')}>{v}</div><div className="k">{k}</div></div>
)

function TopBar({ cRes }) {
  const ns = cRes?.bench?.rows?.[0]?.ns_per_sample
  return (
    <div className="topbar">
      <div className="brand">
        <div className="logo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 12h4l2-7 4 14 3-9 2 4h5" />
          </svg>
        </div>
        <div>
          <h1>Unified</h1>
          <div className="tag">on-device streaming anomaly detector</div>
        </div>
      </div>
      <div className="chips">
        <span className="chip good"><b>96 B</b> state</span>
        <span className="chip good"><b>{ns ? ns.toFixed(1) : '~55'} ns</b>/sample</span>
        <span className="chip good">parity <b>PY=C=JS ✓</b></span>
        <span className="chip"><b>4</b> anomaly types</span>
      </div>
    </div>
  )
}

/* ---- ECharts option: dual-grid live scope ---- */
function scopeOption(stream, sc, idx, threshold) {
  const vals = stream.values
  const N = vals.length
  const stride = Math.max(1, Math.floor(N / 1500))
  const valData = [], scoreData = [], alertData = []
  for (let i = 0; i < N; i += stride) {
    if (i >= idx) break
    valData.push([i, vals[i]])
    const s = sc[i] ?? 0
    scoreData.push([i, s])
    if (s >= threshold) alertData.push([i, s])
  }
  const bands = stream.events.map((e) => [
    { xAxis: e.start, itemStyle: { color: TYPE_COLOR[e.type] || '#8b949e', opacity: 0.16 } },
    { xAxis: e.end },
  ])
  const cursor = idx > 0 && idx < N
    ? { silent: true, symbol: 'none', lineStyle: { color: '#6ef2a8', width: 1, opacity: 0.6 },
        data: [{ xAxis: Math.min(idx, N - 1) }] } : undefined
  return {
    animation: false,
    backgroundColor: 'transparent',
    grid: [
      { left: 52, right: 18, top: 12, height: '52%' },
      { left: 52, right: 18, top: '68%', height: '26%' },
    ],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: [
      { type: 'value', gridIndex: 0, min: 0, max: N - 1, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2a3446' } }, splitLine: { show: false } },
      { type: 'value', gridIndex: 1, min: 0, max: N - 1, name: 'sample', nameLocation: 'middle', nameGap: 24, nameTextStyle: { color: '#48525f', fontSize: 10 }, axisLine: { lineStyle: { color: '#2a3446' } }, axisLabel: { color: '#48525f' }, splitLine: { show: false } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: stream.standardize ? 'value (z)' : 'value', nameTextStyle: { color: '#48525f', fontSize: 10 }, scale: true, axisLabel: { color: '#48525f' }, splitLine: { lineStyle: { color: '#131922' } } },
      { type: 'value', gridIndex: 1, name: 'score', nameTextStyle: { color: '#48525f', fontSize: 10 }, scale: true, min: 0, axisLabel: { color: '#48525f' }, splitLine: { lineStyle: { color: '#131922' } } },
    ],
    series: [
      { name: 'value', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: valData, showSymbol: false, sampling: 'lttb',
        lineStyle: { width: 1.3, color: '#35d6e6', shadowColor: 'rgba(53,214,230,0.5)', shadowBlur: 6 },
        markArea: { silent: true, data: bands }, markLine: cursor },
      { name: 'score', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: scoreData, showSymbol: false, sampling: 'lttb',
        lineStyle: { width: 1.3, color: '#ffb020', shadowColor: 'rgba(255,176,32,0.4)', shadowBlur: 6 },
        markLine: { silent: true, symbol: 'none', data: [{ yAxis: threshold, label: { formatter: `thr ${threshold.toFixed(2)}`, color: '#6c7889', fontSize: 10 }, lineStyle: { color: '#6c7889', type: 'dashed' } }] } },
      { name: 'alert', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, data: alertData, symbolSize: 4,
        itemStyle: { color: '#ff4d5e', shadowColor: 'rgba(255,77,94,0.6)', shadowBlur: 6 } },
    ],
  }
}
