/**
 * Depreciación del mes (D-058): un borrador por mes con todas las cuotas, que alguien revisa y
 * contabiliza en el editor de asientos. Los meses no se saltean; si la API lo impide (409) o
 * falta completar una categoría (422), la pantalla dice qué hacer y lleva ahí.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { Calculator } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Notice, Select, Sheet } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { cx } from '../../../lib/cx'
import { ApiError, get, post } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton, Th } from '../../finance/components'
import { todayIso } from '../../finance/labels'
import { Pyg } from '../components'
import { accountingKeys, useAccountingPerms, useAssetCategories, useFiscalYears, useInvalidateAccounting } from '../data'
import { monthName, monthYear } from '../labels'
import type { FiscalYear, Period } from '../types'
import type { AssetCategory, DepreciationRun } from '../types3b'
import { liveRunByMonth } from './logic'

type Failure = { period: Period; error: unknown }

/** Qué hacer ante cada error de la corrida, con enlaces. */
function FailureNotice({
  failure,
  years,
  categories,
  onGo,
}: {
  failure: Failure
  years: FiscalYear[]
  categories: AssetCategory[]
  onGo: (yearId: string, periodId: string) => void
}) {
  const e = failure.error instanceof ApiError ? failure.error : null
  const month = monthYear(failure.period.start_date)
  if (e?.code === 'DEPRECIATION_MONTH_MISSING') {
    const missing = String((e.details as { month?: string } | null)?.month ?? '')
    const year = years.find((y) => y.start_date <= missing && missing <= y.end_date)
    const period = year?.periods.find((p) => p.start_date.slice(0, 7) === missing.slice(0, 7))
    return (
      <Notice tone="warn" title={`No se puede calcular ${month}: falta ${missing ? monthYear(missing) : 'un mes anterior'}`}>
        {e.message} Contabilizá primero la depreciación de ese mes y después volvé a {month}.{' '}
        {year && period && (
          <button type="button" className="font-medium text-ledger underline-offset-2 hover:underline" onClick={() => onGo(year.id, period.id)}>
            Ir a {monthYear(missing)}
          </button>
        )}
      </Notice>
    )
  }
  if (e?.code === 'DEPRECIATION_RUN_EXISTS') {
    const entryId = (e.details as { entry_id?: string } | null)?.entry_id
    return (
      <Notice tone="warn" title={`${month} ya tiene su corrida`}>
        {e.message}{' '}
        {entryId && (
          <Link to={`/contabilidad/asientos/${entryId}`} className="font-medium text-ledger hover:underline">
            Abrir la corrida de {month}
          </Link>
        )}
      </Notice>
    )
  }
  if (e?.code === 'ASSET_CATEGORY_INCOMPLETE') {
    const bad = ((e.details as { categories?: { name: string; missing: string[] }[] } | null)?.categories ?? []).map((c) => ({
      ...c,
      // La API manda solo el nombre: se busca el id por nombre (gap informado).
      id: categories.find((x) => x.name === c.name)?.id,
    }))
    return (
      <Notice tone="bad" title={`No se puede calcular ${month}: hay categorías incompletas`}>
        Completá estas categorías y volvé a calcular:
        <ul className="mt-1 list-disc pl-5">
          {bad.map((c) => (
            <li key={c.name}>
              {c.id ? (
                <Link to={`/contabilidad/activos/categorias?editar=${c.id}`} className="font-medium text-ledger hover:underline">
                  Completar «{c.name}»
                </Link>
              ) : (
                <span className="font-medium">{c.name}</span>
              )}{' '}
              (falta: {c.missing.join(', ')})
            </li>
          ))}
        </ul>
      </Notice>
    )
  }
  if (e?.code === 'PERIOD_CLOSED') {
    return (
      <Notice tone="warn" title={`${month} está cerrado`}>
        {e.message}{' '}
        <Link to="/contabilidad/ejercicios" className="font-medium text-ledger hover:underline">
          Ir a los ejercicios
        </Link>
      </Notice>
    )
  }
  return <ApiErrorNotice error={failure.error} title={`No se pudo calcular la depreciación de ${month}.`} />
}

