/**
 * Cuadro de depreciación del ejercicio con las columnas del Anexo de la RG 77/2020 (D-067):
 * bienes (1-4), fiscal (5-13) y contable (14-22), agrupado por categoría, con el control de que
 * el valor contable neto (col. 22) concilia con el balance y las advertencias de la API.
 */
import { useQuery } from '@tanstack/react-query'
import { CircleAlert, CircleCheck } from 'lucide-react'
import { Fragment } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Badge, EmptyState, Notice, Select } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney, isZeroAmount } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton } from '../../finance/components'
import { formatBookDate, todayIso } from '../../finance/labels'
import { Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys, useFiscalYears } from '../data'
import { rangeText } from '../labels'
import { ReportSheet } from '../reports/common'
import { ReportActions } from '../reports/ReportActions'
import type { DepreciationSchedule, ScheduleRow, ScheduleTotals } from '../types3b'
import { ACCOUNTING_COLS, COMMON_COLS, type Col, FISCAL_COLS } from './scheduleColumns'

type View = 'fiscal' | 'accounting'
const yearLabel = (y: { start_date: string; end_date: string }) =>
  y.start_date.slice(0, 4) === y.end_date.slice(0, 4) ? y.start_date.slice(0, 4) : `${y.start_date.slice(0, 4)}/${y.end_date.slice(0, 4)}`

const stickyCell = 'sticky left-0 z-10 bg-surface'

function Cells({ cols, row, totals, strong }: { cols: Col[]; row?: ScheduleRow; totals?: ScheduleTotals; strong?: boolean }) {
  return (
    <>
      {cols.map((c) => (
        <td key={c.n} className="px-2.5 py-1.5 text-right whitespace-nowrap tabular-nums">
          {c.money ? (
            (() => {
              const v = row ? row[c.money] : totals?.[c.money]
              if (v === undefined) return null
              return isZeroAmount(v) && !strong ? <span className="text-ink-3">0</span> : <Pyg value={v} strong={strong} />
            })()
          ) : row && c.render ? (
            c.render(row)
          ) : null}
        </td>
      ))}
    </>
  )
}

