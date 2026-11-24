/**
 * Calendario tributario (D-087, D-098): obligaciones por mes de vencimiento, con su estado,
 * `remind_by` y vencimiento, la regla y la norma a un clic, y las acciones (presentada,
 * pagada, no aplica, reabrir). Al abrirlo, quien tiene `tax.manage` lo sincroniza (D-116).
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { Button, EmptyState, Field, Modal, Notice, PageHeader, Select, Sheet } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatMoney } from '../../lib/money'
import { post } from '../../services/api'
import { ApiErrorNotice, Check, TableSkeleton } from '../finance/components'
import { formatBookDate, todayIso } from '../finance/labels'
import { DayStub, ObligationStatusBadge, RulesApplied, UnverifiedMark } from './components'
import { taxKeys, useInvalidateTax, useObligations, useRulesById, useTaxAlerts, useTaxPerms, useTaxProfile } from './data'
import { monthTitle, obligationLabel, OBLIGATION_LABELS, periodLabel } from './labels'
import { actionTitle, displayStatus, groupByDueMonth, isRegister, isVat, type ObligationAction, obligationActions } from './logic'
import { ObligationActionForm } from './ObligationForms'
import type { Obligation, Rule, SyncResult } from './types'

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000)
}

function Amounts({ o }: { o: Obligation }) {
  const rows: [string, string | null][] = [
    ['Estimado', o.calculated_amount],
    ['Declarado', o.declared_amount],
    ['Pagado', o.paid_amount],
  ]
  if (isVat(o)) rows.push(['Saldo a favor declarado', o.declared_credit_balance])
  const shown = rows.filter(([, v]) => v !== null)
  if (shown.length === 0) return null
  return (
    <dl className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
      {shown.map(([label, value]) => (
        <div key={label} className="flex gap-1.5">
          <dt className="text-ink-2">{label}</dt>
          <dd className="font-medium tabular-nums">{formatMoney(value as string, 'PYG')}</dd>
        </div>
      ))}
    </dl>
  )
}

function ObligationRow({
  o,
  today,
  alertDays,
  rulesById,
  canManage,
  highlighted,
  onAction,
}: {
  o: Obligation
  today: string
  alertDays: number
  rulesById: Map<string, Rule>
  canManage: boolean
  highlighted: boolean
  onAction: (action: ObligationAction) => void
}) {
  const status = displayStatus(o, today, alertDays)
  const overdue = status === 'overdue'
  const late = overdue ? daysBetween(o.due_date, today) : 0
  return (
    <li
      id={`ob-${o.id}`}
      className={cx(
        'flex scroll-mt-24 gap-4 px-5 py-4',
        overdue && 'border-l-2 border-debit bg-debit-soft/40 pl-4.5',
        status === 'not_applicable' && 'text-ink-3',
        highlighted && 'outline-2 -outline-offset-2 outline-(--focus)',
      )}
      aria-label={`${obligationLabel(o.code)}, ${periodLabel(o.period_start, o.period_end)}`}
    >
      <DayStub iso={o.due_date} tone={overdue ? 'bad' : status === 'due_soon' ? 'warn' : 'neutral'} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p>
            <span className="font-semibold">{obligationLabel(o.code)}</span>{' '}
            <span className="text-sm text-ink-2">
              · {periodLabel(o.period_start, o.period_end)} · obligación {o.dnit_code}
            </span>
          </p>
          <p className="flex flex-wrap items-center gap-1.5">
            <ObligationStatusBadge status={status} />
            {overdue && <span className="text-sm font-medium text-debit">hace {late} {late === 1 ? 'día' : 'días'}</span>}
            {o.rule_status !== 'verified' && <UnverifiedMark status={o.rule_status} />}
          </p>
        </div>

        <p className="mt-1 text-sm">
          Vence el <span className="font-medium tabular-nums">{formatBookDate(o.due_date)}</span>
          {o.remind_by !== o.due_date && (
            <>
              {' '}
              · se avisa por el <span className="font-medium tabular-nums">{formatBookDate(o.remind_by)}</span>
            </>
          )}
        </p>
        {o.shift_explanation && <p className="mt-0.5 max-w-[75ch] text-sm text-ink-2">{o.shift_explanation}</p>}
        {o.exception && (
          <p className="mt-0.5 text-sm text-ink-2">
            Excepción: {o.exception.legal_reference}
            {o.exception.source_url && (
              <>
                {' '}
                (
                <a href={o.exception.source_url} target="_blank" rel="noreferrer" className="text-ledger hover:underline">
                  fuente
                </a>
                )
              </>
            )}
            .
          </p>
        )}

        <div className="mt-2 flex flex-col gap-1">
          <Amounts o={o} />
          {o.filed_on && (
            <p className="text-sm text-ink-2">
              {isRegister(o) ? 'Confirmado' : 'Presentada'} el {formatBookDate(o.filed_on)}, constancia {o.filing_reference}.
            </p>
          )}
          {o.paid_on && (
            <p className="text-sm text-ink-2">
              Pagada el {formatBookDate(o.paid_on)}
              {o.payment_transaction_id ? ', con un movimiento de finanzas vinculado' : ''}.
            </p>
          )}
          {o.not_applicable_reason && (
            <p className="text-sm text-ink-2">
              No aplica{o.not_applicable_auto ? ' (lo marcó el sistema: el perfil ya no la incluye)' : ''}: {o.not_applicable_reason}
            </p>
          )}
          {o.reopen_reason && o.status === 'pending' && <p className="text-sm text-ink-2">Reabierta: {o.reopen_reason}</p>}
        </div>

        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
            <RulesApplied rules={o.rules_applied} byId={rulesById} />
            {isVat(o) && (
              <Link to={`/impuestos/iva?mes=${o.period_start.slice(0, 7)}`} className="text-sm text-ledger hover:underline">
                Ver la estimación del IVA
              </Link>
            )}
            {isRegister(o) && (
              <Link to={`/impuestos/comprobantes?mes=${o.period_start.slice(0, 7)}`} className="text-sm text-ledger hover:underline">
                Ver los comprobantes del mes
              </Link>
            )}
          </div>
          {canManage && (
            <div className="flex flex-wrap gap-1.5">
              {obligationActions(o).map((a) => (
                <Button
                  key={a}
                  variant={a === 'file' || a === 'pay' ? 'secondary' : 'ghost'}
                  className="h-8"
                  onClick={() => onAction(a)}
                  aria-label={`${actionTitle(a, o)}: ${obligationLabel(o.code)} de ${periodLabel(o.period_start, o.period_end)}`}
                >
                  {a === 'file' ? (isRegister(o) ? 'Confirmado' : 'Presentada') : a === 'pay' ? 'Pagada' : a === 'not_applicable' ? 'No aplica' : 'Reabrir'}
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

function syncSummary(r: SyncResult): string | null {
  const parts: string[] = []
  if (r.created) parts.push(`${r.created} nuevas`)
  if (r.recalculated) parts.push(`${r.recalculated} recalculadas`)
  if (r.not_applicable) parts.push(`${r.not_applicable} pasaron a «no aplica»`)
  if (r.reactivated) parts.push(`${r.reactivated} reactivadas`)
  return parts.length ? `Calendario actualizado: ${parts.join(', ')}.` : null
}

export function CalendarPage() {
  const perms = useTaxPerms()
  const toast = useToast()
  const qc = useQueryClient()
  const invalidate = useInvalidateTax()
  const alerts = useTaxAlerts()
  const profile = useTaxProfile()
  const rulesById = useRulesById()
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const today = alerts.data?.as_of ?? todayIso()
  const year = Number(params.get('anio') ?? params.get('mes')?.slice(0, 4) ?? today.slice(0, 4))
  const status = params.get('estado') ?? ''
  const code = params.get('codigo') ?? ''
  const [dialog, setDialog] = useState<{ action: ObligationAction; o: Obligation } | null>(null)

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.delete('mes')
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  // Sincronizar al abrir (D-087): solo quien puede escribir (D-116); las lecturas no sincronizan.
  const sync = useMutation({
    mutationFn: () => post<SyncResult>('/tax/obligations/sync'),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: taxKeys.obligations() })
      qc.invalidateQueries({ queryKey: taxKeys.alerts() })
      const summary = syncSummary(r)
      if (summary) toast('ok', summary)
    },
  })
  const synced = useRef(false)
  useEffect(() => {
    if (perms.canManage && !synced.current) {
      synced.current = true
      sync.mutate()
    }
  }, [perms.canManage, sync])

  const list = useObligations({ from: `${year}-01-01`, to: `${year}-12-31`, status: status || undefined, code: code || undefined }, !sync.isPending)
  const groups = groupByDueMonth(list.data ?? [])
  const overdueCount = (list.data ?? []).filter((o) => o.is_overdue).length

  // Ir a la obligación del enlace (#ob-…) y resaltarla.
  const target = location.hash.startsWith('#ob-') ? location.hash.slice(4) : null
  useLayoutEffect(() => {
    if (!target || !list.data) return
    document.getElementById(`ob-${target}`)?.scrollIntoView({ block: 'center' })
  }, [target, list.data])

  const close = (changed: boolean) => {
    if (changed && dialog) {
      invalidate()
      toast('ok', `${obligationLabel(dialog.o.code)} de ${periodLabel(dialog.o.period_start, dialog.o.period_end)}: ${actionTitle(dialog.action, dialog.o).toLowerCase()} listo.`)
    }
    setDialog(null)
  }

  return (
    <>
      <PageHeader
        title="Calendario"
        description="Vencimientos por la terminación del RUC (calendario perpetuo de la DNIT), corridos por feriados y excepciones. Lo presentado se registra acá; la presentación se hace en Marangatu."
        actions={
          perms.canManage && (
            <Button variant="secondary" busy={sync.isPending} onClick={() => sync.mutate()}>
              <RefreshCw size={15} aria-hidden />
              Actualizar
            </Button>
          )
        }
      />

      <form
        role="search"
        aria-label="Filtros del calendario"
        onSubmit={(e) => e.preventDefault()}
        className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3 rounded-md border border-line bg-surface p-3.5"
      >
        <div className="flex items-end gap-1">
          <Button type="button" variant="ghost" className="px-2" aria-label="Año anterior" onClick={() => setParam('anio', String(year - 1))}>
            <ChevronLeft size={16} />
          </Button>
          <p className="flex h-9 min-w-16 items-center justify-center text-md font-semibold tabular-nums" aria-live="polite">
            {year}
          </p>
          <Button type="button" variant="ghost" className="px-2" aria-label="Año siguiente" onClick={() => setParam('anio', String(year + 1))}>
            <ChevronRight size={16} />
          </Button>
        </div>
        <Field label="Estado">
          {(p) => (
            <Select {...p} className="w-44" value={status} onChange={(e) => setParam('estado', e.target.value)}>
              <option value="">Todas</option>
              <option value="pending">Pendientes</option>
              <option value="overdue">Vencidas</option>
              <option value="filed">Presentadas</option>
              <option value="paid">Pagadas</option>
              <option value="not_applicable">No aplica</option>
            </Select>
          )}
        </Field>
        <Field label="Obligación">
          {(p) => (
            <Select {...p} className="w-64" value={code} onChange={(e) => setParam('codigo', e.target.value)}>
              <option value="">Todas</option>
              {Object.entries(OBLIGATION_LABELS).map(([c, label]) => (
                <option key={c} value={c}>
                  {label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {overdueCount > 0 && status !== 'overdue' && (
          <div className="ml-auto pb-1.5">
            <Check label={`Solo vencidas (${overdueCount})`} checked={false} onChange={() => setParam('estado', 'overdue')} />
          </div>
        )}
      </form>

      {!perms.canManage && <p className="-mt-1 mb-4 text-sm text-ink-3">{perms.manageReason} El calendario se actualiza cuando alguien que carga datos lo abre.</p>}
      {sync.isError && <ApiErrorNotice error={sync.error} title="No se pudo actualizar el calendario." />}
      {profile.data && !profile.data.current && (
        <div className="mb-4">
          <Notice tone="warn" title="Sin perfil fiscal no hay obligaciones">
            La app no asume el régimen ni las obligaciones.{' '}
            <Link to="/impuestos/perfil" className="font-medium underline">
              Cargá el perfil fiscal
            </Link>{' '}
            y el calendario se arma solo.
          </Notice>
        </div>
      )}

      <Sheet>
        {list.isPending || sync.isPending ? (
          <TableSkeleton rows={6} cols={3} />
        ) : list.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={list.error} title="No se pudo cargar el calendario." />
          </div>
        ) : groups.length === 0 ? (
          <EmptyState
            title={status || code ? 'Ninguna obligación coincide' : `No hay obligaciones con vencimiento en ${year}`}
            action={
              status || code ? (
                <Button variant="secondary" onClick={() => setParams(new URLSearchParams({ anio: String(year) }), { replace: true })}>
                  Quitar filtros
                </Button>
              ) : (
                <Link to="/impuestos/perfil" className="font-medium text-ledger hover:underline">
                  Revisar el perfil fiscal
                </Link>
              )
            }
          >
            {status || code ? 'Probá con otro estado u obligación.' : 'Se generan desde la fecha de alta de cada obligación del perfil hasta tres meses adelante.'}
          </EmptyState>
        ) : (
          groups.map((g) => (
            <section key={g.month} aria-labelledby={`m-${g.month}`} className="border-b border-line last:border-b-0">
              <h2 id={`m-${g.month}`} className={cx('sticky top-0 z-10 border-b border-line bg-sunken px-5 py-2 font-semibold', g.month === today.slice(0, 7) && 'text-ledger')}>
                {monthTitle(g.month)}
                {g.month === today.slice(0, 7) && <span className="ml-2 text-sm font-normal">· este mes</span>}
              </h2>
              <ol className="divide-y divide-line">
                {g.items.map((o) => (
                  <ObligationRow
                    key={o.id}
                    o={o}
                    today={today}
                    alertDays={alerts.data?.alert_days ?? 10}
                    rulesById={rulesById}
                    canManage={perms.canManage}
                    highlighted={o.id === target}
                    onAction={(action) => setDialog({ action, o })}
                  />
                ))}
              </ol>
            </section>
          ))
        )}
      </Sheet>

      <Modal open={dialog !== null} size="lg" title={dialog ? actionTitle(dialog.action, dialog.o) : ''} onClose={() => setDialog(null)}>
        {dialog && <ObligationActionForm key={`${dialog.o.id}-${dialog.action}`} action={dialog.action} o={dialog.o} onDone={close} />}
      </Modal>
    </>
  )
}
