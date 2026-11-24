import type { EntryKind, EntryStatus, LedgerKind, LedgerOrigin, NormalSide } from './types'

export const KIND_LABELS: Record<LedgerKind, string> = {
  asset: 'Activo',
  liability: 'Pasivo',
  equity: 'Patrimonio',
  income: 'Ingreso',
  expense: 'Gasto',
}

export const SIDE_LABELS: Record<NormalSide, string> = { debit: 'Deudora', credit: 'Acreedora' }

/** Naturaleza que corresponde a cada tipo (la regularizadora la invierte a mano). */
export const DEFAULT_SIDE: Record<LedgerKind, NormalSide> = {
  asset: 'debit',
  expense: 'debit',
  liability: 'credit',
  equity: 'credit',
  income: 'credit',
}

/** Patrimoniales (balance) y de resultados: el tipo de una subcuenta no cruza de grupo. */
export const BALANCE_KINDS: LedgerKind[] = ['asset', 'liability', 'equity']
export const RESULT_KINDS: LedgerKind[] = ['income', 'expense']

export const ORIGIN_LABELS: Record<LedgerOrigin, string> = {
  rg49_2014: 'RG 49/2014',
  proposed: 'Propuesta',
  user: 'Agregada',
}

export const ORIGIN_HINTS: Record<LedgerOrigin, string> = {
  rg49_2014: 'Código y nombre del modelo oficial de estados financieros (RG N° 49/2014, DNIT)',
  proposed: 'Agregada en la propuesta, fuera del modelo oficial',
  user: 'Agregada en esta empresa',
}

export const STATUS_LABELS: Record<EntryStatus, string> = {
  draft: 'Borrador',
  posted: 'Contabilizado',
  reversed: 'Revertido',
  discarded: 'Descartado',
}

export const ENTRY_KIND_LABELS: Record<EntryKind, string> = {
  manual: 'Manual',
  finance: 'Desde finanzas',
  reversal: 'Reversión',
  closing: 'Refundición',
}

const MONTHS_LONG = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** "2026-03-05" → "5 de marzo de 2026", sin pasar por zonas horarias. */
export function longDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${Number(d)} de ${MONTHS_LONG[Number(m) - 1]} de ${y}`
}

/** Rango de fechas en palabras: "del 1 de enero al 31 de marzo de 2026". */
export function rangeText(from: string, to: string): string {
  const [fy] = from.split('-')
  const [ty] = to.split('-')
  const start = fy === ty ? longDate(from).replace(/ de \d{4}$/, '') : longDate(from)
  return `del ${start} al ${longDate(to)}`
}

/** Nombre del mes de un período: "2026-03-01" → "Marzo". */
export function monthName(iso: string): string {
  const m = MONTHS_LONG[Number(iso.slice(5, 7)) - 1]
  return m.charAt(0).toUpperCase() + m.slice(1)
}

/** Etiqueta corta de un asiento: "N° 12" o "Borrador". */
export function entryLabel(e: { number: number | null; status: EntryStatus }): string {
  return e.number !== null ? `N° ${e.number}` : e.status === 'discarded' ? 'Descartado' : 'Borrador'
}
