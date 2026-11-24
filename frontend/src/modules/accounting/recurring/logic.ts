/** Lógica de los asientos recurrentes (sin componentes). */
import { toInputText } from '../../../lib/money'
import { formatBookDate } from '../../finance/labels'
import { isZeroPyg } from '../amounts'
import { emptyLine, type LineDraft } from '../editor'
import type { RecurringGenerated, RecurringTemplate, TemplateStatus } from '../types3b'

export function generatedMessage(r: RecurringGenerated): string {
  const created = r.created.length
  const existing = r.existing.length
  if (created === 0 && existing === 0) return 'No hay plantillas activas con asiento en este período.'
  const parts = []
  if (created > 0) parts.push(created === 1 ? 'se generó 1 borrador' : `se generaron ${created} borradores`)
  if (existing > 0) parts.push(existing === 1 ? '1 ya existía (no se duplicó)' : `${existing} ya existían (no se duplicaron)`)
  const text = parts.join(' y ')
  return text.charAt(0).toUpperCase() + text.slice(1) + '.'
}

export function validityText(t: Pick<RecurringTemplate, 'start_date' | 'end_date'>): string {
  return t.end_date ? `del ${formatBookDate(t.start_date)} al ${formatBookDate(t.end_date)}` : `desde el ${formatBookDate(t.start_date)}, sin fin`
}

export interface TemplateHeader {
  description: string
  document_reference: string
  day_of_month: string
  start_date: string
  end_date: string
  status: TemplateStatus
}

export function linesFromTemplate(t: Pick<RecurringTemplate, 'lines'>): LineDraft[] {
  return t.lines.map((l) =>
    emptyLine({
      account_id: l.account_id,
      debit: isZeroPyg(l.debit) ? '' : toInputText(l.debit, 'PYG'),
      credit: isZeroPyg(l.credit) ? '' : toInputText(l.credit, 'PYG'),
      description: l.description ?? '',
      cost_center_id: l.cost_center_id ?? '',
    }),
  )
}

/** Validación del encabezado de la plantilla (las reglas de la API). */
export function templateHeaderErrors(h: TemplateHeader): Partial<Record<keyof TemplateHeader, string>> {
  const out: Partial<Record<keyof TemplateHeader, string>> = {}
  if (!h.description.trim()) out.description = 'Escribí qué registra (va como descripción de cada asiento).'
  const day = h.day_of_month.trim()
  if (!/^\d{1,2}$/.test(day) || Number(day) < 1 || Number(day) > 31) out.day_of_month = 'Un día del 1 al 31.'
  if (!h.start_date) out.start_date = 'Elegí desde cuándo rige.'
  if (h.end_date && h.start_date && h.end_date < h.start_date) out.end_date = 'La fecha de fin es anterior a la de inicio.'
  return out
}
