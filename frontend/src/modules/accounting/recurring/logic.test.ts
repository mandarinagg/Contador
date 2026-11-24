import { describe, expect, it } from 'vitest'
import type { Entry } from '../types'
import { generatedMessage, linesFromTemplate, templateHeaderErrors, validityText } from './logic'

const entries = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `e${i}` }) as Entry)
const header = { description: 'Alquiler', document_reference: '', day_of_month: '5', start_date: '2026-01-01', end_date: '', status: 'active' as const }

describe('generación de recurrentes', () => {
  it('dice cuántos se crearon y cuántos ya existían (sin duplicar)', () => {
    expect(generatedMessage({ created: entries(2), existing: [] })).toBe('Se generaron 2 borradores.')
    expect(generatedMessage({ created: [], existing: entries(1) })).toBe('1 ya existía (no se duplicó).')
    expect(generatedMessage({ created: entries(1), existing: entries(3) })).toBe('Se generó 1 borrador y 3 ya existían (no se duplicaron).')
    expect(generatedMessage({ created: [], existing: [] })).toMatch(/No hay plantillas/)
  })
})

describe('plantilla', () => {
  it('valida descripción, día del 1 al 31 y vigencia', () => {
    expect(templateHeaderErrors(header)).toEqual({})
    expect(Object.keys(templateHeaderErrors({ ...header, description: ' ', day_of_month: '32', start_date: '' })).sort()).toEqual([
      'day_of_month',
      'description',
      'start_date',
    ])
    expect(templateHeaderErrors({ ...header, end_date: '2025-12-31' }).end_date).toMatch(/anterior/)
    expect(templateHeaderErrors({ ...header, day_of_month: '0' }).day_of_month).toBeDefined()
  })

  it('pasa las líneas de la API al editor (importes en formato local y el centro)', () => {
    const lines = linesFromTemplate({
      lines: [
        { line_no: 1, account_id: 'g', account_code: '11.01', account_name: 'Gasto', debit: '3500000', credit: '0', description: null, cost_center_id: 'adm' },
        { line_no: 2, account_id: 'b', account_code: '1.01', account_name: 'Banco', debit: '0', credit: '3500000', description: 'Pago', cost_center_id: null },
      ],
    })
    expect(lines.map(({ key: _k, ...l }) => l)).toEqual([
      { account_id: 'g', debit: '3.500.000', credit: '', description: '', fx: null, cost_center_id: 'adm' },
      { account_id: 'b', debit: '', credit: '3.500.000', description: 'Pago', fx: null, cost_center_id: '' },
    ])
  })

  it('describe la vigencia', () => {
    expect(validityText({ start_date: '2026-01-01', end_date: null })).toBe('desde el 01/01/2026, sin fin')
    expect(validityText({ start_date: '2026-01-01', end_date: '2026-12-31' })).toBe('del 01/01/2026 al 31/12/2026')
  })
})
