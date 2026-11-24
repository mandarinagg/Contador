/**
 * Estado del formulario de un comprobante y su paso al cuerpo de la API (sin componentes,
 * con pruebas en `voucherDraft.test.ts`). Los importes se escriben con formato paraguayo
 * (`1.100.000`) y se mandan como string entero (D-095).
 */
import { parseAmountInput, toInputText } from '../../lib/money'
import { parseRateInput } from '../accounting/amounts'
import { cdcDigits, checkCounterpartyRuc, includedVat, vatAccepted, voucherNumberOk, timbradoOk } from './logic'
import type { Condition, Direction, DocType, Voucher, VoucherIn, VoucherType } from './types'

export interface VoucherDraft {
  direction: Direction
  voucher_type: VoucherType
  is_electronic: boolean
  cdc: string
  timbrado: string
  number: string
  issued_on: string
  doc_type: DocType
  ruc: string
  dv: string
  document: string
  name: string
  condition: Condition
  currency: string
  fx_rate: string
  foreign_total: string
  taxed_10: string
  taxed_5: string
  exempt: string
  /** IVA impreso escrito a mano ('' = el calculado). */
  vat_10: string
  vat_5: string
  imputes_vat: boolean
  imputes_ire: boolean
  imputes_irp: boolean
  related_voucher_id: string
  finance_counterparty_id: string
  transaction_id: string
  notes: string
}

export interface Rates {
  general: string
  reduced: string
}

export const DEFAULT_RATES: Rates = { general: '0.1', reduced: '0.05' }

export function emptyDraft(direction: Direction, issuedOn: string, imputesIre = false): VoucherDraft {
  return {
    direction,
    voucher_type: 'invoice',
    is_electronic: false,
    cdc: '',
    timbrado: '',
    number: '',
    issued_on: issuedOn,
    doc_type: 'ruc',
    ruc: '',
    dv: '',
    document: '',
    name: '',
    condition: 'cash',
    currency: 'PYG',
    fx_rate: '',
    foreign_total: '',
    taxed_10: '',
    taxed_5: '',
    exempt: '',
    vat_10: '',
    vat_5: '',
    imputes_vat: true,
    imputes_ire: imputesIre,
    imputes_irp: false,
    related_voucher_id: '',
    finance_counterparty_id: '',
    transaction_id: '',
    notes: '',
  }
}

const shown = (amount: string) => (amount === '0' ? '' : toInputText(amount, 'PYG'))

export function draftFromVoucher(v: Voucher, rates: Rates = DEFAULT_RATES): VoucherDraft {
  // El IVA impreso solo se muestra «a mano» si difiere del calculado.
  const vat10 = includedVat(v.taxed_10, rates.general) === v.vat_10 ? '' : shown(v.vat_10) || '0'
  const vat5 = includedVat(v.taxed_5, rates.reduced) === v.vat_5 ? '' : shown(v.vat_5) || '0'
  return {
    direction: v.direction,
    voucher_type: v.voucher_type,
    is_electronic: v.is_electronic,
    cdc: v.cdc ?? '',
    timbrado: v.timbrado,
    number: v.number,
    issued_on: v.issued_on,
    doc_type: v.counterparty_doc_type,
    ruc: v.counterparty_ruc ?? '',
    dv: v.counterparty_ruc_dv ?? '',
    document: v.counterparty_document ?? '',
    name: v.counterparty_name,
    condition: v.condition,
    currency: v.currency,
    fx_rate: v.fx_rate ?? '',
    foreign_total: v.foreign_total ?? '',
    taxed_10: shown(v.taxed_10),
    taxed_5: shown(v.taxed_5),
    exempt: shown(v.exempt),
    vat_10: vat10,
    vat_5: vat5,
    imputes_vat: v.imputes_vat,
    imputes_ire: v.imputes_ire,
    imputes_irp: v.imputes_irp,
    related_voucher_id: v.related_voucher_id ?? '',
    finance_counterparty_id: v.finance_counterparty_id ?? '',
    transaction_id: v.transaction_id ?? '',
    notes: v.notes ?? '',
  }
}

/** Importe en guaraníes enteros no negativos; '' cuenta como 0. */
export function readPyg(text: string): { ok: true; value: string } | { ok: false; error: string } {
  if (!text.trim()) return { ok: true, value: '0' }
  const parsed = parseAmountInput(text, 'PYG')
  if (!parsed.ok) return parsed
  if (parsed.value.startsWith('-')) return { ok: false, error: 'Va en positivo: el tipo de comprobante ya dice si suma o resta.' }
  return parsed
}

