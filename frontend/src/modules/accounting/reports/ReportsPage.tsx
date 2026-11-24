/** Libros y balances: diario, mayor, comprobación, balance general y estado de resultados. */
import type { ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { EmptyState, PageHeader } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { BalanceSheetReport } from './BalanceSheetReport'
import { IncomeStatementReport } from './IncomeStatementReport'
import { JournalReport } from './JournalReport'
import { LedgerReport } from './LedgerReport'
import { TrialBalanceReport } from './TrialBalanceReport'

const REPORTS: { slug: string; label: string; render: () => ReactNode; keep: string[] }[] = [
  { slug: 'diario', label: 'Libro diario', render: () => <JournalReport />, keep: ['from', 'to'] },
  { slug: 'mayor', label: 'Libro mayor', render: () => <LedgerReport />, keep: ['from', 'to', 'account_id'] },
  { slug: 'comprobacion', label: 'Balance de comprobación', render: () => <TrialBalanceReport />, keep: ['from', 'to'] },
  { slug: 'balance', label: 'Balance general', render: () => <BalanceSheetReport />, keep: ['at'] },
  { slug: 'resultados', label: 'Estado de resultados', render: () => <IncomeStatementReport />, keep: ['from', 'to'] },
]

export function ReportsPage() {
  const { report } = useParams()
  const { search } = useLocation()
  const current = REPORTS.find((r) => r.slug === report)
  // Al cambiar de reporte se conserva el alcance que tenga sentido (rango o fecha).
  const params = new URLSearchParams(search)
  const linkTo = (r: (typeof REPORTS)[number]) => {
    const keep = new URLSearchParams()
    for (const k of r.keep) {
      const v = params.get(k)
      if (v) keep.set(k, v)
    }
    if (r.keep.includes('at') && !params.get('at') && params.get('to')) keep.set('at', params.get('to') as string)
    const text = keep.toString()
    return `/contabilidad/reportes/${r.slug}${text ? `?${text}` : ''}`
  }
  return (
    <>
      <PageHeader title="Libros y balances" description="Calculados en el momento desde los asientos contabilizados (también los revertidos y sus reversiones, que se compensan). Los borradores no cuentan." />
      <nav aria-label="Reportes contables" className="mb-5 flex flex-wrap gap-1 border-b border-line">
        {REPORTS.map((r) => (
          <Link
            key={r.slug}
            to={linkTo(r)}
            aria-current={r.slug === report ? 'page' : undefined}
            className={cx(
              '-mb-px border-b-2 px-3.5 py-2 transition-colors',
              r.slug === report ? 'border-ledger font-semibold text-ink' : 'border-transparent text-ink-2 hover:border-line-strong hover:text-ink',
            )}
          >
            {r.label}
          </Link>
        ))}
      </nav>
      {current ? current.render() : <EmptyState title="Ese reporte no existe">Elegí uno de la lista de arriba.</EmptyState>}
    </>
  )
}
