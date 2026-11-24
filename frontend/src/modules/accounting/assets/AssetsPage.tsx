/**
 * Bienes de uso (D-057): lista con filtros por categoría, estado y texto, con costo,
 * depreciación acumulada contabilizada y valor neto contable de cada uno.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Badge, EmptyState, Input, Select, Sheet } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton, Th } from '../../finance/components'
import { formatBookDate } from '../../finance/labels'
import { sumPyg } from '../amounts'
import { Pyg, RuledTotal } from '../components'
import { accountingKeys, useAccountingPerms, useAssetCategories } from '../data'
import { monthYear } from '../labels'
import type { AssetStatus, FixedAsset } from '../types3b'

const linkButton =
  'inline-flex h-9 items-center gap-2 rounded-sm border border-transparent bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong focus-visible:outline-2 focus-visible:outline-offset-2'

export function AssetsPage() {
  const perms = useAccountingPerms()
  const [params, setParams] = useSearchParams()
  const categoryId = params.get('categoria') ?? ''
  const status = (params.get('estado') ?? 'active') as AssetStatus | 'all'
  const [text, setText] = useState(params.get('q') ?? '')
  const q = useDeferredValue(text.trim())
  const categories = useAssetCategories()
  const list = useQuery({
    queryKey: [...accountingKeys.assets(), categoryId, status, q],
    queryFn: () => get<FixedAsset[]>(`/accounting/fixed-assets${qs({ category_id: categoryId, status: status === 'all' ? undefined : status, q })}`),
    placeholderData: keepPreviousData,
  })
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const rows = list.data ?? []
  const filtered = Boolean(categoryId || q || status !== 'active')
  const usable = (categories.data ?? []).filter((c) => c.complete && !c.archived_at)
  const canCreate = perms.canManage && usable.length > 0

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3 rounded-md border border-line bg-surface p-3.5">
        <div className="relative w-72">
          <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
          <Input
            type="search"
            aria-label="Buscar bien"
            placeholder="Nombre, descripción o n° de serie"
            className="pl-9"
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              set('q', e.target.value.trim())
            }}
          />
        </div>
        <label className="flex w-64 flex-col gap-1 text-sm text-ink-2">
          Categoría
          <Select value={categoryId} onChange={(e) => set('categoria', e.target.value)}>
            <option value="">Todas</option>
            {(categories.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.archived_at ? ' (archivada)' : ''}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex w-40 flex-col gap-1 text-sm text-ink-2">
          Estado
          <Select value={status} onChange={(e) => set('estado', e.target.value === 'active' ? '' : e.target.value)}>
            <option value="active">En uso</option>
            <option value="disposed">Dados de baja</option>
            <option value="all">Todos</option>
          </Select>
        </label>
        {perms.canManage && (
          <div className="ml-auto">
            {canCreate ? (
              <Link to="/contabilidad/activos/nuevo" className={linkButton}>
                <Plus size={16} />
                Nuevo bien
              </Link>
            ) : (
              <p className="max-w-64 text-sm text-ink-3">Para dar de alta un bien, primero completá al menos una categoría.</p>
            )}
          </div>
        )}
      </div>

      <Sheet>
        {list.isPending ? (
          <TableSkeleton rows={5} cols={6} />
        ) : list.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={list.error} title="No se pudieron cargar los bienes." />
          </div>
        ) : rows.length === 0 ? (
          filtered ? (
            <EmptyState title="Ningún bien coincide con los filtros">
              Probá con otra categoría o estado, o borrá la búsqueda.{' '}
              <button type="button" className="font-medium text-ledger hover:underline" onClick={() => (setText(''), setParams({}, { replace: true }))}>
                Quitar los filtros
              </button>
            </EmptyState>
          ) : (
            <EmptyState
              title="Todavía no hay bienes de uso"
              action={
                canCreate ? (
                  <Link to="/contabilidad/activos/nuevo" className={linkButton}>
                    <Plus size={16} />
                    Dar de alta el primero
                  </Link>
                ) : perms.canManage ? (
                  <Link to="/contabilidad/activos/categorias" className="font-medium text-ledger hover:underline">
                    Cargar y completar las categorías
                  </Link>
                ) : null
              }
            >
              Registrá cada bien con su costo de adquisición y su categoría: el sistema calcula la cuota mensual de depreciación y arma el borrador de
              cada mes.
            </EmptyState>
          )
        ) : (
          <table className={cx('w-full', list.isFetching && 'opacity-70')} aria-label="Bienes de uso">
            <thead className="border-b border-line bg-sunken text-sm text-ink-2">
              <tr>
                <Th>Bien</Th>
                <Th className="w-48">Adquisición</Th>
                <Th align="right" className="w-36">
                  Costo
                </Th>
                <Th align="right" className="w-40">
                  Dep. acumulada
                </Th>
                <Th align="right" className="w-36">
                  Valor neto
                </Th>
                <Th className="w-32">Estado</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((a) => (
                <tr key={a.id} className="hover:bg-sunken/50">
                  <td className="px-4 py-2.5">
                    <Link to={`/contabilidad/activos/${a.id}`} className="font-medium hover:text-ledger hover:underline">
                      {a.name}
                    </Link>
                    <span className="block text-sm text-ink-3">
                      {a.category_name}
                      {a.serial_or_reference ? `, ref. ${a.serial_or_reference}` : ''}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 tabular-nums">
                    {formatBookDate(a.acquired_on)}
                    <span className="block text-sm text-ink-3">desde {monthYear(a.depreciation_start)}</span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Pyg value={a.cost} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Pyg value={a.accumulated_depreciation} muted />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Pyg value={a.net_book_value} strong />
                  </td>
                  <td className="px-4 py-2.5">{a.status === 'disposed' ? <Badge>De baja</Badge> : <Badge tone="ok">En uso</Badge>}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-line-strong">
              <tr>
                <td className="px-4 py-3 font-semibold" colSpan={2}>
                  {rows.length} {rows.length === 1 ? 'bien' : 'bienes'}
                </td>
                <td className="px-4 py-3 text-right">
                  <Pyg value={sumPyg(rows.map((r) => r.cost))} strong />
                </td>
                <td className="px-4 py-3 text-right">
                  <Pyg value={sumPyg(rows.map((r) => r.accumulated_depreciation))} strong />
                </td>
                <td className="px-4 py-3 text-right">
                  <RuledTotal value={sumPyg(rows.map((r) => r.net_book_value))} label="Total valor neto" />
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        )}
      </Sheet>
      <p className="mt-3 text-sm text-ink-3">La depreciación acumulada y el valor neto cuentan solo las cuotas contabilizadas; los borradores no.</p>
    </>
  )
}
