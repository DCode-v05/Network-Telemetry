import { useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import EChart, { themeColors } from '../components/EChart.jsx'
import { UnifiedDetector, CausalStandardizer } from '../lib/unified.js'
import { useJson } from '../lib/useJson.js'

const TICK_MS = 50
const SPEEDS = [{ label: '0.5×', sps: 80 }, { label: '1×', sps: 200 }, { label: '4×', sps: 800 }, { label: '16×', sps: 3200 }, { label: 'MAX', sps: Infinity }]
const TYPE_COLOR = { spike: '#e5484d', transient: '#b45309', drift: '#7c3aed', periodicity: '#0891b2', real: '#0891b2', anomaly: '#8f8f8f' }
const HEADS = [
  { key: 'sDrv', name: 'derivative', sub: 'spike · transient', color: '#e5484d', cap: null },
  { key: 'sDrift', name: 'EWMA control', sub: 'drift', color: '#7c3aed', cap: 0.9 },
  { key: 'sPer', name: 'ACF-drop', sub: 'periodicity', color: '#0891b2', cap: null },
]
const ENGINE_URL = 'http://localhost:8008'
const ENGINES = [
  { id: 'js', label: 'JS', note: 'in-browser' },
  { id: 'python', label: 'Python', note: 'server' },
  { id: 'c', label: 'C', note: 'server' },
]
const fmt = (x, d = 3) => (x == null || Number.isNaN(x) ? '—' : Number(x).toFixed(d))

export default function LivePipeline() {
  const { theme } = useOutletContext()
  const { loading, error, data } = useJson(['data/streams.json', 'data/c_results.json'])
  if (loading) return <div className="page"><div className="loading">loading streams…</div></div>
  if (error) return <div className="page"><div className="error">missing <code>streams.json</code> — run <code>python python/export_streams.py</code></div></div>
  return <Engine streams={data[0].streams} cRes={data[1]} theme={theme} />
}

function Engine({ streams, cRes, theme }) {
  const [selId, setSelId] = useState(streams[0].id)
  const stream = streams.find((s) => s.id === selId) || streams[0]
  const [engine, setEngine] = useState('js')
  const [window_, setWindow] = useState(stream.window)
  const [threshold, setThreshold] = useState(stream.defaultThreshold)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [playing, setPlaying] = useState(false)
  const [idx, setIdx] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)   // bump to re-attempt the engine (retry without refresh)
  const [prep, setPrep] = useState({ ready: false, loading: false, error: null, elapsed: null, down: false })

  const det = useRef(null), std = useRef(null), scores = useRef([]), heads = useRef([]), iRef = useRef(0)
  const N = stream.values.length

  // reset defaults when the input changes
  useEffect(() => { setWindow(stream.window); setThreshold(stream.defaultThreshold) /* eslint-disable-next-line */ }, [selId])

  // prepare the run whenever input / engine / window / retry changes.
  // For Python/C we ALWAYS re-attempt the server here, so selecting the engine
  // again after starting the server just works — no page refresh needed.
  useEffect(() => {
    let cancelled = false
    scores.current = []; heads.current = []; iRef.current = 0; setIdx(0); setPlaying(false)
    if (engine === 'js') {
      det.current = new UnifiedDetector(window_, 1.0)
      std.current = stream.standardize ? new CausalStandardizer() : null
      setPrep({ ready: true, loading: false, error: null, elapsed: null, down: false })
      return () => { cancelled = true }
    }
    setPrep((p) => ({ ...p, ready: false, loading: true, error: null, down: false }))
    fetch(`${ENGINE_URL}/api/run?stream=${selId}&window=${window_}&lang=${engine}`)
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (cancelled) return
        if (!ok) throw new Error(d.error || 'engine error')
        scores.current = d.scores
        heads.current = d.heads.map((h) => ({ score: 0, sDrv: h[0], sDrift: h[1], sPer: h[2] }))
        setPrep({ ready: true, loading: false, error: null, elapsed: d.elapsed_ms, down: false })
      })
      .catch((e) => {
        if (cancelled) return
        const netFail = e instanceof TypeError   // "Failed to fetch" == server unreachable
        setPrep({ ready: false, loading: false, elapsed: null, down: netFail, error: netFail ? null : String(e.message || e) })
      })
    return () => { cancelled = true }
    // eslint-disable-next-line
  }, [selId, engine, window_, reloadKey])

  const reset = () => { scores.current = engine === 'js' ? [] : scores.current; iRef.current = 0; setIdx(0); setPlaying(false); if (engine === 'js') { det.current = new UnifiedDetector(window_, 1.0); std.current = stream.standardize ? new CausalStandardizer() : null; scores.current = []; heads.current = [] } }

  useEffect(() => {
    if (!playing) return
    const sps = SPEEDS[speedIdx].sps
    const id = setInterval(() => {
      const k = sps === Infinity ? N : Math.max(1, Math.round((sps * TICK_MS) / 1000))
      let i = iRef.current
      const end = Math.min(N, i + k)
      if (engine === 'js') {
        const vals = stream.values
        for (; i < end; i++) {
          const x = vals[i]; const fed = std.current ? std.current.push(x) : x
          const r = det.current.update(fed); scores.current.push(r.score); heads.current.push(r)
        }
      } else { i = end }
      iRef.current = i; setIdx(i); if (i >= N) setPlaying(false)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [playing, speedIdx, N, stream, engine])

  const m = useMemo(() => {
    const sc = scores.current, lab = stream.labels
    let tp = 0, fp = 0, fn = 0, tn = 0, alerts = 0
    for (let i = 0; i < idx; i++) { const a = sc[i] >= threshold ? 1 : 0; alerts += a; if (a && lab[i]) tp++; else if (a) fp++; else if (lab[i]) fn++; else tn++ }
    const tpr = tp + fn ? tp / (tp + fn) : 0, fpr = fp + tn ? fp / (fp + tn) : 0
    const prec = tp + fp ? tp / (tp + fp) : 0, f1 = prec + tpr ? (2 * prec * tpr) / (prec + tpr) : 0
    let detected = 0, latSum = 0, latN = 0
    for (const e of stream.events) {
      if (e.start >= idx) continue
      let hit = -1; for (let i = e.start; i < Math.min(idx, e.end + 3); i++) if (sc[i] >= threshold) { hit = i; break }
      if (hit >= 0) { detected++; latSum += hit - e.start; latN++ }
    }
    const last = heads.current[idx - 1] || { score: 0, sDrv: 0, sDrift: 0, sPer: 0 }
    return { alerts, tpr, fpr, f1, detected, lat: latN ? latSum / latN : null, last, curScore: sc[idx - 1] ?? 0 }
  }, [idx, threshold, stream])

  const option = useMemo(() => scopeOption(stream, scores.current, idx, threshold), [idx, threshold, stream, theme.resolved])
  const done = idx >= N
  const engineBusy = prep.loading
  const canPlay = prep.ready && !engineBusy

  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">live pipeline · run it in Python, C, or JS</div>
        <h1>Stream a signal <span className="hero-underline">through the detector</span></h1>
        <p>Pick an input <b>and an engine</b>, then hit stream. JS runs in your browser; Python and C run on the
          local engine server — same 96-byte algorithm, parity-verified (Δ = 0), so every engine gives the same
          result. Drag the threshold to watch precision and recall trade off live.</p>
      </div>

      <div className="deck-row">
        <div className="grp">
          <span className="lbl">input</span>
          <select className="sel" value={selId} onChange={(e) => setSelId(e.target.value)}>
            {streams.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.values.length} samples</option>)}
          </select>
        </div>
        <div className="grp">
          <span className="lbl">engine</span>
          <div className="seg">
            {ENGINES.map((e) => (
              <button key={e.id} className={engine === e.id ? 'on' : ''} title={e.note}
                onClick={() => { setEngine(e.id); setReloadKey((k) => k + 1) }}>{e.label}</button>
            ))}
          </div>
        </div>
        <div className="grp"><span className="lbl">speed</span>
          <div className="seg">{SPEEDS.map((s, i) => <button key={s.label} className={i === speedIdx ? 'on' : ''} onClick={() => setSpeedIdx(i)}>{s.label}</button>)}</div>
        </div>
        <div className="grp">
          <button className="btn primary" disabled={!canPlay}
            onClick={() => (done ? (reset(), setTimeout(() => setPlaying(true), 0)) : setPlaying(!playing))}>
            {playing ? '❙❙ Pause' : done ? '⟲ Replay' : '▶ Stream'}
          </button>
          <button className="btn" onClick={reset}>Reset</button>
        </div>
        <div className="grp"><span className="lbl">window</span>
          <div className="seg">{[10, 20, 24, 30, 50].map((w) => <button key={w} className={w === window_ ? 'on' : ''} onClick={() => setWindow(w)}>{w}</button>)}</div>
        </div>
        <div className="grp"><span className="lbl">threshold</span>
          <input type="range" min="0.2" max={stream.standardize ? 5 : 3} step="0.05" value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value))} />
          <span className="mono" style={{ color: 'var(--accent)', minWidth: 38 }}>{threshold.toFixed(2)}</span>
        </div>
        <div className="grp" style={{ marginLeft: 'auto' }}>
          <span className={'rec ' + (playing ? 'live' : done ? 'done' : canPlay ? '' : 'notready')}>
            <span className="d" />
            {playing ? 'STREAMING' : done ? 'COMPLETE' : engineBusy ? 'PREPARING' : canPlay ? 'READY' : 'NOT READY'}
          </span>
        </div>
      </div>

      {engine !== 'js' && prep.down && (
        <div className="callout" style={{ marginBottom: 16, borderLeftColor: 'var(--amber)' }}>
          <b>Engine server not running.</b> To execute in Python or C, start it from <span className="mono">Final Pipeline</span>:
          <span className="mono" style={{ color: 'var(--accent)' }}> python server.py</span> — then click <b>{engine.toUpperCase()}</b> again (no refresh needed). JS runs without it.
        </div>
      )}
      {prep.error && <div className="callout" style={{ marginBottom: 16, borderLeftColor: 'var(--red)' }}><b>Engine error:</b> <span className="mono">{prep.error}</span></div>}

      <div className="live-grid">
        <div className="card pad0">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
            <span className="mono" style={{ fontSize: 12, color: 'var(--fg-muted)' }}>sample {idx} / {N}</span>
            <div style={{ display: 'flex', gap: 12, marginLeft: 'auto', flexWrap: 'wrap', fontSize: 11, color: 'var(--fg-muted)' }}>
              <span><i style={{ background: 'var(--accent)', width: 10, height: 10, borderRadius: 3, display: 'inline-block', marginRight: 5 }} />value</span>
              <span><i style={{ background: 'var(--amber)', width: 10, height: 10, borderRadius: 3, display: 'inline-block', marginRight: 5 }} />score</span>
              <span><i style={{ background: 'var(--red)', width: 10, height: 10, borderRadius: 3, display: 'inline-block', marginRight: 5 }} />alert</span>
            </div>
          </div>
          <div style={{ padding: 8 }}><EChart option={option} height={420} themeKey={theme.resolved} /></div>
        </div>

        <div>
          <div className="card">
            <div className="section-title" style={{ margin: '0 0 12px' }}>Live readout</div>
            <div className="ro-grid">
              <RO v={fmt(m.curScore, 2)} k="current score" c={m.curScore >= threshold ? 'var(--amber)' : 'var(--fg)'} />
              <RO v={`${m.detected}/${stream.events.length}`} k="events detected" c="var(--green)" />
              <RO v={fmt(m.tpr, 2)} k="recall" c="var(--cyan)" />
              <RO v={fmt(m.fpr, 3)} k="false-pos rate" c={m.fpr > 0.1 ? 'var(--red)' : 'var(--fg)'} />
              <RO v={fmt(m.f1, 2)} k="F1 (sample)" c="var(--fg)" />
              <RO v={m.lat == null ? '—' : fmt(m.lat, 0)} k="latency (samp)" c="var(--fg)" />
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="section-title" style={{ margin: '0 0 8px' }}>Detector heads <span style={{ color: 'var(--fg-subtle)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>· score = max</span></div>
            {HEADS.map((h) => {
              const val = m.last[h.key] || 0
              const winning = m.last.score > 0 && val === Math.max(m.last.sDrv, m.last.sDrift, m.last.sPer)
              return (
                <div className="vu-row" key={h.key}>
                  <div className="vu-top">
                    <span className="nm">{h.name} <small>· {h.sub}</small></span>
                    <span className="mono" style={{ color: winning ? h.color : 'var(--fg-muted)' }}>{fmt(val, 2)}</span>
                  </div>
                  <div className="vu-track">
                    <div className="vu-fill" style={{ width: Math.min(100, (val / 2) * 100) + '%', background: h.color, opacity: winning ? 1 : 0.55 }} />
                    <div className="vu-mark" style={{ left: '50%' }} title="fire line 1.0" />
                    {h.cap && <div className="vu-mark" style={{ left: (h.cap / 2) * 100 + '%', background: h.color }} title="clip 0.9" />}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <div className="section-title" style={{ margin: '0 0 10px' }}>Deployment</div>
            <div className="grid g2" style={{ gap: 10 }}>
              <Mini v={`${cRes?.bench?.state_bytes ?? 96} B`} k="state < 100" c="var(--green)" />
              <Mini v={`${fmt(cRes?.bench?.rows?.[0]?.ns_per_sample, 1)} ns`} k="per sample (C)" c="var(--green)" />
              <Mini v={engine.toUpperCase()} k={prep.elapsed != null ? `ran in ${prep.elapsed} ms` : 'execution engine'} c={engine === 'js' ? 'var(--accent)' : 'var(--green)'} />
              <Mini v="PY=C=JS" k={`parity Δ ${cRes?.parity?.max_diff ?? 0}`} c="var(--accent)" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const RO = ({ v, k, c }) => <div className="ro-cell"><div className="v" style={{ color: c }}>{v}</div><div className="k">{k}</div></div>
const Mini = ({ v, k, c }) => <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '10px 11px', background: 'var(--bg-subtle)' }}><div className="mono" style={{ fontSize: 15, color: c || 'var(--fg)' }}>{v}</div><div style={{ fontSize: 10.5, color: 'var(--fg-muted)', marginTop: 1 }}>{k}</div></div>

function scopeOption(stream, sc, idx, threshold) {
  const t = themeColors()
  const vals = stream.values, N = vals.length
  const stride = Math.max(1, Math.floor(N / 1500))
  const valData = [], scoreData = [], alertData = []
  for (let i = 0; i < N; i += stride) {
    if (i >= idx) break
    valData.push([i, vals[i]]); const s = sc[i] ?? 0; scoreData.push([i, s]); if (s >= threshold) alertData.push([i, s])
  }
  const cursor = idx > 0 && idx < N ? { silent: true, symbol: 'none', lineStyle: { color: t.accent, width: 1, opacity: 0.5 }, data: [{ xAxis: Math.min(idx, N - 1) }] } : undefined
  const ax = { axisLine: { lineStyle: { color: t.border } }, axisLabel: { color: t.subtle }, splitLine: { lineStyle: { color: t.border, opacity: 0.5 } } }
  return {
    animation: false, backgroundColor: 'transparent',
    grid: [{ left: 52, right: 16, top: 12, height: '52%' }, { left: 52, right: 16, top: '68%', height: '26%' }],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: t.bg, borderColor: t.border, textStyle: { color: t.fg, fontSize: 11 } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: [
      { type: 'value', gridIndex: 0, min: 0, max: N - 1, ...ax, axisLabel: { show: false }, splitLine: { show: false } },
      { type: 'value', gridIndex: 1, min: 0, max: N - 1, name: 'sample', nameLocation: 'middle', nameGap: 24, nameTextStyle: { color: t.subtle, fontSize: 10 }, ...ax, splitLine: { show: false } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: 'value', nameTextStyle: { color: t.subtle, fontSize: 10 }, scale: true, ...ax },
      { type: 'value', gridIndex: 1, name: 'score', nameTextStyle: { color: t.subtle, fontSize: 10 }, scale: true, min: 0, ...ax },
    ],
    series: [
      { name: 'value', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: valData, showSymbol: false, sampling: 'lttb', lineStyle: { width: 1.4, color: t.accent }, markLine: cursor },
      { name: 'score', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: scoreData, showSymbol: false, sampling: 'lttb', lineStyle: { width: 1.4, color: t.amber }, markLine: { silent: true, symbol: 'none', data: [{ yAxis: threshold, label: { formatter: `thr ${threshold.toFixed(2)}`, color: t.subtle, fontSize: 10 }, lineStyle: { color: t.subtle, type: 'dashed' } }] } },
      { name: 'alert', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, data: alertData, symbolSize: 4, itemStyle: { color: t.red } },
    ],
  }
}
