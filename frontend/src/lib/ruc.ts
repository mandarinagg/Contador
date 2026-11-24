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

/** Estado del RUC mientras se escribe: vacío (es opcional), mal formado o con DV correcto/incorrecto. */
export function rucStatus(ruc: string, dv: string): { ok: boolean; message?: string } {
  if (!ruc && !dv) return { ok: true }
  if (!/^\d{1,8}$/.test(ruc)) return { ok: false, message: 'El RUC son hasta 8 dígitos, sin puntos ni guion.' }
  const expected = String(rucCheckDigit(ruc))
  if (dv === '') return { ok: false, message: `Falta el dígito verificador (para ese RUC es ${expected}).` }
  if (dv !== expected) return { ok: false, message: `Para ese RUC el dígito verificador es ${expected}.` }
  return { ok: true }
}
