/**
 * Balance de comprobación de sumas y saldos (D-053) con saldo inicial y final (D-062, D-075):
 * lo que la cuenta traía antes del rango, lo que se movió en el rango y con qué saldo termina.
 */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { EmptyState, Notice } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, Check, TableSkeleton } from '../../finance/components'
import { isZeroPyg, subPyg } from '../amounts'
import { Blank, Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys } from '../data'
import { longDate, rangeText } from '../labels'
import type { TrialBalance, TrialRow } from '../types'
import { ReportControls, ReportSheet } from './common'
import { ReportActions } from './ReportActions'
import { textTh, useReportParams } from './params'

const amountTh = 'w-32 px-3 py-2 text-right font-medium'
const groupTh = 'border-l border-line px-3 pt-2 text-center font-medium'

function Cell({ value, first, strong }: { value: string; first?: boolean; strong?: boolean }) {
  return <td className={cx('px-3 py-2 text-right', first && 'border-l border-line')}>{isZeroPyg(value) ? <Blank /> : <Pyg value={value} strong={strong} />}</td>
}

function TotalCell({ value, label, first }: { value: string; label: string; first?: boolean }) {
  return (
    <td className={cx('px-3 py-3 text-right', first && 'border-l border-line')}>
      <RuledTotal value={value} label={`${label} ${formatMoney(value, 'PYG')}`} />
    </td>
  )
}

/** Qué pareja no cuadra, en palabras (para el aviso). */
function unbalancedPairs(d: TrialBalance): string[] {
  const out: string[] = []
  if (!isZeroPyg(subPyg(d.total_opening_debit, d.total_opening_credit))) out.push(`saldo inicial (deudor ${formatMoney(d.total_opening_debit, 'PYG')}, acreedor ${formatMoney(d.total_opening_credit, 'PYG')})`)
  if (!isZeroPyg(subPyg(d.total_debit, d.total_credit))) out.push(`sumas del rango (debe ${formatMoney(d.total_debit, 'PYG')}, haber ${formatMoney(d.total_credit, 'PYG')})`)
  if (!isZeroPyg(subPyg(d.total_closing_debit, d.total_closing_credit))) out.push(`saldo final (deudor ${formatMoney(d.total_closing_debit, 'PYG')}, acreedor ${formatMoney(d.total_closing_credit, 'PYG')})`)
  return out
}

