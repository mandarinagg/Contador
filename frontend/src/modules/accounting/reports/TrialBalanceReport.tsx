/** Balance de comprobación de sumas y saldos del rango (D-053). */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { EmptyState, Notice } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton } from '../../finance/components'
import { subPyg } from '../amounts'
import { Blank, Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys } from '../data'
import { rangeText } from '../labels'
import type { TrialBalance } from '../types'
import { ReportControls, ReportSheet } from './common'
import { amountTh, textTh, useReportParams } from './params'

export function TrialBalanceReport() {
  const { from, to } = useReportParams()
  const valid = from <= to
  const report = useQuery({
    queryKey: [...accountingKeys.reports(), 'trial', from, to],
    queryFn: () => get<TrialBalance>(`/accounting/reports/trial-balance${qs({ from, to })}`),
    enabled: valid,
  })
  const data = report.data
  const ledgerLink = (id: string) => `/contabilidad/reportes/mayor${qs({ account_id: id, from, to })}`

  return (
    <>
      <ReportControls mode="range" />
      <ReportSheet>
        {!valid ? (
          <EmptyState title="El rango no es válido">La fecha «Hasta» es anterior a «Desde».</EmptyState>
        ) : report.isPending ? (
          <TableSkeleton rows={8} cols={5} />
        ) : report.isError || !data ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el balance de comprobación." />
          </div>
        ) : (
          <>
            <ReportHeading title="Balance de comprobación de sumas y saldos" scope={`Movimientos ${rangeText(from, to)}`} status={data.chart_status} />
            {!data.balanced && (
              <div className="px-6 pt-4">
                <Notice tone="bad" title="El balance de comprobación no cuadra">
                  Debe {formatMoney(data.total_debit, 'PYG')} contra haber {formatMoney(data.total_credit, 'PYG')} (diferencia{' '}
                  {formatMoney(subPyg(data.total_debit, data.total_credit), 'PYG')}). Con partida doble esto no debería pasar nunca: no sigas
                  operando y avisá a soporte con esta pantalla.
                </Notice>
              </div>
            )}
            {data.rows.length === 0 ? (
              <EmptyState title="Sin movimientos contabilizados en el rango">
                Para ver saldos acumulados, pedí el rango desde el inicio del primer ejercicio: no hay asiento de apertura en esta versión.
              </EmptyState>
            ) : (
              <table className="w-full" aria-label="Balance de comprobación">
                <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                  <tr>
                    <th scope="col" rowSpan={2} className={textTh}>
                      Cuenta
                    </th>
                    <th scope="colgroup" colSpan={2} className="border-l border-line px-4 pt-2 text-center font-medium">
                      Sumas
                    </th>
                    <th scope="colgroup" colSpan={2} className="border-l border-line px-4 pt-2 text-center font-medium">
                      Saldos
                    </th>
                  </tr>
                  <tr>
                    <th scope="col" className={cx(amountTh, 'w-36 border-l border-line')}>
                      Debe
                    </th>
                    <th scope="col" className={cx(amountTh, 'w-36')}>
                      Haber
                    </th>
                    <th scope="col" className={cx(amountTh, 'w-36 border-l border-line')}>
                      Deudor
                    </th>
                    <th scope="col" className={cx(amountTh, 'w-36')}>
                      Acreedor
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.rows.map((r) => (
                    <tr key={r.account_id}>
                      <td className="px-4 py-2">
                        <Link to={ledgerLink(r.account_id)} className="hover:text-ledger hover:underline">
                          <span className="mr-2 text-ink-2 tabular-nums">{r.code}</span>
                          {r.name}
                        </Link>
                      </td>
                      <td className="border-l border-line px-4 py-2 text-right">{r.debit !== '0' ? <Pyg value={r.debit} /> : <Blank />}</td>
                      <td className="px-4 py-2 text-right">{r.credit !== '0' ? <Pyg value={r.credit} /> : <Blank />}</td>
                      <td className="border-l border-line px-4 py-2 text-right">{r.debit_balance !== '0' ? <Pyg value={r.debit_balance} /> : <Blank />}</td>
                      <td className="px-4 py-2 text-right">{r.credit_balance !== '0' ? <Pyg value={r.credit_balance} /> : <Blank />}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="border-t-2 border-line-strong">
                  <tr>
                    <td className="px-4 py-3 font-semibold">
                      Totales
                      {data.balanced && <span className="ml-2 text-sm font-normal text-ledger">cuadran</span>}
                    </td>
                    <td className="border-l border-line px-4 py-3 text-right">
                      <RuledTotal value={data.total_debit} label={`Total sumas debe ${formatMoney(data.total_debit, 'PYG')}`} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <RuledTotal value={data.total_credit} label={`Total sumas haber ${formatMoney(data.total_credit, 'PYG')}`} />
                    </td>
                    <td className="border-l border-line px-4 py-3 text-right">
                      <RuledTotal value={data.total_debit_balance} label={`Total saldos deudores ${formatMoney(data.total_debit_balance, 'PYG')}`} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <RuledTotal value={data.total_credit_balance} label={`Total saldos acreedores ${formatMoney(data.total_credit_balance, 'PYG')}`} />
                    </td>
                  </tr>
                </tfoot>
              </table>
            )}
          </>
        )}
      </ReportSheet>
    </>
  )
}
