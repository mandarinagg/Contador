/**
 * Importes (D-026): la API los manda y los recibe como **string decimal** ("-1500.50").
 * Este módulo nunca los convierte a `number`: el formato y el parseo trabajan sobre el
 * texto, dígito por dígito, para que no haya redondeos de punto flotante.
 *
 * Formato de pantalla paraguayo: punto de miles y coma decimal. PYG sin decimales
 * (`₲ 1.234.567`), las demás monedas con dos (`US$ 1.234,50`).
 */

export const CURRENCIES = ['PYG', 'USD', 'BRL', 'ARS', 'EUR'] as const
export type Currency = (typeof CURRENCIES)[number]

export const CURRENCY_DECIMALS: Record<string, number> = { PYG: 0, USD: 2, BRL: 2, ARS: 2, EUR: 2 }

export const CURRENCY_SYMBOLS: Record<string, string> = { PYG: '₲', USD: 'US$', BRL: 'R$', ARS: 'AR$', EUR: '€' }

export const CURRENCY_NAMES: Record<string, string> = {
  PYG: 'Guaraníes (₲)',
  USD: 'Dólares (US$)',
  BRL: 'Reales (R$)',
  ARS: 'Pesos argentinos (AR$)',
  EUR: 'Euros (€)',
}

/** Signo matemático real (U+2212): se lee mejor que el guion y los lectores de pantalla lo dicen "menos". */
export const MINUS = '−'

const decimalsOf = (currency: string) => CURRENCY_DECIMALS[currency] ?? 2

function groupThousands(digits: string): string {
  const out: string[] = []
  for (let end = digits.length; end > 0; end -= 3) out.unshift(digits.slice(Math.max(0, end - 3), end))
  return out.join('.')
}

interface Parts {
  negative: boolean
  int: string
  frac: string
}

/** Descompone el string canónico de la API ("-1234.5") sin pasar por `number`. */
function splitCanonical(amount: string): Parts {
  const text = amount.trim()
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text)
  if (!match) throw new Error(`Importe con formato inesperado: ${amount}`)
  const int = match[2].replace(/^0+(?=\d)/, '')
  const frac = match[3] ?? ''
  const isZero = /^0*$/.test(int + frac)
  return { negative: match[1] === '-' && !isZero, int, frac }
}

/** Ajusta la parte decimal a los decimales de la moneda (solo rellena o quita ceros; nunca redondea un valor). */
function fitFraction(frac: string, decimals: number): string {
  if (frac.length <= decimals) return frac.padEnd(decimals, '0')
  // La API ya respeta los decimales de la moneda: lo que sobra son ceros ("150000.00" en PYG).
  return frac.slice(0, decimals)
}

export interface FormatOptions {
  /** `always`: "+₲ 1.000" y "−₲ 1.000"; `negative` (por defecto): solo el menos; `never`: magnitud. */
  sign?: 'always' | 'negative' | 'never'
  /** Sin el símbolo de la moneda (para columnas que ya dicen la moneda). */
  symbol?: boolean
}

/** `formatMoney("-1234567", "PYG")` → `"−₲ 1.234.567"`; `formatMoney("1234.5", "USD")` → `"US$ 1.234,50"`. */
export function formatMoney(amount: string, currency: string, options: FormatOptions = {}): string {
  const { sign = 'negative', symbol = true } = options
  const { negative, int, frac } = splitCanonical(amount)
  const decimals = decimalsOf(currency)
  const body = groupThousands(int) + (decimals > 0 ? `,${fitFraction(frac, decimals)}` : '')
  const prefix = negative ? (sign === 'never' ? '' : MINUS) : sign === 'always' && !isZeroAmount(amount) ? '+' : ''
  return `${prefix}${symbol ? `${CURRENCY_SYMBOLS[currency] ?? currency} ` : ''}${body}`
}

export const isNegative = (amount: string) => splitCanonical(amount).negative
export const isZeroAmount = (amount: string) => /^[+-]?0*(\.0*)?$/.test(amount.trim())

