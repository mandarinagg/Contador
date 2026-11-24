/**
 * Dígito verificador del RUC (módulo 11 de la SET). Mismo algoritmo que el backend
 * (`app/modules/organizations/ruc.py`) y que el proyecto de facturación SIFEN.
 * En el frontend solo sirve para avisar mientras se escribe: el backend valida.
 */
export function rucCheckDigit(digits: string): number {
  if (!/^\d+$/.test(digits)) throw new Error('El dígito verificador se calcula sobre dígitos')
  let total = 0
  let weight = 2
  for (let i = digits.length - 1; i >= 0; i--) {
    total += Number(digits[i]) * weight
    weight = weight === 11 ? 2 : weight + 1
  }
  const rest = total % 11
  return rest > 1 ? 11 - rest : 0
}
