/**
 * Un asiento: editor del borrador (con totales en vivo y la diferencia hasta que balancea) o
 * vista de solo lectura del contabilizado, revertido o descartado, con sus vínculos.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookCheck, Trash2, Undo2 } from 'lucide-react'
import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from 'react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router'
import { Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Sheet, Skeleton, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime } from '../../lib/format'
import { CURRENCY_SYMBOLS, formatMoney } from '../../lib/money'
import { ApiError, get, patch, post } from '../../services/api'
import { Amount, ApiErrorNotice } from '../finance/components'
import { financeKeys } from '../finance/data'
import type { Transaction } from '../finance/types'
import { formatBookDate, todayIso } from '../finance/labels'
import { formatDecimal } from './amounts'
import { postableAccounts } from './chartTree'
import { Blank, EntryStatusBadge, Pyg, RuledTotal } from './components'
import { accountingKeys, useAccountingPerms, useAccountsById, useChart, useCostCenters, useEntry, useFiscalYears, useInvalidateAccounting, useUserName } from './data'
import { buildEntry, emptyLine, fingerprint, type HeaderDraft, type LineDraft, linesFromEntry, missingCenters, totalsOf } from './editor'
import { LinesEditor } from './LinesEditor'
import { DISPOSAL_KIND_LABELS, ENTRY_KIND_LABELS, entryLabel, GENERATED_KINDS, longDate, monthName, REVERSIBLE_KINDS } from './labels'
import type { DepreciationRun, FixedAsset } from './types3b'
import type { Entry, FiscalYear } from './types'

/** El ejercicio y el período de una fecha, si existen. */
function locate(years: FiscalYear[] | undefined, date: string) {
  if (!years || !date) return null
  const year = years.find((y) => y.start_date <= date && date <= y.end_date)
  const period = year?.periods.find((p) => p.start_date <= date && date <= p.end_date)
  return year ? { year, period } : { year: undefined, period: undefined }
}

// --- Editor ---------------------------------------------------------------------------------

