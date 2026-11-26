/**
 * Ingresos y egresos del registro anual (956) del IRP-RSP, sin timbrado (D-143): qué columnas
 * pide cada tipo y el paso del formulario al cuerpo de la API (pruebas en
 * `registerDraft.test.ts`). Las reglas copian las de `backend/app/modules/tax/vouchers.py`
 * (`_validated_register`), que son las del formato oficial
 * (`docs/research/formato_registro_comprobantes.yaml`, INGRESOS y EGRESOS).
 */
import { checkCounterpartyRuc, readPyg, timbradoOk, voucherNumberOk } from './logic'
import type { Direction, DocType, RegisterDirection, RegisterVoucherType, VoucherIn, VoucherType } from './types'
import type { DraftErrors, VoucherDraft } from './voucherDraft'

/** Tipos de la Tabla 4 que admite cada registro, los más usados primero. */
export const REGISTER_TYPES: Record<RegisterDirection, RegisterVoucherType[]> = {
  income: ['other_income', 'payslip', 'credit_sale'],
  expense: ['ips_statement', 'card_statement', 'payslip', 'other_expense', 'bank_transfer', 'credit_purchase', 'foreign_voucher', 'public_entity', 'e_ticketing'],
}

export const isRegister = (direction: Direction): direction is RegisterDirection => direction === 'income' || direction === 'expense'

const ALL_DOC_TYPES: DocType[] = ['ruc', 'identity_card', 'passport', 'foreign_id', 'diplomatic', 'tax_id']

export interface RegisterFields {
  /** Número obligatorio (columna 4); sin número en 205 a 208. */
  numberRequired: boolean
  /** Fecha como período mm/aaaa (206 y 208). */
  period: boolean
  /** Sin contraparte obligatoria (206, 207 y 211 en EGRESOS). */
  counterpartyOptional: boolean
  docTypes: DocType[]
  /** Cuenta o tarjeta y banco (207 y 211). */
  account: boolean
  ipsEmployer: boolean
  /** «Especificar tipo de documento» (209 y 210). */
  description: boolean
  /** Número y timbrado del comprobante asociado (201 y 203). */
  related: boolean
  /** INGRESOS: gravado y no gravado; EGRESOS: solo el total. */
  split: boolean
}

export function registerFields(direction: RegisterDirection, type: VoucherType): RegisterFields {
  const expense = direction === 'expense'
  const docTypes: DocType[] =
    (direction === 'income' && type === 'payslip') || (expense && (type === 'public_entity' || type === 'e_ticketing'))
      ? ['ruc']
      : direction === 'income' && type === 'other_income'
        ? ['ruc', 'identity_card', 'passport']
        : expense && type === 'foreign_voucher'
          ? ['tax_id']
          : ALL_DOC_TYPES
  return {
    numberRequired: !(type === 'payslip' || (expense && (type === 'e_ticketing' || type === 'ips_statement' || type === 'card_statement'))),
    period: type === 'ips_statement' || type === 'payslip',
    counterpartyOptional: expense && (type === 'ips_statement' || type === 'card_statement' || type === 'bank_transfer'),
    docTypes,
    account: expense && (type === 'card_statement' || type === 'bank_transfer'),
    ipsEmployer: type === 'ips_statement',
    description: type === 'other_expense' || type === 'other_income',
    related: type === 'credit_purchase' || type === 'credit_sale',
    split: !expense,
  }
}

/** Cambia el tipo y acomoda lo que depende de él (identificación, sin contraparte, período). */
export function withRegisterType(d: VoucherDraft, type: VoucherType): VoucherDraft {
  if (!isRegister(d.direction)) return { ...d, voucher_type: type }
  const f = registerFields(d.direction, type)
  return {
    ...d,
    voucher_type: type,
    doc_type: f.docTypes.includes(d.doc_type) ? d.doc_type : f.docTypes[0],
    no_counterparty: f.counterpartyOptional && (type === 'ips_statement' || type === 'card_statement'),
    issued_on: f.period && d.issued_on ? `${d.issued_on.slice(0, 7)}-01` : d.issued_on,
  }
}

