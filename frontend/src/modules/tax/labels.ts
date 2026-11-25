/** Textos de la tributación: nombres de obligaciones, estados, tipos y las dudas abiertas de la investigación. */
import type { Condition, DocType, Direction, IreRegime, VoucherType } from './types'

/** Obligaciones que genera el sistema (regla → nombre, D-085). */
export const OBLIGATION_LABELS: Record<string, string> = {
  'IVA-GENERAL-LIQUIDACION': 'IVA General (Formulario 120)',
  'REG-COMPROB-MENSUAL': 'Registro de comprobantes (RG 90)',
  'IRE-GENERAL-DJ': 'IRE General: declaración anual',
  'IRE-SIMPLE-DJ': 'IRE SIMPLE: declaración anual',
  'EEFF-PRESENTACION': 'Estados financieros',
}

export const obligationLabel = (code: string) => OBLIGATION_LABELS[code] ?? code

/** Obligaciones del perfil por código DNIT: qué son y si la app las calcula (D-085). */
export const DNIT_OBLIGATIONS: { code: string; name: string; hint: string }[] = [
  { code: '211', name: 'IVA General', hint: 'Declaración mensual del IVA (Formulario 120). Solo si la empresa es contribuyente del IVA.' },
  { code: '955', name: 'Registro mensual de comprobantes', hint: 'Compras y ventas del mes en Marangatu (RG 90/2021).' },
  { code: '700', name: 'IRE General', hint: 'Declaración anual del IRE en el régimen general (Formulario 500).' },
  { code: '701', name: 'IRE SIMPLE', hint: 'Declaración anual del IRE en el régimen simple (Formulario 501).' },
  { code: '948', name: 'Estados financieros', hint: 'Presentación anual de los estados financieros.' },
]

export const dnitName = (code: string) => DNIT_OBLIGATIONS.find((o) => o.code === code)?.name ?? `Obligación ${code}`

export const IRE_REGIME_LABELS: Record<IreRegime, string> = {
  ire_general: 'IRE General',
  ire_simple: 'IRE SIMPLE',
  unknown: 'Todavía no lo sé',
}

export const OBLIGATION_STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  overdue: 'Vencida',
  due_soon: 'Vence pronto',
  filed: 'Presentada',
  paid: 'Pagada',
  not_applicable: 'No aplica',
}

export const RULE_STATUS_LABELS: Record<string, string> = {
  pending: 'Sin verificar',
  verified: 'Verificada',
  deprecated: 'Deprecada',
}

export const CONFIDENCE_LABELS: Record<string, string> = {
  oficial_leida: 'Fuente oficial leída',
  oficial_citada_por_terceros: 'Oficial, citada por terceros',
  secundaria: 'Fuente secundaria',
  no_encontrada: 'Fuente no encontrada',
}

export const DIRECTION_LABELS: Record<Direction, string> = { purchase: 'Compra', sale: 'Venta' }
export const DIRECTION_PLURAL: Record<Direction, string> = { purchase: 'Compras', sale: 'Ventas' }

export const VOUCHER_TYPE_LABELS: Record<VoucherType, string> = {
  invoice: 'Factura',
  credit_note: 'Nota de crédito',
  debit_note: 'Nota de débito',
}

/** Tipos de identificación de la Tabla 3 de la RG 90 (D-099), con su código oficial. */
export const DOC_TYPE_LABELS: Record<DocType, string> = {
  ruc: 'RUC (11)',
  identity_card: 'Cédula de identidad (12)',
  passport: 'Pasaporte (13)',
  foreign_id: 'Cédula extranjera (14)',
  unnamed: 'Sin nombre (15)',
  diplomatic: 'Diplomático (16)',
  tax_id: 'Identificación tributaria (17)',
}

export const CONDITION_LABELS: Record<Condition, string> = { cash: 'Contado', credit: 'Crédito' }

/** Dudas abiertas de la investigación de la fase 4 (`docs/research/TRIBUTACION_FASE4.md` §6). */
export const DOUBTS: Record<string, string> = {
  'D-F4-1': 'Separador del CSV: la especificación dice coma y su propio ejemplo usa punto y coma. Probá con un archivo de una línea.',
  'D-F4-2': 'La columna «imputa IRE» aplica solo al IRE SIMPLE según las guías de la DNIT; en el IRE General se marca «no imputar».',
  'D-F4-4': 'Notas de crédito: la guía de registro manual pone la recibida en VENTAS y la emitida en COMPRAS.',
  'D-F4-5': 'No hay una norma que diga hasta cuándo se puede computar el crédito de una factura de un mes anterior.',
  'D-F4-6': 'Qué casillas usa la EAS: 5 % «otros bienes y servicios» (151/157) o agrícolas (150/156); compras directas (32/35/38) o indistintas (33/36/39); de dónde salen las retenciones (52).',
  'D-F4-7': 'Redondeo: la app suma el IVA redondeado de cada comprobante; Marangatu podría calcular sobre la suma de las bases.',
  'D-F4-8': 'Tipo de cambio: comprador o vendedor del BCP del día anterior, o la cotización del comprobante.',
  'D-F4-10': 'El algoritmo del DV coincide con los ejemplos oficiales, pero no se encontró el documento oficial que lo describe. Hay RUC antiguos con letra.',
  'D-F4-11': 'No está claro si un vencimiento en sábado pasa al lunes.',
  'D-F4-12': 'No está claro si un feriado nacional corre los vencimientos de la DNIT.',
}

export const doubtText = (code: string) => DOUBTS[code] ?? 'Duda abierta: ver la investigación de la fase 4.'

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** "2026-11" → "Noviembre de 2026". */
export function monthTitle(month: string): string {
  const [y, m] = month.split('-')
  const name = MONTHS[Number(m) - 1]
  return `${name[0].toUpperCase()}${name.slice(1)} de ${y}`
}

export const monthName = (m: number) => MONTHS[m - 1]

/** Período de una obligación: el mes ("octubre de 2026") o el ejercicio ("ejercicio 2026"). */
export function periodLabel(start: string, end: string): string {
  if (start.slice(0, 7) === end.slice(0, 7)) return monthTitle(start.slice(0, 7)).toLowerCase()
  const sy = start.slice(0, 4)
  const ey = end.slice(0, 4)
  return sy === ey ? `ejercicio ${sy}` : `ejercicio ${sy}-${ey}`
}

/** "2026-11-16" → "lun 16/11" (para las listas del calendario). */
export function shortDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const wd = new Intl.DateTimeFormat('es-PY', { weekday: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, d)))
  return `${wd.replace('.', '')} ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`
}

export const ALERT_TITLES: Record<string, string> = {
  OBLIGATIONS_OVERDUE: 'Vencidas sin presentar',
  OBLIGATIONS_DUE_SOON: 'Vencen pronto',
  REGISTER_UNCONFIRMED: 'Registro de comprobantes sin confirmar',
  MONTHS_WITHOUT_VOUCHERS: 'Meses con movimientos y sin comprobantes',
  PROFILE_MISSING: 'Falta el perfil fiscal',
  PROFILE_UNVERIFIED: 'Perfil fiscal sin verificar',
  RULES_UNVERIFIED: 'Reglas en uso sin verificar',
  COUNTERPARTY_RUC_UNCHECKED: 'RUC antiguos para revisar',
}
