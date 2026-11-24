import { useCallback, useEffect, useState } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'
const KEY = 'contador.theme' // preferencia visual, no dato de negocio

function resolve(pref: ThemePreference): 'light' | 'dark' {
  if (pref !== 'system') return pref
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyStoredTheme() {
  const pref = (localStorage.getItem(KEY) as ThemePreference | null) ?? 'system'
  document.documentElement.dataset.theme = resolve(pref)
}

export function useTheme() {
  const [pref, setPref] = useState<ThemePreference>(
    () => (localStorage.getItem(KEY) as ThemePreference | null) ?? 'system',
  )

  useEffect(() => {
    document.documentElement.dataset.theme = resolve(pref)
    if (pref !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => (document.documentElement.dataset.theme = resolve('system'))
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [pref])

  const set = useCallback((next: ThemePreference) => {
    localStorage.setItem(KEY, next)
    setPref(next)
  }, [])

  return { preference: pref, setPreference: set }
}
