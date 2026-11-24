/**
 * Estado del editor de asientos (sin componentes): líneas tal como se escriben, totales en
 * vivo y armado del cuerpo para la API. Todo importe se interpreta con `parseAmountInput` y
 * se suma con `BigInt` (amounts.ts): nunca con `number`.
 */
import { isZeroAmount, parseAmountInput, toInputText } from '../../lib/money'
import { absPyg, comparePyg, formatDecimal, isZeroPyg, parseRateInput, subPyg, sumPyg } from './amounts'
import type { Entry, EntryIn, EntryLineIn, LedgerKind } from './types'

export interface FxDraft {
  currency: string
  amount: string
  rate: string
}

export interface LineDraft {
  key: string
  account_id: string
  debit: string
  credit: string
  description: string
  fx: FxDraft | null
  /** Centro de costos: solo en cuentas de ingreso o gasto (D-060). */
  cost_center_id: string
}

export interface HeaderDraft {
  entry_date: string
  description: string
  document_reference: string
}

let seq = 0
const nextKey = () => `l${++seq}`

export function emptyLine(partial: Partial<LineDraft> = {}): LineDraft {
  return { key: nextKey(), account_id: '', debit: '', credit: '', description: '', fx: null, cost_center_id: '', ...partial }
}

/** Líneas editables a partir de un asiento de la API (borrador existente). */
export function linesFromEntry(entry: Pick<Entry, 'lines'>): LineDraft[] {
  return (entry.lines ?? []).map((l) =>
    emptyLine({
      account_id: l.account_id,
      debit: isZeroPyg(l.debit) ? '' : toInputText(l.debit, 'PYG'),
      credit: isZeroPyg(l.credit) ? '' : toInputText(l.credit, 'PYG'),
      description: l.description ?? '',
      cost_center_id: l.cost_center_id ?? '',
      fx:
        l.fx_currency && l.fx_amount && l.fx_rate
          ? { currency: l.fx_currency, amount: toInputText(l.fx_amount, l.fx_currency), rate: formatDecimal(l.fx_rate) }
          : null,
    }),
  )
}

/** Una línea sin cuenta, sin importes y sin descripción no cuenta (se descarta al guardar). */
export const isBlankLine = (l: LineDraft) => !l.account_id && !l.debit.trim() && !l.credit.trim() && !l.description.trim() && !l.fx && !l.cost_center_id

/** Importe en guaraníes de una celda: el valor canónico, `''` si está vacía o el error. */
export function readPyg(text: string): { value: string } | { error: string } {
  if (!text.trim()) return { value: '' }
  const parsed = parseAmountInput(text, 'PYG')
  if (!parsed.ok) return { error: parsed.error }
  if (parsed.value.startsWith('-')) return { error: 'Sin signo: el lado (debe o haber) ya dice el sentido.' }
  return { value: parsed.value }
}

const valueOr0 = (text: string) => {
  const r = readPyg(text)
  return 'value' in r && r.value ? r.value : '0'
}

export interface Totals {
  debit: string
  credit: string
  /** debe − haber: positivo = falta haber; negativo = falta debe. */
  difference: string
  balanced: boolean
  /** Hay importes (el total no es cero). */
  hasAmounts: boolean
}

/** Totales en vivo: las celdas inválidas cuentan como cero (su error se ve en la celda). */
export function totalsOf(lines: LineDraft[]): Totals {
  const debit = sumPyg(lines.map((l) => valueOr0(l.debit)))
  const credit = sumPyg(lines.map((l) => valueOr0(l.credit)))
  const difference = subPyg(debit, credit)
  const hasAmounts = !isZeroPyg(debit) || !isZeroPyg(credit)
  return { debit, credit, difference, balanced: hasAmounts && isZeroPyg(difference), hasAmounts }
}

/** Lo que le falta a una línea nueva para balancear: `{credit}` si sobra debe, `{debit}` si sobra haber. */
export function remainderFor(lines: LineDraft[]): Partial<LineDraft> {
  const { difference } = totalsOf(lines)
  const cmp = comparePyg(difference, '0')
  if (cmp === 0) return {}
  const text = toInputText(absPyg(difference), 'PYG')
  return cmp > 0 ? { credit: text } : { debit: text }
}

export type LineErrors = Partial<Record<'account' | 'amount' | 'fx' | 'center', string>>

/** Tipo de la cuenta de una línea (para decidir si lleva centro de costos). */
export type KindOf = (accountId: string) => LedgerKind | undefined

