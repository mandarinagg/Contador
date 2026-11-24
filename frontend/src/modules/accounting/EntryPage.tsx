/**
 * Un asiento: editor del borrador (con totales en vivo y la diferencia hasta que balancea) o
 * vista de solo lectura del contabilizado, revertido o descartado, con sus vínculos.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookCheck, CircleCheck, Coins, Keyboard, Plus, Trash2, Undo2, X } from 'lucide-react'
import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router'
import { Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Skeleton, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime } from '../../lib/format'
import { CURRENCY_SYMBOLS, formatMoney, parseAmountInput, toInputText } from '../../lib/money'
import { ApiError, patch, post } from '../../services/api'
import { ApiErrorNotice } from '../finance/components'
import { formatBookDate, todayIso } from '../finance/labels'
import { absPyg, formatDecimal, isWholeDecimal, multiplyDecimal, parseRateInput } from './amounts'
import { postableAccounts } from './chartTree'
import { AccountCombobox, Blank, EntryStatusBadge, Pyg, RuledTotal } from './components'
import { accountingKeys, useAccountingPerms, useAccountsById, useChart, useEntry, useFiscalYears, useInvalidateAccounting, useUserName } from './data'
import { buildEntry, emptyLine, fingerprint, type HeaderDraft, type LineDraft, linesFromEntry, readPyg, remainderFor, totalsOf } from './editor'
import { ENTRY_KIND_LABELS, entryLabel, longDate, monthName } from './labels'
import type { Entry, FiscalYear, LedgerAccount } from './types'

const FX_CURRENCIES = ['USD', 'BRL', 'ARS', 'EUR'] as const

/** El ejercicio y el período de una fecha, si existen. */
function locate(years: FiscalYear[] | undefined, date: string) {
  if (!years || !date) return null
  const year = years.find((y) => y.start_date <= date && date <= y.end_date)
  const period = year?.periods.find((p) => p.start_date <= date && date <= p.end_date)
  return year ? { year, period } : { year: undefined, period: undefined }
}

// --- Celda de importe -------------------------------------------------------------------

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

// --- Editor ---------------------------------------------------------------------------------

type Col = 'account' | 'description' | 'debit' | 'credit'

