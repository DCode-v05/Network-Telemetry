import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

/** Thin wrapper over raw echarts: init(dark) -> setOption -> resize -> dispose. */
export default function EChart({ option, height = 340 }) {
  const ref = useRef(null)
  const chart = useRef(null)

  useEffect(() => {
    chart.current = echarts.init(ref.current, 'dark')
    const onResize = () => chart.current && chart.current.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.current && chart.current.dispose()
    }
  }, [])

  useEffect(() => {
    if (chart.current && option) chart.current.setOption(option, true)
  }, [option])

  return <div ref={ref} style={{ width: '100%', height }} />
}
