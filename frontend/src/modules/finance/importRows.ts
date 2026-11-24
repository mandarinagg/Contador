/** Estado de las filas de un lote analizado: clasificación, conteos y filtros de la revisión. */
import type { ImportRow } from './types'

export type RowStatus = 'error' | 'duplicate' | 'ok'
export type RowFilter = 'all' | 'import' | 'duplicate' | 'error' | 'skip'

export function rowStatus(row: ImportRow): RowStatus {
  if (row.error) return 'error'
  if (row.duplicate_of || row.duplicate_in_file !== null) return 'duplicate'
  return 'ok'
}

/** Lo que se va a crear al confirmar: filas a importar sin error (igual que la API). */
export const willImport = (row: ImportRow) => row.decision === 'import' && !row.error

export interface Tally {
  total: number
  toImport: number
  duplicates: number
  duplicatesImported: number
  errors: number
  skipped: number
}

export function tally(rows: ImportRow[]): Tally {
  const t: Tally = { total: rows.length, toImport: 0, duplicates: 0, duplicatesImported: 0, errors: 0, skipped: 0 }
  for (const row of rows) {
    const status = rowStatus(row)
    if (status === 'error') t.errors += 1
    if (status === 'duplicate') {
      t.duplicates += 1
      if (row.decision === 'import') t.duplicatesImported += 1
    }
    if (willImport(row)) t.toImport += 1
    else t.skipped += 1
  }
  return t
}

export function filterRows(rows: ImportRow[], filter: RowFilter): ImportRow[] {
  switch (filter) {
    case 'import':
      return rows.filter(willImport)
    case 'skip':
      return rows.filter((r) => !willImport(r))
    case 'duplicate':
      return rows.filter((r) => rowStatus(r) === 'duplicate')
    case 'error':
      return rows.filter((r) => rowStatus(r) === 'error')
    default:
      return rows
  }
}

/** Explicación del estado de una fila para la persona. */
export function rowExplanation(row: ImportRow): string | null {
  if (row.error) return row.error
  if (row.duplicate_of) return 'Ya hay un movimiento igual en la cuenta (misma fecha, importe, descripción y referencia).'
  if (row.duplicate_in_file !== null) return `Igual a la fila ${row.duplicate_in_file} de este mismo archivo.`
  return null
}

/** Reemplaza una fila (por número) en la lista, sin tocar las demás. */
export function replaceRow(rows: ImportRow[], updated: ImportRow): ImportRow[] {
  return rows.map((r) => (r.row_number === updated.row_number ? updated : r))
}
