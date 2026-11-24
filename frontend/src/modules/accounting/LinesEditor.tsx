/**
 * Grilla de líneas de un asiento (debe, haber, detalle, centro de costos y moneda extranjera)
 * con los totales en vivo y la diferencia hasta que balancea. La usan el editor de asientos y
 * el de plantillas recurrentes: el mismo teclado, las mismas reglas.
 */
import { CircleCheck, Coins, Keyboard, Plus, X } from 'lucide-react'
import { type Dispatch, type KeyboardEvent, type ReactNode, type SetStateAction, useEffect, useRef } from 'react'
import { Button, Input, Select, Sheet } from '../../components/ui'
import { cx } from '../../lib/cx'
import { formatMoney, parseAmountInput, toInputText } from '../../lib/money'
import { absPyg, formatDecimal, isWholeDecimal, multiplyDecimal, parseRateInput } from './amounts'
import { AccountCombobox, RuledTotal } from './components'
import { centerAllowed, emptyLine, type KindOf, type LineDraft, type LineErrors, readPyg, remainderFor, totalsOf } from './editor'
import type { LedgerAccount } from './types'
import type { CostCenter } from './types3b'

const FX_CURRENCIES = ['USD', 'BRL', 'ARS', 'EUR'] as const

type Col = 'account' | 'description' | 'center' | 'debit' | 'credit'

function AmountCell({
  value,
  onChange,
  label,
  invalid,
  inputRef,
  onKeyDown,
}: {
  value: string
  onChange: (v: string) => void
  label: string
  invalid?: boolean
  inputRef: (el: HTMLInputElement | null) => void
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void
}) {
  return (
    <input
      ref={inputRef}
      aria-label={label}
      aria-invalid={invalid || undefined}
      inputMode="numeric"
      autoComplete="off"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      onBlur={() => {
        const r = readPyg(value)
        if ('value' in r && r.value) onChange(toInputText(r.value, 'PYG'))
      }}
      className={cx(
        'h-9 w-full rounded-sm border border-transparent bg-transparent px-2.5 text-right tabular-nums',
        'hover:border-line-strong focus:border-line-strong focus:bg-surface aria-invalid:border-debit',
        value && 'font-medium',
      )}
    />
  )
}

export const Kbd = ({ children }: { children: ReactNode }) => (
  <kbd className="rounded-sm border border-line-strong bg-surface px-1.5 py-px font-sans text-xs text-ink-2">{children}</kbd>
)

