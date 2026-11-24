import { describe, expect, it } from 'vitest'
import { rucCheckDigit } from '../../lib/ruc'
import {
  addDays,
  cdcMismatches,
  checkCounterpartyRuc,
  displayStatus,
  expandVoucherNumber,
  groupByDueMonth,
  includedVat,
  marangatuName,
  maskCdc,
  maskTimbrado,
  maskVoucherNumber,
  monthEnd,
  parseCdc,
  shiftMonth,
  splitRucInput,
  vatAccepted,
  vatXlsxName,
  voucherXlsxName,
} from './logic'
import type { Obligation } from './types'

// Vectores calculados con el backend (`app.modules.tax.vouchers.included_vat`).
const VAT_10: [string, string][] = [
  ['0', '0'], ['1', '0'], ['5', '0'], ['6', '1'], ['10', '1'], ['11', '1'], ['16', '1'], ['17', '2'], ['21', '2'], ['22', '2'],
  ['105', '10'], ['115', '10'], ['1100000', '100000'], ['210000', '19091'], ['1234567', '112233'], ['999999999', '90909091'],
  ['55', '5'], ['165', '15'], ['33', '3'], ['63', '6'],
]
const VAT_5: [string, string][] = [
  ['0', '0'], ['1', '0'], ['5', '0'], ['6', '0'], ['10', '0'], ['11', '1'], ['16', '1'], ['17', '1'], ['21', '1'], ['22', '1'],
  ['105', '5'], ['115', '5'], ['1100000', '52381'], ['210000', '10000'], ['1234567', '58789'], ['999999999', '47619048'],
  ['55', '3'], ['165', '8'], ['33', '2'], ['63', '3'],
]

describe('IVA incluido (igual que el backend)', () => {
  it.each(VAT_10)('10 %% de %s → %s', (amount, vat) => expect(includedVat(amount, '0.1')).toBe(vat))
  it.each(VAT_5)('5 %% de %s → %s', (amount, vat) => expect(includedVat(amount, '0.05')).toBe(vat))

  it('redondea las mitades hacia arriba', () => {
    // 3 × 1 / (1 + 1) = 1,5 → 2; 1 × 1 / 2 = 0,5 → 1.
    expect(includedVat('3', '1')).toBe('2')
    expect(includedVat('1', '1')).toBe('1')
    // 7 × 0,5 / 1,5 = 2,333… → 2; 8 × 0,5 / 1,5 = 2,666… → 3.
    expect(includedVat('7', '0.5')).toBe('2')
    expect(includedVat('8', '0.5')).toBe('3')
  })

  it('no pierde precisión con importes grandes (BigInt)', () => {
    expect(includedVat('99999999999999999', '0.1')).toBe('9090909090909091')
  })

  it('rechaza importes negativos', () => {
    expect(() => includedVat('-11', '0.1')).toThrow()
  })
})

describe('tolerancia del IVA impreso', () => {
  it('acepta ±1 y rechaza ±2', () => {
    expect(vatAccepted('100000', '100000')).toBe(true)
    expect(vatAccepted('100001', '100000')).toBe(true)
    expect(vatAccepted('99999', '100000')).toBe(true)
    expect(vatAccepted('100002', '100000')).toBe(false)
    expect(vatAccepted('99998', '100000')).toBe(false)
  })
})

describe('DV del RUC (módulo 11, igual que el backend)', () => {
  it.each([
    ['44444401', 7], ['80012345', 0], ['1234567', 9], ['80000519', 8], ['3456789', 5], ['1', 9], ['9', 4], ['10', 8], ['80069563', 1], ['5000000', 4],
  ] as const)('%s → %i', (ruc, dv) => expect(rucCheckDigit(ruc)).toBe(dv))

  it('estado mientras se escribe', () => {
    expect(checkCounterpartyRuc('', '')).toEqual({ kind: 'empty' })
    expect(checkCounterpartyRuc('80012345', '')).toEqual({ kind: 'missing_dv', expected: '0' })
    expect(checkCounterpartyRuc('80012345', '3')).toEqual({ kind: 'wrong_dv', expected: '0' })
    expect(checkCounterpartyRuc('80012345', '0')).toEqual({ kind: 'ok' })
    expect(checkCounterpartyRuc('800-123', '').kind).toBe('invalid')
    // RUC antiguo terminado en letra (D-099): sin DV, para revisar.
    expect(checkCounterpartyRuc('80012345a', '')).toEqual({ kind: 'legacy' })
  })

  it('separa «80012345-0» escrito de una vez', () => {
    expect(splitRucInput('80012345-0')).toEqual({ ruc: '80012345', dv: '0' })
    expect(splitRucInput('800.123')).toEqual({ ruc: '800123', dv: null })
  })
})

