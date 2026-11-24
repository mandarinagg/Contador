/**
 * Estado de resultados por rango, agrupado por la jerarquía del plan (RG 49/2014 Anexo 2), y
 * su vista por centro de costos (D-060): una columna por centro, una «Sin centro» y el total.
 */
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { EmptyState } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney, isNegative, isZeroAmount } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, Check, TableSkeleton } from '../../finance/components'
import { Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys } from '../data'
import { rangeText } from '../labels'
import type { CostCenterColumn, IncomeStatement, StatementNode } from '../types'
import { ReportControls, ReportSheet, StatementRows } from './common'
import { ReportActions } from './ReportActions'
import { useReportParams } from './params'

function MatrixRows({ nodes, depth = 0, linkFor }: { nodes: StatementNode[]; depth?: number; linkFor: (n: StatementNode) => string }) {
  return (
    <>
      {nodes.map((n) => {
        const group = !n.is_postable
        const name = (
          <>
            <span className="mr-2 text-ink-2 tabular-nums">{n.code}</span>
            {n.name}
          </>
        )
        return (
          <MatrixRow key={n.account_id} node={n} depth={depth} group={group} linkFor={linkFor}>
            {n.is_postable ? (
              <Link to={linkFor(n)} className="hover:text-ledger hover:underline">
                {name}
              </Link>
            ) : (
              name
            )}
          </MatrixRow>
        )
      })}
    </>
  )
}

function MatrixRow({ node, depth, group, linkFor, children }: { node: StatementNode; depth: number; group: boolean; linkFor: (n: StatementNode) => string; children: ReactNode }) {
  return (
    <>
      <tr className={cx(group && depth === 0 && 'bg-sunken/40')}>
        <th scope="row" className={cx('py-1.5 pr-3 text-left font-normal', group && (depth === 0 ? 'font-semibold' : 'font-medium'))} style={{ paddingLeft: `${1 + depth * 1.1}rem` }}>
          {children}
        </th>
        {(node.column_amounts ?? []).map((v, i) => (
          <td key={i} className="border-l border-line px-3 py-1.5 text-right">
            {isZeroAmount(v) ? <span className="text-ink-3">·</span> : <Pyg value={v} className={cx(group && 'font-medium')} />}
          </td>
        ))}
        <td className="border-l border-line-strong px-3 py-1.5 text-right">
          <Pyg value={node.amount} strong={group && depth === 0} className={cx(group && depth > 0 && 'font-medium')} />
        </td>
      </tr>
      {node.children.length > 0 && <MatrixRows nodes={node.children} depth={depth + 1} linkFor={linkFor} />}
    </>
  )
}

function ByCenterTable({ data, linkFor }: { data: IncomeStatement; linkFor: (n: StatementNode) => string }) {
  const columns = data.cost_center_columns ?? []
  const outcome = (c: { result: string }) => (isNegative(c.result) ? 'Pérdida' : 'Ganancia')
  const label = (c: CostCenterColumn) => (c.code ? c.code : 'Sin centro')
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem]" aria-label="Estado de resultados por centro de costos">
        <thead className="border-b border-line bg-sunken text-sm text-ink-2">
          <tr>
            <th scope="col" className="px-4 py-2.5 text-left font-medium">
              Cuenta
            </th>
            {columns.map((c) => (
              <th key={c.cost_center_id ?? 'none'} scope="col" className="w-36 border-l border-line px-3 py-2.5 text-right font-medium" title={c.name}>
                <span className="block text-ink">{label(c)}</span>
                <span className="block truncate text-xs font-normal">{c.code ? c.name : 'Líneas sin centro'}</span>
              </th>
            ))}
            <th scope="col" className="w-36 border-l border-line-strong px-3 py-2.5 text-right font-medium">
              <span className="block text-ink">Total</span>
              <span className="block text-xs font-normal">Todas las líneas</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <MatrixRows nodes={data.accounts} linkFor={linkFor} />
        </tbody>
        <tfoot className="border-t-2 border-line-strong text-sm">
          <tr>
            <th scope="row" className="px-4 pt-3 pb-1 text-left font-normal">
              Ingresos
            </th>
            {columns.map((c) => (
              <td key={c.cost_center_id ?? 'none'} className="border-l border-line px-3 pt-3 pb-1 text-right">
                <Pyg value={c.total_income} />
              </td>
            ))}
            <td className="border-l border-line-strong px-3 pt-3 pb-1 text-right">
              <Pyg value={data.total_income} strong />
            </td>
          </tr>
          <tr>
            <th scope="row" className="px-4 py-1 text-left font-normal">
              Costos y gastos
            </th>
            {columns.map((c) => (
              <td key={c.cost_center_id ?? 'none'} className="border-l border-line px-3 py-1 text-right">
                <Pyg value={c.total_expense} />
              </td>
            ))}
            <td className="border-l border-line-strong px-3 py-1 text-right">
              <Pyg value={data.total_expense} strong />
            </td>
          </tr>
          <tr className="text-base">
            <th scope="row" className="px-4 pt-2 pb-3 text-left font-semibold">
              Resultado
            </th>
            {columns.map((c) => (
              <td key={c.cost_center_id ?? 'none'} className="border-l border-line px-3 pt-2 pb-3 text-right" aria-label={`${label(c)}: ${outcome(c)} ${formatMoney(c.result, 'PYG')}`}>
                <RuledTotal value={c.result} />
              </td>
            ))}
            <td className="border-l border-line-strong px-3 pt-2 pb-3 text-right">
              <RuledTotal value={data.result} label={`Resultado total ${formatMoney(data.result, 'PYG')}`} />
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

