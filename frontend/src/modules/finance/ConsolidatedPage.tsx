/**
 * Vista consolidada (BR-FIN-02): cada importe con su contexto identificado. No existe un
 * total que mezcle la empresa con lo personal, ni monedas distintas.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { EmptyState, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { cx } from '../../lib/cx'
import { CURRENCY_NAMES } from '../../lib/money'
import { get, qs } from '../../services/api'
import { useSession } from '../../stores/session'
import { Amount, ApiErrorNotice, ContextTag, Th } from './components'
import { financeKeys } from './data'
import { ContextSwitcher } from './FinanceLayout'
import { formatBookDate } from './labels'
import { usePeriodParams } from './period'
import { PeriodPicker } from './SummaryPage'
import type { Consolidated } from './types'

export function ConsolidatedPage() {
  const { me } = useSession()
  const { from, to, set } = usePeriodParams()
  const data = useQuery({
    queryKey: [...financeKeys.consolidated(), from, to],
    queryFn: () => get<Consolidated>(`/finance/summary/consolidated${qs({ from, to })}`),
    placeholderData: keepPreviousData,
  })
  const org = me?.organization.trade_name ?? me?.organization.legal_name

  return (
    <>
      <div className="mb-7">
        <ContextSwitcher current="consolidado" />
        <div role="note" aria-label="Contexto activo" className="rounded-b-md border border-t-0 border-line bg-sunken px-4 py-2.5 text-sm">
          <span className="font-semibold">Vista consolidada</span>
          <span className="ml-3 text-ink-2">
            Cada importe dice de qué contexto es. La empresa y lo personal no se suman entre sí, ni las monedas entre ellas.
          </span>
        </div>
      </div>
      <PageHeader
        title="Consolidado"
        description={
          data.data
            ? `Del ${formatBookDate(data.data.date_from)} al ${formatBookDate(data.data.date_to)}. Saldos al ${formatBookDate(data.data.date_to)}.`
            : 'Todo lo que ves, lado a lado y separado por contexto.'
        }
      />
      <div className="mb-6">
        <PeriodPicker from={from} to={to} onChange={set} />
      </div>
      {data.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : data.isError ? (
        <ApiErrorNotice error={data.error} title="No se pudo armar el consolidado." />
      ) : (
        <div className={cx('flex flex-col gap-6', data.isPlaceholderData && 'opacity-60')}>
          {data.data.contexts.map(({ context, totals }) => (
            <Sheet key={context.id} className={cx('border-l-4', context.kind === 'personal' ? 'border-l-personal' : 'border-l-ledger')}>
              <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-3.5">
                <div className="flex items-center gap-3">
                  <ContextTag context={context} size="md" />
                  <h2 className="font-semibold">{context.kind === 'business' ? org : 'Tus finanzas personales'}</h2>
                </div>
                <Link to={`/finanzas/${context.id}`} className="text-sm font-medium text-ledger hover:underline">
                  Abrir {context.kind === 'business' ? 'Empresa' : 'Personal'}
                </Link>
              </header>
              {totals.length === 0 ? (
                <EmptyState title="Sin cuentas ni movimientos todavía" />
              ) : (
                <table className="w-full">
                  <caption className="sr-only">
                    Totales de {context.kind === 'business' ? 'la empresa' : 'tus finanzas personales'} por moneda
                  </caption>
                  <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                    <tr>
                      <Th>Moneda</Th>
                      <Th align="right">Entradas</Th>
                      <Th align="right">Salidas</Th>
                      <Th align="right">Neto</Th>
                      <Th align="right">Saldo en cuentas</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {totals.map((t) => (
                      <tr key={t.currency}>
                        <th scope="row" className="px-4 py-3 text-left font-medium">
                          {CURRENCY_NAMES[t.currency] ?? t.currency}
                        </th>
                        <td className="px-4 py-3 text-right">
                          <Amount value={t.income} currency={t.currency} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Amount value={t.expense} currency={t.currency} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Amount value={t.net} currency={t.currency} flow />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Amount value={t.balance} currency={t.currency} strong />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Sheet>
          ))}
        </div>
      )}
    </>
  )
}
