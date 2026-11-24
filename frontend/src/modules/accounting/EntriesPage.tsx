/** Asientos: listado con filtros en la URL y paginación por cursor. */
import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query'
import { Plus, Search, X } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, PageHeader, Select, Sheet } from '../../components/ui'
import { cx } from '../../lib/cx'
import { get, qs } from '../../services/api'
import { ApiErrorNotice, TableSkeleton, Th } from '../finance/components'
import { formatBookDate } from '../finance/labels'
import { postableAccounts } from './chartTree'
import { AccountCombobox, EntryStatusBadge, Pyg } from './components'
import { accountingKeys, useAccountingPerms, useAccountsById, useChart, useFiscalYears } from './data'
import { ENTRY_KIND_LABELS, STATUS_LABELS } from './labels'
import { RecurringDueBanner } from './recurring/RecurringDueBanner'
import type { Entry, EntryKind, EntryStatus } from './types'

const PAGE = 50
const FILTER_KEYS = ['fiscal_year_id', 'status', 'kind', 'from', 'to', 'account_id', 'q'] as const
type FilterKey = (typeof FILTER_KEYS)[number]

export function EntriesPage() {
  const perms = useAccountingPerms()
  const chart = useChart()
  const years = useFiscalYears()
  const byId = useAccountsById(chart.data?.accounts)
  const [params, setParams] = useSearchParams()
  const filter = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ''])) as Record<FilterKey, string>
  const [search, setSearch] = useState(filter.q)
  const q = useDeferredValue(search.trim())
  const setFilter = (key: FilterKey, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const query = { ...filter, q }
  const active = FILTER_KEYS.filter((k) => k !== 'q' && filter[k]).length + (q ? 1 : 0)

  const list = useInfiniteQuery({
    queryKey: [...accountingKeys.entries(), 'list', query],
    queryFn: ({ pageParam }) => get<Entry[]>(`/accounting/entries${qs({ ...query, limit: PAGE, before: pageParam })}`),
    initialPageParam: '' as string,
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].id : undefined),
    placeholderData: keepPreviousData,
  })
  const rows = list.data?.pages.flat() ?? []
  const hasYears = (years.data ?? []).length > 0
  const hasChart = (chart.data?.accounts ?? []).length > 0

  return (
    <>
      <PageHeader
        title="Asientos"
        description="El libro de asientos de la empresa. Un borrador se puede corregir; uno contabilizado no cambia nunca: se corrige con una reversión."
        actions={
          perms.canManage &&
          hasYears &&
          hasChart && (
            <Link to="/contabilidad/asientos/nuevo" className="inline-flex h-9 items-center gap-2 rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong">
              <Plus size={16} />
              Nuevo asiento
            </Link>
          )
        }
      />
      <RecurringDueBanner className="mb-5" />
      {!perms.canManage && <p className="-mt-3 mb-4 text-sm text-ink-3">{perms.manageReason}</p>}

      <form
        role="search"
        aria-label="Filtros de asientos"
        onSubmit={(e) => e.preventDefault()}
        className="mb-4 grid grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(0,1fr))] items-end gap-3 rounded-md border border-line bg-surface p-3.5"
      >
        <Field label="Buscar">
          {(p) => (
            <div className="relative">
              <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
              <Input
                {...p}
                type="search"
                placeholder="Descripción, comprobante o número"
                className="pl-9"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setFilter('q', e.target.value.trim())
                }}
              />
            </div>
          )}
        </Field>
        <Field label="Ejercicio">
          {(p) => (
            <Select {...p} value={filter.fiscal_year_id} onChange={(e) => setFilter('fiscal_year_id', e.target.value)}>
              <option value="">Todos</option>
              {(years.data ?? []).map((y) => (
                <option key={y.id} value={y.id}>
                  {y.start_date.slice(0, 4) === y.end_date.slice(0, 4) ? y.start_date.slice(0, 4) : `${formatBookDate(y.start_date)} – ${formatBookDate(y.end_date)}`}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Estado">
          {(p) => (
            <Select {...p} value={filter.status} onChange={(e) => setFilter('status', e.target.value)}>
              <option value="">Todos</option>
              {(Object.keys(STATUS_LABELS) as EntryStatus[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Tipo">
          {(p) => (
            <Select {...p} value={filter.kind} onChange={(e) => setFilter('kind', e.target.value)}>
              <option value="">Todos</option>
              {(Object.keys(ENTRY_KIND_LABELS) as EntryKind[]).map((k) => (
                <option key={k} value={k}>
                  {ENTRY_KIND_LABELS[k]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <div className="col-span-4 flex flex-wrap items-end gap-x-4 gap-y-3">
          <Field label="Desde">{(p) => <Input {...p} type="date" className="w-40" value={filter.from} onChange={(e) => setFilter('from', e.target.value)} />}</Field>
          <Field label="Hasta">{(p) => <Input {...p} type="date" className="w-40" value={filter.to} onChange={(e) => setFilter('to', e.target.value)} />}</Field>
          <div className="w-96">
            <Field label="Con la cuenta">
              {(p) => (
                <div className="flex gap-1">
                  <AccountCombobox {...p} className="flex-1" accounts={postableAccounts(chart.data?.accounts ?? [])} known={byId} value={filter.account_id} onChange={(id) => setFilter('account_id', id)} />
                  {filter.account_id && (
                    <Button type="button" variant="ghost" className="px-2" aria-label="Quitar el filtro de cuenta" onClick={() => setFilter('account_id', '')}>
                      <X size={15} />
                    </Button>
                  )}
                </div>
              )}
            </Field>
          </div>
          {active > 0 && (
            <Button
              type="button"
              variant="ghost"
              className="ml-auto"
              onClick={() => {
                setSearch('')
                setParams(new URLSearchParams(), { replace: true })
              }}
            >
              <X size={15} />
              Quitar filtros
            </Button>
          )}
        </div>
      </form>

      <Sheet>
        {list.isPending ? (
          <TableSkeleton rows={6} cols={5} />
        ) : list.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={list.error} title="No se pudieron cargar los asientos." />
          </div>
        ) : rows.length === 0 ? (
          active > 0 ? (
            <EmptyState title="Ningún asiento coincide con los filtros">Probá con otro rango de fechas o quitá algún filtro.</EmptyState>
          ) : !hasChart ? (
            <EmptyState title="Primero, el plan de cuentas" action={<Link className="font-medium text-ledger hover:underline" to="/contabilidad/plan">Ir al plan de cuentas</Link>}>
              Cada línea de un asiento va a una cuenta imputable del plan. Cargá el plan propuesto o armá el tuyo.
            </EmptyState>
          ) : !hasYears ? (
            <EmptyState title="Falta el ejercicio" action={<Link className="font-medium text-ledger hover:underline" to="/contabilidad/ejercicios">Ir a Ejercicios y períodos</Link>}>
              La fecha de cada asiento tiene que caer dentro de un ejercicio abierto. Creá el del año en curso.
            </EmptyState>
          ) : (
            <EmptyState
              title="Todavía no hay asientos"
              action={
                perms.canManage && (
                  <Link to="/contabilidad/asientos/nuevo" className="inline-flex h-9 items-center gap-2 rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong">
                    <Plus size={16} />
                    Cargar el primero
                  </Link>
                )
              }
            >
              Cargalos a mano o proponelos desde los movimientos de la empresa en Finanzas: cada movimiento arma un borrador que después se revisa y se
              contabiliza.
            </EmptyState>
          )
        ) : (
          <>
            <table className={cx('w-full table-fixed', list.isPlaceholderData && 'opacity-60')}>
              <colgroup>
                <col className="w-20" />
                <col className="w-28" />
                <col />
                <col className="w-36" />
                <col className="w-40" />
              </colgroup>
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>N°</Th>
                  <Th>Fecha</Th>
                  <Th>Descripción</Th>
                  <Th>Estado</Th>
                  <Th align="right">Importe</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((e) => (
                  <tr key={e.id} className={cx('relative align-top hover:bg-sunken/50', e.status === 'discarded' && 'text-ink-3')}>
                    <td className="px-4 py-3 font-semibold tabular-nums">{e.number ?? <span className="font-normal text-ink-3">—</span>}</td>
                    <td className="px-4 py-3 text-sm text-ink-2 tabular-nums">{formatBookDate(e.entry_date)}</td>
                    <td className="px-4 py-3">
                      <Link to={`/contabilidad/asientos/${e.id}`} className={cx('font-medium break-words after:absolute after:inset-0 hover:text-ledger', e.status === 'discarded' && 'line-through decoration-1')}>
                        {e.description}
                      </Link>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
                        {e.document_reference && <span>Comprobante {e.document_reference}</span>}
                        {e.kind !== 'manual' && <Badge>{ENTRY_KIND_LABELS[e.kind]}</Badge>}
                        {e.status === 'draft' && !e.balanced && <Badge tone="warn">No balancea</Badge>}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <EntryStatusBadge status={e.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Pyg value={e.total_debit} symbol strong={e.status === 'posted'} muted={e.status === 'discarded'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-2">
              <span>
                {rows.length} {rows.length === 1 ? 'asiento' : 'asientos'}
                {list.hasNextPage ? ' cargados' : ''}
              </span>
              {list.hasNextPage && (
                <Button variant="secondary" busy={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
                  Cargar anteriores
                </Button>
              )}
            </div>
          </>
        )}
      </Sheet>
    </>
  )
}
