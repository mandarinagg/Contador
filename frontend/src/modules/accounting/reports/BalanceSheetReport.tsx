/**
 * Balance general a una fecha, en dos columnas enfrentadas (activo | pasivo y patrimonio), con
 * el resultado no refundido y el control activo = pasivo + patrimonio (D-042, D-053).
 */
import { useQuery } from '@tanstack/react-query'
import { CircleCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { EmptyState, Notice } from '../../../components/ui'
import { formatMoney, isNegative, isZeroAmount } from '../../../lib/money'
import { get, qs } from '../../../services/api'
import { ApiErrorNotice, TableSkeleton } from '../../finance/components'
import { subPyg } from '../amounts'
import { Pyg, ReportHeading, RuledTotal } from '../components'
import { accountingKeys } from '../data'
import { longDate } from '../labels'
import type { BalanceSheet, StatementNode } from '../types'
import { ReportControls, ReportSheet, StatementRows } from './common'
import { useReportParams } from './params'

/** Una sola raíz agrupadora («1 ACTIVO»): su nombre es el título y se listan sus hijas. */
function sectionOf(nodes: StatementNode[], fallback: string): { title: string; rows: StatementNode[] } {
  if (nodes.length === 1 && !nodes[0].is_postable) return { title: `${nodes[0].code} ${nodes[0].name}`, rows: nodes[0].children }
  return { title: fallback, rows: nodes }
}

function Section({ title, nodes, total, totalLabel, linkFor }: { title: string; nodes: StatementNode[]; total?: string; totalLabel?: string; linkFor: (n: StatementNode) => string }) {
  const s = sectionOf(nodes, title)
  return (
    <section aria-label={title} className="mb-4">
      <h3 className="px-4 pt-3 pb-1.5 font-semibold tracking-tight">{s.title}</h3>
      {s.rows.length === 0 ? (
        <p className="px-4 py-1.5 text-sm text-ink-3">Sin saldos a la fecha.</p>
      ) : (
        <table className="w-full">
          <tbody>
            <StatementRows nodes={s.rows} linkFor={linkFor} />
          </tbody>
        </table>
      )}
      {total !== undefined && (
        <div className="mt-1 flex items-baseline justify-between border-t border-line px-4 pt-2">
          <span className="font-medium">{totalLabel}</span>
          <Pyg value={total} strong />
        </div>
      )}
    </section>
  )
}

function GrandTotal({ label, value }: { label: ReactNode; value: string }) {
  return (
    <div className="mt-auto flex items-baseline justify-between border-t-2 border-line-strong px-4 py-3">
      <span className="font-semibold">{label}</span>
      <RuledTotal value={value} label={`${typeof label === 'string' ? label : 'Total'} ${formatMoney(value, 'PYG')}`} />
    </div>
  )
}

export function BalanceSheetReport() {
  const { at, from } = useReportParams()
  const report = useQuery({
    queryKey: [...accountingKeys.reports(), 'balance-sheet', at],
    queryFn: () => get<BalanceSheet>(`/accounting/reports/balance-sheet${qs({ at })}`),
  })
  const data = report.data
  const linkFor = (n: StatementNode) => `/contabilidad/reportes/mayor${qs({ account_id: n.account_id, from: from > at ? `${at.slice(0, 4)}-01-01` : from, to: at })}`

  return (
    <>
      <ReportControls mode="at" />
      <ReportSheet>
        {report.isPending ? (
          <TableSkeleton rows={10} cols={2} />
        ) : report.isError || !data ? (
          <div className="p-5">
            <ApiErrorNotice error={report.error} title="No se pudo calcular el balance general." />
          </div>
        ) : (
          <>
            <ReportHeading title="Balance general" scope={`Al ${longDate(at)}, con todo lo contabilizado hasta esa fecha`} status={data.chart_status} />
            {data.assets.length + data.liabilities.length + data.equity.length === 0 && isZeroAmount(data.result) ? (
              <EmptyState title="Sin saldos a la fecha">Todavía no hay asientos contabilizados hasta el {longDate(at)}.</EmptyState>
            ) : (
              <>
                <div className="grid grid-cols-2 divide-x divide-line">
                  <div className="flex flex-col">
                    <Section title="Activo" nodes={data.assets} linkFor={linkFor} />
                    <GrandTotal label="Total del activo" value={data.total_assets} />
                  </div>
                  <div className="flex flex-col">
                    <Section title="Pasivo" nodes={data.liabilities} total={data.total_liabilities} totalLabel="Total del pasivo" linkFor={linkFor} />
                    <Section title="Patrimonio neto" nodes={data.equity} total={data.total_equity} totalLabel="Total del patrimonio neto" linkFor={linkFor} />
                    <div className="mb-4 flex items-baseline justify-between gap-4 border-y border-line bg-sunken/40 px-4 py-2.5">
                      <span>
                        <span className="font-medium">Resultado del ejercicio en curso</span>
                        <span className="block text-sm text-ink-3">
                          {isNegative(data.result) ? 'Pérdida' : isZeroAmount(data.result) ? 'Sin resultado' : 'Ganancia'} no refundida: ingresos menos gastos de los ejercicios abiertos.
                        </span>
                      </span>
                      <Pyg value={data.result} strong />
                    </div>
                    <GrandTotal label="Total del pasivo y el patrimonio" value={data.total_liabilities_and_equity} />
                  </div>
                </div>
                <div className="border-t border-line px-4 py-3">
                  {data.balanced ? (
                    <p className="flex items-center gap-2 text-sm text-ledger" role="status">
                      <CircleCheck size={16} aria-hidden />
                      Cuadra: activo = pasivo + patrimonio + resultado = {formatMoney(data.total_assets, 'PYG')}.
                    </p>
                  ) : (
                    <Notice tone="bad" title="El balance general no cuadra">
                      Activo {formatMoney(data.total_assets, 'PYG')} contra pasivo y patrimonio {formatMoney(data.total_liabilities_and_equity, 'PYG')}{' '}
                      (diferencia {formatMoney(subPyg(data.total_assets, data.total_liabilities_and_equity), 'PYG')}). Con partida doble esto no debería
                      pasar: avisá a soporte con esta pantalla.
                    </Notice>
                  )}
                  <p className="mt-1 text-sm text-ink-3">Las cuentas regularizadoras, como «(-) Depreciación acumulada», restan en su grupo y se ven con signo menos.</p>
                </div>
              </>
            )}
          </>
        )}
      </ReportSheet>
    </>
  )
}
