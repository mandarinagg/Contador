import type { AccountKind, Category, CategoryKind, CounterpartyKind } from './types'

export const ACCOUNT_KIND_LABELS: Record<AccountKind, string> = {
  checking: 'Cuenta corriente',
  savings: 'Caja de ahorro',
  cash: 'Efectivo',
  credit_card: 'Tarjeta de crédito',
  digital_wallet: 'Billetera digital',
  other: 'Otra',
}

export const CATEGORY_KIND_LABELS: Record<CategoryKind, string> = {
  income: 'Ingreso',
  expense: 'Gasto',
}

export const COUNTERPARTY_KIND_LABELS: Record<CounterpartyKind, string> = {
  customer: 'Cliente',
  supplier: 'Proveedor',
  employee: 'Empleado',
  bank: 'Banco',
  government: 'Estado',
  person: 'Persona',
  other: 'Otro',
}

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const MONTHS_LONG = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

/** "2026-03" → "mar 26" (eje del gráfico). */
export function monthShort(month: string): string {
  const [y, m] = month.split('-')
  return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`
}

/** "2026-03" → "marzo de 2026". */
export function monthLong(month: string): string {
  const [y, m] = month.split('-')
  return `${MONTHS_LONG[Number(m) - 1]} de ${y}`
}

/** Fecha contable "2026-03-05" → "05/03/2026" sin pasar por zonas horarias. */
export function formatBookDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

/** Hoy en Asunción como "YYYY-MM-DD" (para valores por defecto de fechas contables). */
export function todayIso(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Asuncion' }).format(new Date())
}

/** Nombre de una categoría con su padre: "Servicios › ANDE". */
export function categoryLabel(categories: Category[], id: string | null): string | null {
  if (!id) return null
  const c = categories.find((x) => x.id === id)
  if (!c) return null
  const parent = c.parent_id ? categories.find((x) => x.id === c.parent_id) : undefined
  return parent ? `${parent.name} › ${c.name}` : c.name
}

/** Orden alfabético en español (tildes y eñes en su lugar). */
export const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, 'es')
