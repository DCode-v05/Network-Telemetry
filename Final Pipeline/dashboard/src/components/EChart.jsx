import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

/** Read theme tokens from CSS variables so charts follow light/dark. */
export function themeColors() {
  const s = getComputedStyle(document.documentElement)
  const v = (n) => s.getPropertyValue(n).trim()
  return {
    fg: v('--fg'), muted: v('--fg-muted'), subtle: v('--fg-subtle'),
    border: v('--border'), grid: v('--border'),
    accent: v('--accent'), green: v('--green'), amber: v('--amber'),
    red: v('--red'), purple: v('--purple'), cyan: v('--cyan'), bg: v('--bg-elevated'),
  }
}

/** Thin echarts wrapper. Re-inits when `themeKey` changes so tooltip/theme follow. */
export default function EChart({ option, height = 340, themeKey }) {
  const ref = useRef(null)
  const chart = useRef(null)

  useEffect(() => {
    chart.current = echarts.init(ref.current, null, { renderer: 'canvas' })
    const onResize = () => chart.current && chart.current.resize()
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.current && chart.current.dispose() }
  }, [themeKey])

  useEffect(() => {
    if (chart.current && option) chart.current.setOption(option, true)
  }, [option, themeKey])

  return <div ref={ref} style={{ width: '100%', height }} />
}