export function DepreciationPage() {
  const perms = useAccountingPerms()
  const years = useFiscalYears()
  const categories = useAssetCategories()
  const navigate = useNavigate()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [params, setParams] = useSearchParams()
  const [failure, setFailure] = useState<Failure | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const list = [...(years.data ?? [])].sort((a, b) => b.start_date.localeCompare(a.start_date))
  const today = todayIso()
  const fallback = list.find((y) => y.start_date <= today && today <= y.end_date) ?? list[0]
  const year = list.find((y) => y.id === params.get('ejercicio')) ?? fallback
  const runs = useQuery({
    enabled: Boolean(year),
    queryKey: accountingKeys.runs(year?.id ?? ''),
    queryFn: () => get<DepreciationRun[]>(`/accounting/depreciation/runs?fiscal_year_id=${year?.id}`),
  })
  const live = liveRunByMonth(runs.data ?? [])
  const reversed = new Set((runs.data ?? []).filter((r) => r.entry_status === 'reversed').map((r) => r.period_id))
  const run = useMutation({
    mutationFn: (p: Period) => post<DepreciationRun>('/accounting/depreciation/run', { period_id: p.id }),
    onMutate: () => setFailure(null),
    onSuccess: (r, p) => {
      invalidate()
      toast('ok', `Borrador de depreciación de ${monthYear(p.start_date)} generado: revisalo y contabilizalo.`)
      navigate(`/contabilidad/asientos/${r.entry_id}`)
    },
    onError: (error, p) => setFailure({ period: p, error }),
  })
  const goTo = (yearId: string, periodId: string) => {
    setParams({ ejercicio: yearId }, { replace: true })
    setHighlight(periodId)
    setFailure(null)
    requestAnimationFrame(() => document.getElementById(`mes-${periodId}`)?.focus())
  }
  const periods = year?.periods ?? []
  // El próximo mes a calcular: el primero abierto sin corrida viva después de la última viva.
  const lastLive = periods.reduce((acc, p, i) => (live.has(p.id) ? i : acc), -1)
  const next = periods.find((p, i) => i > lastLive && p.status === 'open' && !live.has(p.id))

  return (
    <>
      {years.isPending ? (
        <Sheet>
          <TableSkeleton rows={6} cols={4} />
        </Sheet>
      ) : list.length === 0 ? (
        <Sheet>
          <EmptyState
            title="Todavía no hay ejercicios"
            action={
              <Link to="/contabilidad/ejercicios" className="font-medium text-ledger hover:underline">
                Crear el ejercicio
              </Link>
            }
          >
            La depreciación se calcula por mes dentro de un ejercicio contable.
          </EmptyState>
        </Sheet>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-4">
            <label className="flex w-56 flex-col gap-1 text-sm text-ink-2">
              Ejercicio
              <Select value={year?.id} onChange={(e) => (setParams({ ejercicio: e.target.value }, { replace: true }), setFailure(null))}>
                {list.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.start_date.slice(0, 4) === y.end_date.slice(0, 4) ? y.start_date.slice(0, 4) : `${y.start_date.slice(0, 4)}/${y.end_date.slice(0, 4)}`}
                    {y.status === 'closed' ? ' (cerrado)' : ''}
                  </option>
                ))}
              </Select>
            </label>
            <p className="max-w-[70ch] text-sm text-ink-2">
              Cada mes se calcula una vez y queda como borrador; se contabiliza desde el asiento. Los meses van en orden: no se puede contabilizar uno
              si falta el anterior.
            </p>
          </div>
          {failure && (
            <div className="mb-4" role="alert">
              <FailureNotice failure={failure} years={list} categories={categories.data ?? []} onGo={goTo} />
            </div>
          )}
          <Sheet>
            {runs.isPending ? (
              <TableSkeleton rows={6} cols={4} />
            ) : runs.isError ? (
              <div className="p-5">
                <ApiErrorNotice error={runs.error} title="No se pudieron cargar las corridas." />
              </div>
            ) : (
              <table className="w-full" aria-label="Depreciación por mes">
                <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                  <tr>
                    <Th>Mes</Th>
                    <Th className="w-48">Estado</Th>
                    <Th align="right" className="w-40">
                      Total
                    </Th>
                    <Th className="w-64">
                      <span className="sr-only">Acción</span>
                    </Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {periods.map((p) => {
                    const r = live.get(p.id)
                    const isNext = next?.id === p.id
                    return (
                      <tr
                        key={p.id}
                        id={`mes-${p.id}`}
                        tabIndex={-1}
                        className={cx(highlight === p.id && 'bg-amber-soft', isNext && !highlight && 'bg-ledger-soft/50', 'outline-none focus-visible:ring-2 focus-visible:ring-(--focus)')}
                      >
                        <td className="px-4 py-2">
                          <span className="font-medium">{monthName(p.start_date)}</span>
                          {isNext && <span className="ml-2 text-sm text-ledger">el próximo a calcular</span>}
                        </td>
                        <td className="px-4 py-2">
                          {r ? (
                            r.entry_status === 'posted' ? (
                              <Badge tone="ok">Contabilizada</Badge>
                            ) : (
                              <Badge tone="warn">Borrador</Badge>
                            )
                          ) : p.status === 'closed' ? (
                            <Badge>Período cerrado</Badge>
                          ) : (
                            <span className="text-sm text-ink-3">{reversed.has(p.id) ? 'Revertida, sin corrida viva' : 'Sin calcular'}</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right">{r ? <Pyg value={r.total} /> : <span className="text-ink-3">·</span>}</td>
                        <td className="px-4 py-1.5 text-right">
                          {r ? (
                            <Link to={`/contabilidad/asientos/${r.entry_id}`} className="text-sm font-medium text-ledger hover:underline">
                              {r.entry_status === 'draft' ? (perms.canPost ? 'Abrir y contabilizar' : 'Abrir el borrador') : 'Ver el asiento'}
                            </Link>
                          ) : p.status === 'open' && perms.canManage ? (
                            <Button
                              variant={isNext ? 'primary' : 'ghost'}
                              className="h-8"
                              busy={run.isPending && run.variables?.id === p.id}
                              disabled={run.isPending}
                              aria-label={`Calcular la depreciación de ${monthYear(p.start_date)}`}
                              onClick={() => (setHighlight(null), run.mutate(p))}
                            >
                              <Calculator size={15} aria-hidden />
                              {isNext ? `Calcular ${monthName(p.start_date).toLowerCase()}` : 'Calcular'}
                            </Button>
                          ) : null}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </Sheet>
          {!perms.canManage && <p className="mt-3 text-sm text-ink-3">{perms.manageReason}</p>}
        </>
      )}
    </>
  )
}