function EntryEditor({ entry }: { entry?: Entry }) {
  const perms = useAccountingPerms()
  const chart = useChart()
  const years = useFiscalYears()
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const invalidate = useInvalidateAccounting()
  const byId = useAccountsById(chart.data?.accounts)
  const options = useMemo(() => postableAccounts(chart.data?.accounts ?? []), [chart.data])

  const [header, setHeader] = useState<HeaderDraft>(() => ({
    entry_date: entry?.entry_date ?? todayIso(),
    description: entry?.description ?? '',
    document_reference: entry?.document_reference ?? '',
  }))
  const [lines, setLines] = useState<LineDraft[]>(() => (entry ? linesFromEntry(entry) : [emptyLine(), emptyLine()]))
  // Un asiento nuevo sin tocar no tiene cambios: salir no pide confirmación.
  const [saved, setSaved] = useState(() => fingerprint(header, lines))
  const [showErrors, setShowErrors] = useState(false)
  const [dialog, setDialog] = useState<'discard' | null>(null)
  const cells = useRef(new Map<string, HTMLInputElement>())
  const pendingFocus = useRef<string | null>(null)

  const totals = totalsOf(lines)
  const build = buildEntry(header, lines)
  const dirty = fingerprint(header, lines) !== saved
  const where = locate(years.data, header.entry_date)
  const periodClosed = where?.period?.status === 'closed'
  const yearClosed = where?.year?.status === 'closed'
  const noYear = Boolean(header.entry_date && years.data && !where?.year)

  useEffect(() => {
    if (pendingFocus.current) {
      cells.current.get(pendingFocus.current)?.focus()
      pendingFocus.current = null
    }
  })

  const setLine = (key: string, change: Partial<LineDraft>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...change } : l)))
  const addLine = (focus = true) => {
    const line = emptyLine(remainderFor(lines))
    setLines((ls) => [...ls, line])
    if (focus) pendingFocus.current = `${line.key}:account`
  }
  const removeLine = (key: string) => setLines((ls) => (ls.length > 1 ? ls.filter((l) => l.key !== key) : [emptyLine()]))

  const cellKeys = (index: number, col: Col): HTMLInputElement | undefined => {
    const target = lines[index]
    return target ? cells.current.get(`${target.key}:${col}`) : undefined
  }
  const navKeys = (index: number, col: Col) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || (e.key === 'Enter' && !e.ctrlKey && !e.metaKey)) {
      e.preventDefault()
      if (index === lines.length - 1) {
        if (e.key === 'Enter') addLine()
      } else cellKeys(index + 1, col)?.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      cellKeys(index - 1, col)?.focus()
    }
  }

  const persist = async (): Promise<Entry | null> => {
    setShowErrors(true)
    if (!build.body) return null
    const result = entry ? await patch<Entry>(`/accounting/entries/${entry.id}`, build.body) : await post<Entry>('/accounting/entries', build.body)
    qc.setQueryData(accountingKeys.entry(result.id), result)
    setSaved(fingerprint(header, lines))
    return result
  }

  const save = useMutation({
    mutationFn: persist,
    onSuccess: (result) => {
      if (!result) return
      invalidate()
      toast('ok', entry ? 'Borrador guardado.' : 'Borrador creado. Todavía no está en los libros: falta contabilizarlo.')
      if (!entry) navigate(`/contabilidad/asientos/${result.id}`, { replace: true })
    },
  })
  const postEntry = useMutation({
    mutationFn: async () => {
      const current = dirty || !entry ? await persist() : entry
      if (!current) return null
      try {
        return await post<Entry>(`/accounting/entries/${current.id}/post`)
      } catch (e) {
        if (!entry) navigate(`/contabilidad/asientos/${current.id}`, { replace: true })
        throw e
      }
    },
    onSuccess: (result) => {
      if (!result) return
      qc.setQueryData(accountingKeys.entry(result.id), result)
      invalidate()
      toast('ok', `Asiento N° ${result.number} contabilizado.`)
      if (!entry) navigate(`/contabilidad/asientos/${result.id}`, { replace: true })
    },
  })
  const busy = save.isPending || postEntry.isPending
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !busy && currentLocation.pathname !== nextLocation.pathname)

  const onShortcut = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault()
      if (!busy) save.mutate()
    }
  }

  const lineErrors = showErrors ? build.lines : {}
  const canPostNow = perms.canPost && totals.balanced && !periodClosed && !yearClosed && !noYear
  const postBlocker = !totals.balanced
    ? 'Para contabilizar, el debe y el haber tienen que sumar lo mismo.'
    : noYear
      ? 'La fecha no cae en ningún ejercicio.'
      : yearClosed
        ? 'El ejercicio de esa fecha está cerrado.'
        : periodClosed
          ? `${monthName(header.entry_date)} está cerrado: no se contabiliza con fecha en ese mes.`
          : ''
  const error = save.error ?? postEntry.error
  const apiError = error instanceof ApiError ? error : null
  const diffPositive = !totals.difference.startsWith('-')

  return (
    <div onKeyDown={onShortcut}>
      <PageHeader
        title={entry ? 'Borrador de asiento' : 'Nuevo asiento'}
        description={
          entry?.kind === 'finance'
            ? 'Propuesto desde un movimiento de la empresa. Revisalo: no está en los libros hasta que alguien lo contabilice.'
            : 'Un borrador se puede guardar desbalanceado y corregir cuantas veces haga falta. Al contabilizarlo recibe su número y ya no cambia.'
        }
        actions={
          <Link to="/contabilidad/asientos" className="inline-flex h-9 items-center gap-2 rounded-sm px-3 text-ink-2 hover:bg-sunken hover:text-ink">
            <ArrowLeft size={16} />
            Asientos
          </Link>
        }
      />

      {apiError && (
        <div className="mb-4">
          <Notice tone="bad" title={apiError.message}>
            {apiError.code === 'FISCAL_YEAR_NOT_FOUND' || apiError.code === 'PERIOD_CLOSED' || apiError.code === 'FISCAL_YEAR_CLOSED' ? (
              <Link to="/contabilidad/ejercicios" className="font-medium underline">
                Ir a Ejercicios y períodos
              </Link>
            ) : (
              Object.values(apiError.fieldErrors()).join(' ') || null
            )}
          </Notice>
        </div>
      )}

      <Sheet className="mb-5 grid grid-cols-[11rem_minmax(0,1fr)_14rem] gap-4 p-5">
        <Field
          label="Fecha"
          error={showErrors ? build.header.entry_date : undefined}
          hint={noYear ? 'Sin ejercicio para esa fecha.' : periodClosed ? `${monthName(header.entry_date)} está cerrado.` : where?.year ? `Ejercicio ${where.year.start_date.slice(0, 4)}` : undefined}
        >
          {(p) => <Input {...p} type="date" value={header.entry_date} onChange={(e) => setHeader({ ...header, entry_date: e.target.value })} />}
        </Field>
        <Field label="Descripción" error={showErrors ? build.header.description : undefined}>
          {(p) => <Input {...p} autoFocus={!entry} maxLength={500} placeholder="Qué registra: «Cobro de la factura 001-001-0000123»" value={header.description} onChange={(e) => setHeader({ ...header, description: e.target.value })} />}
        </Field>
        <Field label="Comprobante" hint="Factura, recibo u operación que lo respalda.">
          {(p) => <Input {...p} maxLength={100} value={header.document_reference} onChange={(e) => setHeader({ ...header, document_reference: e.target.value })} />}
        </Field>
      </Sheet>

      <Sheet>
        <table className="w-full table-fixed" aria-label="Líneas del asiento">
          <colgroup>
            <col className="w-10" />
            <col className="w-[34%]" />
            <col />
            <col className="w-40" />
            <col className="w-40" />
            <col className="w-20" />
          </colgroup>
          <thead className="border-b border-line bg-sunken text-sm text-ink-2">
            <tr>
              <th scope="col" className="py-2.5 pl-4 text-left font-medium">
                <span className="sr-only">Línea</span>#
              </th>
              <th scope="col" className="px-2.5 py-2.5 text-left font-medium">Cuenta</th>
              <th scope="col" className="px-2.5 py-2.5 text-left font-medium">Detalle de la línea</th>
              <th scope="col" className="px-2.5 py-2.5 text-right font-medium">Debe</th>
              <th scope="col" className="px-2.5 py-2.5 text-right font-medium">Haber</th>
              <th scope="col">
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => {
              const errs = lineErrors[l.key]
              const n = i + 1
              return (
                <LineRows
                  key={l.key}
                  line={l}
                  n={n}
                  errors={errs}
                  options={options}
                  known={byId}
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
              )
            })}
          </tbody>
          <tfoot className="border-t-2 border-line-strong">
            <tr>
              <td colSpan={3} className="px-4 py-3">
                <Button type="button" variant="ghost" className="-ml-2" onClick={() => addLine()}>
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
        <span>
          <Kbd>Ctrl</Kbd> + <Kbd>S</Kbd> guarda el borrador
        </span>
      </p>

      {showErrors && build.general && (
        <div className="mt-4">
          <Notice tone="bad" title={build.general} />
        </div>
      )}
      {showErrors && Object.keys(build.lines).length > 0 && (
        <div className="mt-4">
          <Notice tone="bad" title="Hay líneas para corregir">Están marcadas en rojo, con el motivo debajo.</Notice>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-5">
        {perms.canPost ? (
          <Button onClick={() => postEntry.mutate()} busy={postEntry.isPending} disabled={!canPostNow || save.isPending}>
            <BookCheck size={16} />
            Contabilizar
          </Button>
        ) : null}
        <Button variant="secondary" onClick={() => save.mutate()} busy={save.isPending} disabled={postEntry.isPending || (Boolean(entry) && !dirty)}>
          Guardar borrador
        </Button>
        {entry && (
          <Button variant="ghost" className="hover:text-debit" onClick={() => setDialog('discard')}>
            <Trash2 size={15} />
            Descartar borrador
          </Button>
        )}
        <p className="ml-auto max-w-md text-right text-sm text-ink-3">
          {!perms.canPost ? perms.postReason : postBlocker || (dirty && entry ? 'Hay cambios sin guardar: contabilizar los guarda primero.' : 'Al contabilizar recibe el próximo número del ejercicio.')}
        </p>
      </div>

      <Modal open={dialog === 'discard'} title="Descartar borrador" onClose={() => setDialog(null)}>
        {dialog === 'discard' && entry && <DiscardForm entry={entry} onDone={() => setDialog(null)} />}
      </Modal>
      <Modal open={blocker.state === 'blocked'} title="Hay cambios sin guardar" onClose={() => blocker.reset?.()}>
        <div className="flex flex-col gap-4">
          <p className="text-ink-2">Si salís ahora, se pierden los cambios del asiento que no guardaste.</p>
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button variant="ghost" onClick={() => blocker.reset?.()}>
              Seguir editando
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Salir sin guardar
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

const Kbd = ({ children }: { children: ReactNode }) => (
  <kbd className="rounded-sm border border-line-strong bg-surface px-1.5 py-px font-sans text-xs text-ink-2">{children}</kbd>
)

function LineRows({
  line,
  n,
  errors,
  options,
  known,
  register,
  nav,
  onChange,
  onRemove,
  onAccountKey,
}: {
  line: LineDraft
  n: number
  errors?: Partial<Record<'account' | 'amount' | 'fx', string>>
  options: LedgerAccount[]
  known: Map<string, LedgerAccount>
  register: (col: Col, el: HTMLInputElement | null) => void
  nav: (col: Col) => (e: KeyboardEvent<HTMLInputElement>) => void
  onChange: (change: Partial<LineDraft>) => void
  onRemove: () => void
  onAccountKey: (e: KeyboardEvent<HTMLInputElement>, open: boolean) => void
}) {
  const debitErr = readPyg(line.debit)
  const creditErr = readPyg(line.credit)
  const cellError = 'error' in debitErr ? debitErr.error : 'error' in creditErr ? creditErr.error : undefined
  const message = errors?.account ?? errors?.amount ?? cellError
  const fx = line.fx
  const fxProduct = (() => {
    if (!fx) return null
    const a = parseAmountInput(fx.amount, fx.currency)
    const r = parseRateInput(fx.rate)
    if (!a.ok || !r.ok || a.value.startsWith('-')) return null
    return multiplyDecimal(a.value, r.value)
  })()
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
            onChange={(id) => onChange({ account_id: id })}
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
            <Button type="button" variant="ghost" className="h-8 px-1.5 hover:text-debit" aria-label={`Quitar la línea ${n}`} title="Quitar la línea" onClick={onRemove}>
              <X size={15} />
            </Button>
          </div>
        </td>
      </tr>
      {fx && (
        <tr className="bg-sunken/50">
          <td />
          <td colSpan={5} className="px-1.5 pt-1 pb-2.5">
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
          <td colSpan={5} className="px-3 pb-2 text-sm text-debit">
            Línea {n}: {message}
          </td>
        </tr>
      )}
    </>
  )
}

function DiscardForm({ entry, onDone }: { entry: Entry; onDone: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const invalidate = useInvalidateAccounting()
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const bad = reason.trim().length < 3
  const run = useMutation({
    mutationFn: () => post<Entry>(`/accounting/entries/${entry.id}/discard`, { reason: reason.trim() }),
    onSuccess: (e) => {
      qc.setQueryData(accountingKeys.entry(e.id), e)
      invalidate()
      toast('ok', 'Borrador descartado. Queda en el listado como descartado, con tu motivo.')
      onDone()
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(ev) => {
        ev.preventDefault()
        setTouched(true)
        if (!bad) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Nada se borra: el borrador queda como descartado, sin número, con el motivo.
        {entry.kind === 'finance' && ' El movimiento de finanzas vuelve a quedar sin asiento y se puede proponer de nuevo.'}
      </p>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      <Field label="Motivo" error={touched && bad ? 'Escribí el motivo (al menos 3 caracteres).' : undefined}>
        {(p) => <Textarea {...p} autoFocus maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" busy={run.isPending}>
          Descartar borrador
        </Button>
      </div>
    </form>
  )
}

// --- Reversión ------------------------------------------------------------------------------

function ReverseForm({ entry, onDone }: { entry: Entry; onDone: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const invalidate = useInvalidateAccounting()
  const years = useFiscalYears()
  const [reason, setReason] = useState('')
  const [date, setDate] = useState(entry.entry_date)
  const [needsDate, setNeedsDate] = useState(false)
  const [touched, setTouched] = useState(false)
  const dateRef = useRef<HTMLInputElement>(null)
  const bad = reason.trim().length < 3
  const run = useMutation({
    mutationFn: () => post<Entry>(`/accounting/entries/${entry.id}/reverse`, { reason: reason.trim(), ...(date !== entry.entry_date ? { date } : {}) }),
    onSuccess: (reversal) => {
      qc.setQueryData(accountingKeys.entry(reversal.id), reversal)
      invalidate()
      toast('ok', `Reversión contabilizada: asiento N° ${reversal.number}. El N° ${entry.number} quedó revertido.`)
      onDone()
      navigate(`/contabilidad/asientos/${reversal.id}`)
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'PERIOD_CLOSED') {
        setNeedsDate(true)
        // Sugerencia: el primer día abierto desde la fecha del original.
        const open = (years.data ?? [])
          .flatMap((y) => (y.status === 'open' ? y.periods : []))
          .filter((p) => p.status === 'open' && p.end_date >= entry.entry_date)
          .sort((a, b) => a.start_date.localeCompare(b.start_date))[0]
        if (open) setDate(open.start_date > entry.entry_date ? open.start_date : entry.entry_date)
        setTimeout(() => dateRef.current?.focus(), 0)
      }
    },
  })
  const where = locate(years.data, date)
  const dateBad = date < entry.entry_date
  const err = run.error instanceof ApiError ? run.error : null
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(ev) => {
        ev.preventDefault()
        setTouched(true)
        if (!bad && !dateBad) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Un asiento contabilizado no se modifica: se compensa con otro, de reversión, con las mismas cuentas y el debe y el haber invertidos. Se
        contabiliza en el mismo acto, recibe su propio número y el N° {entry.number} queda revertido.
      </p>
      {err && (
        <Notice tone={err.code === 'PERIOD_CLOSED' ? 'warn' : 'bad'} title={err.code === 'PERIOD_CLOSED' ? 'El período del asiento está cerrado' : err.message}>
          {err.code === 'PERIOD_CLOSED' ? 'Elegí una fecha en un período abierto, igual o posterior a la del asiento original, y volvé a confirmar.' : null}
        </Notice>
      )}
      <Field label="Motivo de la reversión" error={touched && bad ? 'Escribí el motivo (al menos 3 caracteres).' : undefined}>
        {(p) => <Textarea {...p} autoFocus maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <Field
        label="Fecha de la reversión"
        error={dateBad ? 'No puede ser anterior al asiento original.' : undefined}
        hint={
          needsDate
            ? where?.period
              ? `${monthName(date)} ${where.period.status === 'open' ? 'está abierto' : 'también está cerrado'}.`
              : 'Esa fecha no cae en ningún ejercicio.'
            : `Por defecto, la del original (${formatBookDate(entry.entry_date)}).`
        }
      >
        {(p) => <Input {...p} ref={dateRef} type="date" className="w-44" min={entry.entry_date} value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" busy={run.isPending}>
          <Undo2 size={15} />
          Revertir el asiento N° {entry.number}
        </Button>
      </div>
    </form>
  )
}

// --- Vista de solo lectura ---------------------------------------------------------------

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-ink-3">{label}</dt>
      <dd className="mt-0.5 break-words">{children}</dd>
    </div>
  )
}

function RelatedLink({ id, prefix }: { id: string; prefix: string }) {
  const related = useEntry(id)
  return (
    <Link to={`/contabilidad/asientos/${id}`} className="font-medium text-ledger hover:underline">
      {prefix} {related.data ? entryLabel(related.data) : '…'}
    </Link>
  )
}

function EntryView({ entry }: { entry: Entry }) {
  const perms = useAccountingPerms()
  const userName = useUserName()
  const [dialog, setDialog] = useState<'reverse' | null>(null)
  const reversible = entry.status === 'posted' && (entry.kind === 'manual' || entry.kind === 'finance')
  const lines = entry.lines ?? []
  const yearOf = entry.entry_date.slice(0, 4)
  const title = entry.number !== null ? `Asiento N° ${entry.number}` : entry.status === 'discarded' ? 'Asiento descartado' : 'Borrador de asiento'

  return (
    <>
      <PageHeader
        title={title}
        description={entry.description}
        actions={
          <>
            <Link to="/contabilidad/asientos" className="inline-flex h-9 items-center gap-2 rounded-sm px-3 text-ink-2 hover:bg-sunken hover:text-ink">
              <ArrowLeft size={16} />
              Asientos
            </Link>
            {reversible && perms.canPost && (
              <Button variant="danger" onClick={() => setDialog('reverse')}>
                <Undo2 size={15} />
                Revertir
              </Button>
            )}
          </>
        }
      />
      {reversible && !perms.canPost && <p className="-mt-3 mb-4 text-sm text-ink-3">{perms.postReason}</p>}
      {entry.status === 'draft' && (
        <div className="mb-4">
          <Notice tone="warn" title="Borrador: todavía no está en los libros">
            {perms.manageReason || 'Lo puede corregir y contabilizar alguien con permiso.'}
          </Notice>
        </div>
      )}
      {entry.status === 'discarded' && (
        <div className="mb-4">
          <Notice tone="neutral" title="Borrador descartado">
            Motivo: {entry.discard_reason}. Lo descartó {userName(entry.discarded_by)} el {formatDateTime(entry.discarded_at as string)}.
          </Notice>
        </div>
      )}

      <Sheet className="mb-5 px-5 py-4">
        <dl className="grid grid-cols-4 gap-x-6 gap-y-4">
          <Meta label="Fecha">{longDate(entry.entry_date)}</Meta>
          <Meta label="Estado">
            <EntryStatusBadge status={entry.status} />
          </Meta>
          <Meta label="Tipo">{ENTRY_KIND_LABELS[entry.kind]}</Meta>
          <Meta label="Comprobante">{entry.document_reference ?? <span className="text-ink-3">Sin comprobante</span>}</Meta>
          {entry.posted_at && (
            <Meta label="Contabilizado">
              {formatDateTime(entry.posted_at)}
              <span className="block text-sm text-ink-2">por {userName(entry.posted_by)}</span>
            </Meta>
          )}
          <Meta label="Creado">
            {formatDateTime(entry.created_at)}
            <span className="block text-sm text-ink-2">por {userName(entry.created_by)}</span>
          </Meta>
          {(entry.reverses_entry_id || entry.reversed_by_entry_id || entry.source_transaction_id) && (
            <div className="col-span-2 flex flex-col gap-1">
              <dt className="text-sm text-ink-3">Vínculos</dt>
              <dd className="flex flex-col gap-1">
                {entry.reverses_entry_id && <RelatedLink id={entry.reverses_entry_id} prefix="Revierte el asiento" />}
                {entry.reversed_by_entry_id && <RelatedLink id={entry.reversed_by_entry_id} prefix="Revertido por el asiento" />}
                {entry.source_transaction_id && entry.source_context_id && (
                  <Link to={`/finanzas/${entry.source_context_id}/movimientos?tx=${entry.source_transaction_id}`} className="font-medium text-ledger hover:underline">
                    Movimiento de finanzas de origen
                  </Link>
                )}
              </dd>
            </div>
          )}
        </dl>
      </Sheet>

      <Sheet>
        <table className="w-full" aria-label="Líneas del asiento">
          <thead className="border-b border-line bg-sunken text-sm text-ink-2">
            <tr>
              <th scope="col" className="w-10 py-2.5 pl-4 text-left font-medium">#</th>
              <th scope="col" className="px-3 py-2.5 text-left font-medium">Cuenta</th>
              <th scope="col" className="px-3 py-2.5 text-left font-medium">Detalle</th>
              <th scope="col" className="w-40 px-4 py-2.5 text-right font-medium">Debe</th>
              <th scope="col" className="w-40 px-4 py-2.5 text-right font-medium">Haber</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {lines.map((l) => (
              <tr key={l.id} className="align-top">
                <td className="py-2.5 pl-4 text-sm text-ink-3 tabular-nums">{l.line_no}</td>
                <td className={cx('px-3 py-2.5', l.credit !== '0' && 'pl-8')}>
                  <Link to={`/contabilidad/reportes/mayor?account_id=${l.account_id}&from=${yearOf}-01-01&to=${yearOf}-12-31`} className="hover:text-ledger hover:underline">
                    <span className="mr-2 text-ink-2 tabular-nums">{l.account_code}</span>
                    {l.account_name}
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-sm text-ink-2">
                  {l.description}
                  {l.fx_currency && (
                    <span className="block text-ink-3">
                      {formatMoney(l.fx_amount as string, l.fx_currency)} a ₲ {formatDecimal(l.fx_rate as string)} por {CURRENCY_SYMBOLS[l.fx_currency] ?? l.fx_currency}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">{l.debit !== '0' ? <Pyg value={l.debit} /> : <Blank />}</td>
                <td className="px-4 py-2.5 text-right">{l.credit !== '0' ? <Pyg value={l.credit} /> : <Blank />}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-line-strong">
            <tr>
              <td colSpan={3} className="px-4 py-3 font-medium">
                Totales
              </td>
              <td className="px-4 py-3 text-right">
                <RuledTotal value={entry.total_debit} label={`Total debe ${formatMoney(entry.total_debit, 'PYG')}`} />
              </td>
              <td className="px-4 py-3 text-right">
                <RuledTotal value={entry.total_credit} label={`Total haber ${formatMoney(entry.total_credit, 'PYG')}`} />
              </td>
            </tr>
          </tfoot>
        </table>
      </Sheet>

      <Modal open={dialog === 'reverse'} title={`Revertir el asiento N° ${entry.number}`} onClose={() => setDialog(null)}>
        {dialog === 'reverse' && <ReverseForm entry={entry} onDone={() => setDialog(null)} />}
      </Modal>
    </>
  )
}

export function EntryPage() {
  const { id } = useParams()
  const perms = useAccountingPerms()
  const entry = useEntry(id)
  const chart = useChart()
  const years = useFiscalYears()

  if (!id) {
    if (!perms.canManage) return <EmptyState title="Sin acceso">{perms.manageReason}</EmptyState>
    if (chart.isPending || years.isPending) return <Skeleton className="h-40 w-full" />
    return <EntryEditor />
  }
  if (entry.isPending || chart.isPending) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Cargando el asiento">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }
  if (entry.isError || !entry.data) {
    return (
      <EmptyState title="Ese asiento no existe" action={<Link className="font-medium text-ledger hover:underline" to="/contabilidad/asientos">Ir a Asientos</Link>}>
        {entry.error instanceof ApiError ? entry.error.message : 'La dirección no corresponde a ningún asiento de la empresa.'}
      </EmptyState>
    )
  }
  if (entry.data.status === 'draft' && perms.canManage) return <EntryEditor key={entry.data.id} entry={entry.data} />
  return <EntryView key={entry.data.id} entry={entry.data} />
}
