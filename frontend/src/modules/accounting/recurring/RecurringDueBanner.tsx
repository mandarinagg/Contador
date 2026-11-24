/**
 * Aviso de asientos recurrentes pendientes del período actual (D-061), en el inicio y en
 * Asientos. Nada se genera solo: el aviso ofrece generarlos (quien tenga `accounting.manage`).
 */
import { useMutation } from '@tanstack/react-query'
import { Repeat } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { cx } from '../../../lib/cx'
import { formatMoney } from '../../../lib/money'
import { post } from '../../../services/api'
import { errorMessage } from '../../finance/forms'
import { formatBookDate, todayIso } from '../../finance/labels'
import { periodOf, useAccountingPerms, useFiscalYears, useInvalidateAccounting, useRecurringDue } from '../data'
import { monthYear } from '../labels'
import type { RecurringGenerated } from '../types3b'
import { generatedMessage } from './logic'

export function RecurringDueBanner({ className }: { className?: string }) {
  const perms = useAccountingPerms()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const years = useFiscalYears(perms.canRead)
  const period = perms.canRead ? periodOf(years.data, todayIso()) : undefined
  const due = useRecurringDue(period?.status === 'open' ? period.id : undefined)
  const generate = useMutation({
    mutationFn: () => post<RecurringGenerated>('/accounting/recurring/generate', { period_id: period?.id }),
    onSuccess: (r) => {
      invalidate()
      toast('ok', generatedMessage(r))
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudieron generar los asientos recurrentes.')),
  })
  const list = due.data ?? []
  if (!period || list.length === 0) return null
  const month = monthYear(period.start_date)
  return (
    <section
      aria-label="Asientos recurrentes pendientes"
      className={cx('flex flex-wrap items-start gap-x-4 gap-y-2 rounded-md border border-amber/40 bg-amber-soft px-4 py-3', className)}
    >
      <Repeat size={18} className="mt-0.5 shrink-0 text-amber" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">
          {list.length === 1 ? `Falta generar 1 asiento recurrente de ${month}` : `Faltan generar ${list.length} asientos recurrentes de ${month}`}
        </p>
        <ul className="mt-0.5 text-sm text-ink-2">
          {list.slice(0, 4).map((d) => (
            <li key={d.template_id}>
              {d.description}, el {formatBookDate(d.entry_date)}, {formatMoney(d.total, 'PYG')}
            </li>
          ))}
          {list.length > 4 && <li>y {list.length - 4} más.</li>}
        </ul>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <Link to="/contabilidad/recurrentes" className="text-sm font-medium text-ledger hover:underline">
          Ver las plantillas
        </Link>
        {perms.canManage && (
          <Button className="h-8" busy={generate.isPending} onClick={() => generate.mutate()}>
            Generar los de {month.split(' ')[0]}
          </Button>
        )}
      </div>
    </section>
  )
}
