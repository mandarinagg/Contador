import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { EmptyState, Input, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { cx } from '../../lib/cx'
import { CURRENCY_NAMES } from '../../lib/money'
import { get, qs } from '../../services/api'
import { CategoryBars, MonthlyFlowChart } from './charts'
import { Amount, ApiErrorNotice } from './components'
import { financeKeys, useCategories, useFinance } from './data'
import { categoryLabel, formatBookDate, todayIso } from './labels'
import { detectPreset, type PeriodPreset, presetRange, usePeriodParams } from './period'
import type { Consolidated, Summary } from './types'

/** Selector de período: los 12 meses de la API, este año, el anterior o fechas a mano. Vive en la URL. */
export function PeriodPicker({ from, to, onChange }: { from: string; to: string; onChange: (from: string, to: string) => void }) {
  const today = todayIso()
  const preset = detectPreset(from, to, today)
  const options: [PeriodPreset, string][] = [
    ['default', 'Últimos 12 meses'],
    ['this-year', 'Este año'],
    ['last-year', 'Año anterior'],
  ]
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div role="group" aria-label="Período" className="flex rounded-sm border border-line-strong bg-surface p-0.5">
        {options.map(([p, label]) => (
          <button
            key={p}
            type="button"
            aria-pressed={preset === p}
            onClick={() => {
              const r = presetRange(p, today)
              onChange(r?.from ?? '', r?.to ?? '')
            }}
            className={cx('rounded-[3px] px-3 py-1.5 text-sm', preset === p ? 'bg-ledger-soft font-semibold text-ledger' : 'text-ink-2 hover:bg-sunken')}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm text-ink-2">
        Desde
        <Input type="date" className="h-8 w-38" value={from} max={to || undefined} onChange={(e) => onChange(e.target.value, to)} />
      </label>
      <label className="flex items-center gap-2 text-sm text-ink-2">
        Hasta
        <Input type="date" className="h-8 w-38" value={to} min={from || undefined} onChange={(e) => onChange(from, e.target.value)} />
      </label>
    </div>
  )
}

function Figure({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tracking-tight">{children}</dd>
      {hint && <dd className="text-xs text-ink-3">{hint}</dd>}
    </div>
  )
}

export function SummaryPage() {
  const { cid, canWrite } = useFinance()
  const { from, to, set } = usePeriodParams()
  const range = qs({ from, to })
  const summary = useQuery({
    queryKey: [...financeKeys.summary(cid), from, to],
    queryFn: () => get<Summary>(`/finance/contexts/${cid}/summary${range}`),
    placeholderData: keepPreviousData,
  })
  // El saldo total por moneda del contexto lo calcula la API (consolidado): acá no se suma nada.
  const consolidated = useQuery({
    queryKey: [...financeKeys.consolidated(), from, to],
    queryFn: () => get<Consolidated>(`/finance/summary/consolidated${range}`),
    placeholderData: keepPreviousData,
  })
  const categories = useCategories(cid)
  const data = summary.data
  const ownTotals = consolidated.data?.contexts.find((c) => c.context.id === cid)?.totals ?? []
  const currencies = data
    ? [...new Set([...data.balances.filter((b) => !b.archived).map((b) => b.currency), ...data.totals.map((t) => t.currency)])].sort((a, b) =>
        a === 'PYG' ? -1 : b === 'PYG' ? 1 : a.localeCompare(b),
      )
    : []

  return (
    <>
      <PageHeader
        title="Resumen"
        description={
          data ? `Del ${formatBookDate(data.date_from)} al ${formatBookDate(data.date_to)}. Sin anulados ni transferencias entre cuentas propias.` : 'Saldos, entradas y salidas del período.'
        }
      />
      <div className="mb-6">
        <PeriodPicker from={from} to={to} onChange={set} />
      </div>
      {summary.isPending ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : summary.isError ? (
        <ApiErrorNotice error={summary.error} title="No se pudo armar el resumen." />
      ) : data && data.balances.length === 0 ? (
        <Sheet>
          <EmptyState
            title="Todavía no hay cuentas. Creá la primera"
            action={
              canWrite && (
                <Link to={`/finanzas/${cid}/cuentas`} className="inline-flex h-9 items-center gap-2 rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong">
                  <Plus size={16} />
                  Crear una cuenta
                </Link>
              )
            }
          >
            El resumen se arma con tus cuentas y sus movimientos: saldos, lo que entra, lo que sale y en qué se va.
          </EmptyState>
        </Sheet>
      ) : (
        data && (
          <div className={cx('flex flex-col gap-10', summary.isPlaceholderData && 'opacity-60')}>
            {currencies.map((currency) => {
              const totals = data.totals.find((t) => t.currency === currency)
              const balance = ownTotals.find((t) => t.currency === currency)?.balance
              const months = data.by_month.filter((m) => m.currency === currency)
              const expenses = data.expenses_by_category.filter((e) => e.currency === currency)
              const accounts = data.balances.filter((b) => b.currency === currency && !b.archived)
              return (
                <section key={currency} aria-labelledby={`moneda-${currency}`}>
                  <h2 id={`moneda-${currency}`} className="ledger-rule mb-4 flex items-baseline justify-between text-md font-semibold">
                    {CURRENCY_NAMES[currency] ?? currency}
                    <span className="text-sm font-normal text-ink-3">Importes solo en {currency}: nunca se suman con otras monedas</span>
                  </h2>
                  <div className="grid grid-cols-[1fr_17rem] gap-6">
                    <div className="flex flex-col gap-6">
                      <Sheet className="p-5">
                        <dl className="grid grid-cols-4 gap-4">
                          <Figure label="Saldo en cuentas" hint={`al ${formatBookDate(data.date_to)}`}>
                            {balance ? <Amount value={balance} currency={currency} /> : <Skeleton className="h-7 w-24" />}
                          </Figure>
                          <Figure label="Entradas">
                            <Amount value={totals?.income ?? '0'} currency={currency} />
                          </Figure>
                          <Figure label="Salidas">
                            <Amount value={totals?.expense ?? '0'} currency={currency} />
                          </Figure>
                          <Figure label="Neto del período">
                            <Amount value={totals?.net ?? '0'} currency={currency} flow />
                          </Figure>
                        </dl>
                      </Sheet>
                      <Sheet className="p-5">
                        <h3 className="mb-3 font-semibold">Entradas y salidas por mes</h3>
                        {months.length === 0 ? (
                          <p className="py-6 text-ink-2">Sin movimientos en {currency} en este período.</p>
                        ) : (
                          <MonthlyFlowChart rows={months} currency={currency} from={data.date_from} to={data.date_to} />
                        )}
                      </Sheet>
                      <Sheet className="p-5">
                        <h3 className="mb-3 font-semibold">En qué se fue la plata</h3>
                        {expenses.length === 0 ? (
                          <p className="py-4 text-ink-2">Sin salidas en {currency} en este período.</p>
                        ) : (
                          <CategoryBars
                            currency={currency}
                            rows={expenses.map((e) => ({
                              key: e.category_id ?? 'none',
                              label: categoryLabel(categories.data ?? [], e.category_id) ?? e.category_name,
                              amount: e.amount,
                            }))}
                          />
                        )}
                      </Sheet>
                    </div>
                    <Sheet className="self-start">
                      <h3 className="border-b border-line px-4 py-3 font-semibold">Saldo por cuenta</h3>
                      {accounts.length === 0 ? (
                        <p className="px-4 py-4 text-sm text-ink-2">Sin cuentas activas en {currency}.</p>
                      ) : (
                        <ul className="divide-y divide-line">
                          {accounts.map((b) => (
                            <li key={b.account_id} className="flex items-baseline justify-between gap-3 px-4 py-2.5">
                              <Link
                                to={`/finanzas/${cid}/movimientos?account_id=${b.account_id}`}
                                className="min-w-0 truncate text-ink hover:text-ledger hover:underline"
                              >
                                {b.name}
                              </Link>
                              <Amount value={b.balance} currency={currency} className="text-sm font-medium" />
                            </li>
                          ))}
                        </ul>
                      )}
                    </Sheet>
                  </div>
                </section>
              )
            })}
          </div>
        )
      )}
    </>
  )
}
