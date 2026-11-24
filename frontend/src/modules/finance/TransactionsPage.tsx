import { keepPreviousData, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftRight, Ban, Check as CheckIcon, FileUp, Pencil, Plus, Search, X } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, PageHeader, Sheet } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime } from '../../lib/format'
import { get, patch, qs } from '../../services/api'
import { Amount, ApiErrorNotice, Check, TableSkeleton, Th } from './components'
import { errorMessage } from './forms'
import { financeKeys, useAccounts, useCategories, useCounterparties, useFinance } from './data'
import { categoryLabel, formatBookDate } from './labels'
import { AccountSelect, CategorySelect, CounterpartySelect } from './pickers'
import { TransactionForm, TransferForm, VoidForm } from './TransactionForms'
import type { Transaction } from './types'

const PAGE = 50
const FILTER_KEYS = ['account_id', 'category_id', 'counterparty_id', 'from', 'to', 'q', 'unreviewed', 'include_voided'] as const

type Dialog = { kind: 'new' } | { kind: 'transfer' } | { kind: 'edit'; tx: Transaction } | { kind: 'void'; tx: Transaction }

export function TransactionsPage() {
  const { cid, canWrite, readOnlyReason } = useFinance()
  const qc = useQueryClient()
  const toast = useToast()
  const accounts = useAccounts(cid)
  const categories = useCategories(cid)
  const counterparties = useCounterparties(cid)
  // Los filtros viven en la URL: recargar o compartir el enlace los conserva.
  const [params, setParams] = useSearchParams()
  const filter = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ''])) as Record<(typeof FILTER_KEYS)[number], string>
  const [search, setSearch] = useState(filter.q)
  const q = useDeferredValue(search.trim())
  const [dialog, setDialog] = useState<Dialog | null>(null)

  const setFilter = (key: (typeof FILTER_KEYS)[number], value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const activeFilters = FILTER_KEYS.filter((k) => k !== 'q' && filter[k]).length + (q ? 1 : 0)

  const query = { ...filter, q, unreviewed: filter.unreviewed === '1', include_voided: filter.include_voided === '1' }
  const list = useInfiniteQuery({
    queryKey: [...financeKeys.transactions(cid), 'list', query],
    queryFn: ({ pageParam }) => get<Transaction[]>(`/finance/contexts/${cid}/transactions${qs({ ...query, limit: PAGE, before: pageParam })}`),
    initialPageParam: '' as string,
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].id : undefined),
    placeholderData: keepPreviousData,
  })

  const quick = useMutation({
    mutationFn: ({ tx, body }: { tx: Transaction; body: { category_id?: string | null; reviewed?: boolean } }) =>
      patch<Transaction>(`/finance/contexts/${cid}/transactions/${tx.id}`, body),
    onSuccess: (_tx, { body }) => {
      qc.invalidateQueries({ queryKey: financeKeys.context(cid) })
      qc.invalidateQueries({ queryKey: financeKeys.consolidated() })
      toast('ok', body.reviewed ? 'Movimiento marcado como revisado.' : 'Categoría actualizada.')
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo actualizar el movimiento.')),
  })

  const rows = list.data?.pages.flat() ?? []
  const accountsById = new Map((accounts.data ?? []).map((a) => [a.id, a]))
  const cpById = new Map((counterparties.data ?? []).map((c) => [c.id, c]))
  const hasAccounts = (accounts.data ?? []).some((a) => !a.archived_at)
  const close = () => setDialog(null)

  return (
    <>
      <PageHeader
        title="Movimientos"
        description="Todo lo que entra y sale de tus cuentas. Positivo entra, negativo sale. Nada se borra: lo que está mal se anula con un motivo."
        actions={
          canWrite &&
          hasAccounts && (
            <>
              <Button variant="secondary" onClick={() => setDialog({ kind: 'transfer' })}>
                <ArrowLeftRight size={16} />
                Transferencia
              </Button>
              <Button onClick={() => setDialog({ kind: 'new' })}>
                <Plus size={16} />
                Nuevo movimiento
              </Button>
            </>
          )
        }
      />
      {!canWrite && <p className="-mt-3 mb-4 text-sm text-ink-3">{readOnlyReason}</p>}

      <form
        role="search"
        aria-label="Filtros de movimientos"
        onSubmit={(e) => e.preventDefault()}
        className="mb-4 grid grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))] items-end gap-3 rounded-md border border-line bg-surface p-3.5"
      >
        <Field label="Buscar">
          {(p) => (
            <div className="relative">
              <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
              <Input
                {...p}
                type="search"
                placeholder="Descripción o referencia"
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
        <Field label="Cuenta">
          {(p) => <AccountSelect {...p} empty="Todas" accounts={accounts.data ?? []} value={filter.account_id} onChange={(e) => setFilter('account_id', e.target.value)} />}
        </Field>
        <Field label="Categoría">
          {(p) => (
            <CategorySelect {...p} empty="Todas" categories={categories.data ?? []} value={filter.category_id} onChange={(e) => setFilter('category_id', e.target.value)} />
          )}
        </Field>
        <Field label="Contraparte">
          {(p) => (
            <CounterpartySelect
              {...p}
              empty="Todas"
              counterparties={counterparties.data ?? []}
              value={filter.counterparty_id}
              onChange={(e) => setFilter('counterparty_id', e.target.value)}
            />
          )}
        </Field>
        <div className="col-span-4 flex flex-wrap items-end gap-x-5 gap-y-3">
          <Field label="Desde">
            {(p) => <Input {...p} type="date" className="w-40" value={filter.from} onChange={(e) => setFilter('from', e.target.value)} />}
          </Field>
          <Field label="Hasta">
            {(p) => <Input {...p} type="date" className="w-40" value={filter.to} onChange={(e) => setFilter('to', e.target.value)} />}
          </Field>
          <div className="flex h-9 items-center gap-5">
            <Check label="Solo sin revisar" checked={filter.unreviewed === '1'} onChange={(v) => setFilter('unreviewed', v ? '1' : '')} />
            <Check label="Incluir anulados" checked={filter.include_voided === '1'} onChange={(v) => setFilter('include_voided', v ? '1' : '')} />
          </div>
          {activeFilters > 0 && (
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
        {list.isPending || accounts.isPending ? (
          <TableSkeleton rows={6} cols={5} />
        ) : list.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={list.error} title="No se pudieron cargar los movimientos." />
          </div>
        ) : !hasAccounts && rows.length === 0 ? (
          <EmptyState
            title="Primero creá una cuenta"
            action={
              <Link to={`/finanzas/${cid}/cuentas`} className="font-medium text-ledger hover:underline">
                Ir a Cuentas
              </Link>
            }
          >
            Los movimientos siempre pertenecen a una cuenta: el banco, la caja o la tarjeta.
          </EmptyState>
        ) : rows.length === 0 ? (
          activeFilters > 0 ? (
            <EmptyState title="Ningún movimiento coincide con los filtros">Probá con otro período o quitá algún filtro.</EmptyState>
          ) : (
            <EmptyState
              title="Todavía no hay movimientos"
              action={
                canWrite && (
                  <div className="flex gap-2">
                    <Button onClick={() => setDialog({ kind: 'new' })}>
                      <Plus size={16} />
                      Cargar el primero
                    </Button>
                    <Link
                      to={`/finanzas/${cid}/importar`}
                      className="inline-flex h-9 items-center gap-2 rounded-sm border border-line-strong px-3.5 font-medium hover:bg-sunken"
                    >
                      <FileUp size={16} />
                      Importar un extracto
                    </Link>
                  </div>
                )
              }
            >
              Cargalos a mano o importá el extracto del banco en CSV o Excel.
            </EmptyState>
          )
        ) : (
          <>
            <table className={cx('w-full table-fixed', list.isPlaceholderData && 'opacity-60')}>
              <colgroup>
                <col className="w-26" />
                <col />
                <col className="w-56" />
                <col className="w-40" />
                {canWrite && <col className="w-34" />}
              </colgroup>
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>Fecha</Th>
                  <Th>Descripción</Th>
                  <Th>Categoría</Th>
                  <Th align="right">Importe</Th>
                  {canWrite && (
                    <Th>
                      <span className="sr-only">Acciones</span>
                    </Th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((tx) => {
                  const voided = Boolean(tx.voided_at)
                  const account = accountsById.get(tx.account_id)
                  const cp = tx.counterparty_id ? cpById.get(tx.counterparty_id) : undefined
                  const editable = canWrite && !voided
                  return (
                    <tr key={tx.id} className={cx('align-top', voided && 'bg-sunken/50 text-ink-3')}>
                      <td className={cx('px-4 py-3 text-sm tabular-nums', voided ? 'text-ink-3' : 'text-ink-2')}>{formatBookDate(tx.booked_on)}</td>
                      <td className="px-4 py-3">
                        <p className={cx('break-words', voided ? 'line-through decoration-1' : 'font-medium')}>{tx.description}</p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
                          <span>{account?.name ?? 'Cuenta'}</span>
                          {cp && <span>· {cp.name}</span>}
                          {tx.reference && <span>· Ref. {tx.reference}</span>}
                          {tx.transfer_group_id && <Badge>Transferencia</Badge>}
                          {tx.source === 'import' && <Badge>Importado</Badge>}
                          {!tx.reviewed_at && !voided && <Badge tone="warn">Sin revisar</Badge>}
                          {voided && <Badge tone="bad">Anulado</Badge>}
                        </p>
                        {voided && (
                          <p className="mt-1 text-sm text-ink-2">
                            Motivo: {tx.void_reason} <span className="text-ink-3">({formatDateTime(tx.voided_at as string)})</span>
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {tx.transfer_group_id ? (
                          <span className="text-ink-3">No aplica</span>
                        ) : editable ? (
                          <CategorySelect
                            aria-label={`Categoría de ${tx.description}`}
                            className="-ml-2 h-8 border-transparent bg-transparent px-2 text-sm hover:border-line-strong hover:bg-surface"
                            categories={categories.data ?? []}
                            first={tx.amount.startsWith('-') ? 'expense' : 'income'}
                            value={tx.category_id ?? ''}
                            disabled={quick.isPending}
                            onChange={(e) => quick.mutate({ tx, body: { category_id: e.target.value || null } })}
                          />
                        ) : (
                          (categoryLabel(categories.data ?? [], tx.category_id) ?? <span className="text-ink-3">Sin categoría</span>)
                        )}
                      </td>
                      <td className={cx('px-4 py-3 text-right', voided && 'line-through decoration-1 opacity-70')}>
                        <Amount value={tx.amount} currency={tx.currency} flow strong={!voided} />
                      </td>
                      {canWrite && (
                        <td className="px-2 py-2.5">
                          {!voided && (
                            <div className="flex justify-end gap-0.5">
                              {!tx.reviewed_at && (
                                <Button
                                  variant="ghost"
                                  className="h-8 px-2 text-ledger"
                                  aria-label={`Marcar revisado: ${tx.description}`}
                                  title="Marcar revisado"
                                  disabled={quick.isPending}
                                  onClick={() => quick.mutate({ tx, body: { reviewed: true } })}
                                >
                                  <CheckIcon size={15} />
                                </Button>
                              )}
                              <Button variant="ghost" className="h-8 px-2" aria-label={`Editar: ${tx.description}`} title="Editar" onClick={() => setDialog({ kind: 'edit', tx })}>
                                <Pencil size={15} />
                              </Button>
                              <Button
                                variant="ghost"
                                className="h-8 px-2 hover:text-debit"
                                aria-label={`Anular: ${tx.description}`}
                                title="Anular"
                                onClick={() => setDialog({ kind: 'void', tx })}
                              >
                                <Ban size={15} />
                              </Button>
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-2">
              <span>
                {rows.length} {rows.length === 1 ? 'movimiento' : 'movimientos'}
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

      <Modal open={dialog?.kind === 'new' || dialog?.kind === 'edit'} size="lg" title={dialog?.kind === 'edit' ? 'Editar movimiento' : 'Nuevo movimiento'} onClose={close}>
        {(dialog?.kind === 'new' || dialog?.kind === 'edit') && (
          <TransactionForm
            key={dialog.kind === 'edit' ? dialog.tx.id : 'new'}
            transaction={dialog.kind === 'edit' ? dialog.tx : undefined}
            accounts={accounts.data ?? []}
            categories={categories.data ?? []}
            counterparties={counterparties.data ?? []}
            onDone={close}
          />
        )}
      </Modal>
      <Modal open={dialog?.kind === 'void'} title="Anular movimiento" onClose={close}>
        {dialog?.kind === 'void' && <VoidForm key={dialog.tx.id} transaction={dialog.tx} onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'transfer'} size="lg" title="Transferencia entre cuentas propias" onClose={close}>
        {dialog?.kind === 'transfer' && <TransferForm accounts={accounts.data ?? []} onDone={close} />}
      </Modal>
    </>
  )
}