/** Lo que cambia al pasar un borrador a ingreso o egreso: sin timbrado, sin CDC, sin IVA. */
export function defaultRegisterDraft(d: VoucherDraft, direction: RegisterDirection): VoucherDraft {
  return withRegisterType(
    {
      ...d,
      direction,
      is_electronic: false,
      cdc: '',
      timbrado: '',
      number: '',
      condition: 'cash',
      currency: 'PYG',
      fx_rate: '',
      foreign_total: '',
      taxed_5: '',
      vat_10: '',
      vat_5: '',
      imputes_vat: false,
      imputes_irp: true,
      related_voucher_id: '',
      transaction_id: '',
    },
    REGISTER_TYPES[direction][0],
  )
}

const REGISTER_NUMBER = /^[0-9A-Za-z./\- ]{1,20}$/
const MIN_DATE = '2021-01-01'

/** Valida lo que se puede antes de mandar (la API vuelve a validar todo) y arma el cuerpo. */
export function registerDraftToBody(d: VoucherDraft): {
  body: VoucherIn | null
  errors: DraftErrors
} {
  const errors: DraftErrors = {}
  if (!isRegister(d.direction)) throw new Error('registerDraftToBody: no es un ingreso ni un egreso')
  const f = registerFields(d.direction, d.voucher_type)
  if (!REGISTER_TYPES[d.direction].includes(d.voucher_type as RegisterVoucherType)) errors.voucher_type = 'Elegí un tipo de este registro.'
  const issuedOn = f.period && d.issued_on ? `${d.issued_on.slice(0, 7)}-01` : d.issued_on
  if (!issuedOn) errors.issued_on = f.period ? 'Indicá el período (mes y año).' : 'Indicá la fecha del comprobante.'
  else if (issuedOn < MIN_DATE) errors.issued_on = 'El registro no admite fechas anteriores al 01/01/2021.'

  const number = d.number.trim()
  if (number && !REGISTER_NUMBER.test(number)) errors.number = 'Hasta 20 posiciones: números, letras, «/» o «-».'
  else if (!number && f.numberRequired) errors.number = 'Indicá el número del comprobante o de la transacción.'

  const none = f.counterpartyOptional && d.no_counterparty
  const docType: DocType | null = none ? null : d.doc_type
  if (docType !== null && !f.docTypes.includes(docType)) errors.doc_type = 'Ese tipo de identificación no va con este comprobante.'
  if (docType === 'ruc') {
    const check = checkCounterpartyRuc(d.ruc, d.dv)
    if (check.kind === 'empty') errors.ruc = 'Indicá el RUC.'
    else if (check.kind === 'invalid') errors.ruc = check.message
    else if (check.kind === 'missing_dv') errors.dv = `Falta el dígito verificador (para ese RUC es ${check.expected}).`
    else if (check.kind === 'wrong_dv') errors.dv = `Para ese RUC el dígito verificador es ${check.expected}.`
  } else if (docType !== null && !d.document.trim()) {
    errors.document = 'Indicá el número de documento.'
  }
  if (!d.name.trim() && d.voucher_type !== 'ips_statement') errors.name = none ? 'Indicá un nombre o una descripción.' : 'Indicá el nombre o la razón social.'

  const text = (value: string, need: boolean, key: keyof VoucherDraft, message: string) => {
    const v = value.trim()
    if (need && !v) errors[key] = message
    return need && v ? v : null
  }
  const account = text(d.account_number, f.account, 'account_number', 'Indicá el número de cuenta o de tarjeta.')
  const bank = text(d.bank_name, f.account, 'bank_name', 'Indicá el banco, la financiera o la cooperativa.')
  const employer = text(d.ips_employer_number, f.ipsEmployer, 'ips_employer_number', 'Indicá el número de empleador en IPS.')
  const description = text(d.document_description, f.description, 'document_description', 'Indicá qué tipo de documento es.')
  const relatedNumber = text(d.related_number, f.related, 'related_number', 'Indicá el número del comprobante asociado.')
  const relatedTimbrado = text(d.related_timbrado, f.related, 'related_timbrado', 'Indicá el timbrado del comprobante asociado.')
  if (relatedNumber && !voucherNumberOk(relatedNumber)) errors.related_number = 'Va como 001-001-0000001.'
  if (relatedTimbrado && !timbradoOk(relatedTimbrado)) errors.related_timbrado = 'El timbrado tiene 8 dígitos.'

  const taxed = readPyg(d.taxed_10)
  const untaxed = f.split ? readPyg(d.exempt) : ({ ok: true, value: '0' } as const)
  if (!taxed.ok) errors.taxed_10 = taxed.error
  if (!untaxed.ok) errors.exempt = untaxed.error
  if (taxed.ok && untaxed.ok && BigInt(taxed.value) + BigInt(untaxed.value) === 0n) errors.amounts = 'El comprobante tiene que tener algún importe.'

  if (Object.keys(errors).length > 0 || !taxed.ok || !untaxed.ok) return { body: null, errors }
  const body: VoucherIn = {
    direction: d.direction,
    voucher_type: d.voucher_type,
    is_electronic: false,
    cdc: null,
    timbrado: null,
    number: number || null,
    issued_on: issuedOn,
    counterparty_doc_type: docType,
    counterparty_ruc: docType === 'ruc' ? d.ruc.trim().toUpperCase() : null,
    counterparty_ruc_dv: docType === 'ruc' && /^\d+$/.test(d.ruc.trim()) ? d.dv : null,
    counterparty_document: docType !== null && docType !== 'ruc' ? d.document.trim() : null,
    counterparty_name: d.name.trim() || null,
    condition: 'cash',
    currency: 'PYG',
    fx_rate: null,
    foreign_total: null,
    taxed_10: taxed.value,
    taxed_5: '0',
    exempt: untaxed.value,
    imputes_vat: false,
    imputes_ire: d.imputes_ire,
    imputes_irp: d.imputes_irp,
    related_voucher_id: null,
    finance_counterparty_id: d.finance_counterparty_id || null,
    transaction_id: d.transaction_id || null,
    notes: d.notes.trim() || null,
    account_number: account,
    bank_name: bank,
    ips_employer_number: employer,
    document_description: description,
    related_number: relatedNumber,
    related_timbrado: relatedTimbrado,
  }
  return { body, errors }
}

/** Fecha o período como en el formato oficial: «04/2026» en 206 y 208, «20/05/2026» en los demás. */
export function registerDate(v: { direction: Direction; voucher_type: VoucherType; issued_on: string }): string {
  const [y, m, day] = v.issued_on.split('-')
  return isRegister(v.direction) && registerFields(v.direction, v.voucher_type).period ? `${m}/${y}` : `${day}/${m}/${y}`
}

/** «Extracto de cuenta de IPS (206) 04/2026» o «Factura 001-001-0000001». */
export function voucherLabel(
  v: {
    direction: Direction
    voucher_type: VoucherType
    issued_on: string
    number: string | null
  },
  typeLabel: string,
): string {
  if (v.number) return `${typeLabel} ${v.number}`
  return `${typeLabel} ${registerDate(v)}`
}

/** `1234567_REG_2026_00001.zip` (956, como `exports.marangatu_file`). */
export function annualRegisterName(ruc: string, year: number, firstId: number, batches: number): string {
  if (batches > 1) return `${ruc}_REG_${year}_lotes.zip`
  return `${ruc}_REG_${year}_${String(firstId).padStart(5, '0')}.zip`
}
