/** Estado de resultados por rango, agrupado por la jerarquía del plan (RG 49/2014 Anexo 2). */
import { useQuery } from '@tanstack/react-query'
import { EmptyState } from '../../../components/ui'
import { formatMoney, isNegative, isZeroAmount } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton } from '../../finance/components'
import { Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys } from '../data'
import { rangeText } from '../labels'
import type { IncomeStatement, StatementNode } from '../types'
import { ReportControls, ReportSheet, StatementRows } from './common'
import { useReportParams } from './params'

export function IncomeStatementReport() {
  const { from, to } = useReportParams()
  const valid = from <= to
  const report = useQuery({
    queryKey: [...accountingKeys.reports(), 'income', from, to],
    queryFn: () => get<IncomeStatement>(`/accounting/reports/income-statement${qs({ from, to })}`),
    enabled: valid,
  })
  const data = report.data
  const linkFor = (n: StatementNode) => `/contabilidad/reportes/mayor${qs({ account_id: n.account_id, from, to })}`
  const outcome = data ? (isNegative(data.result) ? 'Pérdida del período' : isZeroAmount(data.result) ? 'Resultado del período' : 'Ganancia del período') : ''

  return (
    <>
      <ReportControls mode="range" />
      <ReportSheet>
        {!valid ? (
          <EmptyState title="El rango no es válido">La fecha «Hasta» es anterior a «Desde».</EmptyState>
        ) : report.isPending ? (
          <TableSkeleton rows={10} cols={2} />
        ) : report.isError || !data ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el estado de resultados." />
          </div>
        ) : (
          <>
            <ReportHeading title="Estado de resultados" scope={`Ingresos y gastos ${rangeText(from, to)}, sin el asiento de refundición`} status={data.chart_status} />
            {data.accounts.length === 0 ? (
              <EmptyState title="Sin ingresos ni gastos en el rango">Cuando se contabilicen asientos con cuentas de resultado, aparecen acá agrupados por el plan.</EmptyState>
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
