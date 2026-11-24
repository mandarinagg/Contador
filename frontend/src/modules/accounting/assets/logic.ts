/** Lógica de las pantallas de activos fijos (sin componentes): plan de cuotas, baja y corridas. */
import { sumPyg } from '../amounts'
import type { DepreciationRun, Installment, InstallmentStatus } from '../types3b'

/** Totales del plan por estado (BigInt: nunca `number` para sumar guaraníes). */
export function planTotals(installments: Installment[]) {
  const by = (s: InstallmentStatus) => installments.filter((i) => i.status === s)
  return {
    posted: { count: by('posted').length, amount: sumPyg(by('posted').map((i) => i.amount)) },
    draft: { count: by('draft').length, amount: sumPyg(by('draft').map((i) => i.amount)) },
    pending: { count: by('pending').length, amount: sumPyg(by('pending').map((i) => i.amount)) },
    total: sumPyg(installments.map((i) => i.amount)),
  }
}

/** Cuotas agrupadas por año calendario, en orden. */
export function byYear(installments: Installment[]): [string, Installment[]][] {
  const map = new Map<string, Installment[]>()
  for (const i of installments) {
    const y = i.month.slice(0, 4)
    map.set(y, [...(map.get(y) ?? []), i])
  }
  return [...map.entries()]
}

export function disposeErrors(d: { date: string; reason: string; document: string }) {
  return {
    date: d.date ? undefined : 'Elegí la fecha de la baja.',
    reason: d.reason.trim().length < 3 ? 'Explicá el motivo (al menos 3 caracteres).' : undefined,
    document: d.document.trim() ? undefined : 'El acta es obligatoria: el número o la referencia del acta del contador o de la constancia del auditor (Decreto 3182, art. 58).',
  }
}

/** La corrida viva de cada mes (borrador o contabilizada); las revertidas o descartadas no cuentan. */
export function liveRunByMonth(runs: DepreciationRun[]): Map<string, DepreciationRun> {
  const out = new Map<string, DepreciationRun>()
  for (const r of runs) if (r.entry_status === 'draft' || r.entry_status === 'posted') out.set(r.period_id, r)
  return out
}
