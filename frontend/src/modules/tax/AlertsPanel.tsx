/**
 * Avisos tributarios (D-092, D-098) con su acción. Se usa entero en el Resumen fiscal y
 * resumido en el Inicio. Los calcula la API en el momento (`GET /tax/alerts`).
 */
import { CalendarClock, CircleAlert, Info, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Skeleton } from '../../components/ui'
import { cx } from '../../lib/cx'
import { formatBookDate } from '../finance/labels'
import { ApiErrorNotice } from '../finance/components'
import { useTaxAlerts } from './data'
import { ALERT_TITLES, monthTitle, obligationLabel, periodLabel } from './labels'
import type { AlertObligationItem, RuleApplied, TaxAlert } from './types'

const SEVERITY: Record<TaxAlert['severity'], { icon: ReactNode; bar: string; text: string; label: string }> = {
  danger: { icon: <CircleAlert size={17} aria-hidden />, bar: 'border-debit', text: 'text-debit', label: 'Urgente' },
  warning: { icon: <TriangleAlert size={17} aria-hidden />, bar: 'border-amber', text: 'text-amber', label: 'Atención' },
  info: { icon: <Info size={17} aria-hidden />, bar: 'border-line-strong', text: 'text-ink-2', label: 'Para revisar' },
}

const linkCls = 'font-medium text-ledger hover:underline'

function ObligationItems({ items, limit, showRemind }: { items: AlertObligationItem[]; limit: number; showRemind: boolean }) {
  return (
    <ul className="mt-2 flex flex-col gap-1.5">
      {items.slice(0, limit).map((o) => (
        <li key={o.id} className="text-sm">
          <Link to={`/impuestos/calendario?mes=${o.due_date.slice(0, 7)}#ob-${o.id}`} className="font-medium hover:text-ledger hover:underline">
            {obligationLabel(o.code)}
          </Link>{' '}
          <span className="text-ink-2">
            de {periodLabel(o.period_start, o.period_end)} · vence el {formatBookDate(o.due_date)}
            {showRemind && o.remind_by !== o.due_date && <> · avisamos el {formatBookDate(o.remind_by)}</>}
          </span>
          {showRemind && o.shift_explanation && <span className="block text-ink-3">{o.shift_explanation}</span>}
        </li>
      ))}
      {items.length > limit && <li className="text-sm text-ink-3">y {items.length - limit} más.</li>}
    </ul>
  )
}

