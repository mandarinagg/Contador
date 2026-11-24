import { describe, expect, it } from 'vitest'
import type { Voucher } from './types'
import { draftFromVoucher, draftToBody, emptyDraft, fieldOfApiError, nextNumber, readPyg, vatLine, type VoucherDraft } from './voucherDraft'

/** Compra válida: RUC 80012345-0, 550.000 al 10 % (IVA 50.000). */
const purchase = (over: Partial<VoucherDraft> = {}): VoucherDraft => ({
  ...emptyDraft('purchase', '2026-10-15'),
  ruc: '80012345',
  dv: '0',
  name: '  Proveedora S.A. ',
  timbrado: '12345678',
  number: '001-001-0000145',
  taxed_10: '550.000',
  ...over,
})

describe('readPyg', () => {
  it('vacío cuenta como cero y lee el formato paraguayo', () => {
    expect(readPyg('')).toEqual({ ok: true, value: '0' })
    expect(readPyg('1.100.000')).toEqual({ ok: true, value: '1100000' })
  })
  it('rechaza los negativos: el tipo de comprobante dice si resta', () => {
    expect(readPyg('-5.000').ok).toBe(false)
  })
})

describe('vatLine', () => {
  it('sin IVA impreso usa el calculado', () => {
    expect(vatLine('1.100.000', '', '0.1')).toEqual({ amount: '1100000', calculated: '100000', printed: null, effective: '100000' })
  })
  it('acepta el impreso a ±1 guaraní y lo usa', () => {
    expect(vatLine('1.100.000', '100.001', '0.1').effective).toBe('100001')
    expect(vatLine('1.100.000', '99.999', '0.1').effective).toBe('99999')
  })
  it('rechaza el impreso que difiere en más de 1 guaraní', () => {
    const line = vatLine('1.100.000', '100.002', '0.1')
    expect(line.effective).toBeNull()
    expect(line.error).toMatch(/más de 1 guaraní/)
  })
})