describe('máscaras', () => {
  it('timbrado: 8 dígitos', () => {
    expect(maskTimbrado('1234-5678 90')).toBe('12345678')
  })

  it('número: guiones en su lugar mientras se escribe', () => {
    expect(maskVoucherNumber('0')).toBe('0')
    expect(maskVoucherNumber('0010')).toBe('001-0')
    expect(maskVoucherNumber('001001')).toBe('001-001')
    expect(maskVoucherNumber('0010010000001')).toBe('001-001-0000001')
    expect(maskVoucherNumber('001-001-00000019999')).toBe('001-001-0000001')
  })

  it('número: completa con ceros lo escrito por partes', () => {
    expect(expandVoucherNumber('1-1-145')).toBe('001-001-0000145')
    expect(expandVoucherNumber('001-002-0000450')).toBe('001-002-0000450')
    expect(expandVoucherNumber('0010010000')).toBe('001-001-0000')
  })

  it('CDC: de a cuatro dígitos, hasta 44', () => {
    expect(maskCdc('01444444017')).toBe('0144 4444 017')
    expect(maskCdc('0'.repeat(50)).replace(/ /g, '')).toHaveLength(44)
  })
})

describe('CDC', () => {
  // Ejemplo oficial del Manual Técnico v150 (KuDE «0144 4444 0170 0100 1001 4528 2201 7012 5158 7326 0988»).
  const OFFICIAL = '0144 4444 0170 0100 1001 4528 2201 7012 5158 7326 0988'

  it('lee sus partes y valida el DV', () => {
    expect(parseCdc(OFFICIAL)).toEqual({
      documentType: '01',
      emitterRuc: '44444401',
      emitterDv: '7',
      number: '001-001-0014528',
      issuedOn: '2017-01-25',
      checkOk: true,
    })
    expect(parseCdc(OFFICIAL.replace(/8$/, '3'))?.checkOk).toBe(false)
    expect(parseCdc('0144')).toBeNull()
  })

  it('dice qué no coincide con el comprobante', () => {
    const cdc = parseCdc(OFFICIAL)
    if (!cdc) throw new Error('CDC')
    const base = { direction: 'purchase' as const, voucherType: 'invoice' as const, number: '001-001-0014528', issuedOn: '2017-01-25', emitterRuc: '44444401', emitterDv: '7' }
    expect(cdcMismatches(cdc, base)).toEqual([])
    expect(cdcMismatches(cdc, { ...base, number: '001-001-0014529', issuedOn: '2017-01-26', voucherType: 'credit_note' })).toEqual([
      'el número',
      'la fecha',
      'el tipo de comprobante',
    ])
    expect(cdcMismatches(cdc, { ...base, emitterDv: '3' })).toEqual(['el RUC del proveedor'])
  })
})

const ob = (code: string, due: string, extra: Partial<Obligation> = {}): Obligation =>
  ({ id: `${code}-${due}`, code, due_date: due, remind_by: due, status: 'pending', is_overdue: false, ...extra }) as Obligation

describe('calendario', () => {
  it('agrupa por mes de vencimiento, en orden', () => {
    const groups = groupByDueMonth([
      ob('REG-COMPROB-MENSUAL', '2026-12-10'),
      ob('IVA-GENERAL-LIQUIDACION', '2026-11-16'),
      ob('IRE-GENERAL-DJ', '2027-04-20'),
      ob('CAL', '2026-11-16'),
      ob('IVA-GENERAL-LIQUIDACION', '2026-12-09'),
    ])
    expect(groups.map((g) => g.month)).toEqual(['2026-11', '2026-12', '2027-04'])
    expect(groups[0].items.map((o) => o.code)).toEqual(['CAL', 'IVA-GENERAL-LIQUIDACION'])
    expect(groups[1].items.map((o) => o.due_date)).toEqual(['2026-12-09', '2026-12-10'])
  })

  it('estado a la vista: vencida, por vencer (por remind_by) o pendiente', () => {
    const today = '2026-11-24'
    expect(displayStatus(ob('X', '2026-11-20', { is_overdue: true }), today, 10)).toBe('overdue')
    expect(displayStatus(ob('X', '2026-12-07', { remind_by: '2026-12-04' }), today, 10)).toBe('due_soon')
    expect(displayStatus(ob('X', '2026-12-09', { remind_by: '2026-12-09' }), today, 10)).toBe('pending')
    expect(displayStatus(ob('X', '2026-12-09', { status: 'filed' }), today, 10)).toBe('filed')
  })

  it('fechas sin zona horaria', () => {
    expect(addDays('2026-12-28', 10)).toBe('2027-01-07')
    expect(shiftMonth('2026-11', 2)).toBe('2027-01')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(monthEnd('2028-02')).toBe('2028-02-29')
  })
})

describe('nombres de las descargas (los mismos que arma la API)', () => {
  it('libro de comprobantes y estimación del IVA', () => {
    expect(voucherXlsxName(2026, 10, 'purchase')).toBe('registro-compras-2026-10.xlsx')
    expect(voucherXlsxName(2026, 3, 'sale')).toBe('registro-ventas-2026-03.xlsx')
    expect(voucherXlsxName(2026)).toBe('registro-comprobantes-2026.xlsx')
    expect(vatXlsxName(2026, 1)).toBe('iva-2026-01.xlsx')
  })

  it('archivo de Marangatu', () => {
    expect(marangatuName('44444401', 2026, 10, 1, 1)).toBe('44444401_REG_102026_00001.zip')
    expect(marangatuName('44444401', 2026, 3, 27, 1)).toBe('44444401_REG_032026_00027.zip')
    expect(marangatuName('44444401', 2026, 3, 1, 2)).toBe('44444401_REG_032026_lotes.zip')
  })
})
