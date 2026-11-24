/**
 * Mapeo de columnas de un extracto (lado de la interfaz).
 *
 * El análisis real (fechas, importes, duplicados) lo hace la API al crear el lote. Acá solo:
 * - se lee el principio del archivo para mostrarlo y ofrecer sus columnas,
 * - se adivina un mapeo inicial a partir de los encabezados típicos de los bancos,
 * - y se normaliza el formulario al `mapping` exacto que espera `POST /imports`.
 */
import type { ImportMapping } from './types'

export type Delimiter = ImportMapping['delimiter']
export const DELIMITERS: { value: Delimiter; label: string }[] = [
  { value: ';', label: 'Punto y coma ( ; )' },
  { value: ',', label: 'Coma ( , )' },
  { value: '\t', label: 'Tabulador' },
  { value: '|', label: 'Barra vertical ( | )' },
]

// Hora opcional al final ("15/01/2026 10:23"): la API la ignora si el formato no la pide.
const TIME = String.raw`(?:[ T]\d{1,2}:\d{2}(?::\d{2})?.*)?`
const datePattern = (body: string) => new RegExp(`^${body}${TIME}$`)

export const DATE_FORMATS: { value: string; label: string; pattern: RegExp }[] = [
  { value: '%d/%m/%Y', label: 'dd/mm/aaaa (31/12/2026)', pattern: datePattern(String.raw`\d{1,2}\/\d{1,2}\/\d{4}`) },
  { value: '%d-%m-%Y', label: 'dd-mm-aaaa (31-12-2026)', pattern: datePattern(String.raw`\d{1,2}-\d{1,2}-\d{4}`) },
  { value: '%d.%m.%Y', label: 'dd.mm.aaaa (31.12.2026)', pattern: datePattern(String.raw`\d{1,2}\.\d{1,2}\.\d{4}`) },
  { value: '%d/%m/%y', label: 'dd/mm/aa (31/12/26)', pattern: datePattern(String.raw`\d{1,2}\/\d{1,2}\/\d{2}`) },
  { value: '%Y-%m-%d', label: 'aaaa-mm-dd (2026-12-31)', pattern: datePattern(String.raw`\d{4}-\d{2}-\d{2}`) },
  { value: '%m/%d/%Y', label: 'mm/dd/aaaa (12/31/2026, formato de EE. UU.)', pattern: /^$/ },
]

/** Formulario del mapeo: todo texto, como lo edita la persona. */
export interface MappingForm {
  has_header: boolean
  delimiter: Delimiter
  encoding: ImportMapping['encoding']
  skip_rows: string
  date_column: string
  date_format: string
  description_column: string
  reference_column: string
  amount_mode: 'single' | 'split'
  amount_column: string
  debit_column: string
  credit_column: string
  decimal_separator: ImportMapping['decimal_separator']
  thousands_separator: ImportMapping['thousands_separator']
}

export const EMPTY_FORM: MappingForm = {
  has_header: true,
  delimiter: ';',
  encoding: 'auto',
  skip_rows: '0',
  date_column: '',
  date_format: '%d/%m/%Y',
  description_column: '',
  reference_column: '',
  amount_mode: 'single',
  amount_column: '',
  debit_column: '',
  credit_column: '',
  decimal_separator: ',',
  thousands_separator: '.',
}

// --- Lectura del principio de un CSV --------------------------------------------------

/** Decodifica como la API con `encoding: auto`: UTF-8 (con o sin BOM) y, si falla, Windows-1252. */
export function decodeText(bytes: Uint8Array, encoding: MappingForm['encoding'] = 'auto'): { text: string; encoding: 'utf-8' | 'cp1252' } {
  if (encoding !== 'cp1252') {
    try {
      return { text: new TextDecoder('utf-8', { fatal: true, ignoreBOM: false }).decode(bytes), encoding: 'utf-8' }
    } catch {
      if (encoding === 'utf-8') return { text: new TextDecoder('utf-8').decode(bytes), encoding: 'utf-8' }
    }
  }
  return { text: new TextDecoder('windows-1252').decode(bytes), encoding: 'cp1252' }
}

/** El separador más frecuente y constante en las primeras líneas. */
export function detectDelimiter(text: string): Delimiter {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '').slice(0, 20)
  let best: Delimiter = ';'
  let bestScore = 0
  for (const { value } of DELIMITERS) {
    const counts = lines.map((l) => parseCsvLine(l, value).length - 1)
    const withIt = counts.filter((c) => c > 0)
    if (withIt.length === 0) continue
    // Muchas líneas con el separador y la misma cantidad de columnas = buen candidato.
    const mode = Math.max(...withIt)
    const score = withIt.length * 10 + withIt.filter((c) => c === mode).length + mode / 100
    if (score > bestScore) {
      bestScore = score
      best = value
    }
  }
  return best
}

