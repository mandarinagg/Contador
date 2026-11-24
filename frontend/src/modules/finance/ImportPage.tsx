/**
 * Asistente de importación de extractos (BR-FIN-03, BR-FIN-08):
 * 1. archivo y cuenta → 2. columnas → 3. revisión de filas (válidas, errores, duplicados)
 * → 4. listo. Nada se crea hasta confirmar. El lote en revisión va en la URL (`?lote=`),
 * así que recargar la página no pierde el análisis.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { CheckCircle2, FileSpreadsheet, RotateCcw, Upload } from 'lucide-react'
import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Notice, PageHeader, Select, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime, plural } from '../../lib/format'
import { ApiError, get, patch, post, postForm, qs } from '../../services/api'
import { Amount, ApiErrorNotice, TableSkeleton, Th } from './components'
import { errorMessage } from './forms'
import { financeKeys, useAccounts, useFinance } from './data'
import {
  buildMapping,
  DATE_FORMATS,
  decodeText,
  DELIMITERS,
  detectDelimiter,
  formFromMapping,
  initialForm,
  type MappingErrors,
  type MappingForm,
  missingColumns,
  parseCsv,
  tableView,
} from './importMapping'
import { filterRows, replaceRow, type RowFilter, rowExplanation, rowStatus, tally, willImport } from './importRows'
import { byName, formatBookDate } from './labels'
import { AccountSelect } from './pickers'
import type { Account, ImportBatch, ImportRow } from './types'
import { readXlsxRows } from './xlsxPreview'

const PREVIEW_ROWS = 40
const ROWS_PAGE = 1000
const SHOW_STEP = 300
const STALE_TITLE = 'El análisis quedó desactualizado'

interface LoadedFile {
  file: File
  kind: 'csv' | 'xlsx'
  bytes: Uint8Array
  /** Filas de la hoja (XLSX); en CSV se recalculan con el separador elegido. */
  sheetRows: string[][] | null
  readError?: string
}

const isZip = (b: Uint8Array) => b[0] === 0x50 && b[1] === 0x4b && b[2] === 0x03 && b[3] === 0x04

async function loadFile(file: File): Promise<LoadedFile> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  if (!isZip(bytes)) return { file, kind: 'csv', bytes, sheetRows: null }
  try {
    return { file, kind: 'xlsx', bytes, sheetRows: await readXlsxRows(file, PREVIEW_ROWS) }
  } catch {
    return { file, kind: 'xlsx', bytes, sheetRows: null, readError: 'No se pudo mostrar el contenido del archivo. Podés escribir los nombres de las columnas igual: la API valida el archivo al analizarlo.' }
  }
}

function csvRows(loaded: LoadedFile, form: MappingForm): string[][] {
  if (loaded.kind === 'xlsx') return loaded.sheetRows ?? []
  return parseCsv(decodeText(loaded.bytes, form.encoding).text, form.delimiter, PREVIEW_ROWS)
}

// --- Pasos --------------------------------------------------------------------------

const STEPS = ['Archivo', 'Columnas', 'Revisión', 'Listo'] as const

