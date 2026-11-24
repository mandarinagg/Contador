import { describe, expect, it } from 'vitest'
import { rucCheckDigit } from './ruc'

describe('rucCheckDigit', () => {
  it('reproduce el vector del Manual Técnico SIFEN v150', () => {
    expect(rucCheckDigit('44444401')).toBe(7)
  })
  it('rechaza lo que no son dígitos', () => {
    expect(() => rucCheckDigit('12a4')).toThrow()
  })
})