export function IncomeStatementReport() {
  const { from, to, params, set } = useReportParams()
  const byCenter = params.get('por_centro') === '1'
  const valid = from <= to
  const report = useQuery({
    queryKey: [...accountingKeys.reports(), 'income', from, to, byCenter],
    queryFn: () => get<IncomeStatement>(`/accounting/reports/income-statement${qs({ from, to, by_cost_center: byCenter })}`),
    enabled: valid,
  })
  const data = report.data
  const linkFor = (n: StatementNode) => `/contabilidad/reportes/mayor${qs({ account_id: n.account_id, from, to })}`
  const outcome = data ? (isNegative(data.result) ? 'Pérdida del período' : isZeroAmount(data.result) ? 'Resultado del período' : 'Ganancia del período') : ''

  return (
    <>
      <ReportControls mode="range">
        <div className="order-last basis-full pt-1">
          <Check
            label="Ver por centro de costos"
            hint="Una columna por centro con movimiento en el rango y otra para las líneas sin centro. Las columnas suman el total."
            checked={byCenter}
            onChange={(v) => set({ por_centro: v ? '1' : '' })}
          />
        </div>
      </ReportControls>
      <ReportSheet className={cx(byCenter && 'print-landscape')}>
        {!valid ? (
          <EmptyState title="El rango no es válido">La fecha «Hasta» es anterior a «Desde».</EmptyState>
        ) : report.isPending ? (
          <TableSkeleton rows={10} cols={byCenter ? 4 : 2} />
        ) : report.isError || !data ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el estado de resultados." />
          </div>
        ) : (
          <>
            <ReportHeading
              title={byCenter ? 'Estado de resultados por centro de costos' : 'Estado de resultados'}
              scope={`Ingresos y gastos ${rangeText(from, to)}, sin el asiento de refundición`}
              status={data.chart_status}
              aside={
                <ReportActions
                  path={`/accounting/reports/income-statement${qs({ from, to, by_cost_center: byCenter })}`}
                  report="income-statement"
                  scope={{ from, to }}
                  disabled={data.accounts.length === 0}
                />
              }
            />
            {data.accounts.length === 0 ? (
              <EmptyState title="Sin ingresos ni gastos en el rango">Cuando se contabilicen asientos con cuentas de resultado, aparecen acá agrupados por el plan.</EmptyState>
            ) : byCenter && data.cost_center_columns ? (
              <>
                <ByCenterTable data={data} linkFor={linkFor} />
                <p className="border-t border-line px-4 py-2.5 text-sm text-ink-3">
                  El centro es una dimensión de gestión: no cambia los saldos contables. Los centros se administran en{' '}
                  <Link to="/contabilidad/centros" className="font-medium text-ledger hover:underline" data-print="hide">
                    Centros de costos
                  </Link>
                  .
                </p>
              </>
            ) : (
              <div className="mx-auto max-w-3xl py-2">
                <table className="w-full" aria-label="Estado de resultados">
                  <thead className="sr-only">
                    <tr>
                      <th scope="col">Cuenta</th>
                      <th scope="col">Importe</th>
                    </tr>
                  </thead>
                  <tbody>
                    <StatementRows nodes={data.accounts} linkFor={linkFor} />
                  </tbody>
                </table>
                <dl className="mt-3 border-t-2 border-line-strong px-4 pt-3">
                  <div className="flex items-baseline justify-between py-1">
                    <dt>Total de ingresos</dt>
                    <dd>
                      <Pyg value={data.total_income} strong />
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between py-1">
                    <dt>Total de costos y gastos</dt>
                    <dd>
                      <Pyg value={data.total_expense} strong />
                    </dd>
                  </div>
                  <div className="mt-1 flex items-baseline justify-between border-t border-line py-3">
                    <dt className="font-semibold">{outcome}</dt>
                    <dd>
                      <RuledTotal value={data.result} label={`${outcome} ${formatMoney(data.result, 'PYG')}`} />
                    </dd>
                  </div>
                </dl>
                <p className="px-4 pb-3 text-sm text-ink-3">Resultado = ingresos − costos y gastos. Una pérdida se ve con signo menos.</p>
              </div>
            )}
          </>
        )}
      </ReportSheet>
    </>
  )
}
