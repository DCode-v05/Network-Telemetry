import { HEADS, STATE, NODILUTION } from '../content/architecture.js'

const ATYPE_COLOR = { spike: 'var(--red)', transient: 'var(--amber)', drift: 'var(--purple)', periodicity: 'var(--cyan)' }

const MAP_ROWS = [
  { a: 'Spike', head: 'Derivative', stat: 'first-difference z-score', c: 'var(--red)' },
  { a: 'Transient', head: 'Derivative', stat: 'first-difference z-score', c: 'var(--amber)' },
  { a: 'Drift', head: 'EWMA control-chart', stat: 'held EWMA vs windowed σ', c: 'var(--purple)' },
  { a: 'Periodicity loss', head: 'Gated ACF-drop', stat: 'lag-k autocorrelation drop', c: 'var(--cyan)' },
]

function ArrowV({ label }) {
  return (
    <div className="arrow-v">
      {label && <span className="lab">{label}</span>}
      <svg width="32" height="42" viewBox="0 0 32 42" fill="none">
        <line x1="16" y1="2" x2="16" y2="29" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
        <path d="M16 41 L7 27 L25 27 Z" fill="currentColor" />
      </svg>
    </div>
  )
}
function MiniArrow() {
  return (
    <div className="mini-arrow">
      <svg width="20" height="26" viewBox="0 0 20 26" fill="none">
        <line x1="10" y1="1" x2="10" y2="17" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        <path d="M10 25 L3 15 L17 15 Z" fill="currentColor" />
      </svg>
    </div>
  )
}

export default function Architecture() {
  return (
    <div className="page wide">
      <div className="page-head">
        <div className="eyebrow">unified detector · architecture</div>
        <h1>Three heads, one 96-byte state, <span className="hero-underline">MAX-fused</span></h1>
        <p>Every sample flows through one shared state block into three specialised heads. Each head targets a
          different anomaly class; the final score is the maximum of the three normalised head scores.</p>
      </div>

      {/* ---- the diagram ---- */}
      <div className="dgm">
        <div className="dgm-box">
          <div className="t">telemetry sample&nbsp;&nbsp;<span style={{ color: 'var(--accent)' }}>x</span></div>
          <div className="s">one value in · O(window) work · no look-ahead</div>
        </div>
        <ArrowV />

        <div className="dgm-box state">
          <div className="t">shared state · 96 bytes</div>
          <div style={{ display: 'flex', gap: 6, marginTop: 12, height: 30, borderRadius: 7, overflow: 'hidden', border: '1px solid var(--border)' }}>
            {STATE.items.map((s, i) => (
              <div key={i} title={`${s.k} — ${s.bytes} B`} style={{
                flex: s.bytes, background: ['var(--accent)', 'var(--purple)', 'var(--fg-subtle)'][i],
                display: 'grid', placeItems: 'center', color: '#fff', fontSize: 11.5, fontFamily: 'var(--font-mono)', fontWeight: 600,
              }}>{s.bytes}B</div>
            ))}
          </div>
          <div className="s" style={{ marginTop: 10 }}>
            {STATE.items.map((s) => `${s.k} (${s.detail})`).join('   ·   ')}
          </div>
        </div>
        <ArrowV label="fan out to three heads" />

        <div className="heads-group">
          <div className="hg-label">three heads · share the same 96-byte state</div>
          <div className="heads-cols">{HEADS.map((h) => <MiniArrow key={h.n} />)}</div>
          <div className="heads-cols">
            {HEADS.map((h) => (
              <div className="head-card" key={h.n} style={{ '--hc': h.color }}>
                <div className="hh"><span style={{ opacity: 0.7 }}>H{h.n}</span> · {h.name}</div>
                <div className="st">{h.stat}</div>
                <div className="fx">{h.formula}</div>
                <div className="tags">
                  {h.anomalies.map((a) => <span key={a} className="tpill" style={{ color: ATYPE_COLOR[a], borderColor: 'var(--border-strong)' }}>{a}</span>)}
                </div>
                <div className="why">{h.why}</div>
              </div>
            ))}
          </div>
        </div>
        <ArrowV label="MAX-fuse the three scores" />

        <div className="dgm-box fusion">
          <div className="t">score = max( derivative , drift , periodicity )</div>
        </div>
        <ArrowV />

        <div className="dgm-box output">
          <div className="t">◆ ALERT&nbsp;&nbsp;when&nbsp;&nbsp;score ≥ threshold</div>
        </div>
      </div>

      <div className="section-title">Which head catches which anomaly</div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>anomaly type</th><th>detected by</th><th>statistic</th></tr></thead>
          <tbody>
            {MAP_ROWS.map((r) => (
              <tr key={r.a}>
                <td><span className="dot" style={{ background: r.c, marginRight: 8 }} />{r.a}</td>
                <td style={{ fontWeight: 600 }}>{r.head} head</td>
                <td className="mono" style={{ color: 'var(--fg-muted)' }}>{r.stat}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">The tricks that make it work</div>
      <div className="grid g2">
        {HEADS.map((h) => (
          <div className="card" key={h.n}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span className="badge" style={{ color: h.color, borderColor: h.color }}>{h.trick}</span>
              <span className="desc" style={{ color: 'var(--fg-subtle)' }}>{h.name}</span>
            </div>
            <p className="desc">{h.trickDesc}</p>
          </div>
        ))}
        <div className="card" style={{ borderColor: 'color-mix(in srgb, var(--green) 40%, var(--border))' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span className="badge ok">Share one state block</span>
          </div>
          <p className="desc">3 heads reuse the same 96 bytes instead of ~424 for a naive 4-detector vote. {STATE.note}</p>
        </div>
      </div>

      <div className="callout" style={{ marginTop: 20 }}>
        <b>No-dilution design.</b> {NODILUTION.map((x, i) => (
          <span key={i}><b>{x.t}</b> — {x.d}{i < NODILUTION.length - 1 ? ' · ' : '.'}</span>
        ))}
      </div>
    </div>
  )
}
