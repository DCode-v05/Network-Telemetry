import { useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import EChart, { themeColors } from '../components/EChart.jsx'
import { UnifiedDetector, CausalStandardizer } from '../lib/unified.js'
import { useJson } from '../lib/useJson.js'

const TICK_MS = 50
const SPEEDS = [{ label: '0.5×', sps: 80 }, { label: '1×', sps: 200 }, { label: '4×', sps: 800 }, { label: '16×', sps: 3200 }, { label: 'MAX', sps: Infinity }]
const HEADS = [
  { key: 'sDrv', name: 'derivative', sub: 'spike · transient', color: '#e5484d', cap: null },
  { key: 'sDrift', name: 'EWMA control', sub: 'drift', color: '#7c3aed', cap: 0.9 },
  { key: 'sPer', name: 'ACF-drop', sub: 'periodicity', color: '#0891b2', cap: null },
]
const ENGINE_URL = 'http://localhost:8008'
const ENGINES = [{ id: 'js', label: 'JS' }, { id: 'python', label: 'Python' }, { id: 'c', label: 'C' }]
const LIVE_STREAMS = [
  { id: '__device', name: 'My device', kind: 'live', source: 'device', standardize: true, defaultThreshold: 2.0 },
  { id: '__ip', name: 'Any network', kind: 'live', source: 'ip', standardize: true, defaultThreshold: 2.0 },
]
const MAX_LIVE = 2000
// one dataset per type, kept short
const CATEGORIES = [
  { id: 'clean', label: '① Clean · no anomalies', note: 'A normal baseline with nothing injected. The score should stay below the line, so no false alarms.' },
  { id: 'injected', label: '② Injected anomalies', note: 'Anomalies we injected at known spots, so every alert can be checked against the truth.' },
  { id: 'real', label: '③ Real telemetry', note: 'Real recorded NAB telemetry with genuine, labelled failures. Nothing here is injected.' },
]
const catOf = (s) => CATEGORIES.find((c) => c.id === (s.category || 'injected'))
const fmt = (x, d = 3) => (x == null || Number.isNaN(x) ? '·' : Number(x).toFixed(d))
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)
// short display name: drop anything after a dash or parenthesis
const shortName = (s) => s.name.split(/[—–(]/)[0].trim()

export default function LivePipeline({ embed = false, defaultInput } = {}) {
  const { theme } = useOutletContext()
  const { loading, error, data } = useJson(['data/streams.json'])
  if (loading) return <div className={embed ? '' : 'page'}><div className="loading">loading streams…</div></div>
  if (error) return <div className={embed ? '' : 'page'}><div className="error">missing <code>streams.json</code>, run <code>python python/export_streams.py</code></div></div>
  return <Engine streams={[...data[0].streams, ...LIVE_STREAMS]} theme={theme} embed={embed} defaultInput={defaultInput} />
}

function Engine({ streams, theme, embed, defaultInput }) {
  const [selId, setSelId] = useState(() => (defaultInput && streams.find((s) => s.id === defaultInput) ? defaultInput : streams[0].id))
  const stream = streams.find((s) => s.id === selId) || streams[0]
  const isLive = stream.kind === 'live'
  const [engine, setEngine] = useState('js')
  const [window_, setWindow] = useState(stream.window || 24)
  const [threshold, setThreshold] = useState(stream.defaultThreshold)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [playing, setPlaying] = useState(false)
  const [idx, setIdx] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)
  const [prep, setPrep] = useState({ ready: false, loading: false, error: null, elapsed: null, down: false })
  // live
  const [health, setHealth] = useState(undefined)
  const [ipInput, setIpInput] = useState('')
  const [ping, setPing] = useState(null)
  const [capturing, setCapturing] = useState(false)
  const [liveLen, setLiveLen] = useState(0)
  const [liveMeta, setLiveMeta] = useState(null)

  const scores = useRef([]), heads = useRef([]), iRef = useRef(0)
  const liveValues = useRef([]), loopActive = useRef(false)
  const sessionRef = useRef(null), liveDet = useRef(null), liveStd = useRef(null)
  const engineRef = useRef(engine), windowRef = useRef(window_), ipRef = useRef(ipInput), sourceRef = useRef(stream.source)
  useEffect(() => { engineRef.current = engine }, [engine])
  useEffect(() => { windowRef.current = window_ }, [window_])
  useEffect(() => { ipRef.current = ipInput }, [ipInput])
  useEffect(() => { sourceRef.current = stream.source }, [selId, stream.source])
  useEffect(() => () => { loopActive.current = false; const sid = sessionRef.current; if (sid) fetch(`${ENGINE_URL}/api/live/stop?session=${sid}`).catch(() => {}) }, [])

  const dispValues = isLive ? liveValues.current : stream.values
  const N = isLive ? liveLen : stream.values.length

  // probe health when a live stream is selected (device IP + server status)
  useEffect(() => {
    if (!isLive) return
    let live = true
    setHealth(undefined)
    fetch(ENGINE_URL + '/api/health').then((r) => r.json()).then((d) => live && setHealth(d)).catch(() => live && setHealth(false))
    return () => { live = false }
  }, [selId, isLive])

  // stop any capture + clear live state on input change
  useEffect(() => {
    stopCapture()
    liveValues.current = []; scores.current = []; heads.current = []; iRef.current = 0
    setLiveLen(0); setIdx(0); setLiveMeta(null); setPing(null); setPlaying(false)
    setWindow(stream.window || 24); setThreshold(stream.defaultThreshold)
    // eslint-disable-next-line
  }, [selId])

  // changing engine or window during a live capture needs a fresh session
  useEffect(() => {
    if (!isLive) return
    stopCapture()
    liveValues.current = []; scores.current = []; heads.current = []; iRef.current = 0
    setLiveLen(0); setIdx(0)
    // eslint-disable-next-line
  }, [engine, window_])

  // prepare KNOWN streams (synthetic/NAB)
  useEffect(() => {
    if (isLive) return
    let cancelled = false
    scores.current = []; heads.current = []; iRef.current = 0; setIdx(0); setPlaying(false)
    if (engine === 'js') {
      scoreLocal(stream.values, window_, stream.standardize)
      setPrep({ ready: true, loading: false, error: null, down: false, elapsed: null })
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
      .catch((e) => { if (!cancelled) { const nf = e instanceof TypeError; setPrep({ ready: false, loading: false, elapsed: null, down: nf, error: nf ? null : String(e.message || e) }) } })
    return () => { cancelled = true }
    // eslint-disable-next-line
  }, [selId, engine, window_, reloadKey, isLive])

  function scoreLocal(values, win, standardize) {
    const det = new UnifiedDetector(win, 1.0)
    const std = standardize ? new CausalStandardizer() : null
    const sc = [], hd = []
    for (const x of values) { const fed = std ? std.push(x) : x; const r = det.update(fed); sc.push(r.score); hd.push(r) }
    scores.current = sc; heads.current = hd
  }
  // reveal-only animation loop (KNOWN streams)
  useEffect(() => {
    if (!playing) return
    const sps = SPEEDS[speedIdx].sps
    const id = setInterval(() => {
      const k = sps === Infinity ? N : Math.max(1, Math.round((sps * TICK_MS) / 1000))
      const i = Math.min(N, iRef.current + k)
      iRef.current = i; setIdx(i); if (i >= N) setPlaying(false)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [playing, speedIdx, N])

  // ---- continuous live capture (server session: gap-free sampling + incremental scoring) ----
  async function captureTick() {
    if (!loopActive.current) return
    try {
      const r = await fetch(`${ENGINE_URL}/api/live/next?session=${sessionRef.current}`).then((x) => x.json())
      if (!r.ok) throw new Error(r.error || 'capture failed')
      liveValues.current.push(r.value)
      if (r.score == null) {                       // js: browser scores this sample incrementally
        // device throughput and ping latency are both positive, heavy-tailed/ratio-scale
        // network metrics; log-compress before standardizing so normal bursts/jitter don't
        // get amplified into false anomalies (the detector itself is untouched)
        const pre = Math.log1p(Math.max(0, r.value))
        const fed = liveStd.current.push(pre)
        const rr = liveDet.current.update(fed)
        scores.current.push(rr.score); heads.current.push(rr)
      } else {                                      // python/c: server already scored it
        scores.current.push(r.score)
        heads.current.push({ score: 0, sDrv: r.heads[0], sDrift: r.heads[1], sPer: r.heads[2] })
      }
      const n = liveValues.current.length
      iRef.current = n; setLiveLen(n); setIdx(n)
      if (n >= MAX_LIVE) { stopCapture(); return }
    } catch (e) {
      stopCapture()
      const nf = e instanceof TypeError
      setPrep((p) => ({ ...p, ready: false, down: nf, error: nf ? null : String(e.message || e) }))
      return
    }
    if (loopActive.current) setTimeout(captureTick, sourceRef.current === 'ip' ? 50 : 35)
  }
  async function startCapture() {
    if (stream.source === 'ip' && !(ping && ping.ok)) return
    liveValues.current = []; scores.current = []; heads.current = []; iRef.current = 0
    setLiveLen(0); setIdx(0); setPlaying(false)
    setPrep({ ready: true, loading: false, error: null, down: false, elapsed: null })
    try {
      const q = stream.source === 'ip' ? `source=ip&ip=${encodeURIComponent(ipInput.trim())}` : 'source=device'
      const st = await fetch(`${ENGINE_URL}/api/live/start?${q}&window=${window_}&lang=${engine}`).then((r) => r.json())
      if (!st.ok) throw new Error(st.error || 'could not start capture')
      sessionRef.current = st.session
      liveStd.current = engine === 'js' ? new CausalStandardizer() : null
      liveDet.current = engine === 'js' ? new UnifiedDetector(window_, 1.0) : null
      setLiveMeta({ source: stream.source, ip: stream.source === 'ip' ? ipInput.trim() : (st.device_ip || ''), unit: st.unit })
      loopActive.current = true; setCapturing(true)
      captureTick()
    } catch (e) {
      loopActive.current = false; setCapturing(false)
      const nf = e instanceof TypeError
      setPrep((p) => ({ ...p, ready: false, down: nf, error: nf ? null : String(e.message || e) }))
    }
  }
  function stopCapture() {
    loopActive.current = false; setCapturing(false)
    const sid = sessionRef.current
    if (sid) { fetch(`${ENGINE_URL}/api/live/stop?session=${sid}`).catch(() => {}); sessionRef.current = null }
  }

  const knownDone = !isLive && N > 0 && idx >= N
  function reset() {
    if (isLive) { stopCapture(); liveValues.current = []; scores.current = []; heads.current = []; iRef.current = 0; setLiveLen(0); setIdx(0); setLiveMeta(null) }
    else { iRef.current = 0; setIdx(0); setPlaying(false) }
  }

  async function checkPing() {
    setPing({ loading: true })
    try {
      const r = await fetch(`${ENGINE_URL}/api/ping?ip=${encodeURIComponent(ipInput.trim())}`).then((x) => x.json())
      setPing(r)
    } catch (e) { setPing({ ok: false, error: e instanceof TypeError ? 'engine server not running' : String(e.message || e) }) }
  }

  const m = useMemo(() => {
    const sc = scores.current, live = isLive, lab = live ? null : stream.labels
    let tp = 0, fp = 0, fn = 0, tn = 0, alerts = 0, peak = 0
    for (let i = 0; i < idx; i++) {
      const a = sc[i] >= threshold ? 1 : 0; alerts += a; if (sc[i] > peak) peak = sc[i]
      if (!live) { if (a && lab[i]) tp++; else if (a) fp++; else if (lab[i]) fn++; else tn++ }
    }
    const tpr = tp + fn ? tp / (tp + fn) : 0, fpr = fp + tn ? fp / (fp + tn) : 0
    const prec = tp + fp ? tp / (tp + fp) : 0, f1 = prec + tpr ? (2 * prec * tpr) / (prec + tpr) : 0
    let detected = 0, latSum = 0, latN = 0
    if (!live) for (const e of stream.events) {
      if (e.start >= idx) continue
      let hit = -1; for (let i = e.start; i < Math.min(idx, e.end + 3); i++) if (sc[i] >= threshold) { hit = i; break }
      if (hit >= 0) { detected++; latSum += hit - e.start; latN++ }
    }
    const last = heads.current[idx - 1] || { score: 0, sDrv: 0, sDrift: 0, sPer: 0 }
    return { live, alerts, peak, alertRate: idx ? alerts / idx : 0, tpr, fpr, f1, detected, lat: latN ? latSum / latN : null, last, curScore: sc[idx - 1] ?? 0 }
  }, [idx, threshold, stream, liveLen, isLive])

  const valUnit = isLive ? (liveMeta?.unit || (stream.source === 'ip' ? 'ms' : 'KB/s')) : null
  const option = useMemo(() => scopeOption(dispValues, scores.current, heads.current, isLive ? null : stream.labels, idx, threshold, valUnit), [idx, threshold, theme.resolved, N])

  // primary button
  let primaryLabel, primaryClick, primaryDisabled
  if (isLive) {
    if (capturing) { primaryLabel = '■ Stop'; primaryClick = stopCapture; primaryDisabled = false }
    else { primaryLabel = liveLen > 0 ? '▶ Restart capture' : '▶ Start capture'; primaryClick = startCapture; primaryDisabled = stream.source === 'ip' && !(ping && ping.ok) }
  } else {
    primaryLabel = playing ? '❙❙ Pause' : knownDone ? '⟲ Replay' : '▶ Stream'
    primaryClick = () => (knownDone ? (reset(), setTimeout(() => setPlaying(true), 0)) : setPlaying(!playing))
    primaryDisabled = !(prep.ready && !prep.loading)
  }

  const status = capturing ? 'CAPTURING' : playing ? 'STREAMING'
    : isLive ? (liveLen > 0 ? 'STOPPED' : (stream.source === 'ip' && !(ping && ping.ok) ? 'NOT READY' : 'READY'))
      : (knownDone ? 'COMPLETE' : (prep.ready ? 'READY' : (prep.loading ? 'PREPARING' : 'NOT READY')))
  const statusCls = (capturing || playing) ? 'live' : (status === 'COMPLETE' || status === 'STOPPED') ? 'done' : status === 'NOT READY' ? 'notready' : ''

  return (
    <div className={embed ? '' : 'page wide'}>
      {!embed && (
        <div className="page-head">
          <div className="eyebrow">live pipeline · run it in Python, C, or JS</div>
          <h1>Stream a signal <span className="hero-underline">through the detector</span></h1>
          <p>Pick a dataset or capture <b>live telemetry from your device or any IPv4 host</b>, choose an engine, and
            run. Live capture streams continuously until you press Stop. Same 96-byte algorithm, parity Δ = 0.</p>
        </div>
      )}

      <div className="deck-row">
        <div className="grp">
          <span className="lbl">input</span>
          <select className="sel" value={selId} onChange={(e) => setSelId(e.target.value)}>
            {CATEGORIES.map((c) => {
              const items = streams.filter((s) => s.kind !== 'live' && (s.category || 'injected') === c.id).slice(0, 1)
              if (!items.length) return null
              return (
                <optgroup key={c.id} label={c.label}>
                  {items.map((s) => <option key={s.id} value={s.id}>{shortName(s)} · {s.values.length} samples</option>)}
                </optgroup>
              )
            })}
            <optgroup label="④ Live telemetry">
              {LIVE_STREAMS.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </optgroup>
          </select>
        </div>
        <div className="grp">
          <span className="lbl">engine</span>
          <div className="seg">
            {ENGINES.map((e) => (
              <button key={e.id} className={engine === e.id ? 'on' : ''} onClick={() => { setEngine(e.id); setReloadKey((k) => k + 1) }}>{e.label}</button>
            ))}
          </div>
        </div>
        {!isLive && (
          <div className="grp"><span className="lbl">speed</span>
            <div className="seg">{SPEEDS.map((s, i) => <button key={s.label} className={i === speedIdx ? 'on' : ''} onClick={() => setSpeedIdx(i)}>{s.label}</button>)}</div>
          </div>
        )}
        <div className="grp">
          <button className="btn primary" disabled={primaryDisabled} onClick={primaryClick}>{primaryLabel}</button>
          <button className="btn" onClick={reset} disabled={isLive ? (!capturing && liveLen === 0) : false}>Reset</button>
        </div>
        <div className="grp"><span className="lbl">window</span>
          <div className="seg">{[10, 20, 24, 30, 50].map((w) => <button key={w} className={w === window_ ? 'on' : ''} onClick={() => setWindow(w)}>{w}</button>)}</div>
        </div>
        <div className="grp"><span className="lbl">threshold</span>
          <input type="range" min={isLive ? 1 : 0.2} max={stream.standardize ? 5 : 3} step="0.05" value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value))} />
          <span className="mono" style={{ color: 'var(--accent)', minWidth: 38 }}>{threshold.toFixed(2)}</span>
        </div>
        <div className="grp" style={{ marginLeft: 'auto' }}>
          <span className={'rec ' + statusCls}><span className="d" />{status}</span>
        </div>
      </div>

      {!isLive && catOf(stream) && (
        <div className="callout" style={{ marginBottom: 16, borderLeftColor: stream.category === 'clean' ? 'var(--green)' : stream.category === 'real' ? 'var(--cyan)' : 'var(--accent)' }}>
          <b>{catOf(stream).label.replace(/ ·.*/, '')}.</b> {catOf(stream).note}
        </div>
      )}

      {isLive && (
        <div className="deck-row">
          {stream.source === 'ip' ? (
            <>
              <div className="grp">
                <span className="lbl">target ipv4</span>
                <div className="ip-field">
                  <span className="ip-ico">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" /></svg>
                  </span>
                  <input value={ipInput} placeholder="192.0.2.1" spellCheck={false}
                    onChange={(e) => { setIpInput(e.target.value); setPing(null) }}
                    onKeyDown={(e) => { if (e.key === 'Enter' && ipInput.trim()) checkPing() }} />
                  <button className="ping-btn" onClick={checkPing} disabled={!ipInput.trim() || (ping && ping.loading)}>{ping && ping.loading ? 'Pinging…' : 'Check ping'}</button>
                </div>
              </div>
              <div className="grp">
                {ping && !ping.loading && (ping.ok
                  ? <span className="badge ok">✓ Reachable · {ping.rtt_ms} ms</span>
                  : <span className="badge no">✗ {cap(ping.error) || 'Unreachable'}</span>)}
              </div>
            </>
          ) : (
            <div className="grp"><span className="lbl">device</span>
              <span className="mono">{health && health.device_ip ? health.device_ip : (health === false ? 'server offline' : '…')} · network throughput (KB/s)</span>
            </div>
          )}
          <div className="grp" style={{ color: 'var(--fg-subtle)', fontSize: 12, marginLeft: 'auto' }}>
            {capturing ? 'streaming live · press Stop to end' : 'captures continuously until you press Stop'}
          </div>
        </div>
      )}

      {isLive && prep.down && (
        <div className="callout" style={{ marginBottom: 16, borderLeftColor: 'var(--amber)' }}>
          <b>Engine server not running.</b> Live capture needs it, start it from <span className="mono">Final Pipeline</span>:
          <span className="mono" style={{ color: 'var(--accent)' }}> python server.py</span>, then try again.
        </div>
      )}
      {!isLive && prep.down && (
        <div className="callout" style={{ marginBottom: 16, borderLeftColor: 'var(--amber)' }}>
          <b>Engine server not running.</b> To run in Python or C, start <span className="mono" style={{ color: 'var(--accent)' }}>python server.py</span> then click <b>{engine.toUpperCase()}</b> again. JS runs without it.
        </div>
      )}
      {prep.error && <div className="callout" style={{ marginBottom: 16, borderLeftColor: 'var(--red)' }}><b>Engine error:</b> <span className="mono">{prep.error}</span></div>}

      <div className="live-grid">
        <div className="card pad0">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
            <span className="mono" style={{ fontSize: 12, color: 'var(--fg-muted)' }}>
              {N > 0 ? `sample ${idx} / ${N}` : (isLive ? 'no capture yet' : 'ready')}
              {isLive && liveMeta ? ` · ${liveMeta.source === 'ip' ? 'ping ' + liveMeta.ip : 'device ' + liveMeta.ip} (${liveMeta.unit})` : ''}
            </span>
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
              <RO v={m.alerts} k="alerts" c={m.alerts ? 'var(--red)' : 'var(--green)'} />
              {(m.live || stream.events.length === 0) ? <>
                <RO v={fmt(m.alertRate, 2)} k="alert rate" c="var(--cyan)" />
                <RO v={fmt(m.peak, 2)} k="peak score" c={m.peak >= threshold ? 'var(--amber)' : 'var(--green)'} />
              </> : <>
                <RO v={`${m.detected}/${stream.events.length}`} k="events detected" c="var(--green)" />
                <RO v={fmt(m.tpr, 2)} k="recall" c="var(--cyan)" />
                <RO v={fmt(m.f1, 2)} k="F1 (sample)" c="var(--fg)" />
                <RO v={m.lat == null ? '·' : fmt(m.lat, 0)} k="latency (samp)" c="var(--fg)" />
              </>}
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
                    <div className="vu-mark" style={{ left: '50%' }} />
                    {h.cap && <div className="vu-mark" style={{ left: (h.cap / 2) * 100 + '%', background: h.color }} />}
                  </div>
                </div>
              )
            })}
          </div>

        </div>
      </div>
    </div>
  )
}

