import { useSearchParams } from 'react-router'

/** Períodos y ejes de los resúmenes. Fechas contables como texto "YYYY-MM-DD" (sin zonas horarias). */

/** Todos los meses entre dos fechas, para que el eje no salte los meses sin datos. */
export function monthsBetween(from: string, to: string): string[] {
  let y = Number(from.slice(0, 4))
  let m = Number(from.slice(5, 7))
  const endY = Number(to.slice(0, 4))
  const endM = Number(to.slice(5, 7))
  const out: string[] = []
  while ((y < endY || (y === endY && m <= endM)) && out.length < 240) {
    out.push(`${y}-${String(m).padStart(2, '0')}`)
    m += 1
    if (m > 12) {
      m = 1
      y += 1
    }
  }
  return out
}

/** Paso "redondo" para el eje (1, 2 o 5 por potencia de diez). Solo geometría. */
export function niceStep(max: number, ticks = 3): number {
  if (max <= 0) return 1
  const raw = max / ticks
  const power = 10 ** Math.floor(Math.log10(raw))
  const unit = raw / power
  return (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10) * power
}

export type PeriodPreset = 'default' | 'this-year' | 'last-year' | 'custom'

/** Rango de un período predefinido; `default` = el de la API (últimos 12 meses). */
export function presetRange(preset: PeriodPreset, today: string): { from: string; to: string } | null {
  const year = Number(today.slice(0, 4))
  if (preset === 'this-year') return { from: `${year}-01-01`, to: today }
  if (preset === 'last-year') return { from: `${year - 1}-01-01`, to: `${year - 1}-12-31` }
  return null
}

/** Qué preset corresponde a un from/to de la URL (para marcar el botón activo). */
export function detectPreset(from: string, to: string, today: string): PeriodPreset {
  if (!from && !to) return 'default'
  for (const p of ['this-year', 'last-year'] as const) {
    const r = presetRange(p, today)
    if (r && r.from === from && r.to === to) return p
  }
  return 'custom'
}

/** Período elegido (from/to) guardado en la URL; vacío = el de la API. */
export function usePeriodParams() {
  const [params, setParams] = useSearchParams()
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const set = (f: string, t: string) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of [
      ['from', f],
      ['to', t],
    ] as const) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }
  return { from, to, set }
}
