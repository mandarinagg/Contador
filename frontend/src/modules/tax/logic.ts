/**
 * Lógica de la tributación sin componentes (y con pruebas en `logic.test.ts`).
 *
 * Los importes son guaraníes enteros como string; se opera con BigInt, nunca con `number`.
 * Las fórmulas copian las del backend para que lo que se ve mientras se escribe sea lo mismo
 * que va a guardar la API (que es la que valida):
 * - IVA incluido: `backend/app/modules/tax/vouchers.py`, `included_vat` (importe × tasa /
 *   (1 + tasa), al guaraní más cercano con las mitades hacia arriba; D-088, BR-TAX-09);
 * - DV del RUC y del CDC: módulo 11 (`lib/ruc.ts`, igual que `organizations/ruc.py`);
 * - CDC: estructura del Manual Técnico SIFEN v150 §10.1, como `vouchers._check_cdc` (D-107).
 */
import { parseAmountInput } from '../../lib/money'
import { rucCheckDigit } from '../../lib/ruc'
import type { Direction, Obligation, Voucher, VoucherType } from './types'

/** Importe en guaraníes enteros no negativos; '' cuenta como 0. */
export function readPyg(text: string): { ok: true; value: string } | { ok: false; error: string } {
  if (!text.trim()) return { ok: true, value: '0' }
  const parsed = parseAmountInput(text, 'PYG')
  if (!parsed.ok) return parsed
  if (parsed.value.startsWith('-')) return { ok: false, error: 'Va en positivo: el tipo de comprobante ya dice si suma o resta.' }
  return parsed
}

// --- IVA incluido ------------------------------------------------------------------------

/** "0.1" → {num: 1n, den: 10n}. Tasas positivas con hasta 6 decimales. */
function rateFraction(rate: string): { num: bigint; den: bigint } {
  const m = /^(\d+)(?:\.(\d{1,6}))?$/.exec(rate.trim())
  if (!m) throw new Error(`Tasa con formato inesperado: ${rate}`)
  const frac = m[2] ?? ''
  return { num: BigInt(m[1] + frac), den: 10n ** BigInt(frac.length) }
}

/**
 * IVA incluido en `amount` (guaraníes enteros, ≥ 0) a la tasa `rate` ("0.1" o "0.05").
 * exacto = A × r / (1 + r) = A × num / (den + num); redondeo: ⌊exacto + ½⌋ = ⌊(2·A·num + d) / 2d⌋.
 */
export function includedVat(amount: string, rate: string): string {
  const a = BigInt(amount.trim() || '0')
  if (a < 0n) throw new Error('El importe con IVA incluido va en positivo')
  const { num, den } = rateFraction(rate)
  const d = den + num
  return ((2n * a * num + d) / (2n * d)).toString()
}

/** Tolerancia del IVA impreso (D-088): se acepta si difiere del calculado en ±1 ₲. */
export const VAT_TOLERANCE = 1n

export function vatDifference(printed: string, expected: string): bigint {
  return BigInt(printed) - BigInt(expected)
}

export function vatAccepted(printed: string, expected: string): boolean {
  const diff = vatDifference(printed, expected)
  return diff >= -VAT_TOLERANCE && diff <= VAT_TOLERANCE
}

/** Base sin IVA (importe menos su IVA). */
export const baseOf = (taxed: string, vat: string) => (BigInt(taxed || '0') - BigInt(vat || '0')).toString()

export const sumBig = (...values: (string | null | undefined)[]) => values.reduce((t, v) => t + BigInt(v || '0'), 0n).toString()

// --- Máscaras ------------------------------------------------------------------------------

const digits = (text: string) => text.replace(/\D/g, '')

/** Timbrado: solo dígitos, hasta 8. */
export const maskTimbrado = (text: string) => digits(text).slice(0, 8)

export const timbradoOk = (text: string) => /^\d{8}$/.test(text)

/**
 * Número de comprobante mientras se escribe: los dígitos con los guiones en su lugar
 * (`0010010000001` → `001-001-0000001`; `001001` → `001-001`). Hasta 13 dígitos.
 */
