import { describe, expect, it } from 'vitest'
import type { FiscalYear } from '../types'
import type { AssetCategory } from '../types3b'
import {
  acquiredBeforeNorm,
  type AssetDraft,
  annualQuota,
  checkAsset,
  depreciationStart,
  emptyDraft,
  installmentPlan,
  nextMonthStart,
  parseMonths,
  parseRate,
  residualFromRate,
} from './assetForm'

const category: AssetCategory = {
  id: 'cat',
  code: 'equipos_de_informatica',
  name: 'Equipos de informática',
  useful_life_months: 24,
  residual_rate: '10',
  asset_account_id: 'a',
  accumulated_account_id: 'b',
  expense_account_id: 'c',
  source_url: null,
  legal_reference: null,
  citation: null,
  note: null,
  validation_status: 'pending',
  validated_by_name: null,
  validated_reference: null,
  validated_at: null,
  archived_at: null,
  complete: true,
  missing: [],
}

const draft = (p: Partial<AssetDraft> = {}): AssetDraft => ({
  ...emptyDraft('next_month'),
  category_id: 'cat',
  name: 'Notebook',
  acquired_on: '2026-01-20',
  cost: '12.000.000',
  fiscal_life: '24',
  fiscal_rate: '10',
  ...p,
})

const year = (start: string, end: string) => ({ start_date: start, end_date: end }) as FiscalYear

describe('porcentaje de residual fiscal', () => {
  it('acepta coma o punto y hasta dos decimales, de 0 a 20', () => {
    expect(parseRate('10')).toEqual({ ok: true, value: '10' })
    expect(parseRate('12,5')).toEqual({ ok: true, value: '12.5' })
    expect(parseRate('12.50 %')).toEqual({ ok: true, value: '12.5' })
    expect(parseRate('0')).toEqual({ ok: true, value: '0' })
    expect(parseRate('20')).toEqual({ ok: true, value: '20' })
  })

  it('rechaza más del 20 %, tres decimales o texto', () => {
    expect(parseRate('20,01').ok).toBe(false)
    expect(parseRate('25').ok).toBe(false)
    expect(parseRate('1,234').ok).toBe(false)
    expect(parseRate('diez').ok).toBe(false)
    expect(parseRate('').ok).toBe(false)
  })

  it('el residual se calcula hacia abajo en guaraníes enteros, sin number', () => {
    expect(residualFromRate('12000000', '10')).toBe('1200000')
    expect(residualFromRate('3333333', '12.5')).toBe('416666')
    // Un costo más allá de Number.MAX_SAFE_INTEGER sigue exacto.
    expect(residualFromRate('900719925474099300', '10')).toBe('90071992547409930')
  })
})

describe('vida útil', () => {
  it('meses enteros de 1 a 1200', () => {
    expect(parseMonths('24')).toEqual({ ok: true, value: 24 })
    expect(parseMonths('0').ok).toBe(false)
    expect(parseMonths('1201').ok).toBe(false)
    expect(parseMonths('2,5').ok).toBe(false)
  })
})

describe('inicio de la depreciación', () => {
  it('mes siguiente a la compra, con cambio de año en diciembre', () => {
    expect(depreciationStart('2026-01-20', 'next_month', [])).toBe('2026-02-01')
    expect(depreciationStart('2026-12-31', 'next_month', [])).toBe('2027-01-01')
    expect(nextMonthStart('2026-02-28')).toBe('2026-03-01')
  })

  it('ejercicio siguiente: el día después del cierre o, sin ejercicio, el año civil siguiente', () => {
    expect(depreciationStart('2026-05-10', 'next_fiscal_year', [year('2026-01-01', '2026-12-31')])).toBe('2027-01-01')
    expect(depreciationStart('2026-05-10', 'next_fiscal_year', [year('2025-07-01', '2026-06-30')])).toBe('2026-07-01')
    expect(depreciationStart('2026-05-10', 'next_fiscal_year', [])).toBe('2027-01-01')
  })

  it('ejercicio que cierra a mitad de mes: el primer mes completo siguiente', () => {
    expect(depreciationStart('2026-05-10', 'next_fiscal_year', [year('2025-06-16', '2026-06-15')])).toBe('2026-07-01')
  })
})

describe('plan de cuotas', () => {
  it('cuota lineal y la última absorbe el redondeo: la suma es exacta', () => {
    const plan = installmentPlan('1000000', '0', 3)
    expect(plan).toEqual({ depreciable: '1000000', months: 3, regular: '333333', last: '333334' })
    expect(BigInt(plan.regular) * 2n + BigInt(plan.last)).toBe(1000000n)
  })

  it('cuota anual: 12 cuotas, o la vida si es más corta', () => {
    expect(annualQuota(installmentPlan('12000000', '1200000', 24))).toBe('5400000')
    expect(annualQuota(installmentPlan('1000000', '0', 3))).toBe('1000000')
  })
})

describe('validación del alta', () => {
  it('un bien completo arma el cuerpo con los cuatro parámetros, iguales por defecto', () => {
    const r = checkAsset(draft(), category)
    expect(r.errors).toEqual({})
    expect(r.body).toEqual({
      category_id: 'cat',
      name: 'Notebook',
      description: null,
      serial_or_reference: null,
      acquired_on: '2026-01-20',
      cost: '12000000',
      start_rule: 'next_month',
      fiscal_useful_life_months: 24,
      fiscal_residual_rate: '10',
      useful_life_months: 24,
      residual_value: '1200000',
    })
    expect(r.accounting?.regular).toBe('450000')
    expect(r.nonDeductible).toBeNull()
  })

  it('pide categoría completa, nombre, fecha y costo positivo', () => {
    const r = checkAsset(draft({ category_id: '', name: 'x', acquired_on: '', cost: '0' }), undefined)
    expect(Object.keys(r.errors).sort()).toEqual(['acquired_on', 'category_id', 'cost', 'name'])
    expect(r.body).toBeNull()
    const incomplete = checkAsset(draft(), { ...category, complete: false, missing: ['vida útil'] })
    expect(incomplete.errors.category_id).toContain('vida útil')
  })

  it('el residual contable tiene que ser menor que el costo', () => {
    const r = checkAsset(draft({ same_params: false, life: '24', residual: '12.000.000' }), category)
    expect(r.errors.residual).toMatch(/menor que el costo/)
  })

  it('una cuota de menos de ₲ 1 no se acepta', () => {
    const r = checkAsset(draft({ cost: '10', fiscal_rate: '0', fiscal_life: '24' }), category)
    expect(r.errors.fiscal_life).toMatch(/menos de ₲ 1/)
  })

  it('con parámetros contables distintos calcula la cuota no deducible del primer año', () => {
    // Contable en 12 meses sin residual: 12.000.000 al año; fiscal: 5.400.000.
    const r = checkAsset(draft({ same_params: false, life: '12', residual: '0' }), category)
    expect(r.errors).toEqual({})
    expect(r.body?.useful_life_months).toBe(12)
    expect(r.body?.residual_value).toBe('0')
    expect(r.nonDeductible).toBe('6600000')
  })

  it('advierte las compras anteriores al 14-10-2021', () => {
    expect(acquiredBeforeNorm('2021-10-13')).toBe(true)
    expect(acquiredBeforeNorm('2021-10-14')).toBe(false)
    expect(acquiredBeforeNorm('')).toBe(false)
  })
})