function EntryEditor({ entry }: { entry?: Entry }) {
  const perms = useAccountingPerms()
  const chart = useChart()
  const years = useFiscalYears()
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const invalidate = useInvalidateAccounting()
  const byId = useAccountsById(chart.data?.accounts)
  const options = useMemo(() => postableAccounts(chart.data?.accounts ?? []), [chart.data])
  const centers = useCostCenters()

  const [header, setHeader] = useState<HeaderDraft>(() => ({
    entry_date: entry?.entry_date ?? todayIso(),
    description: entry?.description ?? '',
    document_reference: entry?.document_reference ?? '',
  }))
  const [lines, setLines] = useState<LineDraft[]>(() => (entry ? linesFromEntry(entry) : [emptyLine(), emptyLine()]))
  // Un asiento nuevo sin tocar no tiene cambios: salir no pide confirmación.
  const [saved, setSaved] = useState(() => fingerprint(header, lines))
  const [showErrors, setShowErrors] = useState(false)
  const [dialog, setDialog] = useState<'discard' | null>(null)
  const kindOf = (id: string) => byId.get(id)?.kind

  const totals = totalsOf(lines)
  const build = buildEntry(header, lines, kindOf)
  const missing = missingCenters(lines, kindOf, Boolean(chart.data?.cost_centers_required))
  const dirty = fingerprint(header, lines) !== saved
  const where = locate(years.data, header.entry_date)
  const periodClosed = where?.period?.status === 'closed'
  const yearClosed = where?.year?.status === 'closed'
  const noYear = Boolean(header.entry_date && years.data && !where?.year)

  const persist = async (): Promise<Entry | null> => {
    setShowErrors(true)
    if (!build.body) return null
    const result = entry ? await patch<Entry>(`/accounting/entries/${entry.id}`, build.body) : await post<Entry>('/accounting/entries', build.body)
    qc.setQueryData(accountingKeys.entry(result.id), result)
    setSaved(fingerprint(header, lines))
    return result
  }

  const save = useMutation({
    mutationFn: persist,
    onSuccess: (result) => {
      if (!result) return
      invalidate()
      toast('ok', entry ? 'Borrador guardado.' : 'Borrador creado. Todavía no está en los libros: falta contabilizarlo.')
      if (!entry) navigate(`/contabilidad/asientos/${result.id}`, { replace: true })
    },
  })
  const postEntry = useMutation({
    mutationFn: async () => {
      const current = dirty || !entry ? await persist() : entry
      if (!current) return null
      try {
        return await post<Entry>(`/accounting/entries/${current.id}/post`)
      } catch (e) {
        if (!entry) navigate(`/contabilidad/asientos/${current.id}`, { replace: true })
        throw e
      }
    },
    onSuccess: (result) => {
      if (!result) return
      qc.setQueryData(accountingKeys.entry(result.id), result)
      invalidate()
      toast('ok', `Asiento N° ${result.number} contabilizado.`)
      if (!entry) navigate(`/contabilidad/asientos/${result.id}`, { replace: true })
    },
  })
  const busy = save.isPending || postEntry.isPending
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !busy && currentLocation.pathname !== nextLocation.pathname)

  const onShortcut = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault()
      if (!busy) save.mutate()
    }
  }

  const lineErrors = showErrors ? build.lines : {}
  const canPostNow = perms.canPost && totals.balanced && !periodClosed && !yearClosed && !noYear && missing.length === 0
  const postBlocker = !totals.balanced
    ? 'Para contabilizar, el debe y el haber tienen que sumar lo mismo.'
    : missing.length > 0
      ? 'Falta el centro de costos en las líneas de ingreso o gasto marcadas: la configuración lo exige.'
    : noYear
      ? 'La fecha no cae en ningún ejercicio.'
      : yearClosed
        ? 'El ejercicio de esa fecha está cerrado.'
        : periodClosed
          ? `${monthName(header.entry_date)} está cerrado: no se contabiliza con fecha en ese mes.`
          : ''
  const error = save.error ?? postEntry.error
  const apiError = error instanceof ApiError ? error : null

  return (
    <div onKeyDown={onShortcut}>
      <PageHeader
        title={entry ? 'Borrador de asiento' : 'Nuevo asiento'}
        description={
          entry?.kind === 'finance'
            ? 'Propuesto desde un movimiento de la empresa. Revisalo: no está en los libros hasta que alguien lo contabilice.'
            : entry?.kind === 'recurring'
              ? 'Generado desde una plantilla recurrente. Ajustalo si hace falta: no está en los libros hasta que alguien lo contabilice.'
              : 'Un borrador se puede guardar desbalanceado y corregir cuantas veces haga falta. Al contabilizarlo recibe su número y ya no cambia.'
        }
        actions={
          <Link to="/contabilidad/asientos" className="inline-flex h-9 items-center gap-2 rounded-sm px-3 text-ink-2 hover:bg-sunken hover:text-ink">
            <ArrowLeft size={16} />
            Asientos
          </Link>
        }
      />

      {apiError && (
        <div className="mb-4">
          <Notice tone="bad" title={apiError.message}>
            {apiError.code === 'FISCAL_YEAR_NOT_FOUND' || apiError.code === 'PERIOD_CLOSED' || apiError.code === 'FISCAL_YEAR_CLOSED' ? (
              <Link to="/contabilidad/ejercicios" className="font-medium underline">
                Ir a Ejercicios y períodos
              </Link>
            ) : (
              Object.values(apiError.fieldErrors()).join(' ') || null
            )}
          </Notice>
        </div>
      )}

      <Sheet className="mb-5 grid grid-cols-[11rem_minmax(0,1fr)_14rem] gap-4 p-5">
        <Field
          label="Fecha"
          error={showErrors ? build.header.entry_date : undefined}
          hint={noYear ? 'Sin ejercicio para esa fecha.' : periodClosed ? `${monthName(header.entry_date)} está cerrado.` : where?.year ? `Ejercicio ${where.year.start_date.slice(0, 4)}` : undefined}
        >
          {(p) => <Input {...p} type="date" value={header.entry_date} onChange={(e) => setHeader({ ...header, entry_date: e.target.value })} />}
        </Field>
        <Field label="Descripción" error={showErrors ? build.header.description : undefined}>
          {(p) => <Input {...p} autoFocus={!entry} maxLength={500} placeholder="Qué registra: «Cobro de la factura 001-001-0000123»" value={header.description} onChange={(e) => setHeader({ ...header, description: e.target.value })} />}
        </Field>
        <Field label="Comprobante" hint="Factura, recibo u operación que lo respalda.">
          {(p) => <Input {...p} maxLength={100} value={header.document_reference} onChange={(e) => setHeader({ ...header, document_reference: e.target.value })} />}
        </Field>
      </Sheet>

      <LinesEditor
        lines={lines}
        setLines={setLines}
        errors={lineErrors}
        options={options}
        known={byId}
        kindOf={kindOf}
        centers={centers.data ?? []}
        missingCenterKeys={totals.balanced ? missing : []}
      />

      {showErrors && build.general && (
        <div className="mt-4">
          <Notice tone="bad" title={build.general} />
        </div>
      )}
      {showErrors && Object.keys(build.lines).length > 0 && (
        <div className="mt-4">
          <Notice tone="bad" title="Hay líneas para corregir">Están marcadas en rojo, con el motivo debajo.</Notice>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-5">
        {perms.canPost ? (
          <Button onClick={() => postEntry.mutate()} busy={postEntry.isPending} disabled={!canPostNow || save.isPending}>
            <BookCheck size={16} />
            Contabilizar
          </Button>
        ) : null}
        <Button variant="secondary" onClick={() => save.mutate()} busy={save.isPending} disabled={postEntry.isPending || (Boolean(entry) && !dirty)}>
          Guardar borrador
        </Button>
        {entry && (
          <Button variant="ghost" className="hover:text-debit" onClick={() => setDialog('discard')}>
            <Trash2 size={15} />
            Descartar borrador
          </Button>
        )}
        <p className="ml-auto max-w-md text-right text-sm text-ink-3">
          {!perms.canPost ? perms.postReason : postBlocker || (dirty && entry ? 'Hay cambios sin guardar: contabilizar los guarda primero.' : 'Al contabilizar recibe el próximo número del ejercicio.')}
        </p>
      </div>

      <Modal open={dialog === 'discard'} title="Descartar borrador" onClose={() => setDialog(null)}>
        {dialog === 'discard' && entry && <DiscardForm entry={entry} onDone={() => setDialog(null)} />}
      </Modal>
      <Modal open={blocker.state === 'blocked'} title="Hay cambios sin guardar" onClose={() => blocker.reset?.()}>
        <div className="flex flex-col gap-4">
          <p className="text-ink-2">Si salís ahora, se pierden los cambios del asiento que no guardaste.</p>
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button variant="ghost" onClick={() => blocker.reset?.()}>
              Seguir editando
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Salir sin guardar
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function DiscardForm({ entry, onDone }: { entry: Entry; onDone: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const invalidate = useInvalidateAccounting()
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const bad = reason.trim().length < 3
  const run = useMutation({
    mutationFn: () => post<Entry>(`/accounting/entries/${entry.id}/discard`, { reason: reason.trim() }),
    onSuccess: (e) => {
      qc.setQueryData(accountingKeys.entry(e.id), e)
      invalidate()
      toast('ok', 'Borrador descartado. Queda en el listado como descartado, con tu motivo.')
      onDone()
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(ev) => {
        ev.preventDefault()
        setTouched(true)
        if (!bad) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Nada se borra: el borrador queda como descartado, sin número, con el motivo.
        {entry.kind === 'finance' && ' El movimiento de finanzas vuelve a quedar sin asiento y se puede proponer de nuevo.'}
        {entry.kind === 'depreciation' && ' La depreciación del mes queda libre: se puede volver a correr.'}
        {entry.kind === 'disposal' && ' El bien vuelve a quedar activo, sin los datos de la baja.'}
        {entry.kind === 'recurring' && ' La plantilla se puede volver a generar para este período.'}
      </p>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      <Field label="Motivo" error={touched && bad ? 'Escribí el motivo (al menos 3 caracteres).' : undefined}>
        {(p) => <Textarea {...p} autoFocus maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" busy={run.isPending}>
          Descartar borrador
        </Button>
      </div>
    </form>
  )
}

// --- Reversión ------------------------------------------------------------------------------

function ReverseForm({ entry, onDone }: { entry: Entry; onDone: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const invalidate = useInvalidateAccounting()
  const years = useFiscalYears()
  const [reason, setReason] = useState('')
  const [date, setDate] = useState(entry.entry_date)
  const [needsDate, setNeedsDate] = useState(false)
  const [touched, setTouched] = useState(false)
  const dateRef = useRef<HTMLInputElement>(null)
  const bad = reason.trim().length < 3
  const run = useMutation({
    mutationFn: () => post<Entry>(`/accounting/entries/${entry.id}/reverse`, { reason: reason.trim(), ...(date !== entry.entry_date ? { date } : {}) }),
    onSuccess: (reversal) => {
      qc.setQueryData(accountingKeys.entry(reversal.id), reversal)
      invalidate()
      toast('ok', `Reversión contabilizada: asiento N° ${reversal.number}. El N° ${entry.number} quedó revertido.`)
      onDone()
      navigate(`/contabilidad/asientos/${reversal.id}`)
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'PERIOD_CLOSED') {
        setNeedsDate(true)
        // Sugerencia: el primer día abierto desde la fecha del original.
        const open = (years.data ?? [])
          .flatMap((y) => (y.status === 'open' ? y.periods : []))
          .filter((p) => p.status === 'open' && p.end_date >= entry.entry_date)
          .sort((a, b) => a.start_date.localeCompare(b.start_date))[0]
        if (open) setDate(open.start_date > entry.entry_date ? open.start_date : entry.entry_date)
        setTimeout(() => dateRef.current?.focus(), 0)
      }
    },
  })
  const where = locate(years.data, date)
  const dateBad = date < entry.entry_date
  const err = run.error instanceof ApiError ? run.error : null
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(ev) => {
        ev.preventDefault()
        setTouched(true)
        if (!bad && !dateBad) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Un asiento contabilizado no se modifica: se compensa con otro, de reversión, con las mismas cuentas y el debe y el haber invertidos. Se
        contabiliza en el mismo acto, recibe su propio número y el N° {entry.number} queda revertido.
      </p>
      {err && (
        <Notice tone={err.code === 'PERIOD_CLOSED' ? 'warn' : 'bad'} title={err.code === 'PERIOD_CLOSED' ? 'El período del asiento está cerrado' : err.message}>
          {err.code === 'PERIOD_CLOSED' ? 'Elegí una fecha en un período abierto, igual o posterior a la del asiento original, y volvé a confirmar.' : null}
        </Notice>
      )}
      <Field label="Motivo de la reversión" error={touched && bad ? 'Escribí el motivo (al menos 3 caracteres).' : undefined}>
        {(p) => <Textarea {...p} autoFocus maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <Field
        label="Fecha de la reversión"
        error={dateBad ? 'No puede ser anterior al asiento original.' : undefined}
        hint={
          needsDate
            ? where?.period
              ? `${monthName(date)} ${where.period.status === 'open' ? 'está abierto' : 'también está cerrado'}.`
              : 'Esa fecha no cae en ningún ejercicio.'
            : `Por defecto, la del original (${formatBookDate(entry.entry_date)}).`
        }
      >
        {(p) => <Input {...p} ref={dateRef} type="date" className="w-44" min={entry.entry_date} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" busy={run.isPending}>
          <Undo2 size={15} />
          Revertir el asiento N° {entry.number}
        </Button>
      </div>
    </form>
  )
}

// --- Vista de solo lectura ---------------------------------------------------------------

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-ink-3">{label}</dt>
      <dd className="mt-0.5 break-words">{children}</dd>
    </div>
  )
}

function RelatedLink({ id, prefix }: { id: string; prefix: string }) {
  const related = useEntry(id)
  return (
    <Link to={`/contabilidad/asientos/${id}`} className="font-medium text-ledger hover:underline">
      {prefix} {related.data ? entryLabel(related.data) : '…'}
    </Link>
  )
}

/** Movimiento de finanzas de origen, leído por su id (P-9): se ve qué es sin ir a buscarlo. */
function SourceTransaction({ cid, tid }: { cid: string; tid: string }) {
  const tx = useQuery({
    queryKey: [...financeKeys.transactions(cid), 'detail', tid],
    queryFn: () => get<Transaction>(`/finance/contexts/${cid}/transactions/${tid}`),
  })
  return (
    <span className="flex flex-col">
      <Link to={`/finanzas/${cid}/movimientos?tx=${tid}`} className="font-medium text-ledger hover:underline">
        Movimiento de finanzas de origen
      </Link>
      {tx.data ? (
        <span className="text-sm text-ink-2" data-testid="movimiento-origen">
          {formatBookDate(tx.data.booked_on)}, {tx.data.description}, <Amount value={tx.data.amount} currency={tx.data.currency} flow />
          {tx.data.voided_at && ' (anulado)'}
        </span>
      ) : tx.isError ? (
        <span className="text-sm text-ink-3">{tx.error instanceof ApiError ? tx.error.message : 'No se pudo leer el movimiento.'}</span>
      ) : null}
    </span>
  )
}

/** Detalle por bien de un asiento de depreciación (la corrida que lo generó). */
function DepreciationDetail({ entry }: { entry: Entry }) {
  const runs = useQuery({
    queryKey: accountingKeys.runs(entry.fiscal_year_id),
    queryFn: () => get<DepreciationRun[]>(`/accounting/depreciation/runs?fiscal_year_id=${entry.fiscal_year_id}`),
  })
  const runId = runs.data?.find((r) => r.entry_id === entry.id)?.id
  const run = useQuery({
    enabled: Boolean(runId),
    queryKey: [...accountingKeys.runs(entry.fiscal_year_id), runId],
    queryFn: () => get<DepreciationRun>(`/accounting/depreciation/runs/${runId}`),
  })
  const items = run.data?.items ?? []
  if (!runId || items.length === 0) return null
  return (
    <Sheet className="mt-5">
      <h2 className="border-b border-line px-5 py-3 font-semibold">Detalle por bien</h2>
      <table className="w-full" aria-label="Detalle por bien">
        <thead className="border-b border-line bg-sunken text-sm text-ink-2">
          <tr>
            <th scope="col" className="px-4 py-2 text-left font-medium">Bien</th>
            <th scope="col" className="w-32 px-4 py-2 text-right font-medium">Cuota N°</th>
            <th scope="col" className="w-40 px-4 py-2 text-right font-medium">Importe</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.map((i) => (
            <tr key={i.asset_id}>
              <td className="px-4 py-2">
                <Link to={`/contabilidad/activos/${i.asset_id}`} className="hover:text-ledger hover:underline">
                  {i.asset_name}
                </Link>
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{i.installment}</td>
              <td className="px-4 py-2 text-right">
                <Pyg value={i.amount} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Sheet>
  )
}

/** El bien de un asiento de baja (mientras el bien conserve el vínculo). */
function DisposalAsset({ entry }: { entry: Entry }) {
  const assets = useQuery({ queryKey: [...accountingKeys.assets(), 'list', {}], queryFn: () => get<FixedAsset[]>('/accounting/fixed-assets') })
  const asset = assets.data?.find((a) => a.disposal_entry_id === entry.id)
  if (!asset) return null
  return (
    <span className="flex flex-col">
      <Link to={`/contabilidad/activos/${asset.id}`} className="font-medium text-ledger hover:underline">
        Bien: {asset.name}
      </Link>
      {asset.disposal_kind && (
        <span className="text-sm text-ink-2">
          {DISPOSAL_KIND_LABELS[asset.disposal_kind]}. Motivo: {asset.disposal_reason}. Documento: {asset.disposal_document_reference}.
        </span>
      )}
    </span>
  )
}

function GeneratedDraftActions({ entry, onDiscard }: { entry: Entry; onDiscard: () => void }) {
  const perms = useAccountingPerms()
  const qc = useQueryClient()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const run = useMutation({
    mutationFn: () => post<Entry>(`/accounting/entries/${entry.id}/post`),
    onSuccess: (result) => {
      qc.setQueryData(accountingKeys.entry(result.id), result)
      invalidate()
      toast('ok', `Asiento N° ${result.number} contabilizado.`)
    },
  })
  return (
    <div className="mt-6 border-t border-line pt-5">
      {run.error ? (
        <div className="mb-4">
          <ApiErrorNotice error={run.error} />
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        {perms.canPost && (
          <Button onClick={() => run.mutate()} busy={run.isPending} disabled={!entry.balanced}>
            <BookCheck size={16} />
            Contabilizar
          </Button>
        )}
        {perms.canManage && (
          <Button variant="ghost" className="hover:text-debit" onClick={onDiscard}>
            <Trash2 size={15} />
            Descartar borrador
          </Button>
        )}
        <p className="ml-auto max-w-md text-right text-sm text-ink-3">{perms.canPost ? 'Al contabilizar recibe el próximo número del ejercicio.' : perms.postReason}</p>
      </div>
    </div>
  )
}

function EntryView({ entry }: { entry: Entry }) {
  const perms = useAccountingPerms()
  const userName = useUserName()
  const [dialog, setDialog] = useState<'reverse' | 'discard' | null>(null)
  const reversible = entry.status === 'posted' && REVERSIBLE_KINDS.includes(entry.kind)
  const generatedDraft = entry.status === 'draft' && GENERATED_KINDS.includes(entry.kind)
  const lines = entry.lines ?? []
  const withCenters = lines.some((l) => l.cost_center_id)
  const yearOf = entry.entry_date.slice(0, 4)
  const title = entry.number !== null ? `Asiento N° ${entry.number}` : entry.status === 'discarded' ? 'Asiento descartado' : 'Borrador de asiento'
  const hasLinks = entry.reverses_entry_id || entry.reversed_by_entry_id || entry.source_transaction_id || entry.kind === 'disposal'

  return (
    <>
      <PageHeader
        title={title}
        description={entry.description}
        actions={
          <>
            <Link to="/contabilidad/asientos" className="inline-flex h-9 items-center gap-2 rounded-sm px-3 text-ink-2 hover:bg-sunken hover:text-ink">
              <ArrowLeft size={16} />
              Asientos
            </Link>
            {reversible && perms.canPost && (
              <Button variant="danger" onClick={() => setDialog('reverse')}>
                <Undo2 size={15} />
                Revertir
              </Button>
            )}
          </>
        }
      />
      {reversible && !perms.canPost && <p className="-mt-3 mb-4 text-sm text-ink-3">{perms.postReason}</p>}
      {generatedDraft ? (
        <div className="mb-4">
          <Notice tone="warn" title="Borrador generado: todavía no está en los libros">
            {entry.kind === 'depreciation'
              ? 'Lo armó la corrida de depreciación del mes, con una línea por cuenta y el detalle por bien. No se edita: si algo no está bien, descartalo, corregí el bien o la categoría y volvé a correr el mes.'
              : 'Lo armó la baja del bien: da de baja el costo y la depreciación acumulada, y el neto va a la cuenta de resultado por bajas. No se edita: si algo no está bien, descartalo y volvé a dar de baja el bien.'}
          </Notice>
        </div>
      ) : (
        entry.status === 'draft' && (
          <div className="mb-4">
            <Notice tone="warn" title="Borrador: todavía no está en los libros">
              {perms.manageReason || 'Lo puede corregir y contabilizar alguien con permiso.'}
            </Notice>
          </div>
        )
      )}
      {entry.status === 'discarded' && (
        <div className="mb-4">
          <Notice tone="neutral" title="Borrador descartado">
            Motivo: {entry.discard_reason}. Lo descartó {userName(entry.discarded_by)} el {formatDateTime(entry.discarded_at as string)}.
          </Notice>
        </div>
      )}

      <Sheet className="mb-5 px-5 py-4">
        <dl className="grid grid-cols-4 gap-x-6 gap-y-4">
          <Meta label="Fecha">{longDate(entry.entry_date)}</Meta>
          <Meta label="Estado">
            <EntryStatusBadge status={entry.status} />
          </Meta>
          <Meta label="Tipo">{ENTRY_KIND_LABELS[entry.kind]}</Meta>
          <Meta label="Comprobante">{entry.document_reference ?? <span className="text-ink-3">Sin comprobante</span>}</Meta>
          {entry.posted_at && (
            <Meta label="Contabilizado">
              {formatDateTime(entry.posted_at)}
              <span className="block text-sm text-ink-2">por {entry.posted_by_name ?? 'un usuario sin nombre registrado'}</span>
            </Meta>
          )}
          <Meta label="Creado">
            {formatDateTime(entry.created_at)}
            <span className="block text-sm text-ink-2">por {entry.created_by_name ?? 'un usuario sin nombre registrado'}</span>
          </Meta>
          {hasLinks && (
            <div className="col-span-2 flex flex-col gap-1">
              <dt className="text-sm text-ink-3">Vínculos</dt>
              <dd className="flex flex-col gap-1.5">
                {entry.reverses_entry_id && <RelatedLink id={entry.reverses_entry_id} prefix="Revierte el asiento" />}
                {entry.reversed_by_entry_id && <RelatedLink id={entry.reversed_by_entry_id} prefix="Revertido por el asiento" />}
                {entry.source_transaction_id && entry.source_context_id && <SourceTransaction cid={entry.source_context_id} tid={entry.source_transaction_id} />}
                {entry.kind === 'disposal' && <DisposalAsset entry={entry} />}
              </dd>
            </div>
          )}
        </dl>
      </Sheet>

      <Sheet>
        <table className="w-full" aria-label="Líneas del asiento">
          <thead className="border-b border-line bg-sunken text-sm text-ink-2">
            <tr>
              <th scope="col" className="w-10 py-2.5 pl-4 text-left font-medium">#</th>
              <th scope="col" className="px-3 py-2.5 text-left font-medium">Cuenta</th>
              <th scope="col" className="px-3 py-2.5 text-left font-medium">Detalle</th>
              {withCenters && <th scope="col" className="w-36 px-3 py-2.5 text-left font-medium">Centro</th>}
              <th scope="col" className="w-40 px-4 py-2.5 text-right font-medium">Debe</th>
              <th scope="col" className="w-40 px-4 py-2.5 text-right font-medium">Haber</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {lines.map((l) => (
              <tr key={l.id} className="align-top">
                <td className="py-2.5 pl-4 text-sm text-ink-3 tabular-nums">{l.line_no}</td>
                <td className={cx('px-3 py-2.5', l.credit !== '0' && 'pl-8')}>
                  <Link to={`/contabilidad/reportes/mayor?account_id=${l.account_id}&from=${yearOf}-01-01&to=${yearOf}-12-31`} className="hover:text-ledger hover:underline">
                    <span className="mr-2 text-ink-2 tabular-nums">{l.account_code}</span>
                    {l.account_name}
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-sm text-ink-2">
                  {l.description}
                  {l.fx_currency && (
                    <span className="block text-ink-3">
                      {formatMoney(l.fx_amount as string, l.fx_currency)} a ₲ {formatDecimal(l.fx_rate as string)} por {CURRENCY_SYMBOLS[l.fx_currency] ?? l.fx_currency}
                    </span>
                  )}
                </td>
                {withCenters && <td className="px-3 py-2.5 text-sm">{l.cost_center_code ?? <span className="text-ink-3">—</span>}</td>}
                <td className="px-4 py-2.5 text-right">{l.debit !== '0' ? <Pyg value={l.debit} /> : <Blank />}</td>
                <td className="px-4 py-2.5 text-right">{l.credit !== '0' ? <Pyg value={l.credit} /> : <Blank />}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-line-strong">
            <tr>
              <td colSpan={withCenters ? 4 : 3} className="px-4 py-3 font-medium">
                Totales
              </td>
              <td className="px-4 py-3 text-right">
                <RuledTotal value={entry.total_debit} label={`Total debe ${formatMoney(entry.total_debit, 'PYG')}`} />
              </td>
              <td className="px-4 py-3 text-right">
                <RuledTotal value={entry.total_credit} label={`Total haber ${formatMoney(entry.total_credit, 'PYG')}`} />
              </td>
            </tr>
          </tfoot>
        </table>
      </Sheet>

      {entry.kind === 'depreciation' && <DepreciationDetail entry={entry} />}
      {generatedDraft && <GeneratedDraftActions entry={entry} onDiscard={() => setDialog('discard')} />}

      <Modal open={dialog === 'reverse'} title={`Revertir el asiento N° ${entry.number}`} onClose={() => setDialog(null)}>
        {dialog === 'reverse' && <ReverseForm entry={entry} onDone={() => setDialog(null)} />}
      </Modal>
      <Modal open={dialog === 'discard'} title="Descartar borrador" onClose={() => setDialog(null)}>
        {dialog === 'discard' && <DiscardForm entry={entry} onDone={() => setDialog(null)} />}
      </Modal>
    </>
  )
}

export function EntryPage() {
  const { id } = useParams()
  const perms = useAccountingPerms()
  const entry = useEntry(id)
  const chart = useChart()
  const years = useFiscalYears()

  if (!id) {
    if (!perms.canManage) return <EmptyState title="Sin acceso">{perms.manageReason}</EmptyState>
    if (chart.isPending || years.isPending) return <Skeleton className="h-40 w-full" />
    return <EntryEditor />
  }
  if (entry.isPending || chart.isPending) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Cargando el asiento">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }
  if (entry.isError || !entry.data) {
    return (
      <EmptyState title="Ese asiento no existe" action={<Link className="font-medium text-ledger hover:underline" to="/contabilidad/asientos">Ir a Asientos</Link>}>
        {entry.error instanceof ApiError ? entry.error.message : 'La dirección no corresponde a ningún asiento de la empresa.'}
      </EmptyState>
    )
  }
  if (entry.data.status === 'draft' && perms.canManage && !GENERATED_KINDS.includes(entry.data.kind)) return <EntryEditor key={entry.data.id} entry={entry.data} />
  return <EntryView key={entry.data.id} entry={entry.data} />
}
