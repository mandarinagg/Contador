import { describe, expect, it } from 'vitest'
import { rucCheckDigit, rucStatus } from './ruc'

describe('rucCheckDigit', () => {
  it('reproduce el vector del Manual Técnico SIFEN v150', () => {
    expect(rucCheckDigit('44444401')).toBe(7)
  })
  it('rechaza lo que no son dígitos', () => {
    expect(() => rucCheckDigit('12a4')).toThrow()
  })
})

describe('rucStatus', () => {
  it('vacío es válido (el RUC es opcional)', () => {
    expect(rucStatus('', '')).toEqual({ ok: true })
  })
  it('avisa el DV esperado mientras se escribe', () => {
    expect(rucStatus('44444401', '')).toEqual({ ok: false, message: 'Falta el dígito verificador (para ese RUC es 7).' })
    expect(rucStatus('44444401', '3')).toEqual({ ok: false, message: 'Para ese RUC el dígito verificador es 7.' })
    expect(rucStatus('44444401', '7')).toEqual({ ok: true })
  })
  it('rechaza RUC con más de 8 dígitos o un DV sin RUC', () => {
    expect(rucStatus('123456789', '1').ok).toBe(false)
    expect(rucStatus('', '1').ok).toBe(false)
  })
})