function parseCsvLine(line: string, delimiter: string): string[] {
  return parseCsv(line, delimiter, 1)[0] ?? []
}

/** CSV con comillas (RFC 4180): `"a;b"` es un solo campo y `""` es una comilla. */
export function parseCsv(text: string, delimiter: string, maxRows = Infinity): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  const src = text.startsWith('﻿') ? text.slice(1) : text
  for (let i = 0; i < src.length && rows.length < maxRows; i++) {
    const ch = src[i]
    if (quoted) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          field += '"'
          i++
        } else quoted = false
      } else field += ch
    } else if (ch === '"' && field === '') {
      quoted = true
    } else if (ch === delimiter) {
      row.push(field)
      field = ''
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && src[i + 1] === '\n') i++
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else field += ch
  }
  if ((field !== '' || row.length > 0) && rows.length < maxRows) {
    row.push(field)
    rows.push(row)
  }
  return rows
}

// --- Vista de la tabla según el mapeo -------------------------------------------------

export interface TableView {
  /** Nombres con los que el mapeo se refiere a las columnas (encabezado o "1", "2"…). */
  columns: string[]
  /** Encabezado tal como está en el archivo (vacío si no tiene). */
  header: string[]
  /** Filas de datos con su número de fila en el archivo. */
  data: { line: number; cells: string[] }[]
}

/**
 * Aplica `skip_rows` y `has_header` como la API: se saltean las primeras filas del archivo,
 * se ignoran las vacías y la primera no vacía es el encabezado (si lo hay).
 */
export function tableView(rows: string[][], skipRows: number, hasHeader: boolean): TableView {
  const meaningful = rows
    .map((cells, i) => ({ line: i + 1, cells: cells.map((c) => c.trim()) }))
    .filter((r) => r.line > skipRows && r.cells.some((c) => c !== ''))
  const width = Math.max(0, ...meaningful.map((r) => r.cells.length))
  if (hasHeader && meaningful.length > 0) {
    const [head, ...data] = meaningful
    return { header: head.cells, columns: head.cells.filter((c) => c !== ''), data }
  }
  return { header: [], columns: Array.from({ length: width }, (_, i) => String(i + 1)), data: meaningful }
}

// --- Adivinar el mapeo ----------------------------------------------------------------

export const normalizeHeader = (s: string) =>
  s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()

const HINTS: Record<'date' | 'description' | 'reference' | 'amount' | 'debit' | 'credit', RegExp> = {
  date: /^(fecha( (de )?(operacion|movimiento|valor|transaccion|contable))?|fec|date)$/,
  description: /^(concepto|descripcion|detalle|glosa|movimiento|leyenda|description)$/,
  reference: /^(referencia|ref|comprobante|nro( de)? (operacion|comprobante|documento|transaccion)|n operacion|numero( de)? operacion|documento|nro|operacion)$/,
  amount: /^(importe|monto|valor|amount)$/,
  debit: /^(debito|debitos|debe|egreso|egresos|cargo|cargos|retiro|retiros|salida|salidas)$/,
  credit: /^(credito|creditos|haber|ingreso|ingresos|abono|abonos|deposito|depositos|entrada|entradas)$/,
}

/** Primera suposición del mapeo a partir de los encabezados y de la primera fila de datos. */
export function guessMapping(view: TableView, base: MappingForm): MappingForm {
  const find = (re: RegExp) => view.columns.find((c) => re.test(normalizeHeader(c))) ?? ''
  const next = { ...base }
  if (view.header.length > 0) {
    next.date_column = find(HINTS.date) || next.date_column
    next.description_column = find(HINTS.description) || next.description_column
    next.reference_column = find(HINTS.reference) || next.reference_column
    const debit = find(HINTS.debit)
    const credit = find(HINTS.credit)
    const amount = find(HINTS.amount)
    if (debit && credit && !amount) {
      next.amount_mode = 'split'
      next.debit_column = debit
      next.credit_column = credit
    } else if (amount) {
      next.amount_mode = 'single'
      next.amount_column = amount
    }
  }
  const dateIndex = view.header.length > 0 ? view.header.indexOf(next.date_column) : Number(next.date_column) - 1
  const sample = dateIndex >= 0 ? view.data.find((r) => r.cells[dateIndex])?.cells[dateIndex] : undefined
  if (sample) next.date_format = DATE_FORMATS.find((f) => f.pattern.test(sample))?.value ?? next.date_format
  return next
}