const RO = ({ v, k, c }) => <div className="ro-cell"><div className="v" style={{ color: c }}>{v}</div><div className="k">{k}</div></div>

function scopeOption(values, sc, heads, labels, idx, threshold, valUnit) {
  const t = themeColors()
  const N = values.length
  const stride = Math.max(1, Math.floor(N / 1500))
  const valData = [], scoreData = [], alertData = []
  for (let i = 0; i < N; i += stride) {
    if (i >= idx) break
    valData.push([i, values[i]]); const s = sc[i] ?? 0; scoreData.push([i, s]); if (s >= threshold) alertData.push([i, s])
  }
  const cursor = idx > 0 && idx < N ? { silent: true, symbol: 'none', lineStyle: { color: t.accent, width: 1, opacity: 0.5 }, data: [{ xAxis: Math.min(idx, N - 1) }] } : undefined
  const ax = { axisLine: { lineStyle: { color: t.border } }, axisLabel: { color: t.subtle }, splitLine: { lineStyle: { color: t.border, opacity: 0.5 } } }
  return {
    animation: false, backgroundColor: 'transparent',
    grid: [{ left: 54, right: 16, top: 12, height: '52%' }, { left: 54, right: 16, top: '68%', height: '26%' }],
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      backgroundColor: t.bg, borderColor: t.border, textStyle: { color: t.fg, fontSize: 11 }, extraCssText: 'max-width:240px;line-height:1.5',
      formatter: (ps) => {
        const p = ps && ps[0]
        if (!p) return ''
        const i = p.data[0]
        const v = values[i]
        const s = sc[i] ?? 0
        const h = heads[i] || {}
        const hd = [['Derivative', h.sDrv ?? 0, 'spike · transient', '#e5484d'], ['EWMA control', h.sDrift ?? 0, 'drift', '#7c3aed'], ['ACF-drop', h.sPer ?? 0, 'periodicity', '#0891b2']]
        const mx = Math.max(hd[0][1], hd[1][1], hd[2][1])
        const alert = s >= threshold
        let o = `<div style="font-weight:600;margin-bottom:3px">sample ${i}${N ? ` / ${N - 1}` : ''}</div>`
        o += `<div>value <b>${v != null ? Number(v).toFixed(2) : '·'}</b>${valUnit ? ' ' + valUnit : ''}</div>`
        o += `<div>score <b>${Number(s).toFixed(2)}</b> <span style="color:${t.subtle}">vs thr ${Number(threshold).toFixed(2)}</span></div>`
        o += `<div style="color:${alert ? t.red : t.subtle}">${alert ? '● ALERT · score ≥ threshold' : '○ below threshold'}</div>`
        if (labels && labels[i]) o += `<div style="color:${t.amber}">● labelled anomaly (ground truth)</div>`
        o += `<div style="margin-top:5px;color:${t.subtle}">heads · final score = the max of these</div>`
        for (const [nm, val, sub, color] of hd) {
          const win = val > 0 && val === mx
          o += `<div style="color:${win ? color : t.subtle}">${win ? '▸' : '&nbsp;&nbsp;'} ${nm} <b>${val.toFixed(2)}</b> <span style="opacity:.7">· ${sub}</span></div>`
        }
        return o
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: [
      { type: 'value', gridIndex: 0, min: 0, max: Math.max(1, N - 1), ...ax, axisLabel: { show: false }, splitLine: { show: false } },
      { type: 'value', gridIndex: 1, min: 0, max: Math.max(1, N - 1), name: 'sample', nameLocation: 'middle', nameGap: 24, nameTextStyle: { color: t.subtle, fontSize: 10 }, ...ax, splitLine: { show: false } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: valUnit ? `value (${valUnit})` : 'value', nameTextStyle: { color: t.subtle, fontSize: 10 }, scale: true, ...ax },
      { type: 'value', gridIndex: 1, name: 'score', nameTextStyle: { color: t.subtle, fontSize: 10 }, scale: true, min: 0, ...ax },
    ],
    series: [
      { name: 'value', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: valData, showSymbol: false, sampling: 'lttb', lineStyle: { width: 1.4, color: t.accent }, markLine: cursor },
      { name: 'score', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: scoreData, showSymbol: false, sampling: 'lttb', lineStyle: { width: 1.4, color: t.amber }, markLine: { silent: true, symbol: 'none', data: [{ yAxis: threshold, label: { formatter: `thr ${threshold.toFixed(2)}`, color: t.subtle, fontSize: 10 }, lineStyle: { color: t.subtle, type: 'dashed' } }] } },
      { name: 'alert', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, data: alertData, symbolSize: 4, itemStyle: { color: t.red } },
    ],
  }
}