export function maskVoucherNumber(text: string): string {
  const d = digits(text).slice(0, 13)
  if (d.length <= 3) return d
  if (d.length <= 6) return `${d.slice(0, 3)}-${d.slice(3)}`
  return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`
}

/**
 * Al salir del campo: si se escribió por partes con guiones (`1-1-145`), completa con ceros a
 * la izquierda cada parte (`001-001-0000145`). Si no hay guiones, deja la máscara.
 */
export function expandVoucherNumber(text: string): string {
  const parts = text.trim().split('-')
  if (parts.length === 3 && parts.every((p) => /^\d+$/.test(p)) && parts[0].length <= 3 && parts[1].length <= 3 && parts[2].length <= 7) {
    return `${parts[0].padStart(3, '0')}-${parts[1].padStart(3, '0')}-${parts[2].padStart(7, '0')}`
  }
  return maskVoucherNumber(text)
}

export const voucherNumberOk = (text: string) => /^\d{3}-\d{3}-\d{7}$/.test(text)

/** CDC: 44 dígitos, a la vista de a cuatro como en el KuDE (`0144 4444 0170 …`). */
export function maskCdc(text: string): string {
  return digits(text)
    .slice(0, 44)
    .replace(/(\d{4})(?=\d)/g, '$1 ')
}

export const cdcDigits = (text: string) => digits(text)

export interface CdcParts {
  documentType: string
  emitterRuc: string
  emitterDv: string
  number: string
  issuedOn: string
  checkOk: boolean
}

/** Partes del CDC (Manual Técnico v150 §10.1) y si su dígito verificador cuadra. `null` si no tiene 44 dígitos. */
export function parseCdc(text: string): CdcParts | null {
  const cdc = digits(text)
  if (cdc.length !== 44) return null
  const y = cdc.slice(25, 29)
  const m = cdc.slice(29, 31)
  const d = cdc.slice(31, 33)
  return {
    documentType: cdc.slice(0, 2),
    emitterRuc: cdc.slice(2, 10).replace(/^0+(?=\d)/, ''),
    emitterDv: cdc[10],
    number: `${cdc.slice(11, 14)}-${cdc.slice(14, 17)}-${cdc.slice(17, 24)}`,
    issuedOn: `${y}-${m}-${d}`,
    checkOk: rucCheckDigit(cdc.slice(0, 43)) === Number(cdc[43]),
  }
}

const CDC_TYPES: Partial<Record<VoucherType, string>> = { invoice: '01', credit_note: '05' }

/**
 * Qué no coincide entre el CDC y el comprobante (lo mismo que controla la API, D-107). El
 * emisor es la contraparte en una compra y la organización en una venta.
 */
export function cdcMismatches(
  cdc: CdcParts,
  voucher: { direction: Direction; voucherType: VoucherType; number: string; issuedOn: string; emitterRuc: string; emitterDv: string },
): string[] {
  const out: string[] = []
  if (voucher.emitterRuc && (cdc.emitterRuc !== voucher.emitterRuc.replace(/^0+(?=\d)/, '') || cdc.emitterDv !== voucher.emitterDv)) {
    out.push(voucher.direction === 'purchase' ? 'el RUC del proveedor' : 'el RUC de la empresa')
  }
  if (voucher.number && cdc.number !== voucher.number) out.push('el número')
  if (voucher.issuedOn && cdc.issuedOn !== voucher.issuedOn) out.push('la fecha')
  const type = CDC_TYPES[voucher.voucherType]
  if (type && cdc.documentType !== type) out.push('el tipo de comprobante')
  return out
}

// --- RUC de la contraparte -----------------------------------------------------------------

export type RucCheck =
  | { kind: 'empty' }
  | { kind: 'invalid'; message: string }
  | { kind: 'legacy' }
  | { kind: 'missing_dv'; expected: string }
  | { kind: 'wrong_dv'; expected: string }
  | { kind: 'ok' }

/**
 * Estado del RUC de la contraparte mientras se escribe (D-099): hasta 8 dígitos con su DV
 * módulo 11, o un RUC antiguo terminado en letra (`80012345A`), que se acepta sin DV y queda
 * marcado para revisar.
 */
export function checkCounterpartyRuc(ruc: string, dv: string): RucCheck {
  const r = ruc.trim().toUpperCase()
  if (!r) return { kind: 'empty' }
  if (/^\d{1,8}[A-Z]$/.test(r)) return { kind: 'legacy' }
  if (!/^\d{1,8}$/.test(r)) return { kind: 'invalid', message: 'El RUC son hasta 8 dígitos, sin puntos ni guion (el DV va aparte).' }
  const expected = String(rucCheckDigit(r))
  if (!dv) return { kind: 'missing_dv', expected }
  if (dv !== expected) return { kind: 'wrong_dv', expected }
  return { kind: 'ok' }
}

/** «80012345-6» escrito de una vez en el campo del RUC: lo separa en RUC y DV. */
export function splitRucInput(text: string): { ruc: string; dv: string | null } {
  const m = /^\s*(\d{1,8})\s*-\s*(\d)\s*$/.exec(text)
  if (m) return { ruc: m[1], dv: m[2] }
  return { ruc: text.replace(/[\s.]/g, '').toUpperCase().slice(0, 9), dv: null }
}

// --- Calendario -------------------------------------------------------------------------------

export interface MonthGroup<T> {
  /** "2026-11" */
  month: string
  items: T[]
}

/** Obligaciones agrupadas por el mes de su vencimiento, en orden (dentro del mes, por fecha y código). */
export function groupByDueMonth(obligations: Obligation[]): MonthGroup<Obligation>[] {
  const sorted = [...obligations].sort((a, b) => (a.due_date === b.due_date ? a.code.localeCompare(b.code) : a.due_date < b.due_date ? -1 : 1))
  const groups: MonthGroup<Obligation>[] = []
  for (const o of sorted) {
    const month = o.due_date.slice(0, 7)
    const last = groups[groups.length - 1]
    if (last && last.month === month) last.items.push(o)
    else groups.push({ month, items: [o] })
  }
  return groups
}

/** Estado a la vista: «vencida» se deriva (pendiente y vencimiento < hoy, D-087). */
export type DisplayStatus = 'overdue' | 'due_soon' | 'pending' | 'filed' | 'paid' | 'not_applicable'

export function displayStatus(o: Pick<Obligation, 'status' | 'is_overdue' | 'remind_by'>, today: string, alertDays: number): DisplayStatus {
  if (o.status !== 'pending') return o.status
  if (o.is_overdue) return 'overdue'
  return o.remind_by <= addDays(today, alertDays) ? 'due_soon' : 'pending'
}

/** "2026-11-24" + 10 → "2026-12-04" (fechas sin hora, en UTC para no correr el día). */
export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, d + days))
  return date.toISOString().slice(0, 10)
}

/** Primer día del mes `n` meses después de `month` ("2026-11" → "2027-01" con 2). */
export function shiftMonth(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number)
  const index = y * 12 + (m - 1) + n
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

/** Último día del mes "2026-02" → "2026-02-28". */
export function monthEnd(month: string): string {
  return addDays(`${shiftMonth(month, 1)}-01`, -1)
}

export type ObligationAction = 'file' | 'pay' | 'not_applicable' | 'reopen'

export const isRegister = (o: Pick<Obligation, 'code'>) => o.code === 'REG-COMPROB-MENSUAL'
export const isVat = (o: Pick<Obligation, 'code'>) => o.code === 'IVA-GENERAL-LIQUIDACION'

/** Acciones posibles según el estado (D-087): el registro no se paga. */
export function obligationActions(o: Pick<Obligation, 'code' | 'status'>): ObligationAction[] {
  if (o.status === 'pending') return ['file', 'not_applicable']
  if (o.status === 'filed') return isRegister(o) ? ['reopen'] : ['pay', 'reopen']
  return []
}

export function actionTitle(action: ObligationAction, o: Pick<Obligation, 'code'>): string {
  switch (action) {
    case 'file':
      return isRegister(o) ? 'Registro confirmado en Marangatu' : 'Marcar como presentada'
    case 'pay':
      return 'Marcar como pagada'
    case 'not_applicable':
      return 'No aplica'
    case 'reopen':
      return 'Reabrir la obligación'
  }
}

/** ¿Se puede proponer el asiento? Sin asiento vivo y no anulado (el permiso lo decide quien llama). Los ingresos y egresos del registro anual no proponen asiento (D-143). */
export function canProposeVoucher(v: Pick<Voucher, 'voided_at' | 'journal_entry_status'> & { direction?: Direction }): boolean {
  if (v.direction === 'income' || v.direction === 'expense') return false
  return !v.voided_at && (!v.journal_entry_status || v.journal_entry_status === 'reversed' || v.journal_entry_status === 'discarded')
}

/** Con asiento vivo (D-091) el comprobante solo cambia sus notas y la contraparte de finanzas. */
export const hasLiveEntry = (v: Pick<Voucher, 'journal_entry_status'>) => v.journal_entry_status === 'draft' || v.journal_entry_status === 'posted'

// --- Totales del registro

export interface Totals {
  count: number
  taxed10: bigint
  taxed5: bigint
  exempt: bigint
  vat: bigint
  total: bigint
}

const zero = (): Totals => ({ count: 0, taxed10: 0n, taxed5: 0n, exempt: 0n, vat: 0n, total: 0n })

/** Las notas de crédito restan; las anuladas no cuentan. */
export function voucherTotals(rows: Voucher[]): Record<Direction, Totals> {
  const out: Record<Direction, Totals> = { purchase: zero(), sale: zero(), income: zero(), expense: zero() }
  for (const v of rows) {
    if (v.voided_at) continue
    const t = out[v.direction]
    const sign = v.voucher_type === 'credit_note' ? -1n : 1n
    t.count += 1
    t.taxed10 += sign * BigInt(v.taxed_10)
    t.taxed5 += sign * BigInt(v.taxed_5)
    t.exempt += sign * BigInt(v.exempt)
    t.vat += sign * (BigInt(v.vat_10) + BigInt(v.vat_5))
    t.total += sign * BigInt(v.total)
  }
  return out
}

// --- Descargas -----------------------------------------------------------------------------

/** ¿El perfil vigente tiene el registro anual de comprobantes (956)? Con él se cargan ingresos y egresos (D-143). */
export const hasAnnualRegister = (profile: { current: { obligations: { code: string }[] } | null } | undefined) => Boolean(profile?.current?.obligations.some((o) => o.code === '956'))

/** Igual que `tax/router.py` (`export_vouchers`): `registro-compras-2026-10.xlsx`. */
export function voucherXlsxName(year: number, month?: number | null, direction?: Direction | null): string {
  const which = direction === 'purchase' ? 'compras' : direction === 'sale' ? 'ventas' : 'comprobantes'
  const period = month ? `${year}-${String(month).padStart(2, '0')}` : String(year)
  return `registro-${which}-${period}.xlsx`
}

/** Igual que `tax/router.py` (`vat_estimate`): `iva-2026-10.xlsx`. */
export const vatXlsxName = (year: number, month: number) => `iva-${year}-${String(month).padStart(2, '0')}.xlsx`

/**
 * Archivo de Marangatu (D-096): `<RUC>_REG_<MMAAAA>_<XXXXX>.zip`, o `…_lotes.zip` si hay más
 * de un lote de 5.000 filas. Mismo nombre que `exports.marangatu_file`.
 */
export function marangatuName(ruc: string, year: number, month: number, firstId: number, batches: number): string {
  const period = `${String(month).padStart(2, '0')}${year}`
  if (batches > 1) return `${ruc}_REG_${period}_lotes.zip`
  return `${ruc}_REG_${period}_${String(firstId).padStart(5, '0')}.zip`
}
