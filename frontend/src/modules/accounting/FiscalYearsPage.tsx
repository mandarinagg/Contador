/**
 * Ejercicios y períodos (D-039, D-047, D-050): crear el ejercicio, cerrar y reabrir meses con
 * motivo, y cerrar el ejercicio con la refundición, que es definitivo.
 */
import { useMutation } from '@tanstack/react-query'
import { CalendarPlus, Lock, LockOpen } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Sheet, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime } from '../../lib/format'
import { ApiError, post } from '../../services/api'
import { ApiErrorNotice, ReadOnlyHint, TableSkeleton, Th } from '../finance/components'
import { formatBookDate, todayIso } from '../finance/labels'
import { useAccountingPerms, useFiscalYears, useInvalidateAccounting, useUserName } from './data'
import { longDate, monthName } from './labels'
import type { FiscalYear, Period } from './types'

type Dialog =
  | { kind: 'new' }
  | { kind: 'drafts'; period: Period; drafts: Draft[] }
  | { kind: 'reopen'; period: Period }
  | { kind: 'close-year'; year: FiscalYear }

interface Draft {
  id: string
  entry_date: string
  description: string
}

const yearLabel = (y: FiscalYear) => {
  const a = y.start_date.slice(0, 4)
  const b = y.end_date.slice(0, 4)
  const civil = y.start_date.endsWith('-01-01') && y.end_date.endsWith('-12-31') && a === b
  return civil ? `Ejercicio ${a}` : `Ejercicio ${formatBookDate(y.start_date)} – ${formatBookDate(y.end_date)}`
}

function NewYearForm({ years, onDone }: { years: FiscalYear[]; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const latest = years[0]
  const suggested = latest ? Number(latest.end_date.slice(0, 4)) + 1 : Number(todayIso().slice(0, 4))
  const [mode, setMode] = useState<'civil' | 'range'>('civil')
  const [year, setYear] = useState(String(suggested))
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const run = useMutation({
    mutationFn: () => post<FiscalYear>('/accounting/fiscal-years', mode === 'civil' ? { year: Number(year) } : { start_date: start, end_date: end }),
    onSuccess: (y) => {
      invalidate()
      toast('ok', `${yearLabel(y)} creado con ${y.periods.length} períodos mensuales.`)
      onDone()
    },
  })
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    run.mutate()
  }
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <p className="text-ink-2">
        El ejercicio fiscal es, por defecto, el año civil (Decreto 3182, arts. 14 y 15). Se crea con un período por mes; los asientos se numeran
        correlativamente dentro del ejercicio.
      </p>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium text-ink-2">Duración</legend>
        <label className="flex cursor-pointer items-center gap-2">
          <input type="radio" name="mode" className="accent-(--ledger)" checked={mode === 'civil'} onChange={() => setMode('civil')} />
          Año civil (1 de enero al 31 de diciembre)
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input type="radio" name="mode" className="accent-(--ledger)" checked={mode === 'range'} onChange={() => setMode('range')} />
          Otras fechas <span className="text-sm text-ink-3">(primer ejercicio de una empresa que empezó a mitad de año; hasta 12 meses)</span>
        </label>
      </fieldset>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      {mode === 'civil' ? (
        <Field label="Año">
          {(p) => <Input {...p} autoFocus inputMode="numeric" maxLength={4} className="w-32 tabular-nums" value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ''))} />}
        </Field>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <Field label="Desde">{(p) => <Input {...p} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
          <Field label="Hasta">{(p) => <Input {...p} type="date" value={end} onChange={(e) => setEnd(e.target.value)} />}</Field>
        </div>
      )}
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending} disabled={mode === 'civil' ? year.length !== 4 : !start || !end}>
          Crear ejercicio
        </Button>
      </div>
    </form>
  )
}

