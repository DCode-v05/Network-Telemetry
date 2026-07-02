import { useEffect, useState } from 'react'

const BASE = import.meta.env.BASE_URL

/** Fetch one or more JSON files under public/. Returns {loading, error, data:[...]} */
export function useJson(paths) {
  const [s, setS] = useState({ loading: true, error: null, data: null })
  useEffect(() => {
    let live = true
    Promise.all(paths.map((p) => fetch(BASE + p).then((r) => {
      if (!r.ok) throw new Error(`${p} → ${r.status}`)
      return r.json()
    })))
      .then((d) => live && setS({ loading: false, error: null, data: d }))
      .catch((e) => live && setS({ loading: false, error: String(e), data: null }))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return s
}
