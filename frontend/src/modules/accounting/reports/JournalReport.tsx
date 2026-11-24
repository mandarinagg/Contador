/** Libro diario: asientos contabilizados por fecha y número, con sus líneas y los totales del rango. */
import { useInfiniteQuery } from '@tanstack/react-query'
import { Fragment } from 'react'
import { Link } from 'react-router'
import { Badge, Button, EmptyState } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton } from '../../finance/components'
import { formatBookDate } from '../../finance/labels'
import { Blank, Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys } from '../data'
import { ENTRY_KIND_LABELS, rangeText } from '../labels'
import type { JournalReport as Journal } from '../types'
import { ReportControls, ReportSheet } from './common'
import { amountTh, textTh, useReportParams } from './params'

export function JournalReport() {
  const { from, to } = useReportParams()
  const valid = from <= to
  const report = useInfiniteQuery({
    queryKey: [...accountingKeys.reports(), 'journal', from, to],
    queryFn: ({ pageParam }) => get<Journal>(`/accounting/reports/journal${qs({ from, to, after: pageParam })}`),
    initialPageParam: '' as string,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: valid,
  })
  const first = report.data?.pages[0]
  const entries = report.data?.pages.flatMap((p) => p.entries) ?? []

  return (
    <>
      <ReportControls mode="range" />
      <ReportSheet>
        {!valid ? (
          <EmptyState title="El rango no es válido">La fecha «Hasta» es anterior a «Desde».</EmptyState>
        ) : report.isPending ? (
          <TableSkeleton rows={8} cols={4} />
        ) : report.isError || !first ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el libro diario." />
          </div>
        ) : (
          <>
            <ReportHeading title="Libro diario" scope={`Asientos contabilizados ${rangeText(from, to)}`} status={first.chart_status} />
            {entries.length === 0 ? (
              <EmptyState title="Sin asientos contabilizados en el rango">
                Los borradores no aparecen en el diario hasta que se contabilizan. Probá con otro rango o revisá los{' '}
                <Link to="/contabilidad/asientos?status=draft" className="font-medium text-ledger hover:underline">
                  borradores pendientes
                </Link>
                .
              </EmptyState>
            ) : (
              <table className="w-full" aria-label="Libro diario">
                <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                  <tr>
                    <th scope="col" className={cx(textTh, 'w-28')}>
                      Fecha
                    </th>
                    <th scope="col" className={textTh}>
                      Cuenta y detalle
                    </th>
                    <th scope="col" className={amountTh}>
                      Debe
                    </th>
                    <th scope="col" className={amountTh}>
                      Haber
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <Fragment key={e.id}>
                      <tr className="border-t border-line-strong first:border-t-0">
                        <td className="px-4 pt-3 pb-1 text-sm text-ink-2 tabular-nums">{formatBookDate(e.entry_date)}</td>
                        <td colSpan={3} className="px-4 pt-3 pb-1">
                          <Link to={`/contabilidad/asientos/${e.id}`} className="font-semibold hover:text-ledger hover:underline">
                            Asiento N° {e.number}
                          </Link>
                          <span className="ml-3">{e.description}</span>
                          <span className="ml-3 inline-flex gap-1.5 align-middle">
                            {e.kind !== 'manual' && <Badge>{ENTRY_KIND_LABELS[e.kind]}</Badge>}
                            {e.status === 'reversed' && <Badge>Revertido</Badge>}
                          </span>
                          {e.document_reference && <span className="ml-3 text-sm text-ink-2">Comprobante {e.document_reference}</span>}
                        </td>
                      </tr>
                      {(e.lines ?? []).map((l) => (
                        <tr key={l.id}>
                          <td />
                          <td className={cx('py-1 pr-4', l.credit !== '0' ? 'pl-12' : 'pl-4')}>
                            <span className="mr-2 text-ink-2 tabular-nums">{l.account_code}</span>
                            {l.account_name}
                            {l.description && l.description !== e.description && <span className="ml-2 text-sm text-ink-3">{l.description}</span>}
                          </td>
                          <td className="px-4 py-1 text-right">{l.debit !== '0' ? <Pyg value={l.debit} /> : <Blank />}</td>
                          <td className="px-4 py-1 text-right">{l.credit !== '0' ? <Pyg value={l.credit} /> : <Blank />}</td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={4} className="pb-2" />
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
                <tfoot className="border-t-2 border-line-strong">
                  <tr>
                    <td />
                    <td className="px-4 py-3 font-semibold">Totales del período</td>
                    <td className="px-4 py-3 text-right">
                      <RuledTotal value={first.total_debit} label={`Total debe ${formatMoney(first.total_debit, 'PYG')}`} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <RuledTotal value={first.total_credit} label={`Total haber ${formatMoney(first.total_credit, 'PYG')}`} />
                    </td>
                  </tr>
                </tfoot>
              </table>
            )}
            {report.hasNextPage && (
              <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-2">
                <span>Se muestran {entries.length} asientos; los totales son de todo el rango.</span>
                <Button variant="secondary" busy={report.isFetchingNextPage} onClick={() => report.fetchNextPage()}>
                  Cargar más asientos
                </Button>
              </div>
            )}
          </>
        )}
      </ReportSheet>
    </>
  )
}