/** Un centro de costos solo va en cuentas de ingreso o de gasto (D-060, BR-ACC-16). */
export const centerAllowed = (kind: LedgerKind | undefined) => kind === 'income' || kind === 'expense'

export interface BuildResult {
  body: EntryIn | null
  header: Partial<Record<keyof HeaderDraft, string>>
  lines: Record<string, LineErrors>
  /** Error general (sin líneas). */
  general?: string
}

export interface LinesResult {
  lines: EntryLineIn[]
  errors: Record<string, LineErrors>
  general?: string
}

/**
 * Valida y arma las líneas para la API: cada una con cuenta y exactamente un importe mayor
 * que cero; la moneda extranjera completa o nada; el centro de costos solo si la cuenta es de
 * resultado (si la cuenta cambió a una patrimonial, el centro se descarta).
 */
export function buildLines(lines: LineDraft[], kindOf: KindOf = () => undefined): LinesResult {
  const result: LinesResult = { lines: [], errors: {} }
  const used = lines.filter((l) => !isBlankLine(l))
  if (used.length === 0) result.general = 'Agregá al menos una línea.'
  for (const l of used) {
    const errors: LineErrors = {}
    if (!l.account_id) errors.account = 'Elegí la cuenta.'
    const d = readPyg(l.debit)
    const c = readPyg(l.credit)
    let debit = ''
    let credit = ''
    if ('error' in d) errors.amount = d.error
    else if ('error' in c) errors.amount = c.error
    else {
      debit = d.value && !isZeroPyg(d.value) ? d.value : ''
      credit = c.value && !isZeroPyg(c.value) ? c.value : ''
      if (debit && credit) errors.amount = 'Una línea lleva debe o haber, no los dos.'
      else if (!debit && !credit) errors.amount = 'Escribí el importe en el debe o en el haber.'
    }
    const line: EntryLineIn = { account_id: l.account_id, description: l.description.trim() || null }
    if (debit) line.debit = debit
    if (credit) line.credit = credit
    if (l.cost_center_id && centerAllowed(kindOf(l.account_id))) line.cost_center_id = l.cost_center_id
    if (l.fx) {
      const amount = parseAmountInput(l.fx.amount, l.fx.currency)
      const rate = parseRateInput(l.fx.rate)
      if (!l.fx.amount.trim() || !l.fx.rate.trim()) errors.fx = 'Completá el importe en moneda extranjera y la cotización, o quitá la moneda extranjera.'
      else if (!amount.ok) errors.fx = amount.error
      else if (amount.value.startsWith('-') || isZeroAmount(amount.value)) errors.fx = 'El importe en moneda extranjera va en positivo.'
      else if (!rate.ok) errors.fx = rate.error
      else {
        line.fx_currency = l.fx.currency
        line.fx_amount = amount.value
        line.fx_rate = rate.value
      }
    }
    if (Object.keys(errors).length) result.errors[l.key] = errors
    result.lines.push(line)
  }
  return result
}

/**
 * Valida y arma el cuerpo de `POST/PATCH /accounting/entries`. El borrador puede estar
 * desbalanceado (lo valida el contabilizar).
 */
export function buildEntry(header: HeaderDraft, lines: LineDraft[], kindOf?: KindOf): BuildResult {
  const result: BuildResult = { body: null, header: {}, lines: {} }
  if (!header.entry_date) result.header.entry_date = 'Elegí la fecha del asiento.'
  if (!header.description.trim()) result.header.description = 'Escribí qué registra el asiento.'
  const built = buildLines(lines, kindOf)
  result.lines = built.errors
  result.general = built.general
  if (Object.keys(result.header).length || Object.keys(result.lines).length || result.general) return result
  result.body = {
    entry_date: header.entry_date,
    description: header.description.trim(),
    document_reference: header.document_reference.trim() || null,
    lines: built.lines,
  }
  return result
}

/**
 * Líneas de ingreso o gasto sin centro cuando la configuración lo exige
 * (`cost_centers_required`): no impiden guardar el borrador, sí contabilizarlo.
 */
export function missingCenters(lines: LineDraft[], kindOf: KindOf, required: boolean): string[] {
  if (!required) return []
  return lines.filter((l) => !isBlankLine(l) && l.account_id && centerAllowed(kindOf(l.account_id)) && !l.cost_center_id).map((l) => l.key)
}

/** Huella para saber si hay cambios sin guardar. */
export const fingerprint = (header: HeaderDraft, lines: LineDraft[]) =>
  JSON.stringify([header, lines.filter((l) => !isBlankLine(l)).map(({ key: _k, ...rest }) => rest)])