export interface VatLine {
  amount: string | null
  calculated: string | null
  printed: string | null
  /** Lo que se guarda: el impreso si se escribió, si no el calculado. */
  effective: string | null
  error?: string
}

/** IVA de una tasa mientras se escribe: calculado, impreso y si la diferencia se acepta (±1). */
export function vatLine(amountText: string, printedText: string, rate: string): VatLine {
  const amount = readPyg(amountText)
  if (!amount.ok) return { amount: null, calculated: null, printed: null, effective: null }
  const calculated = includedVat(amount.value, rate)
  if (!printedText.trim()) return { amount: amount.value, calculated, printed: null, effective: calculated }
  const printed = readPyg(printedText)
  if (!printed.ok) return { amount: amount.value, calculated, printed: null, effective: null, error: printed.error }
  if (!vatAccepted(printed.value, calculated)) {
    return {
      amount: amount.value,
      calculated,
      printed: printed.value,
      effective: null,
      error: `Difiere en más de 1 guaraní del calculado (${toInputText(calculated, 'PYG')}). Revisá el importe o el IVA impreso.`,
    }
  }
  return { amount: amount.value, calculated, printed: printed.value, effective: printed.value }
}

export type DraftErrors = Partial<Record<keyof VoucherDraft | 'amounts', string>>

/**
 * Valida lo que se puede validar antes de mandar (la API vuelve a validar todo) y arma el
 * cuerpo.
 */
export function draftToBody(d: VoucherDraft, rates: Rates = DEFAULT_RATES): { body: VoucherIn | null; errors: DraftErrors } {
  const errors: DraftErrors = {}
  if (!timbradoOk(d.timbrado)) errors.timbrado = 'El timbrado tiene 8 dígitos.'
  if (!voucherNumberOk(d.number)) errors.number = 'El número va como 001-001-0000001 (establecimiento, punto y número).'
  if (!d.issued_on) errors.issued_on = 'Indicá la fecha del comprobante.'
  if (d.is_electronic && cdcDigits(d.cdc).length !== 44) errors.cdc = 'El CDC tiene 44 dígitos (los del KuDE).'
  const docType: DocType = d.direction === 'purchase' ? 'ruc' : d.doc_type
  if (docType === 'ruc') {
    const check = checkCounterpartyRuc(d.ruc, d.dv)
    if (check.kind === 'empty') errors.ruc = d.direction === 'purchase' ? 'Una compra lleva el RUC del proveedor: sin RUC no hay crédito fiscal.' : 'Indicá el RUC del cliente.'
    else if (check.kind === 'invalid') errors.ruc = check.message
    else if (check.kind === 'missing_dv') errors.dv = `Falta el dígito verificador (para ese RUC es ${check.expected}).`
    else if (check.kind === 'wrong_dv') errors.dv = `Para ese RUC el dígito verificador es ${check.expected}.`
  } else if (docType !== 'unnamed' && !d.document.trim()) {
    errors.document = 'Indicá el número de documento.'
  }
  if (docType !== 'unnamed' && !d.name.trim()) errors.name = 'Indicá el nombre o la razón social.'
  if (d.voucher_type !== 'invoice' && !d.related_voucher_id) errors.related_voucher_id = 'Una nota referencia la factura que corrige.'

  const t10 = readPyg(d.taxed_10)
  const t5 = readPyg(d.taxed_5)
  const ex = readPyg(d.exempt)
  if (!t10.ok) errors.taxed_10 = t10.error
  if (!t5.ok) errors.taxed_5 = t5.error
  if (!ex.ok) errors.exempt = ex.error
  const v10 = vatLine(d.taxed_10, d.vat_10, rates.general)
  const v5 = vatLine(d.taxed_5, d.vat_5, rates.reduced)
  if (v10.error) errors.vat_10 = v10.error
  if (v5.error) errors.vat_5 = v5.error
  if (t10.ok && t5.ok && ex.ok && BigInt(t10.value) + BigInt(t5.value) + BigInt(ex.value) === 0n) errors.amounts = 'El comprobante tiene que tener algún importe.'

  let fx: { fx_rate: string; foreign_total: string } | null = null
  if (d.currency !== 'PYG') {
    const total = parseAmountInput(d.foreign_total, d.currency)
    const rate = parseRateInput(d.fx_rate)
    if (!rate.ok) errors.fx_rate = rate.error
    if (!total.ok) errors.foreign_total = total.error
    else if (total.value.startsWith('-')) errors.foreign_total = 'Va en positivo.'
    if (rate.ok && total.ok) fx = { fx_rate: rate.value, foreign_total: total.value }
  }

  if (Object.keys(errors).length > 0 || !t10.ok || !t5.ok || !ex.ok) return { body: null, errors }
  const body: VoucherIn = {
    direction: d.direction,
    voucher_type: d.voucher_type,
    is_electronic: d.is_electronic,
    cdc: d.is_electronic ? cdcDigits(d.cdc) : null,
    timbrado: d.timbrado,
    number: d.number,
    issued_on: d.issued_on,
    counterparty_doc_type: docType,
    counterparty_ruc: docType === 'ruc' ? d.ruc.trim().toUpperCase() : null,
    counterparty_ruc_dv: docType === 'ruc' && /^\d+$/.test(d.ruc.trim()) ? d.dv : null,
    counterparty_document: docType !== 'ruc' && docType !== 'unnamed' ? d.document.trim() : null,
    counterparty_name: d.name.trim() || null,
    condition: d.condition,
    currency: d.currency,
    fx_rate: fx?.fx_rate ?? null,
    foreign_total: fx?.foreign_total ?? null,
    taxed_10: t10.value,
    taxed_5: t5.value,
    exempt: ex.value,
    imputes_vat: d.imputes_vat,
    imputes_ire: d.imputes_ire,
    imputes_irp: d.imputes_irp,
    related_voucher_id: d.voucher_type !== 'invoice' ? d.related_voucher_id || null : null,
    finance_counterparty_id: d.finance_counterparty_id || null,
    transaction_id: d.transaction_id || null,
    notes: d.notes.trim() || null,
  }
  // Solo el impreso escrito a mano: si no, la API calcula el mismo que se ve (BR-TAX-09).
  if (v10.printed !== null) body.vat_10 = v10.printed
  if (v5.printed !== null) body.vat_5 = v5.printed
  return { body, errors }
}

