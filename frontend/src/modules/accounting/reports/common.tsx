/** Piezas comunes de los libros y estados: rango en la URL, saldos con su lado y filas jerárquicas. */
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Button, Field, Input, Sheet } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { formatMoney, isNegative, isZeroAmount } from '../../../lib/money'
import { absPyg } from '../amounts'
import { useFiscalYears } from '../data'
import type { NormalSide, StatementNode } from '../types'
import { Pyg } from '../components'
import { useReportParams } from './params'

/** Barra de controles de un reporte (rango, fecha, cuenta) con atajos por ejercicio. */
export function ReportControls({ mode, children }: { mode: 'range' | 'at'; children?: ReactNode }) {
  const { from, to, at, set } = useReportParams()
  const years = useFiscalYears()
  const invalid = mode === 'range' && to < from
  return (
    <form
      onSubmit={(e) => e.preventDefault()}
      aria-label="Alcance del reporte"
      className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3 rounded-md border border-line bg-surface p-3.5"
    >
      {children}
      {mode === 'range' ? (
        <>
          <Field label="Desde">{(p) => <Input {...p} type="date" className="w-40" value={from} onChange={(e) => set({ from: e.target.value })} />}</Field>
          <Field label="Hasta" error={invalid ? 'Es anterior a «Desde».' : undefined}>
            {(p) => <Input {...p} type="date" className="w-40" value={to} onChange={(e) => set({ to: e.target.value })} />}
          </Field>
        </>
      ) : (
        <Field label="Al">{(p) => <Input {...p} type="date" className="w-40" value={at} onChange={(e) => set({ at: e.target.value })} />}</Field>
      )}
      {(years.data ?? []).length > 0 && (
        <div className="flex flex-wrap gap-1.5 pb-0.5" role="group" aria-label="Atajos por ejercicio">
          {(years.data ?? []).slice(0, 3).map((y) => {
            const label = y.start_date.slice(0, 4) === y.end_date.slice(0, 4) ? `Ejercicio ${y.start_date.slice(0, 4)}` : `Ejercicio ${y.start_date}`
            const activeNow = mode === 'range' ? from === y.start_date && to === y.end_date : at === y.end_date
            return (
              <Button
                key={y.id}
                type="button"
                variant="secondary"
                className={cx('h-8', activeNow && 'border-ledger bg-ledger-soft text-ledger hover:bg-ledger-soft')}
                aria-pressed={activeNow}
                onClick={() => set(mode === 'range' ? { from: y.start_date, to: y.end_date } : { at: y.end_date })}
              >
                {mode === 'range' ? label : `Cierre ${label.toLowerCase()}`}
              </Button>
            )
          })}
        </div>
      )}
    </form>
  )
}

/**
 * Saldo del libro mayor según la naturaleza de la cuenta (D-053): positivo = del lado de su
 * naturaleza. Se muestra la magnitud con «D» (deudor) o «A» (acreedor): no depende del color.
 */
export function SideBalance({ value, normal, strong }: { value: string; normal: NormalSide; strong?: boolean }) {
  if (isZeroAmount(value)) return <span className={cx('tabular-nums', strong && 'font-semibold')}>0</span>
  const side: NormalSide = isNegative(value) ? (normal === 'debit' ? 'credit' : 'debit') : normal
  const word = side === 'debit' ? 'deudor' : 'acreedor'
  return (
    <span className={cx('whitespace-nowrap tabular-nums', strong && 'font-semibold', side !== normal && 'text-debit')} title={`Saldo ${word}${side !== normal ? ', contrario a la naturaleza de la cuenta' : ''}`}>
      {formatMoney(absPyg(value), 'PYG', { symbol: false })}
      <span className="ml-1.5 inline-block w-3 text-xs font-medium text-ink-2" aria-hidden>
        {side === 'debit' ? 'D' : 'A'}
      </span>
      <span className="sr-only"> {word}</span>
    </span>
  )
}

/** Filas jerárquicas de un estado (balance general, resultados): las agrupadoras en negrita. */
export function StatementRows({ nodes, depth = 0, linkFor }: { nodes: StatementNode[]; depth?: number; linkFor?: (n: StatementNode) => string }) {
  return (
    <>
      {nodes.map((n) => (
        <StatementRow key={n.account_id} node={n} depth={depth} linkFor={linkFor} />
      ))}
    </>
  )
}

function StatementRow({ node, depth, linkFor }: { node: StatementNode; depth: number; linkFor?: (n: StatementNode) => string }) {
  const group = !node.is_postable
  const name = (
    <>
      <span className="mr-2 text-ink-2 tabular-nums">{node.code}</span>
      {node.name}
    </>
  )
  return (
    <>
      <tr className={cx(group && depth === 0 && 'bg-sunken/40')}>
        <td className={cx('py-1.5 pr-3', group && (depth === 0 ? 'font-semibold' : 'font-medium'))} style={{ paddingLeft: `${1 + depth * 1.1}rem` }}>
          {node.is_postable && linkFor ? (
            <Link to={linkFor(node)} className="hover:text-ledger hover:underline">
              {name}
            </Link>
          ) : (
            name
          )}
        </td>
        <td className="py-1.5 pr-4 text-right">
          <Pyg value={node.amount} strong={group && depth === 0} className={cx(group && depth > 0 && 'font-medium')} />
        </td>
      </tr>
      {node.children.length > 0 && <StatementRows nodes={node.children} depth={depth + 1} linkFor={linkFor} />}
    </>
  )
}

export function ReportSheet({ children, className }: { children: ReactNode; className?: string }) {
  return <Sheet className={cx('overflow-hidden', className)}>{children}</Sheet>
}
