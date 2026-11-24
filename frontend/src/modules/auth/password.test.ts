import { describe, expect, it } from 'vitest'
import { passwordProblem } from './password'

describe('passwordProblem (espejo de la política del backend)', () => {
  it('acepta una contraseña fuerte', () => {
    expect(passwordProblem('Clave-Segura-2026')).toBeUndefined()
  })
  it.each([
    ['corta', 'al menos 12'],
    ['solominusculaslarga', 'tres de'],
    [' Clave-Segura-2026', 'espacios'],
  ])('rechaza %s', (pw, fragment) => {
    expect(passwordProblem(pw)).toContain(fragment)
  })
})
