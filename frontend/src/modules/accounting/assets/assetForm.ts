/**
 * Lógica del alta y la edición de un bien (sin componentes), espejo de las reglas de la API
 * (`backend/app/modules/accounting/assets.py`, D-057, D-064, D-065, D-070). Importes en
 * guaraníes enteros como string y aritmética con BigInt: nunca `number` para operar.
 */
import { parseAmountInput, toInputText } from '../../../lib/money'
import { bigToPyg, pygToBig } from '../amounts'
import type { FiscalYear, StartRule } from '../types'
import type { AssetCategory, FixedAsset, FixedAssetIn } from '../types3b'

/** Desde el 14-10-2021 rige la redacción del Decreto 6105/2021 del art. 31 (vidas útiles candidatas). */
export const NORM_IN_FORCE_SINCE = '2021-10-14'
export const MAX_RESIDUAL_RATE = '20'

export const acquiredBeforeNorm = (date: string) => Boolean(date) && date < NORM_IN_FORCE_SINCE

export interface AssetDraft {
  category_id: string
  name: string
  description: string
  serial_or_reference: string
  acquired_on: string
  cost: string
  start_rule: StartRule
  /** Vida útil fiscal en meses y porcentaje de residual fiscal (de la categoría, editables). */
  fiscal_life: string
  fiscal_rate: string
  /** N° de la autorización de la DNIT, si la vida útil o el residual fiscal salen de la categoría (D-125). */
  authorization: string
  /** Contables iguales a los fiscales (lo normal); si no, los de abajo. */
  same_params: boolean
  life: string
  residual: string
  /** N° del asiento de compra, opcional. */
  acquisition_number: string
}

export function emptyDraft(startRule: StartRule): AssetDraft {
  return {
    category_id: '',
    name: '',
    description: '',
    serial_or_reference: '',
    acquired_on: '',
    cost: '',
    start_rule: startRule,
    fiscal_life: '',
    fiscal_rate: '',
    authorization: '',
    same_params: true,
    life: '',
    residual: '',
    acquisition_number: '',
  }
}

/** Borrador a partir de un bien existente (para editarlo). */
export function draftFromAsset(a: FixedAsset, acquisitionNumber: number | null): AssetDraft {
  const same = a.useful_life_months === a.fiscal_useful_life_months && a.residual_value === a.fiscal_residual_value
  return {
    category_id: a.category_id,
    name: a.name,
    description: a.description ?? '',
    serial_or_reference: a.serial_or_reference ?? '',
    acquired_on: a.acquired_on,
    cost: toInputText(a.cost, 'PYG'),
    start_rule: a.start_rule,
    fiscal_life: String(a.fiscal_useful_life_months),
    fiscal_rate: a.fiscal_residual_rate.replace('.', ','),
    authorization: a.fiscal_life_authorization ?? '',
    same_params: same,
    life: String(a.useful_life_months),
    residual: toInputText(a.residual_value, 'PYG'),
    acquisition_number: acquisitionNumber !== null ? String(acquisitionNumber) : '',
  }
}

/** Los parámetros fiscales que propone la categoría al elegirla. */
export function categoryDefaults(c: AssetCategory): Pick<AssetDraft, 'fiscal_life' | 'fiscal_rate'> {
  return { fiscal_life: c.useful_life_months ? String(c.useful_life_months) : '', fiscal_rate: (c.residual_rate ?? '').replace('.', ',') }
}

/**
 * ¿La vida útil o el residual fiscal salen de la tabla de la categoría? Entonces hace falta la
 * autorización de la DNIT (Decreto 3182, art. 31, último párrafo; D-125). Sin datos válidos, no.
 */
export function offTable(d: Pick<AssetDraft, 'fiscal_life' | 'fiscal_rate'>, c: AssetCategory | undefined): boolean {
  if (!c || c.useful_life_months === null || c.residual_rate === null) return false
  const life = parseMonths(d.fiscal_life)
  const rate = parseRate(d.fiscal_rate)
  const tableRate = parseRate(c.residual_rate)
  if (!life.ok || !rate.ok || !tableRate.ok) return false
  return life.value !== c.useful_life_months || compareRate(rate.value, tableRate.value) !== 0
}

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string }

/** Porcentaje escrito por una persona ("10", "12,5", "12.50") → "12.5"; de 0 a 20, hasta dos decimales. */
export function parseRate(text: string): Parsed<string> {
  const t = text.trim().replace('%', '').trim().replace(',', '.')
  if (!t) return { ok: false, error: 'Escribí el porcentaje (0 si no tiene residual).' }
  const m = /^(\d{1,2})(?:\.(\d{1,2}))?$/.exec(t)
  if (!m) return { ok: false, error: 'Un número de 0 a 20, con hasta dos decimales (por ejemplo 10 o 12,5).' }
  const frac = (m[2] ?? '').replace(/0+$/, '')
  const value = `${Number(m[1])}${frac ? `.${frac}` : ''}`
  if (compareRate(value, MAX_RESIDUAL_RATE) > 0) return { ok: false, error: 'El residual fiscal no puede superar el 20 % del costo (Ley 6380, art. 11).' }
  return { ok: true, value }
}