describe('draftToBody', () => {
  it('arma el cuerpo de una compra: importes enteros, nombre recortado, sin IVA impreso', () => {
    const { body, errors } = draftToBody(purchase())
    expect(errors).toEqual({})
    expect(body).toMatchObject({
      direction: 'purchase',
      counterparty_doc_type: 'ruc',
      counterparty_ruc: '80012345',
      counterparty_ruc_dv: '0',
      counterparty_name: 'Proveedora S.A.',
      taxed_10: '550000',
      taxed_5: '0',
      exempt: '0',
      cdc: null,
      related_voucher_id: null,
      fx_rate: null,
    })
    // La API calcula el mismo IVA que se ve: no se manda salvo que se escriba el impreso.
    expect(body).not.toHaveProperty('vat_10')
  })

  it('manda el IVA impreso solo si se escribió', () => {
    const { body } = draftToBody(purchase({ vat_10: '50.001' }))
    expect(body?.vat_10).toBe('50001')
    expect(body).not.toHaveProperty('vat_5')
  })

  it('una compra siempre va con RUC, aunque el borrador diga otro documento', () => {
    const { body } = draftToBody(purchase({ doc_type: 'identity_card', document: '1234567' }))
    expect(body?.counterparty_doc_type).toBe('ruc')
    expect(body?.counterparty_document).toBeNull()
  })

  it('una compra sin RUC no tiene crédito fiscal', () => {
    expect(draftToBody(purchase({ ruc: '', dv: '' })).errors.ruc).toMatch(/sin RUC no hay crédito fiscal/)
  })

  it('controla el DV del RUC', () => {
    expect(draftToBody(purchase({ dv: '7' })).errors.dv).toBe('Para ese RUC el dígito verificador es 0.')
    expect(draftToBody(purchase({ dv: '' })).errors.dv).toMatch(/Falta el dígito verificador/)
  })

  it('timbrado, número, fecha y CDC', () => {
    const { body, errors } = draftToBody(purchase({ timbrado: '1234', number: '1-1-1', issued_on: '', is_electronic: true, cdc: '123' }))
    expect(body).toBeNull()
    expect(Object.keys(errors).sort()).toEqual(['cdc', 'issued_on', 'number', 'timbrado'])
  })

  it('un comprobante sin importes no se manda', () => {
    expect(draftToBody(purchase({ taxed_10: '' })).errors.amounts).toBeDefined()
  })

  it('una nota necesita la factura que corrige', () => {
    expect(draftToBody(purchase({ voucher_type: 'credit_note' })).errors.related_voucher_id).toBeDefined()
    const { body } = draftToBody(purchase({ voucher_type: 'credit_note', related_voucher_id: 'f-1' }))
    expect(body?.related_voucher_id).toBe('f-1')
  })

  it('venta sin nombre: sin documento ni nombre', () => {
    const { body, errors } = draftToBody({ ...emptyDraft('sale', '2026-10-15'), doc_type: 'unnamed', timbrado: '87654321', number: '001-001-0000001', exempt: '20.000' })
    expect(errors).toEqual({})
    expect(body).toMatchObject({ counterparty_doc_type: 'unnamed', counterparty_ruc: null, counterparty_document: null, counterparty_name: null })
  })

  it('venta con cédula: exige el número de documento', () => {
    const sale = { ...emptyDraft('sale', '2026-10-15'), doc_type: 'identity_card' as const, name: 'Cliente', timbrado: '87654321', number: '001-001-0000001', taxed_5: '105.000' }
    expect(draftToBody(sale).errors.document).toBeDefined()
    expect(draftToBody({ ...sale, document: ' 1234567 ' }).body?.counterparty_document).toBe('1234567')
  })

  it('moneda extranjera: exige la cotización y el total en esa moneda', () => {
    const usd = purchase({ currency: 'USD' })
    const { errors } = draftToBody(usd)
    expect(errors.fx_rate).toBeDefined()
    expect(errors.foreign_total).toBeDefined()
    const { body } = draftToBody({ ...usd, fx_rate: '7.300', foreign_total: '75,34' })
    expect(body).toMatchObject({ currency: 'USD', foreign_total: '75.34' })
    expect(body?.fx_rate).toMatch(/^7300(\.0+)?$/)
  })

  it('RUC antiguo terminado en letra: se acepta sin DV, en mayúsculas', () => {
    const { body, errors } = draftToBody(purchase({ ruc: '80012345a', dv: '' }))
    expect(errors).toEqual({})
    expect(body?.counterparty_ruc).toBe('80012345A')
    expect(body?.counterparty_ruc_dv).toBeNull()
  })

  it('RUC con otro formato: error en el RUC', () => {
    expect(draftToBody(purchase({ ruc: '80.012.345', dv: '' })).errors.ruc).toMatch(/hasta 8 dígitos/)
  })
})

describe('draftFromVoucher', () => {
  it('muestra el IVA impreso a mano solo si difiere del calculado', () => {
    const base = { ...draftToBody(purchase()).body, taxed_10: '550000', taxed_5: '0', exempt: '0', vat_10: '50000', vat_5: '0' } as unknown as Voucher
    expect(draftFromVoucher(base).vat_10).toBe('')
    expect(draftFromVoucher({ ...base, vat_10: '50001' }).vat_10).toBe('50.001')
    expect(draftFromVoucher(base).taxed_10).toBe('550.000')
  })
})

describe('nextNumber y fieldOfApiError', () => {
  it('siguiente número del talonario', () => {
    expect(nextNumber('001-001-0000007')).toBe('001-001-0000008')
    expect(nextNumber('001-001-9999999')).toBe('')
    expect(nextNumber('1-1-1')).toBe('')
  })
  it('errores de la API van al campo que corresponde', () => {
    expect(fieldOfApiError('RUC_CHECK_DIGIT_INVALID', null)).toBe('dv')
    expect(fieldOfApiError('VAT_MISMATCH', { field: 'vat_5' })).toBe('vat_5')
    expect(fieldOfApiError('VAT_MISMATCH', null)).toBe('vat_10')
    expect(fieldOfApiError('PERIOD_CONFIRMED', null)).toBeNull()
  })
})
