/** Libro mayor de una cuenta: saldo anterior, movimientos con saldo acumulado y saldo final. */
import { useInfiniteQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { Button, EmptyState, Field } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton } from '../../finance/components'
import { formatBookDate } from '../../finance/labels'
import { postableAccounts } from '../chartTree'
import { AccountCombobox, Blank, Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys, useAccountsById, useChart } from '../data'
import { KIND_LABELS, longDate, rangeText, SIDE_LABELS } from '../labels'
import type { LedgerReport as Ledger } from '../types'
import { ReportControls, ReportSheet, SideBalance } from './common'
import { amountTh, textTh, useReportParams } from './params'

export function LedgerReport() {
  const { from, to, accountId, set } = useReportParams()
  const chart = useChart()
  const byId = useAccountsById(chart.data?.accounts)
  // También las archivadas: su historia sigue en los libros.
  const options = (chart.data?.accounts ?? []).filter((a) => a.is_postable)
  const valid = from <= to
  const report = useInfiniteQuery({
    queryKey: [...accountingKeys.reports(), 'ledger', accountId, from, to],
    queryFn: ({ pageParam }) => get<Ledger>(`/accounting/reports/ledger/${accountId}${qs({ from, to, after: pageParam })}`),
    initialPageParam: '' as string,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: valid && Boolean(accountId),
  })
  const first = report.data?.pages[0]
  const last = report.data?.pages.at(-1)
  const movements = report.data?.pages.flatMap((p) => p.movements) ?? []
  const account = first?.account

  return (
    <>
      <ReportControls mode="range">
        <div className="w-[26rem]">
          <Field label="Cuenta">
            {(p) => (
              <AccountCombobox
                {...p}
                accounts={options.length ? options : postableAccounts(chart.data?.accounts ?? [])}
                known={byId}
                value={accountId}
                onChange={(id) => set({ account_id: id })}
                placeholder="Elegí una cuenta imputable"
              />
            )}
          </Field>
        </div>
      </ReportControls>
      <ReportSheet>
        {!accountId ? (
          <EmptyState title="Elegí una cuenta">
            El mayor muestra, para una cuenta imputable, el saldo con que llega al rango, cada movimiento con su saldo acumulado y el saldo final.
          </EmptyState>
        ) : !valid ? (
          <EmptyState title="El rango no es válido">La fecha «Hasta» es anterior a «Desde».</EmptyState>
        ) : report.isPending ? (
          <TableSkeleton rows={6} cols={5} />
        ) : report.isError || !first || !account || !last ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el libro mayor." />
          </div>
        ) : (
          <>
            <ReportHeading
              title={`Libro mayor: ${account.code} ${account.name}`}
              scope={`${KIND_LABELS[account.kind]}, naturaleza ${SIDE_LABELS[account.normal_side].toLowerCase()}. Movimientos ${rangeText(from, to)}`}
              status={first.chart_status}
            />
            <table className="w-full" aria-label="Libro mayor">
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <th scope="col" className={cx(textTh, 'w-28')}>
                    Fecha
                  </th>
                  <th scope="col" className={cx(textTh, 'w-20')}>
                    Asiento
                  </th>
                  <th scope="col" className={textTh}>
                    Detalle
                  </th>
                  <th scope="col" className={amountTh}>
                    Debe
                  </th>
                  <th scope="col" className={amountTh}>
                    Haber
                  </th>
                  <th scope="col" className={amountTh}>
                    Saldo
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                <tr className="bg-sunken/40">
                  <td className="px-4 py-2 text-sm text-ink-2 tabular-nums">{formatBookDate(from)}</td>
                  <td />
                  <td className="px-4 py-2 font-medium">Saldo anterior (antes del {longDate(from)})</td>
                  <td />
                  <td />
                  <td className="px-4 py-2 text-right">
                    <SideBalance value={first.opening_balance} normal={account.normal_side} />
                  </td>
                </tr>
                {movements.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-ink-2">
                      Sin movimientos contabilizados en el rango.
                    </td>
                  </tr>
                )}
                {movements.map((m) => (
                  <tr key={m.line_id} className="align-top">
                    <td className="px-4 py-2 text-sm text-ink-2 tabular-nums">{formatBookDate(m.entry_date)}</td>
                    <td className="px-4 py-2 tabular-nums">
                      <Link to={`/contabilidad/asientos/${m.entry_id}`} className="font-medium text-ledger hover:underline" aria-label={`Asiento N° ${m.number}`}>
                        N° {m.number}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      {m.entry_description}
                      {(m.line_description && m.line_description !== m.entry_description) || m.document_reference ? (
                        <span className="block text-sm text-ink-3">
                          {[m.line_description !== m.entry_description ? m.line_description : null, m.document_reference && `Comprobante ${m.document_reference}`].filter(Boolean).join('. ')}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-right">{m.debit !== '0' ? <Pyg value={m.debit} /> : <Blank />}</td>
                    <td className="px-4 py-2 text-right">{m.credit !== '0' ? <Pyg value={m.credit} /> : <Blank />}</td>
                    <td className="px-4 py-2 text-right">
                      <SideBalance value={m.balance} normal={account.normal_side} />
                    </td>
                  </tr>
                ))}
              </tbody>
              {!report.hasNextPage && (
                <tfoot className="border-t-2 border-line-strong">
                  <tr>
                    <td colSpan={3} className="px-4 py-3 font-semibold">
                      Totales y saldo final al {longDate(to)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <RuledTotal value={first.total_debit} label={`Total debe ${formatMoney(first.total_debit, 'PYG')}`} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <RuledTotal value={first.total_credit} label={`Total haber ${formatMoney(first.total_credit, 'PYG')}`} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="ledger-rule inline-block" aria-label={`Saldo final ${formatMoney(first.closing_balance, 'PYG')}`}>
                        <SideBalance value={first.closing_balance} normal={account.normal_side} strong />
                      </span>
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
            <p className="border-t border-line px-4 py-2.5 text-sm text-ink-3">
              Saldo según la naturaleza de la cuenta: «D» deudor, «A» acreedor. Un saldo contrario a la naturaleza se marca además en rojo.
            </p>
            {report.hasNextPage && (
              <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-2">
                <span>Se muestran {movements.length} movimientos; el saldo acumulado sigue en la página siguiente.</span>
                <Button variant="secondary" busy={report.isFetchingNextPage} onClick={() => report.fetchNextPage()}>
                  Cargar más movimientos
                </Button>
              </div>
            )}
          </>
        )}
      </ReportSheet>
    </>
  )
}
