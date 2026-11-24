/**
 * Gráficos de finanzas en SVG propio, con los tokens del sistema (sin librerías).
 *
 * Los importes llegan como string exacto. Para **dibujar** (alto o largo de una barra) se usa
 * `amountForGeometry`; todo número que se lee en pantalla sale del string original con
 * `formatMoney`, nunca de esa magnitud aproximada.
 *
 * Flujo mensual: columnas divergentes desde una sola línea base: lo que entra hacia arriba,
 * lo que sale hacia abajo (la posición dice el sentido; el color y la leyenda lo repiten).
 */
import { useEffect, useRef, useState } from 'react'
import { cx } from '../../lib/cx'
import { amountForGeometry, CURRENCY_SYMBOLS, formatMoney } from '../../lib/money'
import { monthLong, monthShort } from './labels'
import { monthsBetween, niceStep } from './period'
import type { CurrencyTotals } from './types'

export type MonthRow = CurrencyTotals & { month: string }

const compact = new Intl.NumberFormat('es-PY', { notation: 'compact', maximumFractionDigits: 1 })

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(el.clientWidth)
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

const HEIGHT = 220
const PAD = { top: 14, bottom: 30, left: 56, right: 8 }

export function MonthlyFlowChart({ rows, currency, from, to }: { rows: MonthRow[]; currency: string; from: string; to: string }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const [asTable, setAsTable] = useState(false)
  const zero = currency === 'PYG' ? '0' : '0.00'
  const byMonth = new Map(rows.map((r) => [r.month, r]))
  const months = monthsBetween(from, to).map((month) => byMonth.get(month) ?? { month, currency, income: zero, expense: zero, net: zero })

  const maxIn = Math.max(0, ...months.map((m) => amountForGeometry(m.income)))
  const maxOut = Math.max(0, ...months.map((m) => amountForGeometry(m.expense)))
  const step = niceStep(Math.max(maxIn, maxOut, 1))
  // Cada lado del cero ocupa lo que necesita: un lado chico no se estira hasta un paso entero.
  const side = (max: number) => (max <= 0 ? 0 : max < step * 0.6 ? max * 1.15 : Math.ceil(max / step) * step)
  const top = maxIn > 0 || maxOut <= 0 ? Math.max(side(maxIn), maxOut > 0 ? 0 : step) : 0
  const bottom = side(maxOut)
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const y = (v: number) => PAD.top + (plotH * (top - v)) / (top + bottom || 1)
  const baseline = y(0)
  const innerW = Math.max(0, width - PAD.left - PAD.right)
  const band = months.length ? innerW / months.length : 0
  const barW = Math.min(18, Math.max(3, (band - 6) / 2))
  const ticks: number[] = [0]
  for (let v = step; v <= top + 1e-9; v += step) ticks.push(v)
  for (let v = -step; v >= -bottom - 1e-9; v -= step) ticks.push(v)
  const labelEvery = band < 34 ? Math.ceil(34 / Math.max(band, 1)) : 1
  const active = hover !== null ? months[hover] : null
  const symbol = CURRENCY_SYMBOLS[currency] ?? currency

  /** Columna con el extremo de datos redondeado (4px) y la base recta. */
  const column = (x: number, value: number, up: boolean) => {
    const h = Math.abs(y(value) - baseline)
    if (h < 0.5) return ''
    const r = Math.min(4, h, barW / 2)
    const y0 = baseline
    const y1 = up ? baseline - h : baseline + h
    const s = up ? 1 : -1
    return `M${x},${y0} V${y1 + s * r} Q${x},${y1} ${x + r},${y1} H${x + barW - r} Q${x + barW},${y1} ${x + barW},${y1 + s * r} V${y0} Z`
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-4">
        <ul className="flex gap-4 text-sm text-ink-2" aria-label="Leyenda">
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-[2px] bg-chart-in" />
            Entradas (hacia arriba)
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-[2px] bg-chart-out" />
            Salidas (hacia abajo)
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-0.5 w-3 bg-ink" />
            Neto
          </li>
        </ul>
        <button type="button" onClick={() => setAsTable(!asTable)} aria-pressed={asTable} className="text-sm font-medium text-ledger hover:underline">
          {asTable ? 'Ver gráfico' : 'Ver como tabla'}
        </button>
      </div>
      {asTable ? (
        <table className="w-full text-sm">
          <caption className="sr-only">Entradas, salidas y neto por mes en {currency}</caption>
          <thead className="border-b border-line text-ink-2">
            <tr>
              <th scope="col" className="py-1.5 text-left font-medium">Mes</th>
              <th scope="col" className="py-1.5 text-right font-medium">Entradas</th>
              <th scope="col" className="py-1.5 text-right font-medium">Salidas</th>
              <th scope="col" className="py-1.5 text-right font-medium">Neto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {months.map((m) => (
              <tr key={m.month}>
                <th scope="row" className="py-1.5 text-left font-normal capitalize">{monthLong(m.month)}</th>
                <td className="py-1.5 text-right">{formatMoney(m.income, currency)}</td>
                <td className="py-1.5 text-right">{formatMoney(m.expense, currency)}</td>
                <td className={cx('py-1.5 text-right', m.net.startsWith('-') && 'text-debit')}>{formatMoney(m.net, currency, { sign: 'always' })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div ref={ref} className="relative">
          {width > 0 && (
            <svg width={width} height={HEIGHT} role="img" aria-label={`Entradas y salidas por mes en ${currency}. Usá Ver como tabla para los valores exactos.`}>
              {ticks.map((v) => (
                <g key={v}>
                  <line x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} stroke={v === 0 ? 'var(--line-strong)' : 'var(--line)'} strokeWidth={1} />
                  <text x={PAD.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-ink-3 text-[11px] tabular-nums">
                    {v === 0 ? `${symbol} 0` : `${v < 0 ? '−' : ''}${compact.format(Math.abs(v))}`}
                  </text>
                </g>
              ))}
              {months.map((m, i) => {
                const x0 = PAD.left + i * band
                const cx0 = x0 + band / 2
                const income = amountForGeometry(m.income)
                const expense = amountForGeometry(m.expense)
                const net = amountForGeometry(m.net)
                return (
                  <g key={m.month}>
                    {hover === i && <rect x={x0 + 1} y={PAD.top} width={band - 2} height={plotH} fill="var(--sunken)" />}
                    <path d={column(cx0 - barW - 1, income, true)} fill="var(--chart-in)" />
                    <path d={column(cx0 + 1, expense, false)} fill="var(--chart-out)" />
                    {(income > 0 || expense > 0) && (
                      <line x1={cx0 - barW - 3} x2={cx0 + barW + 3} y1={y(net)} y2={y(net)} stroke="var(--ink)" strokeWidth={2} strokeLinecap="round" />
                    )}
                    {i % labelEvery === 0 && (
                      <text x={cx0} y={HEIGHT - 10} textAnchor="middle" className="fill-ink-3 text-[11px]">
                        {monthShort(m.month)}
                      </text>
                    )}
                    <rect
                      x={x0}
                      y={0}
                      width={band}
                      height={HEIGHT}
                      fill="transparent"
                      tabIndex={0}
                      role="graphics-symbol"
                      aria-label={`${monthLong(m.month)}: entradas ${formatMoney(m.income, currency)}, salidas ${formatMoney(m.expense, currency)}, neto ${formatMoney(m.net, currency, { sign: 'always' })}`}
                      onMouseEnter={() => setHover(i)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(i)}
                      onBlur={() => setHover(null)}
                      className="outline-none focus-visible:stroke-(--focus) focus-visible:stroke-2"
                    />
                  </g>
                )
              })}
            </svg>
          )}
          {active && hover !== null && (
            <div
              role="presentation"
              className="pointer-events-none absolute z-10 w-56 rounded-md bg-surface px-3 py-2.5 text-sm shadow-(--shadow-float)"
              style={{
                top: 4,
                left: Math.min(Math.max(0, PAD.left + hover * band + band / 2 - 112), Math.max(0, width - 224)),
              }}
            >
              <p className="mb-1.5 font-semibold capitalize">{monthLong(active.month)}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums">
                <dt className="flex items-center gap-1.5 text-ink-2">
                  <span aria-hidden className="size-2 rounded-[2px] bg-chart-in" />
                  Entradas
                </dt>
                <dd className="text-right">{formatMoney(active.income, currency)}</dd>
                <dt className="flex items-center gap-1.5 text-ink-2">
                  <span aria-hidden className="size-2 rounded-[2px] bg-chart-out" />
                  Salidas
                </dt>
                <dd className="text-right">{formatMoney(active.expense, currency)}</dd>
                <dt className="border-t border-line pt-0.5 text-ink-2">Neto</dt>
                <dd className={cx('border-t border-line pt-0.5 text-right font-semibold', active.net.startsWith('-') && 'text-debit')}>
                  {formatMoney(active.net, currency, { sign: 'always' })}
                </dd>
              </dl>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Gastos por categoría: barras horizontales ordenadas, el importe exacto al final. */
export function CategoryBars({ rows, currency }: { rows: { key: string; label: string; amount: string }[]; currency: string }) {
  const max = Math.max(1, ...rows.map((r) => amountForGeometry(r.amount)))
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-ink-2" title={r.label}>
            {r.label}
          </span>
          <span className="h-2.5 rounded-r-[4px] bg-sunken">
            <span
              className="block h-full rounded-r-[4px] bg-chart-out"
              style={{ width: `${Math.max(0.5, (amountForGeometry(r.amount) / max) * 100)}%` }}
            />
          </span>
          <span className="text-right tabular-nums">{formatMoney(r.amount, currency)}</span>
        </li>
      ))}
    </ul>
  )
}
