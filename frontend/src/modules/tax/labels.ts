/** Textos de la tributación: nombres de obligaciones, estados, tipos y las dudas abiertas de la investigación. */
import type { LegalForm } from '../../types/api'
import type { Condition, DocType, Direction, IreRegime, VoucherType } from './types'

/** Obligaciones que genera el sistema (regla → nombre, D-085). */
export const OBLIGATION_LABELS: Record<string, string> = {
  'IVA-GENERAL-LIQUIDACION': 'IVA General (Formulario 120)',
  'REG-COMPROB-MENSUAL': 'Registro de comprobantes (RG 90)',
  'IRE-GENERAL-DJ': 'IRE General: declaración anual',
  'IRE-SIMPLE-DJ': 'IRE SIMPLE: declaración anual',
  'EEFF-PRESENTACION': 'Estados financieros',
  'IRP-RSP-DJ': 'IRP-RSP: declaración anual (Formulario 515)',
  'IRP-RGC-DJ': 'IRP-RGC: declaración anual (Formulario 516)',
  'REG-COMPROB-ANUAL': 'Registro anual de comprobantes (956)',
  'IRE-RESIMPLE-DJ': 'RESIMPLE: declaración anual (Formulario 502)',
}

export const obligationLabel = (code: string) => OBLIGATION_LABELS[code] ?? code

/**
 * Obligaciones del perfil por código DNIT: qué son y si la app las calcula (D-085). `forms`: las
 * formas jurídicas que pueden tenerla (sin `forms`, todas); el backend hace el mismo control (D-142).
 */
export const DNIT_OBLIGATIONS: { code: string; name: string; hint: string; forms?: LegalForm[] }[] = [
  { code: '211', name: 'IVA General', hint: 'Declaración mensual del IVA (Formulario 120). Solo para contribuyentes del IVA.' },
  { code: '955', name: 'Registro mensual de comprobantes', hint: 'Compras y ventas del mes en Marangatu (RG 90/2021).' },
  { code: '700', name: 'IRE General', hint: 'Declaración anual del IRE en el régimen general (Formulario 500).' },
  { code: '701', name: 'IRE SIMPLE', hint: 'Declaración anual del IRE en el régimen simple (Formulario 501).' },
  { code: '702', name: 'RESIMPLE', hint: 'Declaración anual del RESIMPLE (Formulario 502), hasta el 26 de febrero.', forms: ['PERSONA_FISICA', 'UNIPERSONAL'] },
  { code: '715', name: 'IRP-RSP', hint: 'Renta personal por servicios (Formulario 515): declaración anual en marzo.', forms: ['PERSONA_FISICA'] },
  { code: '716', name: 'IRP-RGC', hint: 'Rentas y ganancias del capital, como alquileres (Formulario 516): declaración anual en marzo.', forms: ['PERSONA_FISICA'] },
  { code: '956', name: 'Registro anual de comprobantes', hint: 'Ingresos y egresos del año en Marangatu, con la 715 y sin IVA (RG 90/2021): se confirma en febrero.', forms: ['PERSONA_FISICA'] },
  { code: '948', name: 'Estados financieros', hint: 'Presentación anual de los estados financieros.' },
]

/** Las obligaciones de la lista que corresponden a la forma jurídica. */
export const obligationsFor = (legalForm: LegalForm | undefined) => DNIT_OBLIGATIONS.filter((o) => !o.forms || (legalForm !== undefined && o.forms.includes(legalForm)))

export const dnitName = (code: string) => DNIT_OBLIGATIONS.find((o) => o.code === code)?.name ?? `Obligación ${code}`

/** Sin el IRE General, la persona física no está obligada a la partida doble: la contabilidad queda como opcional, nunca se bloquea (D-142). */
export const accountingOptional = (legalForm: LegalForm | undefined, regime: IreRegime | undefined) => legalForm === 'PERSONA_FISICA' && regime !== undefined && regime !== 'ire_general'

export const IRE_REGIME_LABELS: Record<IreRegime, string> = {
  ire_general: 'IRE General',
  ire_simple: 'IRE SIMPLE',
  resimple: 'RESIMPLE',
  none: 'Sin IRE',
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

export const DIRECTION_LABELS: Record<Direction, string> = { purchase: 'Compra', sale: 'Venta', income: 'Ingreso', expense: 'Egreso' }
export const DIRECTION_PLURAL: Record<Direction, string> = { purchase: 'Compras', sale: 'Ventas', income: 'Ingresos', expense: 'Egresos' }

export const VOUCHER_TYPE_LABELS: Record<VoucherType, string> = {
  invoice: 'Factura',
  credit_note: 'Nota de crédito',
  debit_note: 'Nota de débito',
  // Tabla 4 de la RG 90/2021: sin timbrado, del registro de ingresos y egresos (D-143).
  credit_purchase: 'Egreso por compra a crédito (201)',
  foreign_voucher: 'Comprobante del exterior legalizado (202)',
  credit_sale: 'Ingreso por venta a crédito (203)',
  public_entity: 'Entidad pública, religiosa o de beneficio público (204)',
  e_ticketing: 'Extracto de billetaje electrónico (205)',
  ips_statement: 'Extracto de cuenta de IPS (206)',
  card_statement: 'Extracto de tarjeta de crédito o débito (207)',
  payslip: 'Liquidación de salario (208)',
  other_expense: 'Otro comprobante de egreso (209)',
  other_income: 'Otro comprobante de ingreso (210)',
  bank_transfer: 'Transferencia, giro o boleta de depósito (211)',
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

/** Dudas abiertas de la investigación de la fase 4 (`docs/research/TRIBUTACION_FASE4.md` §6). Las resueltas (D-122) ya no se muestran. */
export const DOUBTS: Record<string, string> = {
  'D-F4-1': 'Separador del CSV: la especificación dice coma y su propio ejemplo usa punto y coma. Probá con un archivo de una línea.',
  'D-F4-2': 'La columna «imputa IRE» aplica solo al IRE SIMPLE según las guías de la DNIT; en el IRE General se marca «no imputar».',
  'D-F4-7': 'Redondeo: la app aplica la tasa sobre la suma de las bases del mes, como pide el instructivo del Formulario 120; la norma no dice cómo se redondea la mitad de un guaraní (la app redondea hacia arriba).',
  'D-F4-8': 'Tipo de cambio: comprador o vendedor del BCP del día anterior, o la cotización del comprobante.',
  'D-F4-10': 'El algoritmo del DV coincide con los ejemplos oficiales, pero no se encontró el documento oficial que lo describe. Hay RUC antiguos con letra.',
  'D-F4-12': 'No está claro si un feriado nacional corre los vencimientos de la DNIT.',
  // Persona física (`docs/research/TRIBUTACION_PERSONA_FISICA.md` §9).
  'D-PF-7': 'Si aparece el IVA, la 956 pasa a la 955 en enero del año siguiente (RG 90/2021, art. 14); falta leer el texto de la RG 132/2023.',
  'D-PF-18':
    'Cómo se cargan los importes: en un ingreso, «gravado» y «no gravado o exonerado»; en un egreso, solo el total. El cobro de una venta a crédito (203) va por lo cobrado, y lo que identifica a un comprobante sin número es su período, su contraparte y, en el IPS, el número de empleador.',
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
