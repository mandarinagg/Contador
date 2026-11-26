import { describe, expect, it } from 'vitest'
import { annualRegisterName, defaultRegisterDraft, registerDate, registerDraftToBody, registerFields, voucherLabel, withRegisterType } from './registerDraft'
import { canProposeVoucher, hasAnnualRegister, voucherTotals } from './logic'
import type { Voucher } from './types'
import { draftFromVoucher, draftToBody, emptyDraft, fieldOfApiError, type VoucherDraft } from './voucherDraft'

/** Otro comprobante de ingreso (210): honorarios cobrados a una persona con cédula. */
const income = (over: Partial<VoucherDraft> = {}): VoucherDraft => ({
  ...emptyDraft('income', '2026-03-10'),
  doc_type: 'identity_card',
  document: '2345678',
  name: ' Juan Pérez ',
  number: 'R-15',
  document_description: 'Recibo de honorarios',
  taxed_10: '300.000',
  exempt: '50.000',
  ...over,
})

/** Extracto de cuenta de IPS (206): período, sin número ni contraparte. */
const ips = (over: Partial<VoucherDraft> = {}): VoucherDraft => ({
  ...withRegisterType(emptyDraft('expense', '2026-04-18'), 'ips_statement'),
  ips_employer_number: '0012345',
  taxed_10: '450.000',
  ...over,
})

describe('registerFields', () => {
  it('pide en cada tipo las columnas del formato oficial', () => {
    expect(registerFields('income', 'payslip')).toMatchObject({ numberRequired: false, period: true, docTypes: ['ruc'], split: true })
    expect(registerFields('expense', 'payslip')).toMatchObject({ numberRequired: false, period: true, split: false })
    expect(registerFields('expense', 'ips_statement')).toMatchObject({ ipsEmployer: true, counterpartyOptional: true, account: false })
    expect(registerFields('expense', 'card_statement')).toMatchObject({ account: true, numberRequired: false, period: false })
    expect(registerFields('expense', 'bank_transfer')).toMatchObject({ account: true, numberRequired: true, counterpartyOptional: true })
    expect(registerFields('income', 'other_income')).toMatchObject({ description: true, docTypes: ['ruc', 'identity_card', 'passport'] })
    expect(registerFields('expense', 'foreign_voucher').docTypes).toEqual(['tax_id'])
    expect(registerFields('income', 'credit_sale')).toMatchObject({ related: true, description: false })
    expect(registerFields('expense', 'e_ticketing')).toMatchObject({ numberRequired: false, docTypes: ['ruc'] })
  })
})

describe('borrador de ingreso o egreso', () => {
  it('empieza sin timbrado, sin IVA y al IRP', () => {
    const d = emptyDraft('expense', '2026-04-18')
    expect(d).toMatchObject({ voucher_type: 'ips_statement', imputes_vat: false, imputes_irp: true, no_counterparty: true, issued_on: '2026-04-01' })
    expect(emptyDraft('income', '2026-03-10').voucher_type).toBe('other_income')
  })

  it('al pasar de una compra a un egreso borra el timbrado, el CDC y el IVA', () => {
    const purchase = { ...emptyDraft('purchase', '2026-05-20'), timbrado: '12345678', number: '001-001-0000001', is_electronic: true, cdc: '0'.repeat(44), vat_10: '5', taxed_5: '10' }
    const d = defaultRegisterDraft(purchase, 'expense')
    expect(d).toMatchObject({ direction: 'expense', timbrado: '', number: '', is_electronic: false, cdc: '', vat_10: '', taxed_5: '', imputes_vat: false })
  })

  it('al cambiar el tipo ajusta la identificación y el día del período', () => {
    const d = withRegisterType(income({ issued_on: '2026-02-25' }), 'payslip')
    expect(d.doc_type).toBe('ruc')
    expect(d.issued_on).toBe('2026-02-01')
  })
})

describe('registerDraftToBody', () => {
  it('arma un ingreso con gravado y no gravado', () => {
    const { body, errors } = registerDraftToBody(income())
    expect(errors).toEqual({})
    expect(body).toMatchObject({
      direction: 'income',
      voucher_type: 'other_income',
      timbrado: null,
      number: 'R-15',
      counterparty_doc_type: 'identity_card',
      counterparty_document: '2345678',
      counterparty_ruc: null,
      counterparty_name: 'Juan Pérez',
      taxed_10: '300000',
      exempt: '50000',
      taxed_5: '0',
      imputes_vat: false,
      imputes_irp: true,
      document_description: 'Recibo de honorarios',
      account_number: null,
      related_number: null,
    })
  })

  it('arma un extracto de IPS sin número ni contraparte, con el período el día 1', () => {
    const { body, errors } = draftToBody(ips())
    expect(errors).toEqual({})
    expect(body).toMatchObject({ issued_on: '2026-04-01', number: null, counterparty_doc_type: null, counterparty_name: null, ips_employer_number: '0012345', exempt: '0', taxed_10: '450000' })
  })

  it('en un egreso no manda el no gravado aunque quede escrito', () => {
    expect(registerDraftToBody(ips({ exempt: '9.999' })).body?.exempt).toBe('0')
  })

  it('pide lo que el tipo exige', () => {
    expect(registerDraftToBody(income({ number: '' })).errors.number).toMatch(/número/)
    expect(registerDraftToBody(income({ document_description: ' ' })).errors.document_description).toBeDefined()
    expect(registerDraftToBody(income({ document: '' })).errors.document).toBeDefined()
    expect(registerDraftToBody(income({ taxed_10: '', exempt: '' })).errors.amounts).toBeDefined()
    expect(registerDraftToBody(income({ issued_on: '2020-12-31' })).errors.issued_on).toMatch(/2021/)
    expect(registerDraftToBody(income({ number: 'R#1' })).errors.number).toBeDefined()
    expect(registerDraftToBody(ips({ ips_employer_number: '' })).errors.ips_employer_number).toBeDefined()
    const card = withRegisterType(emptyDraft('expense', '2026-05-20'), 'card_statement')
    const errors = registerDraftToBody({ ...card, taxed_10: '1' }).errors
    expect(Object.keys(errors).sort()).toEqual(['account_number', 'bank_name', 'name'])
  })

  it('valida el RUC con su DV y el comprobante asociado de la venta a crédito', () => {
    const payslip = withRegisterType(income(), 'payslip')
    expect(registerDraftToBody({ ...payslip, ruc: '80000005', dv: '9' }).errors.dv).toMatch(/dígito verificador/)
    const credit = withRegisterType(income(), 'credit_sale')
    const { errors } = registerDraftToBody({ ...credit, related_number: '1-1-1', related_timbrado: '123' })
    expect(errors.related_number).toMatch(/001-001-0000001/)
    expect(errors.related_timbrado).toMatch(/8 dígitos/)
    expect(errors.document_description).toBeUndefined()
  })

  it('no acepta una identificación que el tipo no admite', () => {
    const payslip = withRegisterType(income(), 'payslip')
    expect(registerDraftToBody({ ...payslip, doc_type: 'identity_card' }).errors.doc_type).toBeDefined()
  })
})

