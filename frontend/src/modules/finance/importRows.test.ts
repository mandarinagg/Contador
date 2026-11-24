import { describe, expect, it } from 'vitest'
import { filterRows, replaceRow, rowExplanation, rowStatus, tally } from './importRows'
import type { ImportRow } from './types'

const row = (n: number, extra: Partial<ImportRow> = {}): ImportRow => ({
  row_number: n,
  raw: {},
  booked_on: '2026-03-02',
  amount: '-150000',
  description: `Fila ${n}`,
  reference: null,
  error: null,
  duplicate_of: null,
  duplicate_in_file: null,
  decision: 'import',
  ...extra,
})

const rows = [
  row(2),
  row(3, { duplicate_of: 'tx-1', decision: 'skip' }),
  row(4, { duplicate_in_file: 2, decision: 'import' }),
  row(5, { error: 'Fecha inválida: 31/02/2026', booked_on: null, decision: 'skip' }),
  row(6, { decision: 'skip' }),
]

describe('filas de un lote', () => {
  it('clasifica error, duplicado (contra la base o el archivo) y normal', () => {
    expect(rows.map(rowStatus)).toEqual(['ok', 'duplicate', 'duplicate', 'error', 'ok'])
  })

  it('cuenta lo que se va a importar como la API: decisión import y sin error', () => {
    expect(tally(rows)).toEqual({ total: 5, toImport: 2, duplicates: 2, duplicatesImported: 1, errors: 1, skipped: 3 })
    // Una fila con error nunca cuenta como importable, aunque su decisión dijera "import".
    expect(tally([row(9, { error: 'x', decision: 'import' })]).toImport).toBe(0)
  })

  it('filtra para la revisión', () => {
    const numbers = (f: Parameters<typeof filterRows>[1]) => filterRows(rows, f).map((r) => r.row_number)
    expect(numbers('all')).toEqual([2, 3, 4, 5, 6])
    expect(numbers('import')).toEqual([2, 4])
    expect(numbers('skip')).toEqual([3, 5, 6])
    expect(numbers('duplicate')).toEqual([3, 4])
    expect(numbers('error')).toEqual([5])
  })

  it('explica cada estado en palabras', () => {
    expect(rowExplanation(rows[0])).toBeNull()
    expect(rowExplanation(rows[1])).toMatch(/Ya hay un movimiento igual/)
    expect(rowExplanation(rows[2])).toBe('Igual a la fila 2 de este mismo archivo.')
    expect(rowExplanation(rows[3])).toBe('Fecha inválida: 31/02/2026')
  })

  it('reemplaza una fila actualizada por la API', () => {
    const next = replaceRow(rows, { ...rows[1], decision: 'import' })
    expect(next[1].decision).toBe('import')
    expect(next[0]).toBe(rows[0])
    expect(tally(next).toImport).toBe(3)
  })
})