export function LinesEditor({
  lines,
  setLines,
  errors,
  options,
  known,
  kindOf,
  centers,
  missingCenterKeys = [],
  allowFx = true,
  label = 'Líneas del asiento',
  onShortcutHint = true,
}: {
  lines: LineDraft[]
  setLines: Dispatch<SetStateAction<LineDraft[]>>
  /** Errores por línea (se muestran después del primer intento de guardar). */
  errors: Record<string, LineErrors>
  options: LedgerAccount[]
  known: Map<string, LedgerAccount>
  kindOf: KindOf
  /** Centros de costos (incluidos los archivados, para nombrar líneas viejas). */
  centers: CostCenter[]
  /** Líneas de resultado sin centro cuando la configuración lo exige. */
  missingCenterKeys?: string[]
  allowFx?: boolean
  label?: string
  onShortcutHint?: boolean
}) {
  const cells = useRef(new Map<string, HTMLInputElement | HTMLSelectElement>())
  const pendingFocus = useRef<string | null>(null)
  const totals = totalsOf(lines)
  const activeCenters = centers.filter((c) => !c.archived_at)
  const showCenters = activeCenters.length > 0 || lines.some((l) => l.cost_center_id)

  useEffect(() => {
    if (pendingFocus.current) {
      cells.current.get(pendingFocus.current)?.focus()
      pendingFocus.current = null
    }
  })

  const setLine = (key: string, change: Partial<LineDraft>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...change } : l)))
  const addLine = () => {
    const line = emptyLine(remainderFor(lines))
    setLines((ls) => [...ls, line])
    pendingFocus.current = `${line.key}:account`
  }
  const removeLine = (key: string) => setLines((ls) => (ls.length > 1 ? ls.filter((l) => l.key !== key) : [emptyLine()]))
  const cellAt = (index: number, col: Col) => {
    const target = lines[index]
    return target ? cells.current.get(`${target.key}:${col}`) : undefined
  }
  const navKeys = (index: number, col: Col) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || (e.key === 'Enter' && !e.ctrlKey && !e.metaKey)) {
      e.preventDefault()
      if (index === lines.length - 1) {
        if (e.key === 'Enter') addLine()
      } else cellAt(index + 1, col)?.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      cellAt(index - 1, col)?.focus()
    }
  }
  const diffPositive = !totals.difference.startsWith('-')
  const amountSpan = showCenters ? 4 : 3

  return (
    <>
      <Sheet>
        <table className="w-full table-fixed" aria-label={label}>
          <colgroup>
            <col className="w-10" />
            <col className={showCenters ? 'w-[30%]' : 'w-[34%]'} />
            <col />
            {showCenters && <col className="w-40" />}
            <col className="w-36" />
            <col className="w-36" />
            <col className={allowFx ? 'w-20' : 'w-12'} />
          </colgroup>
          <thead className="border-b border-line bg-sunken text-sm text-ink-2">
            <tr>
              <th scope="col" className="py-2.5 pl-4 text-left font-medium">
                <span className="sr-only">Línea</span>#
              </th>
              <th scope="col" className="px-2.5 py-2.5 text-left font-medium">Cuenta</th>
              <th scope="col" className="px-2.5 py-2.5 text-left font-medium">Detalle de la línea</th>
              {showCenters && (
                <th scope="col" className="px-2.5 py-2.5 text-left font-medium" title="Solo en cuentas de ingreso o de gasto">
                  Centro de costos
                </th>
              )}
              <th scope="col" className="px-2.5 py-2.5 text-right font-medium">Debe</th>
              <th scope="col" className="px-2.5 py-2.5 text-right font-medium">Haber</th>
              <th scope="col">
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <LineRows
                key={l.key}
                line={l}
                n={i + 1}
                errors={errors[l.key]}
                centerMissing={missingCenterKeys.includes(l.key)}
                options={options}
                known={known}
                kindOf={kindOf}
                centers={centers}
                showCenters={showCenters}
                allowFx={allowFx}
                register={(col, el) => {
                  const k = `${l.key}:${col}`
                  if (el) cells.current.set(k, el)
                  else cells.current.delete(k)
                }}
                nav={(col) => navKeys(i, col)}
                onChange={(change) => setLine(l.key, change)}
                onRemove={() => removeLine(l.key)}
                onAccountKey={(e, open) => {
                  if (!open && e.key === 'Enter') {
                    e.preventDefault()
                    cells.current.get(`${l.key}:${l.credit ? 'credit' : 'debit'}`)?.focus()
                  }
                }}
              />
            ))}
          </tbody>
          <tfoot className="border-t-2 border-line-strong">
            <tr>
              <td colSpan={amountSpan} className="px-4 py-3">
                <Button type="button" variant="ghost" className="-ml-2" onClick={addLine}>
                  <Plus size={15} />
                  Agregar línea
                </Button>
              </td>
              <td className="py-3 pr-4 pl-1.5 text-right">
                <RuledTotal value={totals.debit} label={`Total debe ${formatMoney(totals.debit, 'PYG')}`} />
              </td>
              <td className="py-3 pr-4 pl-1.5 text-right">
                <RuledTotal value={totals.credit} label={`Total haber ${formatMoney(totals.credit, 'PYG')}`} />
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
        <div
          role="status"
          aria-live="polite"
          aria-label="Balance del asiento"
          className={cx(
            'flex flex-wrap items-center gap-x-5 gap-y-1 rounded-b-md border-t px-5 py-3.5',
            totals.balanced ? 'border-line bg-ledger-soft' : totals.hasAmounts ? 'border-amber/40 bg-amber-soft' : 'border-line bg-sunken',
          )}
        >
          {totals.balanced ? (
            <p className="flex items-center gap-2 font-medium text-ledger">
              <CircleCheck size={18} aria-hidden />
              Balancea: el debe y el haber suman {formatMoney(totals.debit, 'PYG')}.
            </p>
          ) : !totals.hasAmounts ? (
            <p className="text-ink-2">Todavía sin importes: cada línea va al debe o al haber. Los totales y la diferencia se calculan mientras escribís.</p>
          ) : (
            <>
              <p className="flex items-baseline gap-3">
                <span className="text-sm font-medium text-amber">Diferencia</span>
                <span className="text-lg font-semibold text-ink tabular-nums" data-testid="diferencia">
                  {formatMoney(absPyg(totals.difference), 'PYG')}
                </span>
              </p>
              <p className="text-sm text-ink-2">
                {diffPositive ? 'Sobra debe: falta ese importe en el haber.' : 'Sobra haber: falta ese importe en el debe.'} Una línea nueva lo propone
                sola.
              </p>
            </>
          )}
        </div>
      </Sheet>

      <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-3">
        <Keyboard size={15} aria-hidden />
        <span>
          <Kbd>Tab</Kbd> pasa de celda en celda
        </span>
        <span>
          <Kbd>Enter</Kbd> o <Kbd>↓</Kbd> baja de línea; en la última, agrega otra
        </span>
        {onShortcutHint && (
          <span>
            <Kbd>Ctrl</Kbd> + <Kbd>S</Kbd> guarda
          </span>
        )}
        {showCenters && <span>El centro de costos solo se ofrece en cuentas de ingreso o de gasto.</span>}
      </p>
    </>
  )
}