export function TrialBalanceReport() {
  const { from, to, params, set } = useReportParams()
  const showRange = params.get('saldo_rango') === '1'
  const valid = from <= to
  const report = useQuery({
    queryKey: [...accountingKeys.reports(), 'trial', from, to],
    queryFn: () => get<TrialBalance>(`/accounting/reports/trial-balance${qs({ from, to })}`),
    enabled: valid,
  })
  const data = report.data
  const ledgerLink = (id: string) => `/contabilidad/reportes/mayor${qs({ account_id: id, from, to })}`
  const pairs = data ? unbalancedPairs(data) : []

  return (
    <>
      <ReportControls mode="range">
        <div className="order-last basis-full pt-1">
          <Check
            label="Mostrar también el saldo del rango"
            hint="Solo lo movido entre las dos fechas, sin el saldo inicial (como en la versión anterior del reporte)."
            checked={showRange}
            onChange={(v) => set({ saldo_rango: v ? '1' : '' })}
          />
        </div>
      </ReportControls>
      <ReportSheet className={cx(showRange && 'print-landscape')}>
        {!valid ? (
          <EmptyState title="El rango no es válido">La fecha «Hasta» es anterior a «Desde».</EmptyState>
        ) : report.isPending ? (
          <TableSkeleton rows={8} cols={7} />
        ) : report.isError || !data ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el balance de comprobación." />
          </div>
        ) : (
          <>
            <ReportHeading
              title="Balance de comprobación de sumas y saldos"
              scope={`Saldo al ${longDate(from)}, movimientos ${rangeText(from, to)} y saldo final`}
              status={data.chart_status}
              aside={<ReportActions path={`/accounting/reports/trial-balance${qs({ from, to })}`} report="trial-balance" scope={{ from, to }} disabled={data.rows.length === 0} />}
            />
            {!data.balanced && (
              <div className="px-6 pt-4">
                <Notice tone="bad" title="El balance de comprobación no cuadra">
                  No cuadra: {pairs.join('; ')}. Con partida doble esto no debería pasar nunca: no sigas operando y avisá a soporte con esta pantalla.
                </Notice>
              </div>
            )}
            {data.rows.length === 0 ? (
              <EmptyState title="Sin saldos ni movimientos contabilizados">
                Ninguna cuenta tiene saldo al {longDate(from)} ni movimientos en el rango. Los borradores no cuentan hasta que se contabilizan.
              </EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[56rem]" aria-label="Balance de comprobación">
                  <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                    <tr>
                      <th scope="col" rowSpan={2} className={cx(textTh, 'align-bottom')}>
                        Cuenta
                      </th>
                      <th scope="colgroup" colSpan={2} className={groupTh}>
                        Saldo inicial
                      </th>
                      <th scope="colgroup" colSpan={2} className={groupTh}>
                        Movimientos del rango
                      </th>
                      {showRange && (
                        <th scope="colgroup" colSpan={2} className={groupTh}>
                          Saldo del rango
                        </th>
                      )}
                      <th scope="colgroup" colSpan={2} className={groupTh}>
                        Saldo final
                      </th>
                    </tr>
                    <tr>
                      <th scope="col" className={cx(amountTh, 'border-l border-line')}>
                        Deudor
                      </th>
                      <th scope="col" className={amountTh}>
                        Acreedor
                      </th>
                      <th scope="col" className={cx(amountTh, 'border-l border-line')}>
                        Debe
                      </th>
                      <th scope="col" className={amountTh}>
                        Haber
                      </th>
                      {showRange && (
                        <>
                          <th scope="col" className={cx(amountTh, 'border-l border-line')}>
                            Deudor
                          </th>
                          <th scope="col" className={amountTh}>
                            Acreedor
                          </th>
                        </>
                      )}
                      <th scope="col" className={cx(amountTh, 'border-l border-line')}>
                        Deudor
                      </th>
                      <th scope="col" className={amountTh}>
                        Acreedor
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.rows.map((r: TrialRow) => (
                      <tr key={r.account_id}>
                        <td className="px-4 py-2">
                          <Link to={ledgerLink(r.account_id)} className="hover:text-ledger hover:underline">
                            <span className="mr-2 text-ink-2 tabular-nums">{r.code}</span>
                            {r.name}
                          </Link>
                        </td>
                        <Cell value={r.opening_debit} first />
                        <Cell value={r.opening_credit} />
                        <Cell value={r.debit} first />
                        <Cell value={r.credit} />
                        {showRange && (
                          <>
                            <Cell value={r.debit_balance} first />
                            <Cell value={r.credit_balance} />
                          </>
                        )}
                        <Cell value={r.closing_debit} first strong />
                        <Cell value={r.closing_credit} strong />
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="border-t-2 border-line-strong">
                    <tr>
                      <td className="px-4 py-3 font-semibold">
                        Totales
                        {data.balanced && <span className="ml-2 text-sm font-normal text-ledger">cuadran</span>}
                      </td>
                      <TotalCell value={data.total_opening_debit} label="Total saldos iniciales deudores" first />
                      <TotalCell value={data.total_opening_credit} label="Total saldos iniciales acreedores" />
                      <TotalCell value={data.total_debit} label="Total sumas debe" first />
                      <TotalCell value={data.total_credit} label="Total sumas haber" />
                      {showRange && (
                        <>
                          <TotalCell value={data.total_debit_balance} label="Total saldos del rango deudores" first />
                          <TotalCell value={data.total_credit_balance} label="Total saldos del rango acreedores" />
                        </>
                      )}
                      <TotalCell value={data.total_closing_debit} label="Total saldos finales deudores" first />
                      <TotalCell value={data.total_closing_credit} label="Total saldos finales acreedores" />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
            <p className="border-t border-line px-4 py-2.5 text-sm text-ink-3">
              Saldo inicial: todo lo contabilizado antes del {longDate(from)}, con la refundición de los ejercicios cerrados (las cuentas de resultado arrancan
              en cero). No hay asiento de apertura: el saldo se calcula.
            </p>
          </>
        )}
      </ReportSheet>
    </>
  )
}
