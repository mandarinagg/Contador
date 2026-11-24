/** Resumen fiscal: los avisos (D-092) con su acción y los próximos vencimientos. */
import { BadgePercent, ReceiptText } from 'lucide-react'
import { Link } from 'react-router'
import { PageHeader, Sheet, Skeleton } from '../../components/ui'
import { todayIso } from '../finance/labels'
import { AlertsPanel } from './AlertsPanel'
import { DayStub, ObligationStatusBadge, UnverifiedMark } from './components'
import { useObligations, useTaxAlerts, useTaxProfile } from './data'
import { IRE_REGIME_LABELS, obligationLabel, periodLabel } from './labels'
import { addDays, displayStatus } from './logic'
import type { Obligation } from './types'

const UPCOMING_DAYS = 75

function Upcoming({ items, today, alertDays }: { items: Obligation[]; today: string; alertDays: number }) {
  if (items.length === 0) {
    return <p className="px-5 py-6 text-sm text-ink-2">No hay vencimientos pendientes en los próximos {UPCOMING_DAYS} días.</p>
  }
  return (
    <ol className="divide-y divide-line">
      {items.map((o) => {
        const status = displayStatus(o, today, alertDays)
        return (
          <li key={o.id} className="flex items-start gap-3 px-5 py-3">
            <DayStub iso={o.due_date} tone={status === 'due_soon' ? 'warn' : 'neutral'} />
            <div className="min-w-0 flex-1">
              <Link to={`/impuestos/calendario?mes=${o.due_date.slice(0, 7)}#ob-${o.id}`} className="font-medium hover:text-ledger hover:underline">
                {obligationLabel(o.code)}
              </Link>
              <p className="text-sm text-ink-2">{periodLabel(o.period_start, o.period_end)}</p>
              <p className="mt-1 flex flex-wrap gap-1.5">
                <ObligationStatusBadge status={status} />
                {o.rule_status !== 'verified' && <UnverifiedMark status={o.rule_status} />}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function TaxSummaryPage() {
  const alerts = useTaxAlerts()
  const profile = useTaxProfile()
  const today = alerts.data?.as_of ?? todayIso()
  const upcoming = useObligations({ from: today, to: addDays(today, UPCOMING_DAYS), status: 'pending' }, alerts.isSuccess)
  const current = profile.data?.current

  return (
    <>
      <PageHeader
        title="Resumen fiscal"
        description="Lo que hay que presentar, lo que vence y lo que falta cargar. La app no presenta nada: arma recordatorios y borradores para que vos o tu contador lo hagan en Marangatu."
        actions={
          <>
            <Link to="/impuestos/iva" className="inline-flex h-9 items-center gap-2 rounded-sm border border-line-strong bg-surface px-3.5 font-medium hover:bg-sunken">
              <BadgePercent size={16} aria-hidden />
              IVA del mes
            </Link>
            <Link to="/impuestos/comprobantes/cargar" className="inline-flex h-9 items-center gap-2 rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong">
              <ReceiptText size={16} aria-hidden />
              Cargar comprobantes
            </Link>
          </>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)_20rem] items-start gap-6">
        <Sheet>
          <h2 className="border-b border-line px-5 py-3.5 font-semibold">Avisos</h2>
          <AlertsPanel />
        </Sheet>
        <div className="flex flex-col gap-6">
          <Sheet>
            <h2 className="border-b border-line px-5 py-3.5 font-semibold">Próximos vencimientos</h2>
            {upcoming.isPending ? (
              <div className="flex flex-col gap-3 p-5">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
            ) : (
              <Upcoming items={upcoming.data ?? []} today={today} alertDays={alerts.data?.alert_days ?? 10} />
            )}
            <p className="border-t border-line px-5 py-3 text-sm">
              <Link to="/impuestos/calendario" className="font-medium text-ledger hover:underline">
                Ver el calendario completo
              </Link>
            </p>
          </Sheet>
          <Sheet className="p-5">
            <h2 className="font-semibold">Perfil fiscal</h2>
            {profile.isPending ? (
              <Skeleton className="mt-3 h-5 w-32" />
            ) : current ? (
              <>
                <p className="mt-2 text-sm text-ink-2">
                  {IRE_REGIME_LABELS[current.ire_regime]}
                  {current.vat_taxpayer ? ', contribuyente del IVA' : ', no contribuyente del IVA'}. Obligaciones:{' '}
                  <span className="tabular-nums">{current.obligations.map((o) => o.code).join(', ') || 'ninguna'}</span>.
                </p>
                <p className="mt-2">
                  {current.origin === 'verified' ? (
                    <UnverifiedMark status="verified" />
                  ) : (
                    <UnverifiedMark status="pending" label="Declarado, sin verificar" />
                  )}
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm text-ink-2">Sin perfil no hay calendario: la app no asume el régimen ni las obligaciones.</p>
            )}
            <Link to="/impuestos/perfil" className="mt-3 inline-block text-sm font-medium text-ledger hover:underline">
              {current ? 'Ver el perfil' : 'Cargar el perfil fiscal'}
            </Link>
          </Sheet>
        </div>
      </div>
    </>
  )
}