/** Errores de la API que corresponden a un campo del formulario (los demás van en un aviso general). */
export function fieldOfApiError(code: string, details: unknown): keyof VoucherDraft | null {
  switch (code) {
    case 'VAT_MISMATCH':
      return ((details as { field?: string } | null)?.field as keyof VoucherDraft) ?? 'vat_10'
    case 'RUC_CHECK_DIGIT_INVALID':
      return 'dv'
    case 'COUNTERPARTY_RUC_REQUIRED':
    case 'COUNTERPARTY_RUC_MISMATCH':
      return 'ruc'
    case 'COUNTERPARTY_DOCUMENT_REQUIRED':
      return 'document'
    case 'COUNTERPARTY_NAME_REQUIRED':
      return 'name'
    case 'CDC_REQUIRED':
    case 'CDC_NOT_APPLICABLE':
    case 'CDC_CHECK_DIGIT_INVALID':
    case 'CDC_MISMATCH':
      return 'cdc'
    case 'FX_RATE_REQUIRED':
    case 'FX_NOT_APPLICABLE':
      return 'fx_rate'
    case 'FX_TOTAL_MISMATCH':
      return 'foreign_total'
    case 'RELATED_VOUCHER_REQUIRED':
    case 'RELATED_VOUCHER_NOT_FOUND':
    case 'RELATED_VOUCHER_INVALID':
    case 'VOUCHER_NOTE_MISMATCH':
    case 'CREDIT_NOTE_EXCEEDS_ORIGINAL':
      return 'related_voucher_id'
    case 'VOUCHER_TOTAL_ZERO':
      return 'taxed_10'
    default:
      return null
  }
}

/** Siguiente número del talonario propio (ventas): `001-001-0000007` → `001-001-0000008`. */
export function nextNumber(number: string): string {
  const m = /^(\d{3})-(\d{3})-(\d{7})$/.exec(number)
  if (!m || m[3] === '9999999') return ''
  return `${m[1]}-${m[2]}-${String(Number(m[3]) + 1).padStart(7, '0')}`
}