function ReopenForm({ period, onDone }: { period: Period; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const bad = reason.trim().length < 3
  const run = useMutation({
    mutationFn: () => post<Period>(`/accounting/periods/${period.id}/reopen`, { reason: reason.trim() }),
    onSuccess: () => {
      invalidate()
      toast('ok', `${monthName(period.start_date)} reabierto.`)
      onDone()
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        setTouched(true)
        if (!bad) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Reabrir {monthName(period.start_date).toLowerCase()} permite volver a contabilizar y revertir con fecha en ese mes. El motivo queda en la
        auditoría.
      </p>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      <Field label="Motivo de la reapertura" error={touched && bad ? 'Escribí el motivo (al menos 3 caracteres).' : undefined}>
        {(p) => <Textarea {...p} autoFocus maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          Reabrir período
        </Button>
      </div>
    </form>
  )
}

function CloseYearForm({ year, onDone }: { year: FiscalYear; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const run = useMutation({
    mutationFn: () => post<FiscalYear>(`/accounting/fiscal-years/${year.id}/close`),
    onSuccess: (y) => {
      invalidate()
      toast('ok', y.closing_entry_id ? `${yearLabel(y)} cerrado: se contabilizó la refundición.` : `${yearLabel(y)} cerrado (no tuvo resultados que refundir).`)
      onDone()
    },
  })
  const err = run.error instanceof ApiError ? run.error : null
  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink-2">Cerrar el ejercicio hace dos cosas, en este orden:</p>
      <ol className="flex list-decimal flex-col gap-2 pl-5 text-ink-2">
        <li>
          Contabiliza el <span className="font-medium text-ink">asiento de refundición</span>, fechado el {longDate(year.end_date)}: lleva a cero cada cuenta
          de ingreso y de gasto con saldo, contra la cuenta de resultados del ejercicio.
        </li>
        <li>
          Deja el ejercicio <span className="font-medium text-ink">cerrado para siempre</span>: no se puede reabrir, ni sus períodos. Un error que
          aparezca después se corrige con un asiento en el ejercicio siguiente.
        </li>
      </ol>
      <p className="text-sm text-ink-3">Exige todos los períodos cerrados, ningún borrador y la cuenta de resultados configurada en el plan de cuentas.</p>
      {err && (
        <Notice tone="bad" title={err.message}>
          {err.code === 'RETAINED_EARNINGS_NOT_SET' && (
            <Link to="/contabilidad/plan" className="font-medium underline">
              Configurar la cuenta de resultados en el plan de cuentas
            </Link>
          )}
          {err.code === 'FISCAL_YEAR_HAS_DRAFTS' && (
            <Link to={`/contabilidad/asientos?fiscal_year_id=${year.id}&status=draft`} className="font-medium underline">
              Ver los borradores del ejercicio
            </Link>
          )}
        </Notice>
      )}
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button variant="danger" busy={run.isPending} onClick={() => run.mutate()}>
          <Lock size={15} />
          Cerrar el ejercicio definitivamente
        </Button>
      </div>
    </div>
  )
}

function YearSheet({ year, canPost, onDialog }: { year: FiscalYear; canPost: boolean; onDialog: (d: Dialog) => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const userName = useUserName()
  const closed = year.status === 'closed'
  const closePeriod = useMutation({
    mutationFn: (p: Period) => post<Period>(`/accounting/periods/${p.id}/close`),
    onSuccess: (p) => {
      invalidate()
      toast('ok', `${monthName(p.start_date)} cerrado: ya no se contabiliza con fecha en ese mes.`)
    },
    onError: (e, p) => {
      if (e instanceof ApiError && e.code === 'PERIOD_HAS_DRAFTS') {
        const drafts = ((e.details as { drafts?: Draft[] } | null)?.drafts ?? []) as Draft[]
        onDialog({ kind: 'drafts', period: p, drafts })
      } else toast('bad', e instanceof ApiError ? e.message : 'No se pudo cerrar el período.')
    },
  })
  const openCount = year.periods.filter((p) => p.status === 'open').length
  const today = todayIso()

  return (
    <Sheet>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2.5 text-md font-semibold">
            {yearLabel(year)}
            {closed ? <Badge>Cerrado</Badge> : <Badge tone="ok">Abierto</Badge>}
          </h2>
          <p className="mt-0.5 text-sm text-ink-2">
            Del {longDate(year.start_date)} al {longDate(year.end_date)}.{' '}
            {year.last_entry_number > 0 ? `Último asiento contabilizado: N° ${year.last_entry_number}.` : 'Todavía sin asientos contabilizados.'}
            {closed && year.closed_at && ` Cerrado el ${formatDateTime(year.closed_at)} por ${userName(year.closed_by)}.`}
          </p>
          {closed && year.closing_entry_id && (
            <Link to={`/contabilidad/asientos/${year.closing_entry_id}`} className="text-sm font-medium text-ledger hover:underline">
              Ver el asiento de refundición
            </Link>
          )}
        </div>
        {!closed && canPost && (
          <Button variant="danger" className="ml-auto" onClick={() => onDialog({ kind: 'close-year', year })} title={openCount ? `Faltan cerrar ${openCount} períodos` : undefined}>
            <Lock size={15} />
            Cerrar el ejercicio
          </Button>
        )}
      </div>
      <table className="w-full">
        <thead className="border-b border-line bg-sunken text-sm text-ink-2">
          <tr>
            <Th>Período</Th>
            <Th>Fechas</Th>
            <Th>Estado</Th>
            <Th>Detalle</Th>
            {canPost && !closed && (
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {year.periods.map((p) => {
            const isClosed = p.status === 'closed'
            const current = p.start_date <= today && today <= p.end_date
            return (
              <tr key={p.id} className={cx(isClosed && 'bg-sunken/40')}>
                <td className="px-4 py-2.5 font-medium">
                  {monthName(p.start_date)} {p.start_date.slice(0, 4)}
                  {current && <span className="ml-2 text-sm font-normal text-ink-3">(mes actual)</span>}
                </td>
                <td className="px-4 py-2.5 text-sm text-ink-2 tabular-nums">
                  {formatBookDate(p.start_date)} al {formatBookDate(p.end_date)}
                </td>
                <td className="px-4 py-2.5">
                  {isClosed ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-ink-2">
                      <Lock size={13} aria-hidden /> Cerrado
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-sm text-ledger">
                      <LockOpen size={13} aria-hidden /> Abierto
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-sm text-ink-2">
                  {isClosed && p.closed_at ? `Cerrado el ${formatDateTime(p.closed_at)}` : p.reopen_reason ? `Reabierto: ${p.reopen_reason}` : ''}
                </td>
                {canPost && !closed && (
                  <td className="px-3 py-1.5 text-right">
                    {isClosed ? (
                      <Button variant="ghost" className="h-8" aria-label={`Reabrir ${monthName(p.start_date)}`} onClick={() => onDialog({ kind: 'reopen', period: p })}>
                        <LockOpen size={14} />
                        Reabrir
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        className="h-8"
                        aria-label={`Cerrar ${monthName(p.start_date)}`}
                        busy={closePeriod.isPending && closePeriod.variables?.id === p.id}
                        disabled={closePeriod.isPending}
                        onClick={() => closePeriod.mutate(p)}
                      >
                        <Lock size={14} />
                        Cerrar
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </Sheet>
  )
}

export function FiscalYearsPage() {
  const years = useFiscalYears()
  const perms = useAccountingPerms()
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const close = () => setDialog(null)
  const list = years.data ?? []

  return (
    <>
      <PageHeader
        title="Ejercicios y períodos"
        description="Un período cerrado no recibe asientos ni reversiones con fecha en él. Se reabre con un motivo; el ejercicio cerrado no se reabre."
        actions={
          perms.canPost &&
          list.length > 0 && (
            <Button onClick={() => setDialog({ kind: 'new' })}>
              <CalendarPlus size={16} />
              Nuevo ejercicio
            </Button>
          )
        }
      />
      {!perms.canPost && <p className="-mt-3 mb-4 text-sm text-ink-3">{perms.postReason}</p>}
      {years.isPending ? (
        <Sheet>
          <TableSkeleton rows={6} cols={4} />
        </Sheet>
      ) : years.isError ? (
        <ApiErrorNotice error={years.error} title="No se pudieron cargar los ejercicios." />
      ) : list.length === 0 ? (
        <Sheet>
          <EmptyState
            title="Todavía no hay ejercicios"
            action={
              perms.canPost ? (
                <Button onClick={() => setDialog({ kind: 'new' })}>
                  <CalendarPlus size={16} />
                  Crear el ejercicio {todayIso().slice(0, 4)}
                </Button>
              ) : (
                <ReadOnlyHint reason="Lo crea el propietario o el contador." />
              )
            }
          >
            Sin un ejercicio abierto no se pueden cargar asientos: la fecha de cada asiento tiene que caer dentro de uno.
          </EmptyState>
        </Sheet>
      ) : (
        <div className="flex flex-col gap-6">
          {list.map((y) => (
            <YearSheet key={y.id} year={y} canPost={perms.canPost} onDialog={setDialog} />
          ))}
        </div>
      )}

      <Modal open={dialog?.kind === 'new'} title="Nuevo ejercicio" onClose={close}>
        {dialog?.kind === 'new' && <NewYearForm years={list} onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'reopen'} title="Reabrir período" onClose={close}>
        {dialog?.kind === 'reopen' && <ReopenForm period={dialog.period} onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'close-year'} title="Cerrar el ejercicio" onClose={close}>
        {dialog?.kind === 'close-year' && <CloseYearForm year={dialog.year} onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'drafts'} title="El período tiene borradores" onClose={close}>
        {dialog?.kind === 'drafts' && (
          <div className="flex flex-col gap-4">
            <p className="text-ink-2">
              {monthName(dialog.period.start_date)} no se puede cerrar mientras tenga borradores con fecha en él. Contabilizalos, descartalos o
              cambiales la fecha, y volvé a intentar.
            </p>
            <ul className="divide-y divide-line rounded-sm border border-line">
              {dialog.drafts.map((d) => (
                <li key={d.id} className="flex items-baseline gap-3 px-3.5 py-2.5">
                  <span className="text-sm text-ink-2 tabular-nums">{formatBookDate(d.entry_date)}</span>
                  <Link to={`/contabilidad/asientos/${d.id}`} className="min-w-0 flex-1 font-medium text-ledger hover:underline">
                    {d.description}
                  </Link>
                </li>
              ))}
            </ul>
            <div className="flex justify-end border-t border-line pt-4">
              <Button variant="secondary" onClick={close}>
                Entendido
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