/** Valor absoluto del string canónico. */
export function absAmount(amount: string): string {
  return amount.trim().replace(/^[+-]/, '')
}

/** Cambia el signo del string canónico (para pasar "sale 1500" a "-1500"). */
export function negateAmount(amount: string): string {
  const text = amount.trim()
  if (isZeroAmount(text)) return absAmount(text)
  return text.startsWith('-') ? text.slice(1) : `-${text.replace(/^\+/, '')}`
}

/** Para la entrada de un formulario: "1234567.5" → "1.234.567,50" (sin símbolo ni signo). */
export function toInputText(amount: string, currency: string): string {
  return formatMoney(absAmount(amount), currency, { symbol: false, sign: 'never' })
}

export type ParsedAmount = { ok: true; value: string } | { ok: false; error: string }

const MAX_INT_DIGITS = 16
const GROUPED = /^\d{1,3}(\.\d{3})+$/

/**
 * Entrada de importes como la escribe una persona en Paraguay y salida canónica para la API.
 *
 * - `1.234.567` → `"1234567"` (punto de miles); `1234567,50` y `1.234.567,50` → `"1234567.50"`.
 * - Un único punto que no agrupa de a tres (`1234.5`) se toma como decimal.
 * - Acepta espacios, el símbolo de la moneda y signo `-`/`+`/`−` al principio.
 * - PYG no lleva decimales (salvo ceros: `1.500,00` → `"1500"`); las demás monedas, hasta dos.
 * - Devuelve el valor con los decimales de la moneda; nunca redondea.
 */
export function parseAmountInput(input: string, currency: string): ParsedAmount {
  let text = input.replace(/[\s ]/g, '').replace(/₲|US\$|R\$|AR\$|€|Gs\.?|\$/gi, '')
  if (!text) return { ok: false, error: 'Ingresá un importe.' }
  let negative = false
  if (/^[-+−]/.test(text)) {
    negative = text[0] !== '+'
    text = text.slice(1)
  }
  if (!/^[\d.,]+$/.test(text)) return { ok: false, error: 'Usá solo números, punto de miles y coma decimal.' }

  let int: string
  let frac = ''
  const commas = text.split(',').length - 1
  if (commas > 1) return { ok: false, error: 'El importe tiene más de una coma decimal.' }
  if (commas === 1) {
    const [intPart, fracPart] = text.split(',')
    if (fracPart.includes('.') || fracPart === '') return { ok: false, error: 'Después de la coma van solo los decimales.' }
    if (intPart.includes('.') && !GROUPED.test(intPart)) return { ok: false, error: 'Los puntos de miles van cada tres cifras (1.234.567).' }
    int = intPart.replaceAll('.', '') || '0'
    frac = fracPart
  } else if (text.includes('.')) {
    if (GROUPED.test(text)) {
      int = text.replaceAll('.', '')
    } else if ((text.match(/\./g) ?? []).length === 1 && !text.startsWith('.') && !text.endsWith('.')) {
      ;[int, frac] = text.split('.')
    } else {
      return { ok: false, error: 'Los puntos de miles van cada tres cifras (1.234.567).' }
    }
  } else {
    int = text
  }

  int = int.replace(/^0+(?=\d)/, '')
  if (int.length > MAX_INT_DIGITS) return { ok: false, error: 'El importe es demasiado grande.' }
  const decimals = decimalsOf(currency)
  const significant = frac.replace(/0+$/, '')
  if (significant.length > decimals) {
    return {
      ok: false,
      error: decimals === 0 ? `Los importes en ${currency} no llevan decimales.` : `Los importes en ${currency} llevan como máximo ${decimals} decimales.`,
    }
  }
  const value = decimals > 0 ? `${int}.${significant.padEnd(decimals, '0')}` : int
  if (isZeroAmount(value)) return { ok: true, value }
  return { ok: true, value: negative ? `-${value}` : value }
}

/**
 * Magnitud aproximada **solo para dibujar** (alto de una barra en un gráfico). Nunca se usa
 * para operar, comparar importes de negocio ni enviar a la API.
 */
export function amountForGeometry(amount: string): number {
  return Number(amount)
}