const voucher = (over: Partial<Voucher>): Voucher =>
  ({
    id: 'v1',
    direction: 'expense',
    voucher_type: 'card_statement',
    is_electronic: false,
    cdc: null,
    timbrado: null,
    number: null,
    issued_on: '2026-05-20',
    counterparty_doc_type: null,
    counterparty_ruc: null,
    counterparty_ruc_dv: null,
    counterparty_document: null,
    counterparty_name: 'Gastos médicos',
    taxed_10: '800000',
    taxed_5: '0',
    exempt: '0',
    total: '800000',
    vat_10: '0',
    vat_5: '0',
    imputes_vat: false,
    imputes_ire: false,
    imputes_irp: true,
    account_number: '4111-XXXX-1234',
    bank_name: 'Banco Uno',
    ips_employer_number: null,
    document_description: null,
    related_number: null,
    related_timbrado: null,
    related_voucher_id: null,
    finance_counterparty_id: null,
    transaction_id: null,
    journal_entry_status: null,
    voided_at: null,
    notes: null,
    currency: 'PYG',
    fx_rate: null,
    foreign_total: null,
    condition: 'cash',
    ...over,
  }) as Voucher

describe('ingresos y egresos guardados', () => {
  it('vuelven al formulario sin perder lo propio del tipo', () => {
    const d = draftFromVoucher(voucher({}))
    expect(d).toMatchObject({ no_counterparty: true, account_number: '4111-XXXX-1234', bank_name: 'Banco Uno', number: '', timbrado: '', taxed_10: '800.000' })
    expect(draftToBody(d).body).toMatchObject({ counterparty_doc_type: null, account_number: '4111-XXXX-1234', bank_name: 'Banco Uno', number: null })
  })

  it('se muestran con su período o fecha y no proponen asiento', () => {
    expect(registerDate(voucher({ voucher_type: 'ips_statement', issued_on: '2026-04-01' }))).toBe('04/2026')
    expect(registerDate(voucher({}))).toBe('20/05/2026')
    expect(voucherLabel(voucher({}), 'Extracto')).toBe('Extracto 20/05/2026')
    expect(voucherLabel(voucher({ number: 'TRX-9' }), 'Transferencia')).toBe('Transferencia TRX-9')
    expect(canProposeVoucher(voucher({}))).toBe(false)
    expect(canProposeVoucher(voucher({ direction: 'purchase' }))).toBe(true)
  })

  it('suman aparte de las compras y ventas', () => {
    const t = voucherTotals([voucher({}), voucher({ id: 'v2', direction: 'income', voucher_type: 'other_income', taxed_10: '300000', exempt: '50000', total: '350000' })])
    expect(t.expense.total).toBe(800000n)
    expect(t.income).toMatchObject({ count: 1, taxed10: 300000n, exempt: 50000n, total: 350000n })
    expect(t.purchase.count).toBe(0)
  })

  it('ubica en su campo los errores de la API', () => {
    expect(fieldOfApiError('FIELD_REQUIRED', { field: 'bank_name' })).toBe('bank_name')
    expect(fieldOfApiError('COUNTERPARTY_DOC_TYPE_INVALID', { field: 'counterparty_doc_type' })).toBe('doc_type')
    expect(fieldOfApiError('VOUCHER_NUMBER_INVALID', { field: 'related_number' })).toBe('related_number')
    expect(fieldOfApiError('VOUCHER_NUMBER_REQUIRED', { field: 'number' })).toBe('number')
  })
})

describe('archivo anual', () => {
  it('se llama como el 956 de Marangatu', () => {
    expect(annualRegisterName('1234567', 2026, 1, 1)).toBe('1234567_REG_2026_00001.zip')
    expect(annualRegisterName('1234567', 2026, 3, 2)).toBe('1234567_REG_2026_lotes.zip')
  })

  it('se ofrece solo con la 956 en el perfil vigente', () => {
    expect(hasAnnualRegister({ current: { obligations: [{ code: '715' }, { code: '956' }] } })).toBe(true)
    expect(hasAnnualRegister({ current: { obligations: [{ code: '211' }, { code: '955' }] } })).toBe(false)
    expect(hasAnnualRegister({ current: null })).toBe(false)
    expect(hasAnnualRegister(undefined)).toBe(false)
  })
})
