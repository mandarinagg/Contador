import type { EntryKind, EntryStatus, LedgerKind, LedgerOrigin, NormalSide, StartRule } from './types'
import type { DisposalKind, InstallmentStatus } from './types3b'

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
  depreciation: 'Depreciación',
  disposal: 'Baja de bien',
  recurring: 'Recurrente',
}

/** Borradores generados que no se editan: se descartan y se vuelven a generar (409 ENTRY_NOT_EDITABLE). */
export const GENERATED_KINDS: EntryKind[] = ['closing', 'depreciation', 'disposal']

/** Tipos que se pueden revertir (las reversiones y la refundición, no). */
export const REVERSIBLE_KINDS: EntryKind[] = ['manual', 'finance', 'depreciation', 'disposal', 'recurring']

export const START_RULE_LABELS: Record<StartRule, string> = {
  next_month: 'Desde el mes siguiente a la compra',
  next_fiscal_year: 'Desde el ejercicio siguiente',
}

export const DISPOSAL_KIND_LABELS: Record<DisposalKind, string> = {
  sale: 'Venta',
  scrap: 'Destrucción o desuso',
  donation: 'Donación',
}

export const INSTALLMENT_STATUS_LABELS: Record<InstallmentStatus, string> = {
  posted: 'Contabilizada',
  draft: 'En borrador',
  pending: 'Pendiente',
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

/** "2026-03-01" → "marzo de 2026". */
export function monthYear(iso: string): string {
  return `${MONTHS_LONG[Number(iso.slice(5, 7)) - 1]} de ${iso.slice(0, 4)}`
}

/** Meses en años legibles: 24 → "2 años"; 18 → "1 año y 6 meses"; 6 → "6 meses". */
export function monthsText(months: number): string {
  const y = Math.floor(months / 12)
  const m = months % 12
  const years = y === 0 ? '' : y === 1 ? '1 año' : `${y} años`
  const rest = m === 0 ? '' : m === 1 ? '1 mes' : `${m} meses`
  return years && rest ? `${years} y ${rest}` : years || rest || '0 meses'
}

/** Porcentaje de la API ("10", "12.5") en formato local: "10 %", "12,5 %". */
export function percentText(rate: string | null): string {
  return rate === null ? '—' : `${rate.replace('.', ',')} %`
}
