import { useCallback, useEffect, useState } from 'react'

const KEY = 'theme'
const q = () => window.matchMedia('(prefers-color-scheme: dark)')

function apply(pref) {
  const dark = pref === 'dark' || (pref === 'system' && q().matches)
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  return dark ? 'dark' : 'light'
}

/** Theme preference: 'system' (default, follows the browser) | 'light' | 'dark'. */
export function useTheme() {
  const [pref, setPref] = useState(() => localStorage.getItem(KEY) || 'system')
  const [resolved, setResolved] = useState(() => document.documentElement.getAttribute('data-theme') || 'light')

  useEffect(() => {
    setResolved(apply(pref))
    localStorage.setItem(KEY, pref)
  }, [pref])

  useEffect(() => {
    const mq = q()
    const h = () => { if (pref === 'system') setResolved(apply('system')) }
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [pref])

  const cycle = useCallback(() => {
    setPref((p) => (p === 'system' ? 'light' : p === 'light' ? 'dark' : 'system'))
  }, [])

  return { pref, resolved, setPref, cycle }
}
