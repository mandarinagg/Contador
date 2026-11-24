/** Alcance de los reportes en la URL (rango o fecha, y la cuenta del mayor). */
import { useSearchParams } from 'react-router'
import { todayIso } from '../../finance/labels'

/** Parámetros de un reporte en la URL, con valores por defecto (el año en curso hasta hoy). */
export function useReportParams() {
  const [params, setParams] = useSearchParams()
  const today = todayIso()
  const from = params.get('from') || `${today.slice(0, 4)}-01-01`
  const to = params.get('to') || today
  const at = params.get('at') || today
  const accountId = params.get('account_id') ?? ''
  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }
  return { from, to, at, accountId, set }
}

export const amountTh = 'w-40 px-4 py-2.5 text-right font-medium'
export const textTh = 'px-4 py-2.5 text-left font-medium'
