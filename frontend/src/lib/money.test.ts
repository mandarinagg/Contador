import { describe, expect, it } from 'vitest'
import { formatMoney, isNegative, negateAmount, parseAmountInput, toInputText } from './money'

describe('formatMoney', () => {
  it('PYG sin decimales con punto de miles', () => {
    expect(formatMoney('1234567', 'PYG')).toBe('₲ 1.234.567')
    expect(formatMoney('150000.00', 'PYG')).toBe('₲ 150.000')
    expect(formatMoney('0', 'PYG')).toBe('₲ 0')
  })

  it('otras monedas con dos decimales y coma', () => {
    expect(formatMoney('1234.5', 'USD')).toBe('US$ 1.234,50')
    expect(formatMoney('0.30', 'EUR')).toBe('€ 0,30')
    expect(formatMoney('1000000', 'BRL')).toBe('R$ 1.000.000,00')
  })

  it('signo: menos real para salidas y más opcional para entradas', () => {
    expect(formatMoney('-45000', 'PYG')).toBe('−₲ 45.000')
    expect(formatMoney('45000', 'PYG', { sign: 'always' })).toBe('+₲ 45.000')
    expect(formatMoney('-45000', 'PYG', { sign: 'never' })).toBe('₲ 45.000')
    expect(formatMoney('-0.00', 'USD')).toBe('US$ 0,00')
    expect(formatMoney('0', 'PYG', { sign: 'always' })).toBe('₲ 0')
  })

  it('sin símbolo para columnas', () => {
    expect(formatMoney('-1234.56', 'USD', { symbol: false })).toBe('−1.234,56')
  })

  it('importes enormes sin perder exactitud (más allá de Number.MAX_SAFE_INTEGER)', () => {
    expect(formatMoney('9999999999999999.99', 'USD')).toBe('US$ 9.999.999.999.999.999,99')
  })

  it('rechaza lo que no es el formato de la API', () => {
    expect(() => formatMoney('1,5', 'USD')).toThrow()
  })
})

describe('parseAmountInput', () => {
  const ok = (input: string, currency: string) => {
    const r = parseAmountInput(input, currency)
    if (!r.ok) throw new Error(r.error)
    return r.value
  }
  const err = (input: string, currency: string) => {
    const r = parseAmountInput(input, currency)
    return r.ok ? null : r.error
  }

  it('acepta punto de miles', () => {
    expect(ok('1.234.567', 'PYG')).toBe('1234567')
    expect(ok('1.500', 'PYG')).toBe('1500')
    expect(ok('1.234.567', 'USD')).toBe('1234567.00')
  })

  it('acepta coma decimal con o sin miles', () => {
    expect(ok('1234567,50', 'USD')).toBe('1234567.50')
    expect(ok('1.234.567,5', 'USD')).toBe('1234567.50')
    expect(ok('0,3', 'EUR')).toBe('0.30')
    expect(ok(',5', 'USD')).toBe('0.50')
  })

  it('un único punto que no agrupa de a tres es decimal', () => {
    expect(ok('1234.5', 'USD')).toBe('1234.50')
    expect(ok('12.50', 'USD')).toBe('12.50')
  })

  it('signo, espacios y símbolo de moneda', () => {
    expect(ok('-45.000', 'PYG')).toBe('-45000')
    expect(ok('−45.000', 'PYG')).toBe('-45000')
    expect(ok('+ 45.000', 'PYG')).toBe('45000')
    expect(ok('₲ 1.000.000', 'PYG')).toBe('1000000')
    expect(ok('US$ 10,00', 'USD')).toBe('10.00')
    expect(ok('Gs. 5.000', 'PYG')).toBe('5000')
    expect(ok('-0', 'PYG')).toBe('0')
    expect(ok('007', 'PYG')).toBe('7')
  })

  it('PYG no lleva decimales salvo ceros', () => {
    expect(ok('1.500,00', 'PYG')).toBe('1500')
    expect(err('1.500,50', 'PYG')).toBe('Los importes en PYG no llevan decimales.')
  })

  it('máximo dos decimales en las demás monedas', () => {
    expect(err('10,555', 'USD')).toBe('Los importes en USD llevan como máximo 2 decimales.')
    expect(ok('10,550', 'USD')).toBe('10.55')
  })

  it('rechaza formatos ambiguos o mal escritos', () => {
    expect(err('', 'PYG')).toBe('Ingresá un importe.')
    expect(err('12a', 'PYG')).not.toBeNull()
    expect(err('1,2,3', 'USD')).not.toBeNull()
    expect(err('1.23.456', 'PYG')).not.toBeNull()
    expect(err('12.34.5', 'USD')).not.toBeNull()
    expect(err('1.234,5.0', 'USD')).not.toBeNull()
    expect(err('10,', 'USD')).not.toBeNull()
    expect(err('12345678901234567', 'PYG')).toBe('El importe es demasiado grande.')
  })

  it('ida y vuelta con el formato de entrada', () => {
    expect(toInputText('1234567.5', 'USD')).toBe('1.234.567,50')
    expect(ok(toInputText('-1234567', 'PYG'), 'PYG')).toBe('1234567')
  })
})

describe('signo', () => {
  it('detecta y cambia el signo sobre el texto', () => {
    expect(isNegative('-1')).toBe(true)
    expect(isNegative('-0.00')).toBe(false)
    expect(negateAmount('1500')).toBe('-1500')
    expect(negateAmount('-1500.50')).toBe('1500.50')
    expect(negateAmount('0')).toBe('0')
  })
})