/**
 * Mapeo inicial de un archivo recién elegido: encuentra la fila del encabezado (los bancos
 * suelen poner títulos antes), y desde ahí adivina columnas y formato de fecha.
 */
export function initialForm(rows: string[][], delimiter: Delimiter, encoding: MappingForm['encoding'] = 'auto'): MappingForm {
  const headerIndex = rows.slice(0, 30).findIndex((cells) => cells.some((c) => HINTS.date.test(normalizeHeader(c))))
  const skip = Math.max(0, headerIndex)
  const base: MappingForm = { ...EMPTY_FORM, delimiter, encoding, skip_rows: String(skip), has_header: headerIndex >= 0 }
  return guessMapping(tableView(rows, skip, base.has_header), base)
}

// --- Del formulario al mapeo de la API (y de vuelta) ----------------------------------

export type MappingErrors = Partial<Record<keyof MappingForm, string>>

/** Valida y arma el `mapping` exacto de la API. Devuelve los errores por campo si los hay. */
export function buildMapping(form: MappingForm): { mapping: ImportMapping; errors?: undefined } | { mapping?: undefined; errors: MappingErrors } {
  const errors: MappingErrors = {}
  const col = (v: string) => v.trim()
  const required = 'Elegí la columna.'
  if (!col(form.date_column)) errors.date_column = required
  if (!col(form.description_column)) errors.description_column = required
  if (form.amount_mode === 'single') {
    if (!col(form.amount_column)) errors.amount_column = required
  } else {
    if (!col(form.debit_column)) errors.debit_column = required
    if (!col(form.credit_column)) errors.credit_column = required
    if (col(form.debit_column) && col(form.debit_column) === col(form.credit_column)) errors.credit_column = 'Débito y crédito son columnas distintas.'
  }
  if (!form.date_format.includes('%')) errors.date_format = 'El formato usa códigos como %d/%m/%Y.'
  if (form.decimal_separator === form.thousands_separator) errors.thousands_separator = 'Tiene que ser distinto del separador decimal.'
  const skip = form.skip_rows.trim() === '' ? 0 : Number(form.skip_rows)
  if (!Number.isInteger(skip) || skip < 0 || skip > 1000) errors.skip_rows = 'Un número entre 0 y 1000.'
  if (Object.keys(errors).length > 0) return { errors }
  return {
    mapping: {
      has_header: form.has_header,
      delimiter: form.delimiter,
      encoding: form.encoding,
      date_column: col(form.date_column),
      date_format: form.date_format.trim(),
      description_column: col(form.description_column),
      reference_column: col(form.reference_column) || null,
      amount:
        form.amount_mode === 'single'
          ? { mode: 'single', column: col(form.amount_column) }
          : { mode: 'split', debit_column: col(form.debit_column), credit_column: col(form.credit_column) },
      decimal_separator: form.decimal_separator,
      thousands_separator: form.thousands_separator,
      skip_rows: skip,
    },
  }
}

/** Formulario a partir del mapeo guardado en un lote anterior (para reutilizarlo). */
export function formFromMapping(m: ImportMapping): MappingForm {
  return {
    has_header: m.has_header,
    delimiter: m.delimiter,
    encoding: m.encoding,
    skip_rows: String(m.skip_rows ?? 0),
    date_column: m.date_column,
    date_format: m.date_format,
    description_column: m.description_column,
    reference_column: m.reference_column ?? '',
    amount_mode: m.amount.mode,
    amount_column: m.amount.mode === 'single' ? m.amount.column : '',
    debit_column: m.amount.mode === 'split' ? m.amount.debit_column : '',
    credit_column: m.amount.mode === 'split' ? m.amount.credit_column : '',
    decimal_separator: m.decimal_separator,
    thousands_separator: m.thousands_separator,
  }
}

/** Columnas del mapeo que no están en el archivo (para avisar antes de enviar). */
export function missingColumns(form: MappingForm, available: string[]): string[] {
  if (available.length === 0) return []
  const have = new Set(available.map(sameColumnKey))
  const used = [form.date_column, form.description_column, form.reference_column]
  used.push(...(form.amount_mode === 'single' ? [form.amount_column] : [form.debit_column, form.credit_column]))
  return used.map((c) => c.trim()).filter((c) => c !== '' && !have.has(sameColumnKey(c)))
}

/** Igual que la API (`normalize_text`): minúsculas, sin tildes, espacios colapsados. */
function sameColumnKey(s: string): string {
  return s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().split(/\s+/).filter(Boolean).join(' ')
}