function LineRows({
  line,
  n,
  errors,
  centerMissing,
  options,
  known,
  kindOf,
  centers,
  showCenters,
  allowFx,
  register,
  nav,
  onChange,
  onRemove,
  onAccountKey,
}: {
  line: LineDraft
  n: number
  errors?: LineErrors
  centerMissing: boolean
  options: LedgerAccount[]
  known: Map<string, LedgerAccount>
  kindOf: KindOf
  centers: CostCenter[]
  showCenters: boolean
  allowFx: boolean
  register: (col: Col, el: HTMLInputElement | HTMLSelectElement | null) => void
  nav: (col: Col) => (e: KeyboardEvent<HTMLInputElement>) => void
  onChange: (change: Partial<LineDraft>) => void
  onRemove: () => void
  onAccountKey: (e: KeyboardEvent<HTMLInputElement>, open: boolean) => void
}) {
  const debitErr = readPyg(line.debit)
  const creditErr = readPyg(line.credit)
  const cellError = 'error' in debitErr ? debitErr.error : 'error' in creditErr ? creditErr.error : undefined
  const centerMessage = centerMissing ? 'Elegí el centro de costos: la configuración lo exige en ingresos y gastos para contabilizar.' : undefined
  const message = errors?.account ?? errors?.amount ?? cellError ?? errors?.center ?? centerMessage
  const fx = line.fx
  const allowed = centerAllowed(kindOf(line.account_id))
  const centerOptions = centers.filter((c) => !c.archived_at || c.id === line.cost_center_id)
  const fxProduct = (() => {
    if (!fx) return null
    const a = parseAmountInput(fx.amount, fx.currency)
    const r = parseRateInput(fx.rate)
    if (!a.ok || !r.ok || a.value.startsWith('-')) return null
    return multiplyDecimal(a.value, r.value)
  })()
  const span = showCenters ? 6 : 5
  return (
    <>
      <tr className={cx('border-t border-line first:border-t-0', message && 'bg-debit-soft/40')}>
        <td className="py-1.5 pl-4 text-sm text-ink-3 tabular-nums">{n}</td>
        <td className="px-1.5 py-1.5">
          <AccountCombobox
            aria-label={`Cuenta de la línea ${n}`}
            aria-invalid={Boolean(errors?.account) || undefined}
            accounts={options}
            known={known}
            value={line.account_id}
            // Al pasar a una cuenta patrimonial, el centro deja de corresponder.
            onChange={(id) => onChange({ account_id: id, ...(centerAllowed(kindOf(id)) ? {} : { cost_center_id: '' }) })}
            inputRef={(el) => register('account', el)}
            onKeyDown={onAccountKey}
          />
        </td>
        <td className="px-1.5 py-1.5">
          <input
            ref={(el) => register('description', el)}
            aria-label={`Detalle de la línea ${n}`}
            maxLength={300}
            value={line.description}
            onChange={(e) => onChange({ description: e.target.value })}
            onKeyDown={nav('description')}
            placeholder="Opcional"
            className="h-9 w-full rounded-sm border border-transparent bg-transparent px-2.5 placeholder:text-ink-3 hover:border-line-strong focus:border-line-strong focus:bg-surface"
          />
        </td>
        {showCenters && (
          <td className="px-1.5 py-1.5">
            {allowed ? (
              <select
                ref={(el) => register('center', el)}
                aria-label={`Centro de costos de la línea ${n}`}
                aria-invalid={centerMissing || undefined}
                value={line.cost_center_id}
                onChange={(e) => onChange({ cost_center_id: e.target.value })}
                className="h-9 w-full truncate rounded-sm border border-transparent bg-transparent px-2 text-base hover:border-line-strong focus:border-line-strong focus:bg-surface aria-invalid:border-debit"
              >
                <option value="">Sin centro</option>
                {centerOptions.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} {c.name}
                    {c.archived_at ? ' (archivado)' : ''}
                  </option>
                ))}
              </select>
            ) : (
              <span className="block px-2.5 text-sm text-ink-3" title="El centro de costos va solo en cuentas de ingreso o de gasto">
                {line.account_id ? '—' : ''}
                <span className="sr-only">{line.account_id ? 'No corresponde: la cuenta no es de ingreso ni de gasto' : ''}</span>
              </span>
            )}
          </td>
        )}
        <td className="px-1.5 py-1.5">
          <AmountCell
            label={`Debe de la línea ${n}`}
            value={line.debit}
            invalid={Boolean(errors?.amount) || 'error' in debitErr}
            inputRef={(el) => register('debit', el)}
            onKeyDown={nav('debit')}
            onChange={(v) => onChange(v.trim() ? { debit: v, credit: '' } : { debit: v })}
          />
        </td>
        <td className="px-1.5 py-1.5">
          <AmountCell
            label={`Haber de la línea ${n}`}
            value={line.credit}
            invalid={Boolean(errors?.amount) || 'error' in creditErr}
            inputRef={(el) => register('credit', el)}
            onKeyDown={nav('credit')}
            onChange={(v) => onChange(v.trim() ? { credit: v, debit: '' } : { credit: v })}
          />
        </td>
        <td className="pr-2">
          <div className="flex justify-end">
            {allowFx && (
              <Button
                type="button"
                variant="ghost"
                className={cx('h-8 px-1.5', fx && 'text-ledger')}
                aria-label={fx ? `Quitar moneda extranjera de la línea ${n}` : `Moneda extranjera en la línea ${n}`}
                aria-pressed={Boolean(fx)}
                title="Moneda extranjera (informativa)"
                onClick={() => onChange({ fx: fx ? null : { currency: 'USD', amount: '', rate: '' } })}
              >
                <Coins size={15} />
              </Button>
            )}
            <Button type="button" variant="ghost" className="h-8 px-1.5 hover:text-debit" aria-label={`Quitar la línea ${n}`} title="Quitar la línea" onClick={onRemove}>
              <X size={15} />
            </Button>
          </div>
        </td>
      </tr>
      {fx && (
        <tr className="bg-sunken/50">
          <td />
          <td colSpan={span} className="px-1.5 pt-1 pb-2.5">
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-sm text-ink-2">
                Moneda
                <Select className="h-8 w-24" value={fx.currency} onChange={(e) => onChange({ fx: { ...fx, currency: e.target.value } })}>
                  {FX_CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink-2">
                Importe en {fx.currency}
                <Input className="h-8 w-36 text-right tabular-nums" inputMode="decimal" value={fx.amount} onChange={(e) => onChange({ fx: { ...fx, amount: e.target.value } })} />
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink-2">
                Cotización (₲ por 1 {fx.currency})
                <Input className="h-8 w-36 text-right tabular-nums" inputMode="decimal" value={fx.rate} onChange={(e) => onChange({ fx: { ...fx, rate: e.target.value } })} />
              </label>
              <p className="pb-1.5 text-sm text-ink-3">
                {fxProduct ? (
                  <>
                    Producto: ₲ {formatDecimal(fxProduct)}
                    {!isWholeDecimal(fxProduct) && ' (no es entero: redondealo en el debe o el haber)'}.{' '}
                  </>
                ) : null}
                Informativo: el asiento balancea en guaraníes.
              </p>
            </div>
            {errors?.fx && <p className="mt-1 text-sm text-debit">{errors.fx}</p>}
          </td>
        </tr>
      )}
      {message && (
        <tr className="bg-debit-soft/40">
          <td />
          <td colSpan={span} className="px-3 pb-2 text-sm text-debit">
            Línea {n}: {message}
          </td>
        </tr>
      )}
    </>
  )
}