function Stepper({ current }: { current: number }) {
  return (
    <ol className="mb-6 flex items-center gap-2 text-sm" aria-label="Pasos de la importación">
      {STEPS.map((label, i) => {
        const n = i + 1
        const state = n < current ? 'done' : n === current ? 'current' : 'todo'
        return (
          <li key={label} className="flex items-center gap-2" aria-current={state === 'current' ? 'step' : undefined}>
            {i > 0 && <span aria-hidden className={cx('h-px w-8', n <= current ? 'bg-ledger' : 'bg-line-strong')} />}
            <span
              className={cx(
                'grid size-6 place-items-center rounded-full text-xs font-semibold',
                state === 'done' && 'bg-ledger text-surface',
                state === 'current' && 'border-2 border-ledger text-ledger',
                state === 'todo' && 'border border-line-strong text-ink-3',
              )}
            >
              {state === 'done' ? '✓' : n}
            </span>
            <span className={cx(state === 'current' ? 'font-semibold text-ink' : 'text-ink-2')}>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}

function FileStep({
  accounts,
  accountId,
  onAccount,
  onFile,
  busy,
}: {
  accounts: Account[]
  accountId: string
  onAccount: (id: string) => void
  onFile: (f: File) => void
  busy: boolean
}) {
  const { cid } = useFinance()
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const recent = useQuery({
    queryKey: [...financeKeys.imports(cid), 'recent'],
    queryFn: () => get<ImportBatch[]>(`/finance/contexts/${cid}/imports${qs({ limit: 8 })}`),
  })
  const accountName = (id: string) => accounts.find((a) => a.id === id)?.name ?? 'Cuenta'

  return (
    <div className="flex flex-col gap-6">
      <Sheet className="p-6">
        <div className="grid max-w-2xl gap-5">
          <Field label="Cuenta del extracto" hint="Los movimientos se van a crear en esta cuenta, con su moneda.">
            {(p) => <AccountSelect {...p} accounts={accounts} value={accountId} onChange={(e) => onAccount(e.target.value)} />}
          </Field>
          <div>
            <p className="mb-1.5 text-sm font-medium text-ink-2" id="archivo-label">
              Archivo
            </p>
            <label
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                const f = e.dataTransfer.files[0]
                if (f) setFile(f)
              }}
              className={cx(
                'flex cursor-pointer flex-col items-center gap-2 rounded-md border-2 border-dashed px-6 py-8 text-center transition-colors has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
                dragging ? 'border-ledger bg-ledger-soft' : 'border-line-strong hover:bg-sunken',
              )}
            >
              <FileSpreadsheet size={28} className="text-ink-3" aria-hidden />
              {file ? (
                <span>
                  <span className="font-medium">{file.name}</span>
                  <span className="block text-sm text-ink-2">{(file.size / 1024).toFixed(0)} KB · elegí otro si no es este</span>
                </span>
              ) : (
                <span>
                  <span className="font-medium text-ledger">Elegí el extracto</span> o arrastralo acá
                  <span className="block text-sm text-ink-2">CSV o Excel (.xlsx), hasta 10 MB y 20.000 filas. El .xls antiguo no se admite.</span>
                </span>
              )}
              <input
                type="file"
                aria-labelledby="archivo-label"
                accept=".csv,.txt,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="sr-only"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
          <div>
            <Button disabled={!file || !accountId} busy={busy} onClick={() => file && onFile(file)}>
              Continuar
            </Button>
          </div>
        </div>
      </Sheet>

      {recent.data && recent.data.length > 0 && (
        <Sheet>
          <h2 className="border-b border-line px-4 py-3 font-semibold">Importaciones recientes</h2>
          <ul className="divide-y divide-line">
            {recent.data.map((b) => (
              <li key={b.id} className="flex items-center gap-4 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{b.filename}</span>
                  <span className="text-ink-2"> → {accountName(b.account_id)}</span>
                </span>
                <span className="text-ink-3">{formatDateTime(b.created_at)}</span>
                {b.status === 'committed' && <Badge tone="ok">{plural(b.rows_imported, 'importado', 'importados')}</Badge>}
                {b.status === 'cancelled' && <Badge>Cancelada</Badge>}
                {b.status === 'previewed' && (
                  <Link to={`?lote=${b.id}`} className="font-medium text-ledger hover:underline">
                    Retomar revisión
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </Sheet>
      )}
    </div>
  )
}

function ColumnPicker({
  label,
  value,
  onChange,
  columns,
  error,
  optional,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  columns: string[]
  error?: string
  optional?: boolean
}) {
  return (
    <Field label={label} error={error} hint={optional ? 'Opcional.' : undefined}>
      {(p) =>
        columns.length > 0 ? (
          <Select {...p} value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="">{optional ? '— Ninguna —' : '— Elegí una columna —'}</option>
            {value && !columns.includes(value) && <option value={value}>{value} (no está en el archivo)</option>}
            {columns.map((c) => (
              <option key={c} value={c}>
                {/^\d+$/.test(c) ? `Columna ${c}` : c}
              </option>
            ))}
          </Select>
        ) : (
          <Input {...p} value={value} placeholder="Nombre exacto de la columna" onChange={(e) => onChange(e.target.value)} />
        )
      }
    </Field>
  )
}

function MappingStep({
  loaded,
  account,
  form,
  setForm,
  onBack,
  onAnalyzed,
}: {
  loaded: LoadedFile
  account: Account
  form: MappingForm
  setForm: (f: MappingForm) => void
  onBack: () => void
  onAnalyzed: (batch: ImportBatch) => void
}) {
  const { cid } = useFinance()
  const [errors, setErrors] = useState<MappingErrors>({})
  const [serverColumns, setServerColumns] = useState<string[]>([])
  const last = useQuery({
    queryKey: [...financeKeys.imports(cid), 'last', account.id],
    queryFn: () => get<ImportBatch[]>(`/finance/contexts/${cid}/imports${qs({ account_id: account.id, limit: 1 })}`),
  })
  const lastBatch = last.data?.[0]
  const rows = useMemo(() => csvRows(loaded, form), [loaded, form])
  const skip = Number(form.skip_rows) || 0
  const view = tableView(rows, skip, form.has_header)
  const columns = view.columns.length > 0 ? view.columns : serverColumns
  const missing = missingColumns(form, columns)
  const set = (patchForm: Partial<MappingForm>) => setForm({ ...form, ...patchForm })

  const analyze = useMutation({
    mutationFn: (mapping: object) => {
      const body = new FormData()
      body.set('file', loaded.file)
      body.set('account_id', account.id)
      body.set('mapping', JSON.stringify(mapping))
      return postForm<ImportBatch>(`/finance/contexts/${cid}/imports${qs({ rows_limit: ROWS_PAGE })}`, body)
    },
    onSuccess: onAnalyzed,
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'IMPORT_COLUMN_NOT_FOUND') {
        const available = (e.details as { available?: string[] } | null)?.available ?? []
        if (available.length > 0) setServerColumns(available)
      }
    },
  })
  const apiError = analyze.error instanceof ApiError ? analyze.error : null
  const columnDetails = apiError?.code === 'IMPORT_COLUMN_NOT_FOUND' ? (apiError.details as { missing?: string[]; available?: string[] }) : null

  const submit = () => {
    const built = buildMapping(form)
    setErrors(built.errors ?? {})
    if (built.mapping) analyze.mutate(built.mapping)
  }

  // Columnas del mapeo resaltadas en la vista previa.
  const roles = new Map<string, string>()
  const mark = (col: string, role: string) => col && roles.set(col, role)
  mark(form.date_column, 'Fecha')
  mark(form.description_column, 'Descripción')
  mark(form.reference_column, 'Referencia')
  if (form.amount_mode === 'single') mark(form.amount_column, 'Importe')
  else {
    mark(form.debit_column, 'Débito (sale)')
    mark(form.credit_column, 'Crédito (entra)')
  }
  const width = Math.max(0, ...rows.slice(0, PREVIEW_ROWS).map((r) => r.length))
  const nameOf = (i: number) => (form.has_header ? (view.header[i] ?? '') : String(i + 1))
  const headerLine = form.has_header ? (rows.findIndex((r, i) => i + 1 > skip && r.some((c) => c.trim() !== '')) + 1) : 0

  return (
    <div className="flex flex-col gap-5">
      <Sheet className="flex items-center justify-between gap-4 px-5 py-3.5">
        <p className="min-w-0">
          <span className="font-medium">{loaded.file.name}</span>
          <span className="text-ink-2">
            {' '}
            → {account.name} ({account.currency}) · {loaded.kind === 'xlsx' ? 'Excel (primera hoja)' : 'CSV'}
          </span>
        </p>
        <Button variant="ghost" onClick={onBack}>
          Cambiar archivo o cuenta
        </Button>
      </Sheet>

      {lastBatch && (
        <Notice tone="neutral" title="Esta cuenta ya tiene una importación anterior">
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {lastBatch.filename}, {formatDateTime(lastBatch.created_at)}. Si el banco no cambió el formato, usá el mismo mapeo.
            <button type="button" className="font-medium text-ledger hover:underline" onClick={() => setForm(formFromMapping(lastBatch.mapping))}>
              Usar el mapeo de la última importación
            </button>
          </span>
        </Notice>
      )}
      {loaded.readError && <Notice tone="warn" title="Sin vista previa del archivo">{loaded.readError}</Notice>}

      <div className="grid grid-cols-[22rem_minmax(0,1fr)] items-start gap-5">
        <Sheet className="flex flex-col gap-5 p-5">
          <fieldset className="flex flex-col gap-3">
            <legend className="mb-2 font-semibold">Estructura</legend>
            <Field label="Filas a saltear al principio" hint="Títulos del banco antes del encabezado." error={errors.skip_rows}>
              {(p) => <Input {...p} inputMode="numeric" className="w-24" value={form.skip_rows} onChange={(e) => set({ skip_rows: e.target.value.replace(/\D/g, '') })} />}
            </Field>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="size-4 accent-(--ledger)" checked={form.has_header} onChange={(e) => set({ has_header: e.target.checked })} />
              La primera fila tiene los nombres de las columnas
            </label>
            {loaded.kind === 'csv' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Separador">
                  {(p) => (
                    <Select {...p} value={form.delimiter} onChange={(e) => set({ delimiter: e.target.value as MappingForm['delimiter'] })}>
                      {DELIMITERS.map((d) => (
                        <option key={d.value} value={d.value}>
                          {d.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field label="Codificación">
                  {(p) => (
                    <Select {...p} value={form.encoding} onChange={(e) => set({ encoding: e.target.value as MappingForm['encoding'] })}>
                      <option value="auto">Automática</option>
                      <option value="utf-8">UTF-8</option>
                      <option value="cp1252">Windows (ANSI)</option>
                    </Select>
                  )}
                </Field>
              </div>
            )}
          </fieldset>

          <fieldset className="flex flex-col gap-3 border-t border-line pt-4">
            <legend className="mb-2 font-semibold">Columnas</legend>
            <ColumnPicker label="Fecha" value={form.date_column} onChange={(v) => set({ date_column: v })} columns={columns} error={errors.date_column} />
            <Field label="Formato de la fecha" error={errors.date_format} hint={loaded.kind === 'xlsx' ? 'Las celdas con formato de fecha de Excel se leen solas.' : undefined}>
              {(p) => (
                <Select {...p} value={form.date_format} onChange={(e) => set({ date_format: e.target.value })}>
                  {!DATE_FORMATS.some((f) => f.value === form.date_format) && <option value={form.date_format}>{form.date_format}</option>}
                  {DATE_FORMATS.map((f) => (
                    <option key={f.value} value={f.value}>
                      {f.label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <ColumnPicker label="Descripción" value={form.description_column} onChange={(v) => set({ description_column: v })} columns={columns} error={errors.description_column} />
            <ColumnPicker label="Referencia" optional value={form.reference_column} onChange={(v) => set({ reference_column: v })} columns={columns} />
            <fieldset>
              <legend className="mb-1.5 text-sm font-medium text-ink-2">Importe</legend>
              <div className="flex flex-col gap-1.5">
                <label className="flex items-center gap-2">
                  <input type="radio" name="amount_mode" className="accent-(--ledger)" checked={form.amount_mode === 'single'} onChange={() => set({ amount_mode: 'single' })} />
                  Una columna con signo (negativo = sale)
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="amount_mode" className="accent-(--ledger)" checked={form.amount_mode === 'split'} onChange={() => set({ amount_mode: 'split' })} />
                  Dos columnas: débito y crédito
                </label>
              </div>
            </fieldset>
            {form.amount_mode === 'single' ? (
              <ColumnPicker label="Columna del importe" value={form.amount_column} onChange={(v) => set({ amount_column: v })} columns={columns} error={errors.amount_column} />
            ) : (
              <>
                <ColumnPicker label="Débito (sale)" value={form.debit_column} onChange={(v) => set({ debit_column: v })} columns={columns} error={errors.debit_column} />
                <ColumnPicker label="Crédito (entra)" value={form.credit_column} onChange={(v) => set({ credit_column: v })} columns={columns} error={errors.credit_column} />
              </>
            )}
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 border-t border-line pt-4">
            <legend className="mb-2 font-semibold">Números</legend>
            <Field label="Decimales con">
              {(p) => (
                <Select {...p} value={form.decimal_separator} onChange={(e) => set({ decimal_separator: e.target.value as MappingForm['decimal_separator'] })}>
                  <option value=",">Coma (1.234,50)</option>
                  <option value=".">Punto (1,234.50)</option>
                </Select>
              )}
            </Field>
            <Field label="Miles con" error={errors.thousands_separator}>
              {(p) => (
                <Select {...p} value={form.thousands_separator} onChange={(e) => set({ thousands_separator: e.target.value as MappingForm['thousands_separator'] })}>
                  <option value=".">Punto</option>
                  <option value=",">Coma</option>
                  <option value=" ">Espacio</option>
                  <option value="">Sin separador</option>
                </Select>
              )}
            </Field>
          </fieldset>
        </Sheet>

        <div className="sticky top-4 flex min-w-0 flex-col gap-4">
          {apiError && (
            <Notice tone="bad" title={apiError.message}>
              {columnDetails?.available && columnDetails.available.length > 0 && (
                <>Columnas del archivo: {columnDetails.available.join(', ')}. Elegilas en los campos de la izquierda.</>
              )}
              {apiError.code === 'IMPORT_UNSUPPORTED_FORMAT' && ' Elegí otro archivo con «Cambiar archivo o cuenta».'}
              {Object.values(apiError.fieldErrors()).join(' ')}
            </Notice>
          )}
          {missing.length > 0 && !apiError && (
            <Notice tone="warn" title="Hay columnas del mapeo que no están en el archivo">
              {missing.join(', ')}. Elegí las columnas correctas antes de analizar.
            </Notice>
          )}
          <Sheet className="min-w-0">
            <h2 className="flex items-baseline justify-between border-b border-line px-4 py-3 font-semibold">
              Así se lee el archivo
              <span className="text-sm font-normal text-ink-3">Primeras {Math.min(rows.length, PREVIEW_ROWS)} filas</span>
            </h2>
            {rows.length === 0 ? (
              <p className="px-4 py-6 text-ink-2">Sin vista previa disponible.</p>
            ) : (
              <div className="max-h-[32rem] overflow-auto">
                <table className="w-max min-w-full text-sm">
                  <thead className="sticky top-0 bg-sunken text-ink-2">
                    <tr>
                      <th scope="col" className="px-2 py-2 text-right font-medium">Fila</th>
                      {Array.from({ length: width }, (_, i) => {
                        const role = roles.get(nameOf(i))
                        return (
                          <th key={i} scope="col" className="px-3 py-2 text-left font-medium whitespace-nowrap">
                            {role ? <Badge tone="ok">{role}</Badge> : <span className="text-ink-3">—</span>}
                          </th>
                        )
                      })}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {rows.slice(0, PREVIEW_ROWS).map((cells, i) => {
                      const line = i + 1
                      const skipped = line <= skip
                      const isHeader = line === headerLine
                      return (
                        <tr key={line} className={cx(skipped && 'text-ink-3 line-through decoration-1', isHeader && 'bg-ledger-soft font-semibold')}>
                          <td className="px-2 py-1.5 text-right text-xs text-ink-3 tabular-nums no-underline">{line}</td>
                          {Array.from({ length: width }, (_, j) => (
                            <td key={j} className={cx('max-w-64 truncate px-3 py-1.5 whitespace-nowrap', !skipped && !isHeader && roles.has(nameOf(j)) && 'bg-ledger-soft/50')}>
                              {cells[j] ?? ''}
                            </td>
                          ))}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="border-t border-line px-4 py-2.5 text-sm text-ink-3">
              Tachadas: filas que se saltean. Resaltada: el encabezado. Analizar no crea movimientos: primero vas a revisar cada fila.
            </p>
          </Sheet>
          <div className="flex gap-2">
            <Button onClick={submit} busy={analyze.isPending}>
              <Upload size={16} />
              Analizar archivo
            </Button>
            <Button variant="ghost" onClick={onBack}>
              Volver
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// --- Revisión del lote ------------------------------------------------------------------

type BatchPages = InfiniteData<ImportBatch, number | null>

function batchKey(cid: string, bid: string) {
  return [...financeKeys.imports(cid), 'batch', bid] as const
}

/** Conteo que además filtra la tabla: el número dice cuántas, el texto qué son. */
function FilterChip({ active, onClick, count, label, tone }: { active: boolean; onClick: () => void; count: number; label: string; tone?: 'warn' | 'bad' | 'ok' }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        'flex flex-col items-start rounded-md border px-4 py-2.5 text-left transition-colors',
        active ? 'border-ink bg-surface shadow-(--shadow-sheet)' : 'border-line bg-surface/60 hover:bg-surface',
      )}
    >
      <span className={cx('text-lg leading-tight font-semibold', tone === 'bad' && 'text-debit', tone === 'warn' && 'text-amber', tone === 'ok' && 'text-ledger')}>
        {count}
      </span>
      <span className="text-sm text-ink-2">{label}</span>
    </button>
  )
}

function ReviewStep({
  bid,
  accounts,
  onReanalyze,
  onDone,
}: {
  bid: string
  accounts: Account[]
  onReanalyze: (batch: ImportBatch) => void
  onDone: () => void
}) {
  const { cid, canWrite } = useFinance()
  const qc = useQueryClient()
  const toast = useToast()
  const [filter, setFilter] = useState<RowFilter>('all')
  const [shown, setShown] = useState(SHOW_STEP)
  const [notice, setNotice] = useState<{ tone: 'warn' | 'bad'; title: string; body?: ReactNode } | null>(null)

  const batch = useInfiniteQuery({
    queryKey: batchKey(cid, bid),
    queryFn: ({ pageParam }) =>
      get<ImportBatch>(`/finance/contexts/${cid}/imports/${bid}${qs({ rows_limit: ROWS_PAGE, rows_after: pageParam ?? undefined })}`),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (last.rows && last.rows.length === ROWS_PAGE ? last.rows[last.rows.length - 1].row_number : undefined),
  })
  // Se traen todas las filas (hasta 20.000) para que los conteos y la revisión sean completos.
  useEffect(() => {
    if (batch.hasNextPage && !batch.isFetchingNextPage) void batch.fetchNextPage()
  }, [batch])

  const pages = batch.data?.pages ?? []
  const meta = pages[pages.length - 1]
  const rows = pages.flatMap((p) => p.rows ?? [])
  const loadingRows = batch.hasNextPage || batch.isFetchingNextPage
  const account = accounts.find((a) => a.id === meta?.account_id)
  const t = tally(rows)

  const setRows = (update: (rows: ImportRow[]) => ImportRow[]) =>
    qc.setQueryData<BatchPages>(batchKey(cid, bid), (old) =>
      old ? { ...old, pages: old.pages.map((p) => ({ ...p, rows: p.rows ? update(p.rows) : p.rows })) } : old,
    )

  const decide = useMutation({
    mutationFn: ({ row, decision }: { row: ImportRow; decision: 'import' | 'skip' }) =>
      patch<ImportRow>(`/finance/contexts/${cid}/imports/${bid}/rows/${row.row_number}`, { decision }),
    onSuccess: (updated) => setRows((list) => replaceRow(list, updated)),
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar la decisión de la fila.')),
  })

  const commit = useMutation({
    mutationFn: () => post<ImportBatch>(`/finance/contexts/${cid}/imports/${bid}/commit`),
    onSuccess: (done) => {
      setNotice(null)
      qc.setQueryData<BatchPages>(batchKey(cid, bid), (old) => (old ? { ...old, pages: old.pages.map((p) => ({ ...done, rows: p.rows })) } : old))
      qc.invalidateQueries({ queryKey: financeKeys.context(cid) })
      qc.invalidateQueries({ queryKey: financeKeys.consolidated() })
      toast('ok', `Se importaron ${plural(done.rows_imported, 'movimiento', 'movimientos')}.`)
    },
    onError: (e) => {
      if (!(e instanceof ApiError)) return setNotice({ tone: 'bad', title: errorMessage(e) })
      if (e.code === 'IMPORT_NEW_DUPLICATES') {
        const list = (e.details as { rows?: number[] } | null)?.rows ?? []
        setNotice({
          tone: 'warn',
          title: 'Aparecieron movimientos iguales desde el análisis',
          body: (
            <>
              Alguien cargó o importó en esta cuenta movimientos iguales a {list.length === 1 ? 'la fila' : 'las filas'} {list.join(', ')} después de que
              analizaste el archivo. Se marcaron como duplicadas y no se van a importar. Revisalas abajo (filtro «Duplicadas») y, si son legítimas,
              marcalas para importar. Después confirmá de nuevo: no se creó nada todavía.
            </>
          ),
        })
        setFilter('duplicate')
        void qc.invalidateQueries({ queryKey: batchKey(cid, bid) })
      } else if (e.code === 'IMPORT_STALE') {
        setNotice({
          tone: 'bad',
          title: STALE_TITLE,
          body: (
            <>
              {e.message} Este lote ya no se puede confirmar y no se creó nada. Cancelalo o volvé a analizar el archivo con la cuenta como está
              ahora.
            </>
          ),
        })
      } else if (e.code === 'IMPORT_ALREADY_COMMITTED' || e.code === 'IMPORT_CANCELLED') {
        setNotice({ tone: 'warn', title: e.message })
        void qc.invalidateQueries({ queryKey: batchKey(cid, bid) })
      } else {
        setNotice({ tone: 'bad', title: e.message })
      }
    },
  })

  const cancel = useMutation({
    mutationFn: () => post<ImportBatch>(`/finance/contexts/${cid}/imports/${bid}/cancel`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: financeKeys.imports(cid) })
      toast('ok', 'Importación cancelada. No se creó ningún movimiento.')
      onDone()
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cancelar la importación.')),
  })

  if (batch.isPending) return <TableSkeleton rows={6} cols={6} />
  if (batch.isError || !meta) {
    return (
      <EmptyState title="No se pudo abrir el análisis" action={<Button variant="secondary" onClick={onDone}>Empezar una importación</Button>}>
        {errorMessage(batch.error)}
      </EmptyState>
    )
  }

  if (meta.status === 'committed') {
    return (
      <>
      <Stepper current={4} />
      <Sheet className="p-8">
        <CheckCircle2 size={28} className="text-ledger" aria-hidden />
        <h2 className="mt-3 text-lg font-semibold">Listo: {plural(meta.rows_imported, 'movimiento importado', 'movimientos importados')}</h2>
        <p className="mt-1 max-w-[65ch] text-ink-2">
          En {account?.name ?? 'la cuenta'} desde {meta.filename}. Nacen <strong>sin revisar</strong>: pasá por Movimientos para asignarles categoría y
          marcarlos revisados. {meta.rows_duplicate > 0 && `${plural(meta.rows_duplicate, 'fila duplicada', 'filas duplicadas')} y `}
          {meta.rows_error > 0 && `${plural(meta.rows_error, 'fila con error', 'filas con error')} `}
          {(meta.rows_duplicate > 0 || meta.rows_error > 0) && 'quedaron en el lote sin importar.'}
        </p>
        <div className="mt-5 flex gap-2">
          <Link
            to={`/finanzas/${cid}/movimientos?account_id=${meta.account_id}&unreviewed=1`}
            className="inline-flex h-9 items-center gap-2 rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong"
          >
            Revisar los importados
          </Link>
          <Button variant="secondary" onClick={onDone}>
            Importar otro extracto
          </Button>
        </div>
      </Sheet>
      </>
    )
  }
  if (meta.status === 'cancelled') {
    return (
      <EmptyState title="Esta importación fue cancelada" action={<Button onClick={onDone}>Empezar otra importación</Button>}>
        No se creó ningún movimiento a partir de {meta.filename}.
      </EmptyState>
    )
  }

  const visible = filterRows(rows, filter)
  return (
    <div className="flex flex-col gap-4">
      <Stepper current={3} />
      <Sheet className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
        <p>
          <span className="font-medium">{meta.filename}</span>
          <span className="text-ink-2">
            {' '}
            → {account?.name ?? 'Cuenta'} ({meta.currency}) · analizado {formatDateTime(meta.created_at)}
          </span>
        </p>
        <Badge tone="warn">Sin confirmar: todavía no se creó nada</Badge>
      </Sheet>

      {notice && (
        <Notice tone={notice.tone} title={notice.title}>
          {notice.body}
          {notice.title === STALE_TITLE && (
            <span className="mt-2 block">
              <Button variant="secondary" onClick={() => onReanalyze(meta)}>
                <RotateCcw size={15} />
                Analizar de nuevo
              </Button>
            </span>
          )}
        </Notice>
      )}

      <div className="grid grid-cols-5 gap-2" role="group" aria-label="Filtrar filas">
        {(
          [
            ['all', t.total, 'Filas', undefined],
            ['import', t.toImport, 'A importar', 'ok'],
            ['duplicate', t.duplicates, 'Duplicadas', 'warn'],
            ['error', t.errors, 'Con error', 'bad'],
            ['skip', t.skipped, 'Se omiten', undefined],
          ] as const
        ).map(([key, n, label, tone]) => (
          <FilterChip
            key={key}
            active={filter === key}
            tone={tone}
            count={n}
            label={label}
            onClick={() => {
              setFilter(key)
              setShown(SHOW_STEP)
            }}
          />
        ))}
      </div>

      <Sheet>
        {visible.length === 0 ? (
          <p className="px-5 py-8 text-ink-2">No hay filas en este grupo.</p>
        ) : (
          <table className="w-full table-fixed text-sm">
            <colgroup>
              <col className="w-14" />
              <col className="w-26" />
              <col />
              <col className="w-36" />
              <col className="w-64" />
              <col className="w-24" />
            </colgroup>
            <thead className="border-b border-line bg-sunken text-ink-2">
              <tr>
                <Th align="right">Fila</Th>
                <Th>Fecha</Th>
                <Th>Descripción</Th>
                <Th align="right">Importe</Th>
                <Th>Estado</Th>
                <Th>Importar</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visible.slice(0, shown).map((row) => {
                const status = rowStatus(row)
                const importing = willImport(row)
                return (
                  <tr key={row.row_number} className={cx('align-top', !importing && 'text-ink-2')}>
                    <td className="px-4 py-2.5 text-right text-ink-3 tabular-nums">{row.row_number}</td>
                    <td className="px-4 py-2.5 tabular-nums">{row.booked_on ? formatBookDate(row.booked_on) : <span className="text-ink-3">—</span>}</td>
                    <td className="px-4 py-2.5">
                      <p className="break-words">{row.description ?? <span className="text-ink-3">{Object.values(row.raw).filter(Boolean).join(' · ')}</span>}</p>
                      {row.reference && <p className="text-ink-3">Ref. {row.reference}</p>}
                    </td>
                    <td className="px-4 py-2.5 text-right">{row.amount ? <Amount value={row.amount} currency={meta.currency} flow /> : <span className="text-ink-3">—</span>}</td>
                    <td className="px-4 py-2.5">
                      {status === 'ok' ? (
                        <Badge tone="ok">Válida</Badge>
                      ) : (
                        <>
                          <Badge tone={status === 'error' ? 'bad' : 'warn'}>{status === 'error' ? 'Error' : 'Duplicada'}</Badge>
                          <p className={cx('mt-1', status === 'error' ? 'text-debit' : 'text-ink-2')}>{rowExplanation(row)}</p>
                        </>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <label className={cx('flex items-center gap-2', row.error || !canWrite ? 'text-ink-3' : 'cursor-pointer')}>
                        <input
                          type="checkbox"
                          className="size-4 accent-(--ledger)"
                          checked={importing}
                          disabled={Boolean(row.error) || !canWrite || decide.isPending}
                          aria-label={`Importar la fila ${row.row_number}`}
                          onChange={(e) => decide.mutate({ row, decision: e.target.checked ? 'import' : 'skip' })}
                        />
                        {importing ? 'Sí' : 'No'}
                      </label>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {visible.length > shown && (
          <div className="border-t border-line p-4">
            <Button variant="secondary" onClick={() => setShown(shown + SHOW_STEP)}>
              Mostrar {Math.min(SHOW_STEP, visible.length - shown)} filas más de {visible.length - shown}
            </Button>
          </div>
        )}
      </Sheet>

      {canWrite && (
        <div className="sticky bottom-0 -mx-2 flex items-center justify-between gap-4 rounded-md border border-line bg-surface px-5 py-3.5 shadow-(--shadow-float)">
          <p className="text-ink-2">
            {loadingRows ? (
              <span className="inline-flex items-center gap-2">
                <Skeleton className="h-4 w-4" /> Cargando todas las filas…
              </span>
            ) : t.toImport === 0 ? (
              'No hay filas marcadas para importar.'
            ) : (
              <>
                Se van a crear <strong className="text-ink">{plural(t.toImport, 'movimiento', 'movimientos')}</strong> en {account?.name ?? 'la cuenta'}, sin
                revisar.
                {t.duplicatesImported > 0 && ` Incluye ${plural(t.duplicatesImported, 'duplicado que marcaste', 'duplicados que marcaste')} como legítimo.`}
              </>
            )}
          </p>
          <div className="flex shrink-0 gap-2">
            <Button variant="ghost" busy={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancelar importación
            </Button>
            <Button
              busy={commit.isPending}
              disabled={loadingRows || t.toImport === 0 || notice?.title === STALE_TITLE}
              onClick={() => commit.mutate()}
            >
              Confirmar importación
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// --- Página ---------------------------------------------------------------------------

export function ImportPage() {
  const { cid, canWrite, readOnlyReason } = useFinance()
  const accounts = useAccounts(cid)
  const [params, setParams] = useSearchParams()
  const bid = params.get('lote')
  const [accountId, setAccountId] = useState(params.get('cuenta') ?? '')
  const [loaded, setLoaded] = useState<LoadedFile | null>(null)
  const [form, setForm] = useState<MappingForm | null>(null)
  const [reading, setReading] = useState(false)
  const toast = useToast()
  const active = (accounts.data ?? []).filter((a) => !a.archived_at).sort(byName)
  const account = (accounts.data ?? []).find((a) => a.id === (accountId || active[0]?.id))

  const chooseFile = async (file: File) => {
    setReading(true)
    try {
      const l = await loadFile(file)
      if (l.kind === 'xlsx') {
        setForm(initialForm(l.sheetRows ?? [], ';'))
      } else {
        const { text } = decodeText(l.bytes)
        const delimiter = detectDelimiter(text)
        setForm(initialForm(parseCsv(text, delimiter, PREVIEW_ROWS), delimiter))
      }
      setLoaded(l)
    } catch {
      toast('bad', 'No se pudo leer el archivo elegido.')
    } finally {
      setReading(false)
    }
  }

  const step = bid ? 3 : loaded && form ? 2 : 1
  const reset = () => {
    setLoaded(null)
    setForm(null)
    setParams(new URLSearchParams(), { replace: true })
  }

  return (
    <>
      <PageHeader
        title="Importar extracto"
        description="Del CSV o Excel del banco a movimientos, sin tipear. Primero se analiza y revisás fila por fila: nada se crea hasta que confirmás."
      />
      {!canWrite ? (
        <Sheet>
          <EmptyState title="Solo lectura">{readOnlyReason} Importar crea movimientos.</EmptyState>
        </Sheet>
      ) : accounts.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : accounts.isError ? (
        <ApiErrorNotice error={accounts.error} title="No se pudieron cargar las cuentas." />
      ) : active.length === 0 && !bid ? (
        <Sheet>
          <EmptyState
            title="Primero creá una cuenta"
            action={
              <Link to={`/finanzas/${cid}/cuentas`} className="font-medium text-ledger hover:underline">
                Ir a Cuentas
              </Link>
            }
          >
            El extracto se importa en una cuenta: elegí o creá la del banco que lo emitió.
          </EmptyState>
        </Sheet>
      ) : (
        <>
          {step < 3 && <Stepper current={step} />}
          {step === 3 && bid ? (
            <ReviewStep
              key={bid}
              bid={bid}
              accounts={accounts.data ?? []}
              onDone={reset}
              onReanalyze={(b) => {
                setAccountId(b.account_id)
                setParams(new URLSearchParams(), { replace: true })
                if (loaded) setForm(formFromMapping(b.mapping))
              }}
            />
          ) : step === 2 && loaded && form && account ? (
            <MappingStep
              loaded={loaded}
              account={account}
              form={form}
              setForm={setForm}
              onBack={() => {
                setLoaded(null)
                setForm(null)
              }}
              onAnalyzed={(b) => setParams(new URLSearchParams({ lote: b.id }))}
            />
          ) : (
            <FileStep
              accounts={accounts.data ?? []}
              accountId={account?.id ?? ''}
              onAccount={setAccountId}
              onFile={(f) => void chooseFile(f)}
              busy={reading}
            />
          )}
        </>
      )}
    </>
  )
}
