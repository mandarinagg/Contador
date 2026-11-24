/**
 * Aritmética de importes contables sin punto flotante (BR-ACC-05).
 *
 * El debe y el haber son guaraníes enteros como string (`"150000"`). Las sumas y restas se
 * hacen con `BigInt`; nunca se pasa por `number`. Las cotizaciones (hasta 6 decimales) y los
 * importes en otra moneda se multiplican como enteros escalados.
 */
import { MINUS } from '../../lib/money'

const INTEGER = /^([+-]?)(\d+)(?:\.(0*))?$/

/** "150000", "-150000" o "150000.00" (ceros de relleno) → BigInt. Cualquier otra cosa lanza. */
export function pygToBig(amount: string): bigint {
  const m = INTEGER.exec(amount.trim())
  if (!m) throw new Error(`Importe en guaraníes con formato inesperado: ${amount}`)
  const value = BigInt(m[2])
  return m[1] === '-' ? -value : value
}

export const bigToPyg = (value: bigint): string => value.toString()

/** Suma exacta de importes en guaraníes. */
export function sumPyg(values: Iterable<string>): string {
  let total = 0n
  for (const v of values) total += pygToBig(v)
  return bigToPyg(total)
}

/** `a − b` exacto. */
export const subPyg = (a: string, b: string): string => bigToPyg(pygToBig(a) - pygToBig(b))

export const comparePyg = (a: string, b: string): -1 | 0 | 1 => {
  const d = pygToBig(a) - pygToBig(b)
  return d === 0n ? 0 : d > 0n ? 1 : -1
}

export const isZeroPyg = (a: string) => pygToBig(a) === 0n
export const absPyg = (a: string) => a.trim().replace(/^[+-]/, '')

// --- Decimales escalados (cotizaciones y moneda extranjera) ---------------------------

interface Scaled {
  value: bigint
  scale: number
}

function toScaled(decimal: string): Scaled {
  const m = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(decimal.trim())
  if (!m) throw new Error(`Número decimal con formato inesperado: ${decimal}`)
  const frac = m[3] ?? ''
  const value = BigInt(m[2] + frac)
  return { value: m[1] === '-' ? -value : value, scale: frac.length }
}

function fromScaled({ value, scale }: Scaled): string {
  const negative = value < 0n
  let digits = (negative ? -value : value).toString().padStart(scale + 1, '0')
  let out = digits
  if (scale > 0) {
    const int = digits.slice(0, digits.length - scale)
    const frac = digits.slice(digits.length - scale).replace(/0+$/, '')
    out = frac ? `${int}.${frac}` : int
  }
  digits = out
  return negative && !/^0(\.0*)?$/.test(digits) ? `-${digits}` : digits
}

/** Producto exacto de dos decimales en texto: `"120.35" × "7300.25"` → `"878585.0875"`. */
export function multiplyDecimal(a: string, b: string): string {
  const x = toScaled(a)
  const y = toScaled(b)
  return fromScaled({ value: x.value * y.value, scale: x.scale + y.scale })
}

/** ¿El decimal es un entero exacto? (`"878585.00"` sí, `"878585.0875"` no). */
export const isWholeDecimal = (a: string) => /^[+-]?\d+(\.0*)?$/.test(a.trim())

// --- Entrada de cotizaciones -------------------------------------------------------------

export type ParsedRate = { ok: true; value: string } | { ok: false; error: string }

const GROUPED = /^\d{1,3}(\.\d{3})+$/

/**
 * Cotización escrita por una persona en Paraguay (guaraníes por unidad): `7.300`, `7300,25`,
 * `7.300,25` o `7300.25` → `"7300.25"`. Hasta 6 decimales, positiva; nunca redondea.
 */
export function parseRateInput(input: string): ParsedRate {
  const text = input.replace(/[\s ]/g, '').replace(/₲|Gs\.?/gi, '')
  if (!text) return { ok: false, error: 'Escribí la cotización.' }
  if (!/^[\d.,]+$/.test(text)) return { ok: false, error: 'La cotización va en positivo, solo con números, puntos de miles y coma decimal.' }
  let int: string
  let frac = ''
  if (text.includes(',')) {
    const parts = text.split(',')
    if (parts.length > 2 || parts[1] === '' || parts[1].includes('.')) return { ok: false, error: 'La cotización tiene una sola coma decimal.' }
    if (parts[0].includes('.') && !GROUPED.test(parts[0])) return { ok: false, error: 'Los puntos de miles van cada tres cifras (7.300).' }
    int = parts[0].replaceAll('.', '') || '0'
    frac = parts[1]
  } else if (GROUPED.test(text)) {
    int = text.replaceAll('.', '')
  } else if ((text.match(/\./g) ?? []).length === 1 && !text.startsWith('.') && !text.endsWith('.')) {
    ;[int, frac] = text.split('.')
  } else if (!text.includes('.')) {
    int = text
  } else {
    return { ok: false, error: 'Los puntos de miles van cada tres cifras (7.300).' }
  }
  frac = frac.replace(/0+$/, '')
  if (frac.length > 6) return { ok: false, error: 'La cotización admite hasta 6 decimales.' }
  int = int.replace(/^0+(?=\d)/, '')
  if (int.length > 12) return { ok: false, error: 'La cotización es demasiado grande.' }
  const value = frac ? `${int}.${frac}` : int
  if (/^0(\.0*)?$/.test(value)) return { ok: false, error: 'La cotización tiene que ser mayor que cero.' }
  return { ok: true, value }
}

/** Formato de pantalla de una cotización o de un decimal: `"7300.25"` → `"7.300,25"`. */
export function formatDecimal(value: string): string {
  const m = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value.trim())
  if (!m) return value
  const groups: string[] = []
  for (let end = m[2].length; end > 0; end -= 3) groups.unshift(m[2].slice(Math.max(0, end - 3), end))
  return `${m[1] === '-' ? MINUS : ''}${groups.join('.')}${m[3] ? `,${m[3]}` : ''}`
}
