import { describe, expect, it } from 'vitest'
import { comparePyg, formatDecimal, isWholeDecimal, multiplyDecimal, parseRateInput, pygToBig, subPyg, sumPyg } from './amounts'

describe('sumas de guaraníes con BigInt', () => {
  it('suma exacta más allá de Number.MAX_SAFE_INTEGER', () => {
    // Con number: 9007199254740993 + 1 daría 9007199254740994 por redondeo binario.
    expect(sumPyg(['9007199254740993', '1'])).toBe('9007199254740994')
    expect(sumPyg(['9999999999999999', '9999999999999999'])).toBe('19999999999999998')
  })

  it('acepta los ceros de relleno de la API y signos', () => {
    expect(sumPyg(['150000.00', '-50000', '0'])).toBe('100000')
    expect(pygToBig('-0')).toBe(0n)
  })

  it('rechaza decimales significativos en guaraníes', () => {
    expect(() => pygToBig('10.5')).toThrow()
    expect(() => pygToBig('abc')).toThrow()
  })

  it('resta y compara', () => {
    expect(subPyg('100', '250')).toBe('-150')
    expect(comparePyg('100', '99')).toBe(1)
    expect(comparePyg('100', '100')).toBe(0)
    expect(comparePyg('-1', '0')).toBe(-1)
  })

  it('suma vacía es cero', () => {
    expect(sumPyg([])).toBe('0')
  })
})

describe('producto exacto (moneda extranjera × cotización)', () => {
  it('sin redondeo', () => {
    expect(multiplyDecimal('120.35', '7300.25')).toBe('878585.0875')
    expect(multiplyDecimal('100', '7300')).toBe('730000')
    expect(multiplyDecimal('0.10', '0.2')).toBe('0.02')
    expect(multiplyDecimal('100.50', '7300.10')).toBe('733660.05')
  })

  it('distingue enteros exactos', () => {
    expect(isWholeDecimal(multiplyDecimal('100.00', '7300'))).toBe(true)
    expect(isWholeDecimal('878585.0875')).toBe(false)
  })
})

describe('parseRateInput', () => {
  it('formatos paraguayos', () => {
    expect(parseRateInput('7.300')).toEqual({ ok: true, value: '7300' })
    expect(parseRateInput('7300,25')).toEqual({ ok: true, value: '7300.25' })
    expect(parseRateInput('7.300,25')).toEqual({ ok: true, value: '7300.25' })
    expect(parseRateInput('7300.25')).toEqual({ ok: true, value: '7300.25' })
    expect(parseRateInput('₲ 7.310,123456')).toEqual({ ok: true, value: '7310.123456' })
    expect(parseRateInput('7300,500000')).toEqual({ ok: true, value: '7300.5' })
  })

  it('errores claros', () => {
    expect(parseRateInput('').ok).toBe(false)
    expect(parseRateInput('0').ok).toBe(false)
    expect(parseRateInput('-7300').ok).toBe(false)
    expect(parseRateInput('7300,1234567').ok).toBe(false)
    expect(parseRateInput('73.00.1').ok).toBe(false)
  })

  it('formato de pantalla', () => {
    expect(formatDecimal('7300.25')).toBe('7.300,25')
    expect(formatDecimal('1234567')).toBe('1.234.567')
    expect(formatDecimal('-878585.0875')).toBe('−878.585,0875')
  })
})
