/**
 * Asientos recurrentes (D-061): plantillas con día del mes y vigencia, que se pausan y activan,
 * y la generación de los borradores de un período (sin duplicar los que ya existen).
 */
import { useMutation } from '@tanstack/react-query'
import { Pause, Play, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Badge, Button, EmptyState, Notice, PageHeader, Select, Sheet } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { cx } from '../../../lib/cx'
import { patch, post } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton, Th } from '../../finance/components'
import { errorMessage } from '../../finance/forms'
import { formatBookDate, todayIso } from '../../finance/labels'
import { EntryStatusBadge, Pyg } from '../components'
import { periodOf, useAccountingPerms, useFiscalYears, useInvalidateAccounting, useRecurringTemplates } from '../data'
import { entryLabel, monthYear } from '../labels'
import type { Entry } from '../types'
import type { RecurringGenerated, RecurringTemplate } from '../types3b'
import { RecurringDueBanner } from './RecurringDueBanner'
import { generatedMessage, validityText } from './logic'

const linkButton =
  'inline-flex h-9 items-center gap-2 rounded-sm border border-transparent bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong'

function ResultList({ title, entries }: { title: string; entries: Entry[] }) {
  if (entries.length === 0) return null
  return (
    <div>
      <h3 className="text-sm font-medium text-ink-2">{title}</h3>
      <ul className="mt-1 divide-y divide-line text-sm">
        {entries.map((e) => (
          <li key={e.id} className="flex items-center gap-3 py-1.5">
            <Link to={`/contabilidad/asientos/${e.id}`} className="min-w-0 flex-1 truncate font-medium text-ledger hover:underline">
              {e.description}
            </Link>
            <span className="text-ink-2 tabular-nums">{formatBookDate(e.entry_date)}</span>
            <span className="w-20">{entryLabel(e)}</span>
            <EntryStatusBadge status={e.status} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function Generate() {
  const perms = useAccountingPerms()
  const years = useFiscalYears()
  const invalidate = useInvalidateAccounting()
  const toast = useToast()
  const periods = (years.data ?? []).flatMap((y) => y.periods.filter((p) => p.status === 'open')).sort((a, b) => a.start_date.localeCompare(b.start_date))
  const current = periodOf(years.data, todayIso())
  const [periodId, setPeriodId] = useState('')
  const selected = periods.find((p) => p.id === periodId) ?? (current?.status === 'open' ? current : periods[0])
  const [result, setResult] = useState<{ month: string; data: RecurringGenerated } | null>(null)
  const run = useMutation({
    mutationFn: () => post<RecurringGenerated>('/accounting/recurring/generate', { period_id: selected?.id }),
    onMutate: () => setResult(null),
    onSuccess: (data) => {
      invalidate()
      setResult({ month: monthYear(selected?.start_date ?? ''), data })
      toast('ok', generatedMessage(data))
    },
  })
  if (!perms.canManage) return null
  return (
    <Sheet className="p-5">
      <h2 className="font-semibold">Generar los del período</h2>
      <p className="mt-1 text-sm text-ink-2">Crea un borrador por cada plantilla activa con fecha en el mes. Si ya se generó, no lo duplica.</p>
      {periods.length === 0 ? (
        <p className="mt-3 text-sm text-ink-3">No hay períodos abiertos.</p>
      ) : (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            run.mutate()
          }}
        >
          <label className="flex flex-col gap-1 text-sm text-ink-2">
            Período
            <Select value={selected?.id} onChange={(e) => (setPeriodId(e.target.value), setResult(null))}>
              {periods.map((p) => (
                <option key={p.id} value={p.id}>
                  {monthYear(p.start_date)}
                  {p.id === current?.id ? ' (actual)' : ''}
                </option>
              ))}
            </Select>
          </label>
          <Button type="submit" className="self-start" busy={run.isPending}>
            Generar los borradores
          </Button>
        </form>
      )}
      {run.error ? (
        <div className="mt-3">
          <ApiErrorNotice error={run.error} title="No se generó ningún asiento." />
        </div>
      ) : null}
      {result && (
        <div className="mt-4 flex flex-col gap-3 border-t border-line pt-3" role="status" aria-label="Resultado de la generación">
          <p className="text-sm font-medium">
            {result.month}: {generatedMessage(result.data)}
          </p>
          <ResultList title="Creados ahora" entries={result.data.created} />
          <ResultList title="Ya existían" entries={result.data.existing} />
        </div>
      )}
    </Sheet>
  )
}

export function RecurringPage() {
  const perms = useAccountingPerms()
  const templates = useRecurringTemplates()
  const invalidate = useInvalidateAccounting()
  const toast = useToast()
  const toggle = useMutation({
    mutationFn: (t: RecurringTemplate) => patch<RecurringTemplate>(`/accounting/recurring/${t.id}`, { status: t.status === 'active' ? 'paused' : 'active' }),
    onSuccess: (t) => {
      invalidate()
      toast('ok', t.status === 'paused' ? `«${t.description}» en pausa: no se genera hasta reactivarla.` : `«${t.description}» activa de nuevo.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar la plantilla.')),
  })
  const list = templates.data ?? []

  return (
    <>
      <PageHeader
        title="Asientos recurrentes"
        description="Plantillas para lo que se repite todos los meses (alquiler, honorarios, cuotas). Cada mes generan un borrador que se revisa y contabiliza como cualquier asiento."
        actions={
          perms.canManage &&
          list.length > 0 && (
            <Link to="/contabilidad/recurrentes/nueva" className={linkButton}>
              <Plus size={16} />
              Nueva plantilla
            </Link>
          )
        }
      />
      <RecurringDueBanner className="mb-5" />
      <div className="grid grid-cols-[minmax(0,1fr)_21rem] items-start gap-6">
        <Sheet>
          {templates.isPending ? (
            <TableSkeleton rows={4} cols={5} />
          ) : templates.isError ? (
            <div className="p-5">
              <ApiErrorNotice error={templates.error} title="No se pudieron cargar las plantillas." />
            </div>
          ) : list.length === 0 ? (
            <EmptyState
              title="Todavía no hay plantillas"
              action={
                perms.canManage ? (
                  <Link to="/contabilidad/recurrentes/nueva" className={linkButton}>
                    <Plus size={16} />
                    Crear la primera
                  </Link>
                ) : (
                  <p className="text-sm text-ink-3">{perms.manageReason}</p>
                )
              }
            >
              Cargá una vez las líneas del asiento que se repite y el día del mes. Al empezar cada mes, el sistema avisa y genera los borradores.
            </EmptyState>
          ) : (
            <table className="w-full" aria-label="Plantillas de asientos recurrentes">
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>Plantilla</Th>
                  <Th className="w-20">Día</Th>
                  <Th align="right" className="w-36">
                    Importe
                  </Th>
                  <Th className="w-28">Estado</Th>
                  {perms.canManage && (
                    <Th className="w-16">
                      <span className="sr-only">Acciones</span>
                    </Th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.map((t) => (
                  <tr key={t.id} className={cx(t.status === 'paused' && 'text-ink-2')}>
                    <td className="px-4 py-2.5">
                      <Link to={`/contabilidad/recurrentes/${t.id}`} className="font-medium hover:text-ledger hover:underline">
                        {t.description}
                      </Link>
                      <span className="block text-sm text-ink-3">
                        {validityText(t)}. {t.lines.map((l) => l.account_code).join(', ')}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums">{t.day_of_month}</td>
                    <td className="px-4 py-2.5 text-right">
                      <Pyg value={t.total} />
                    </td>
                    <td className="px-4 py-2.5">{t.status === 'active' ? <Badge tone="ok">Activa</Badge> : <Badge>En pausa</Badge>}</td>
                    {perms.canManage && (
                      <td className="px-3 py-1.5 text-right">
                        <Button
                          variant="ghost"
                          className="h-8 px-2"
                          aria-label={`${t.status === 'active' ? 'Pausar' : 'Activar'} ${t.description}`}
                          title={t.status === 'active' ? 'Pausar' : 'Activar'}
                          busy={toggle.isPending && toggle.variables?.id === t.id}
                          onClick={() => toggle.mutate(t)}
                        >
                          {t.status === 'active' ? <Pause size={15} /> : <Play size={15} />}
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Sheet>
        <div className="flex flex-col gap-4">
          <Generate />
          <Notice tone="neutral" title="Días que no existen">
            Si el día es 29, 30 o 31 y el mes es más corto, el asiento va el último día del mes.
          </Notice>
        </div>
      </div>
    </>
  )
}