function AlertBody({ alert, compact }: { alert: TaxAlert; compact: boolean }) {
  const limit = compact ? 2 : 8
  switch (alert.code) {
    case 'OBLIGATIONS_OVERDUE':
    case 'OBLIGATIONS_DUE_SOON':
      return (
        <>
          <ObligationItems items={alert.items as AlertObligationItem[]} limit={limit} showRemind={alert.code === 'OBLIGATIONS_DUE_SOON'} />
          {alert.code === 'OBLIGATIONS_DUE_SOON' && !compact && (
            <p className="mt-2 text-sm text-ink-3">
              Avisamos por la fecha fija del calendario aunque el vencimiento se corra por un día inhábil: no está verificado que sábados y feriados corran el plazo
              (dudas D-F4-11 y D-F4-12).
            </p>
          )}
        </>
      )
    case 'REGISTER_UNCONFIRMED': {
      const items = alert.items as AlertObligationItem[]
      return (
        <ul className="mt-2 flex flex-col gap-1">
          {items.slice(0, limit).map((o) => (
            <li key={o.id} className="text-sm">
              <span className="font-medium">{monthTitle(o.period_start.slice(0, 7))}</span>:{' '}
              <Link to={`/impuestos/comprobantes?mes=${o.period_start.slice(0, 7)}`} className={linkCls}>
                revisar los comprobantes
              </Link>{' '}
              y{' '}
              <Link to={`/impuestos/calendario?mes=${o.due_date.slice(0, 7)}#ob-${o.id}`} className={linkCls}>
                marcarlo confirmado
              </Link>
            </li>
          ))}
          {items.length > limit && <li className="text-sm text-ink-3">y {items.length - limit} más.</li>}
        </ul>
      )
    }
    case 'MONTHS_WITHOUT_VOUCHERS': {
      const items = alert.items as { month: string }[]
      return (
        <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm">
          {items.slice(0, compact ? 4 : 12).map((m) => (
            <Link key={m.month} to={`/impuestos/comprobantes/cargar?mes=${m.month.slice(0, 7)}`} className={linkCls}>
              Cargar {monthTitle(m.month.slice(0, 7)).toLowerCase()}
            </Link>
          ))}
        </p>
      )
    }
    case 'PROFILE_MISSING':
      return (
        <p className="mt-2 text-sm">
          <Link to="/impuestos/perfil" className={linkCls}>
            Cargar el perfil fiscal
          </Link>
        </p>
      )
    case 'PROFILE_UNVERIFIED':
      return (
        <p className="mt-2 text-sm">
          <Link to="/impuestos/perfil" className={linkCls}>
            Ver el perfil y pedir la verificación
          </Link>
        </p>
      )
    case 'RULES_UNVERIFIED': {
      const items = alert.items as RuleApplied[]
      return (
        <p className="mt-2 text-sm text-ink-2">
          {!compact && <span className="tabular-nums">{items.map((r) => `${r.code} v${r.version}`).join(', ')}. </span>}
          <Link to="/impuestos/reglas" className={linkCls}>
            Revisar las reglas
          </Link>
        </p>
      )
    }
    case 'COUNTERPARTY_RUC_UNCHECKED': {
      const items = alert.items as { voucher_id: string; number: string; ruc: string; name: string }[]
      return (
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {items.slice(0, limit).map((v) => (
            <li key={v.voucher_id}>
              <Link to={`/impuestos/comprobantes/${v.voucher_id}`} className={linkCls}>
                {v.number}
              </Link>{' '}
              <span className="text-ink-2">
                {v.name}, RUC {v.ruc}
              </span>
            </li>
          ))}
        </ul>
      )
    }
    default:
      return null
  }
}

export function AlertsPanel({ compact = false }: { compact?: boolean }) {
  const alerts = useTaxAlerts()
  if (alerts.isPending) {
    return (
      <div className="flex flex-col gap-3 p-5" aria-busy="true" aria-label="Cargando avisos">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-5 w-3/5" />
      </div>
    )
  }
  if (alerts.isError) {
    return (
      <div className="p-5">
        <ApiErrorNotice error={alerts.error} title="No se pudieron calcular los avisos." />
      </div>
    )
  }
  const list = alerts.data.alerts
  if (list.length === 0) {
    return (
      <p className="flex items-center gap-2 px-5 py-6 text-ink-2">
        <CalendarClock size={17} className="text-ledger" aria-hidden />
        Sin avisos: no hay vencimientos en los próximos {alerts.data.alert_days} días ni nada pendiente de revisar.
      </p>
    )
  }
  return (
    <ul className="divide-y divide-line" aria-label="Avisos de impuestos">
      {list.map((a) => {
        const s = SEVERITY[a.severity]
        return (
          <li key={a.code} className={cx('border-l-2 py-3.5 pr-5', compact ? 'pl-4' : 'pl-5', s.bar)}>
            <div className="flex items-start gap-2.5">
              <span className={cx('mt-0.5 shrink-0', s.text)}>{s.icon}</span>
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  <span className="sr-only">{s.label}: </span>
                  {ALERT_TITLES[a.code] ?? a.code}
                  {a.items.length > 0 && <span className="ml-1.5 text-ink-3 tabular-nums">({a.count})</span>}
                </p>
                {!compact && <p className="mt-0.5 max-w-[70ch] text-sm text-ink-2">{a.message}</p>}
                <AlertBody alert={a} compact={compact} />
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