/** Centésimos de un porcentaje canónico ("12.5" → 1250n). */
function rateHundredths(rate: string): bigint {
  const [i, f = ''] = rate.split('.')
  return BigInt(i) * 100n + BigInt((f + '00').slice(0, 2))
}

const compareRate = (a: string, b: string) => {
  const d = rateHundredths(a) - rateHundredths(b)
  return d === 0n ? 0 : d > 0n ? 1 : -1
}

/** Residual fiscal = costo × porcentaje, en guaraníes enteros hacia abajo (igual que la API, D-070). */
export function residualFromRate(cost: string, rate: string): string {
  return bigToPyg((pygToBig(cost) * rateHundredths(rate)) / 10_000n)
}

/** Meses de vida útil: entero de 1 a 1200. */
export function parseMonths(text: string): Parsed<number> {
  const t = text.trim()
  if (!t) return { ok: false, error: 'Escribí la vida útil en meses.' }
  if (!/^\d{1,4}$/.test(t)) return { ok: false, error: 'En meses enteros (por ejemplo 24 para dos años).' }
  const n = Number(t)
  if (n < 1 || n > 1200) return { ok: false, error: 'Entre 1 y 1200 meses.' }
  return { ok: true, value: n }
}

function parsePygPositive(text: string, label: string, allowZero = false): Parsed<string> {
  const p = parseAmountInput(text, 'PYG')
  if (!p.ok) return { ok: false, error: p.error }
  if (p.value.startsWith('-')) return { ok: false, error: `${label} va en positivo.` }
  if (!allowZero && pygToBig(p.value) === 0n) return { ok: false, error: `${label} tiene que ser mayor que cero.` }
  return { ok: true, value: p.value }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Primer día del mes siguiente: "2026-01-20" → "2026-02-01"; diciembre pasa al año siguiente. */
export function nextMonthStart(date: string): string {
  const y = Number(date.slice(0, 4))
  const m = Number(date.slice(5, 7))
  return m === 12 ? `${y + 1}-01-01` : `${y}-${pad(m + 1)}-01`
}

/**
 * Mes de inicio de la depreciación (D-064, Decreto 3182 art. 30), como lo calcula la API:
 * `next_month`, el mes siguiente a la compra; `next_fiscal_year`, el primer mes completo del
 * ejercicio siguiente (o el año civil siguiente si el ejercicio de la compra no está creado).
 */
export function depreciationStart(acquiredOn: string, rule: StartRule, years: FiscalYear[]): string {
  if (rule === 'next_month') return nextMonthStart(acquiredOn)
  const year = years.find((y) => y.start_date <= acquiredOn && acquiredOn <= y.end_date)
  if (!year) return `${Number(acquiredOn.slice(0, 4)) + 1}-01-01`
  // El día siguiente al cierre si es un día 1; si no, el primer mes completo: en los dos casos,
  // el primer día del mes siguiente al del cierre.
  return nextMonthStart(year.end_date)
}

export interface Plan {
  depreciable: string
  months: number
  /** Cuota de los meses 1 a n−1 (hacia abajo). */
  regular: string
  /** La última absorbe la diferencia: la suma es exactamente el importe depreciable (D-057). */
  last: string
}

/** Plan lineal mensual exacto en guaraníes (el mismo cálculo que `depreciation.quota`). */
export function installmentPlan(cost: string, residual: string, months: number): Plan {
  const depreciable = pygToBig(cost) - pygToBig(residual)
  const regular = depreciable / BigInt(months)
  const last = depreciable - regular * BigInt(months - 1)
  return { depreciable: bigToPyg(depreciable), months, regular: bigToPyg(regular), last: bigToPyg(last) }
}

/** Cuota del primer año completo (12 meses o la vida, lo que sea menor). Para comparar fiscal y contable. */
export function annualQuota(plan: Plan): string {
  const n = Math.min(12, plan.months)
  return n === plan.months ? plan.depreciable : bigToPyg(pygToBig(plan.regular) * BigInt(n))
}

export interface AssetCheck {
  errors: Partial<Record<keyof AssetDraft, string>>
  body: FixedAssetIn | null
  fiscal: Plan | null
  accounting: Plan | null
  /** Cuota anual no deducible: la contable supera a la fiscal (RG 77/2020, col. 20). */
  nonDeductible: string | null
}

/**
 * Valida el borrador como la API (residual menor que el costo, residual fiscal hasta 20 %,
 * importe depreciable de al menos un guaraní por mes) y arma el cuerpo. Envía siempre los
 * cuatro parámetros: así el bien guarda exactamente lo que se ve en pantalla.
 */
export function checkAsset(d: AssetDraft, category: AssetCategory | undefined): AssetCheck {
  const errors: AssetCheck['errors'] = {}
  if (!d.category_id) errors.category_id = 'Elegí la categoría.'
  else if (category && !category.complete) errors.category_id = `La categoría está incompleta: falta ${category.missing.join(', ')}.`
  else if (category?.archived_at) errors.category_id = 'La categoría está archivada.'
  if (d.name.trim().length < 2) errors.name = 'Escribí el nombre del bien (al menos 2 caracteres).'
  if (!d.acquired_on) errors.acquired_on = 'Elegí la fecha de adquisición (la del comprobante de compra).'
  const cost = parsePygPositive(d.cost, 'El costo')
  if (!cost.ok) errors.cost = cost.error
  const fLife = parseMonths(d.fiscal_life)
  if (!fLife.ok) errors.fiscal_life = fLife.error
  const fRate = parseRate(d.fiscal_rate)
  if (!fRate.ok) errors.fiscal_rate = fRate.error

  let fiscal: Plan | null = null
  let accounting: Plan | null = null
  let residual: string | null = null
  let life: number | null = null
  if (cost.ok && fRate.ok && fLife.ok) {
    const fResidual = residualFromRate(cost.value, fRate.value)
    fiscal = installmentPlan(cost.value, fResidual, fLife.value)
    if (pygToBig(fiscal.depreciable) < BigInt(fLife.value)) {
      errors.fiscal_life = `El importe depreciable fiscal (${fiscal.depreciable}) es menor que la vida útil en meses: la cuota daría menos de ₲ 1.`
      fiscal = null
    }
    if (d.same_params) {
      residual = fResidual
      life = fLife.value
    }
  }
  if (!d.same_params) {
    const l = parseMonths(d.life)
    if (!l.ok) errors.life = l.error
    else life = l.value
    const r = parsePygPositive(d.residual || '0', 'El residual', true)
    if (!r.ok) errors.residual = r.error
    else if (cost.ok && pygToBig(r.value) >= pygToBig(cost.value)) errors.residual = 'El valor residual contable tiene que ser menor que el costo.'
    else residual = r.value
  }
  if (cost.ok && residual !== null && life !== null) {
    accounting = installmentPlan(cost.value, residual, life)
    if (pygToBig(accounting.depreciable) < BigInt(life)) {
      errors[d.same_params ? 'fiscal_life' : 'life'] = 'El importe depreciable es menor que la vida útil en meses: la cuota daría menos de ₲ 1.'
      accounting = null
    }
  }
  if (d.acquisition_number.trim() && !/^\d{1,9}$/.test(d.acquisition_number.trim())) errors.acquisition_number = 'El número del asiento, sin letras.'
  const needsAuthorization = offTable(d, category)
  const authorization = d.authorization.trim().replace(/\s+/g, ' ')
  if (needsAuthorization && !authorization)
    errors.authorization =
      'La vida útil o el residual fiscal difieren de la categoría: solo la DNIT los cambia, bien por bien (Decreto 3182, art. 31). Escribí el número de su autorización o usá los de la categoría.'
  else if (authorization.length > 100) errors.authorization = 'Hasta 100 caracteres.'

  let nonDeductible: string | null = null
  if (fiscal && accounting) {
    const diff = pygToBig(annualQuota(accounting)) - pygToBig(annualQuota(fiscal))
    nonDeductible = diff > 0n ? bigToPyg(diff) : null
  }

  const ok = Object.keys(errors).length === 0 && cost.ok && fRate.ok && fLife.ok && residual !== null && life !== null
  const body: FixedAssetIn | null = ok
    ? {
        category_id: d.category_id,
        name: d.name.trim(),
        description: d.description.trim() || null,
        serial_or_reference: d.serial_or_reference.trim() || null,
        acquired_on: d.acquired_on,
        cost: cost.value,
        start_rule: d.start_rule,
        fiscal_useful_life_months: fLife.value,
        fiscal_residual_rate: fRate.value,
        fiscal_life_authorization: needsAuthorization ? authorization : null,
        useful_life_months: life as number,
        residual_value: residual as string,
      }
    : null
  return { errors, body, fiscal, accounting, nonDeductible }
}

/** ¿El bien tiene depreciaciones vivas (borrador o contabilizadas)? Entonces solo cambian nombre, descripción, referencia y asiento de compra (D-071). */
export const hasLiveDepreciation = (a: FixedAsset) => (a.installments ?? []).some((i) => i.status !== 'pending')