function Reconciliation({ data }: { data: DepreciationSchedule }) {
  const r = data.reconciliation
  return (
    <section aria-labelledby="conciliacion" className="avoid-break border-t border-line px-6 py-5">
      <div className="flex items-start gap-3">
        {r.reconciled ? <CircleCheck size={20} className="mt-0.5 shrink-0 text-ledger" aria-hidden /> : <CircleAlert size={20} className="mt-0.5 shrink-0 text-debit" aria-hidden />}
        <div className="min-w-0 flex-1">
          <h3 id="conciliacion" className="font-semibold">
            {r.reconciled ? 'Concilia con el balance' : 'No concilia con el balance'}
          </h3>
          <p className="mt-0.5 text-sm text-ink-2">
            El valor contable neto al cierre (columna 22) tiene que ser igual al saldo de las cuentas de bienes menos sus depreciaciones acumuladas al{' '}
            {formatBookDate(data.date_to)}.
            {!r.reconciled &&
              ' La diferencia suele ser una compra registrada en otra cuenta, un bien sin dar de alta o una depreciación cargada a mano: revisá el mayor de la cuenta.'}
          </p>
          {r.lines.length > 0 && (
            <table className="mt-3 w-full max-w-3xl text-sm" aria-label="Conciliación por cuenta">
              <thead className="text-ink-2">
                <tr className="border-b border-line">
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Cuenta
                  </th>
                  <th scope="col" className="w-36 py-1.5 pl-3 text-right font-medium">
                    Saldo en el mayor
                  </th>
                  <th scope="col" className="w-36 py-1.5 pl-3 text-right font-medium">
                    Según el cuadro
                  </th>
                  <th scope="col" className="w-32 py-1.5 pl-3 text-right font-medium">
                    Diferencia
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {r.lines.map((l) => (
                  <tr key={l.account_id}>
                    <td className="py-1.5 pr-3">
                      <Link to={`/contabilidad/reportes/mayor${qs({ account_id: l.account_id, from: data.date_from, to: data.date_to })}`} className="hover:text-ledger hover:underline">
                        <span className="mr-2 text-ink-2 tabular-nums">{l.code}</span>
                        {l.name}
                      </Link>
                    </td>
                    <td className="py-1.5 pl-3 text-right">
                      <Pyg value={l.ledger_balance} />
                    </td>
                    <td className="py-1.5 pl-3 text-right">
                      <Pyg value={l.schedule_amount} />
                    </td>
                    <td className={cx('py-1.5 pl-3 text-right', !isZeroAmount(l.difference) && 'font-semibold text-debit')}>
                      {isZeroAmount(l.difference) ? <span className="text-ink-3">0</span> : formatMoney(l.difference, 'PYG')}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-line-strong">
                  <td className="py-2 pr-3 font-semibold">Total</td>
                  <td className="py-2 pl-3 text-right">
                    <RuledTotal value={r.ledger_total} label={`Saldo neto en el mayor ${formatMoney(r.ledger_total, 'PYG')}`} />
                  </td>
                  <td className="py-2 pl-3 text-right">
                    <RuledTotal value={r.schedule_total} label={`Neto según el cuadro ${formatMoney(r.schedule_total, 'PYG')}`} />
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      </div>
    </section>
  )
}

export function SchedulePage() {
  const fiscalYears = useFiscalYears()
  const [params, setParams] = useSearchParams()
  const view: View = params.get('vista') === 'contable' ? 'accounting' : 'fiscal'
  const list = [...(fiscalYears.data ?? [])].sort((a, b) => b.start_date.localeCompare(a.start_date))
  const today = todayIso()
  const year = list.find((y) => y.id === params.get('ejercicio')) ?? list.find((y) => y.start_date <= today && today <= y.end_date) ?? list[0]
  const report = useQuery({
    enabled: Boolean(year),
    queryKey: [...accountingKeys.reports(), 'depreciation-schedule', year?.id],
    queryFn: () => get<DepreciationSchedule>(`/accounting/reports/depreciation-schedule?fiscal_year_id=${year?.id}`),
  })
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const data = report.data
  const cols = [...COMMON_COLS, ...(view === 'fiscal' ? FISCAL_COLS : ACCOUNTING_COLS)]
  const assetCount = data?.categories.reduce((n, c) => n + c.assets.length, 0) ?? 0
  const width = cols.length + 1

  if (fiscalYears.isPending) return <TableSkeleton rows={6} cols={6} />
  if (list.length === 0)
    return (
      <EmptyState
        title="Todavía no hay ejercicios"
        action={
          <Link to="/contabilidad/ejercicios" className="font-medium text-ledger hover:underline">
            Crear el ejercicio
          </Link>
        }
      >
        El cuadro de depreciación es anual: se arma por ejercicio contable.
      </EmptyState>
    )

  return (
    <>
      <form aria-label="Alcance del reporte" className="mb-4 flex flex-wrap items-end gap-x-6 gap-y-3" onSubmit={(e) => e.preventDefault()}>
        <label className="flex w-48 flex-col gap-1 text-sm text-ink-2">
          Ejercicio
          <Select value={year?.id} onChange={(e) => set('ejercicio', e.target.value)}>
            {list.map((y) => (
              <option key={y.id} value={y.id}>
                {yearLabel(y)}
                {y.status === 'closed' ? ' (cerrado)' : ''}
              </option>
            ))}
          </Select>
        </label>
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-sm text-ink-2">Columnas</legend>
          <div className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
            {(
              [
                ['fiscal', 'Fiscal (1 a 13)'],
                ['accounting', 'Contable (14 a 22)'],
              ] as const
            ).map(([v, label]) => (
              <label
                key={v}
                className={cx(
                  'cursor-pointer rounded-sm px-3 py-1 text-sm has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
                  view === v ? 'bg-ledger text-surface' : 'text-ink-2 hover:text-ink',
                )}
              >
                <input type="radio" name="vista" className="sr-only" checked={view === v} onChange={() => set('vista', v === 'accounting' ? 'contable' : '')} />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
      </form>

      <ReportSheet className="print-landscape print-dense">
        {report.isPending ? (
          <TableSkeleton rows={6} cols={6} />
        ) : report.isError || !data ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo armar el cuadro de depreciación." />
          </div>
        ) : (
          <>
            <ReportHeading
              title={`Cuadro de depreciación ${view === 'fiscal' ? 'fiscal' : 'contable'} del ejercicio ${year ? yearLabel(year) : ''}`}
              scope={`Columnas del Anexo de la RG 77/2020, ${rangeText(data.date_from, data.date_to)}`}
              status={data.chart_status}
              aside={<ReportActions path={`/accounting/reports/depreciation-schedule?fiscal_year_id=${data.fiscal_year_id}`} report="depreciation-schedule" scope={{ from: year?.start_date, to: year?.end_date }} disabled={assetCount === 0} />}
            />
            {data.warnings.length > 0 && (
              <div className="border-b border-line px-6 py-4">
                <Notice tone="warn" title="Antes de presentarlo">
                  <ul className="list-disc pl-4">
                    {data.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </Notice>
              </div>
            )}
            {assetCount === 0 ? (
              <EmptyState
                title="Sin bienes en este ejercicio"
                action={
                  <Link to="/contabilidad/activos" className="font-medium text-ledger hover:underline" data-print="hide">
                    Ir a los bienes
                  </Link>
                }
              >
                El cuadro incluye los bienes en uso durante el ejercicio y los dados de baja en él.
              </EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[72rem] text-sm" aria-label={`Cuadro de depreciación, vista ${view === 'fiscal' ? 'fiscal' : 'contable'}`}>
                  <thead className="border-b border-line bg-sunken align-bottom text-xs text-ink-2">
                    <tr>
                      <th scope="col" className={cx(stickyCell, 'min-w-56 bg-sunken px-3 py-2 text-left font-medium')}>
                        <span className="block tabular-nums text-ink-3">1</span>
                        Descripción del bien
                      </th>
                      {cols.map((c) => (
                        <th key={c.n} scope="col" className={cx('px-2.5 py-2 text-right font-medium', c.money ? 'min-w-28' : 'min-w-20', c.n === 20 && 'text-amber')}>
                          <span className="block tabular-nums text-ink-3">{c.n}</span>
                          {c.title}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  {data.categories.map((g) => (
                    <Fragment key={g.category_id}>
                      <tbody className="divide-y divide-line">
                        <tr className="bg-sunken/50">
                          <th scope="rowgroup" colSpan={width} className="px-3 py-1.5 text-left">
                            <span className="sticky left-3 inline-flex items-center gap-2">
                              <span className="font-semibold">{g.name}</span>
                              {g.validation_status !== 'validated' && <Badge tone="warn">Sin validar</Badge>}
                            </span>
                          </th>
                        </tr>
                        {g.assets.map((r) => (
                          <tr key={r.asset_id}>
                            <th scope="row" className={cx(stickyCell, 'px-3 py-1.5 text-left font-normal')}>
                              <Link to={`/contabilidad/activos/${r.asset_id}`} className="hover:text-ledger hover:underline">
                                {r.description}
                              </Link>
                              {r.disposed_on && <span className="block text-xs text-ink-3">De baja el {formatBookDate(r.disposed_on)}</span>}
                            </th>
                            <Cells cols={cols} row={r} />
                          </tr>
                        ))}
                        <tr className="border-t border-line-strong">
                          <th scope="row" className={cx(stickyCell, 'px-3 py-1.5 text-left font-medium')}>
                            Subtotal {g.name}
                          </th>
                          <Cells cols={cols} totals={g.totals} />
                        </tr>
                      </tbody>
                    </Fragment>
                  ))}
                  <tfoot className="border-t-2 border-line-strong">
                    <tr>
                      <th scope="row" className={cx(stickyCell, 'px-3 py-2.5 text-left font-semibold')}>
                        Total del ejercicio
                      </th>
                      {cols.map((c) => (
                        <td key={c.n} className="px-2.5 py-2.5 text-right whitespace-nowrap">
                          {c.money ? <RuledTotal value={data.totals[c.money]} label={`Total columna ${c.n} ${formatMoney(data.totals[c.money], 'PYG')}`} /> : null}
                        </td>
                      ))}
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
            {assetCount > 0 && <Reconciliation data={data} />}
          </>
        )}
      </ReportSheet>
    </>
  )
}
