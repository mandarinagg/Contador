/**
 * Formulario de un comprobante, pensado para cargar facturas en serie con el teclado
 * (D-088, D-099). El IVA se calcula mientras se escribe con la regla de tasas vigente a la
 * fecha y se puede ajustar al impreso (±1 ₲). Antes de guardar avisa si ya está cargado.
 */
import { useQuery } from '@tanstack/react-query'
import { CircleCheck, CircleAlert, TriangleAlert } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, type Ref, useDeferredValue, useId, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { Button, Field, Input, Notice, Select, Textarea } from '../../components/ui'
import { cx } from '../../lib/cx'
import { CURRENCIES, CURRENCY_NAMES, formatMoney, parseAmountInput, toInputText } from '../../lib/money'
import { ApiError, get, qs } from '../../services/api'
import { formatDecimal, multiplyDecimal, parseRateInput } from '../accounting/amounts'
import { AmountInput, ApiErrorNotice, Check } from '../finance/components'
import { useContexts, useCounterparties } from '../finance/data'
import { formatBookDate } from '../finance/labels'
import type { Counterparty, Transaction } from '../finance/types'
import { DoubtNote, UnverifiedMark } from './components'
import { useRules } from './data'
import { CONDITION_LABELS, DIRECTION_LABELS, DOC_TYPE_LABELS, VOUCHER_TYPE_LABELS } from './labels'
import { addDays, cdcMismatches, checkCounterpartyRuc, expandVoucherNumber, maskCdc, maskTimbrado, maskVoucherNumber, parseCdc, splitRucInput, sumBig } from './logic'
import type { Direction, DocType, Rule, Voucher, VoucherType } from './types'
import { DEFAULT_RATES, type DraftErrors, draftToBody, type Rates, readPyg, type VoucherDraft, vatLine } from './voucherForm'

/** Tasas de la regla `IVA-GENERAL-TASAS` vigente a la fecha (BR-TAX-09); sin regla, las de la ley y la marca. */
export function useRatesAt(day: string): { rates: Rates; rule: Rule | undefined } {
  const rules = useRules()
  return useMemo(() => {
    const rule = (rules.data ?? []).find(
      (r) => r.code === 'IVA-GENERAL-TASAS' && r.validation_status !== 'deprecated' && r.valid_from && r.valid_from <= day && (!r.valid_to || day <= r.valid_to),
    )
    const p = rule?.parameters as { general_rate?: string; reduced_rate?: string } | undefined
    return { rates: p?.general_rate && p.reduced_rate ? { general: String(p.general_rate), reduced: String(p.reduced_rate) } : DEFAULT_RATES, rule }
  }, [rules.data, day])
}

// --- Contraparte por RUC, con autocompletado desde las contrapartes de finanzas ------------

function CounterpartyCombobox({
  value,
  onChange,
  onPick,
  counterparties,
  inputRef,
  ...aria
}: {
  value: string
  onChange: (text: string) => void
  onPick: (c: Counterparty) => void
  counterparties: Counterparty[]
  inputRef?: Ref<HTMLInputElement>
  id?: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
  disabled?: boolean
}) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const q = value.trim().toLowerCase()
  const options = useMemo(
    () => (q ? counterparties.filter((c) => !c.archived_at && c.ruc && (c.ruc.startsWith(q) || c.name.toLowerCase().includes(q))).slice(0, 8) : []),
    [counterparties, q],
  )
  const show = open && options.length > 0
  const choose = (c: Counterparty | undefined) => {
    if (c) onPick(c)
    setOpen(false)
  }
  return (
    <div className="relative">
      <Input
        {...aria}
        ref={inputRef}
        role="combobox"
        aria-expanded={show}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={show && options[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        placeholder="RUC o nombre"
        className="tabular-nums"
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
          setActive(0)
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
          if (e.key === 'ArrowDown' && options.length) {
            e.preventDefault()
            setOpen(true)
            setActive((a) => Math.min(options.length - 1, show ? a + 1 : 0))
          } else if (e.key === 'ArrowUp' && show) {
            e.preventDefault()
            setActive((a) => Math.max(0, a - 1))
          } else if ((e.key === 'Enter' || e.key === 'Tab') && show) {
            if (e.key === 'Enter') e.preventDefault()
            choose(options[active])
          } else if (e.key === 'Escape' && show) {
            e.preventDefault()
            e.stopPropagation()
            setOpen(false)
          }
        }}
      />
      {show && (
        <ul id={listId} role="listbox" aria-label="Contrapartes de finanzas" className="absolute top-full left-0 z-30 mt-1 w-[max(100%,24rem)] rounded-md bg-surface py-1 shadow-(--shadow-float)">
          {options.map((c, i) => (
            <li
              key={c.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(c)}
              className={cx('flex cursor-pointer items-baseline gap-3 px-3 py-1.5', i === active && 'bg-ledger-soft')}
            >
              <span className="w-24 shrink-0 text-sm text-ink-2 tabular-nums">
                {c.ruc}-{c.ruc_check_digit}
              </span>
              <span className="truncate">{c.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Segmented<T extends string>({ name, value, options, onChange, disabled }: { name: string; value: T; options: [T, string][]; onChange: (v: T) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label={name} className="inline-flex rounded-sm border border-line-strong bg-surface p-0.5">
      {options.map(([v, label]) => (
        <label
          key={v}
          className={cx(
            'cursor-pointer rounded-[3px] px-3 py-1.5 text-sm font-medium has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
            value === v ? 'bg-ledger text-surface' : 'text-ink-2 hover:text-ink',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        >
          <input type="radio" className="sr-only" name={name} value={v} checked={value === v} disabled={disabled} onChange={() => onChange(v)} />
          {label}
        </label>
      ))}
    </div>
  )
}

/** Fila de importe por tasa: lo que dice la factura (IVA incluido) y el IVA, calculado o impreso. */
function RateRow({
  label,
  rateText,
  amount,
  vat,
  onAmount,
  onVat,
  amountError,
  vatError,
  rate,
  disabled,
}: {
  label: string
  rateText: string
  amount: string
  vat: string
  onAmount: (t: string) => void
  onVat: (t: string) => void
  amountError?: string
  vatError?: string
  rate: string | null
  disabled?: boolean
}) {
  const line = vatLine(amount, vat, rate ?? '0')
  const amountId = useId()
  const vatId = useId()
  const touched = vat.trim() !== ''
  const diff = line.printed !== null && line.calculated !== null ? BigInt(line.printed) - BigInt(line.calculated) : 0n
  return (
    <div className="grid grid-cols-[9rem_minmax(0,1fr)_minmax(0,0.8fr)] items-start gap-x-4 gap-y-1 border-b border-line py-3 last:border-b-0">
      <label htmlFor={amountId} className="pt-2 text-sm font-medium">
        {label}
        <span className="block text-xs font-normal text-ink-3">{rateText}</span>
      </label>
      <div>
        <AmountInput
          id={amountId}
          currency="PYG"
          value={amount}
          onChange={onAmount}
          disabled={disabled}
          aria-invalid={amountError ? true : undefined}
          aria-describedby={amountError ? `${amountId}-e` : undefined}
        />
        {amountError && (
          <p id={`${amountId}-e`} className="mt-1 text-sm text-debit">
            {amountError}
          </p>
        )}
      </div>
      {rate !== null ? (
        <div>
          <div className="flex items-center gap-2">
            <label htmlFor={vatId} className="shrink-0 text-sm text-ink-2">
              IVA
            </label>
            <Input
              id={vatId}
              inputMode="numeric"
              className={cx('text-right tabular-nums', !touched && 'text-ink-2')}
              placeholder={line.calculated !== null ? toInputText(line.calculated, 'PYG') : '0'}
              value={vat}
              disabled={disabled}
              onChange={(e) => onVat(e.target.value)}
              aria-invalid={vatError || line.error ? true : undefined}
              aria-describedby={`${vatId}-h`}
              title="Vacío: el calculado. Escribí el impreso si difiere en 1 guaraní."
            />
          </div>
          <p id={`${vatId}-h`} className={cx('mt-1 text-xs', vatError || line.error ? 'text-debit' : 'text-ink-3')} aria-live="polite">
            {vatError ?? line.error ?? (touched ? (diff === 0n ? 'Igual al calculado.' : `Impreso, ${diff > 0n ? '+' : '−'}1 respecto del calculado: se acepta.`) : 'Calculado. Si la factura dice otro (±1), escribilo.')}
          </p>
        </div>
      ) : (
        <p className="pt-2 text-sm text-ink-3">Sin IVA</p>
      )}
    </div>
  )
}

export interface VoucherFormProps {
  draft: VoucherDraft
  setDraft: (d: VoucherDraft) => void
  mode: 'new' | 'edit'
  /** Comprobante que se edita (para no avisarse a sí mismo como duplicado). */
  editing?: Voucher
  /** Con asiento vivo: solo las notas (D-091). */
  notesOnly?: boolean
  organizationRuc: { ruc: string | null; dv: string | null }
  confirmedMonth: { obligationId: string; dueMonth: string } | null
  busy: boolean
  apiError: unknown
  fieldErrors: DraftErrors
  onSubmit: (d: VoucherDraft) => void
  onCancel?: () => void
  submitLabel: string
  firstFieldRef?: Ref<HTMLInputElement>
}

export function VoucherForm({
  draft: d,
  setDraft,
  mode,
  editing,
  notesOnly = false,
  organizationRuc,
  confirmedMonth,
  busy,
  apiError,
  fieldErrors,
  onSubmit,
  onCancel,
  submitLabel,
  firstFieldRef,
}: VoucherFormProps) {
  const set = (patch: Partial<VoucherDraft>) => setDraft({ ...d, ...patch })
  const { rates, rule } = useRatesAt(d.issued_on || '9999-12-31')
  const contexts = useContexts()
  const business = contexts.data?.find((c) => c.kind === 'business')
  const counterparties = useCounterparties(business?.id ?? '')
  const cps = business ? (counterparties.data ?? []) : []
  const [localErrors, setLocalErrors] = useState<DraftErrors>({})
  const errors: DraftErrors = { ...localErrors, ...fieldErrors }
  const purchase = d.direction === 'purchase'
  const docType: DocType = purchase ? 'ruc' : d.doc_type
  const locked = Boolean(confirmedMonth) || notesOnly

  // RUC mientras se escribe (DV módulo 11, o RUC antiguo con letra: D-099).
  const rucCheck = docType === 'ruc' ? checkCounterpartyRuc(d.ruc, d.dv) : null
  const rucMessage =
    rucCheck?.kind === 'wrong_dv'
      ? `Para ese RUC el dígito verificador es ${rucCheck.expected}.`
      : rucCheck?.kind === 'invalid'
        ? rucCheck.message
        : rucCheck?.kind === 'missing_dv'
          ? `Falta el dígito verificador (para ese RUC es ${rucCheck.expected}).`
          : undefined

  // CDC: DV y coherencia con el comprobante (D-107).
  const cdc = d.is_electronic ? parseCdc(d.cdc) : null
  const cdcProblems = cdc
    ? cdcMismatches(cdc, {
        direction: d.direction,
        voucherType: d.voucher_type,
        number: d.number,
        issuedOn: d.issued_on,
        emitterRuc: purchase ? (/^\d+$/.test(d.ruc) ? d.ruc : '') : (organizationRuc.ruc ?? ''),
        emitterDv: purchase ? d.dv : (organizationRuc.dv ?? ''),
      })
    : []

  // Aviso de duplicado antes de guardar (BR-TAX-07, D-104): mismo tipo, timbrado, número y, en compras, RUC.
  const dupKey = useDeferredValue(/^\d{8}$/.test(d.timbrado) && /^\d{3}-\d{3}-\d{7}$/.test(d.number) ? `${d.direction}|${d.number}` : '')
  const dupQuery = useQuery({
    enabled: Boolean(dupKey) && mode === 'new',
    queryKey: ['tax', 'vouchers', 'duplicate', dupKey],
    queryFn: () => get<Voucher[]>(`/tax/vouchers${qs({ direction: d.direction, q: d.number, voided: 'exclude', limit: 50 })}`),
    staleTime: 5_000,
  })
  const duplicate = (dupQuery.data ?? []).find(
    (v) =>
      v.id !== editing?.id &&
      v.timbrado === d.timbrado &&
      v.number === d.number &&
      v.voucher_type === d.voucher_type &&
      (!purchase || (v.counterparty_ruc ?? '') === d.ruc.trim().toUpperCase()),
  )

  // Notas: la factura original, de la misma contraparte y dirección.
  const identity = docType === 'ruc' ? d.ruc.trim().toUpperCase() : d.document.trim()
  const originals = useQuery({
    enabled: d.voucher_type !== 'invoice' && identity.length > 0,
    queryKey: ['tax', 'vouchers', 'originals', d.direction, docType, identity],
    queryFn: () =>
      get<Voucher[]>(`/tax/vouchers${qs(docType === 'ruc' ? { direction: d.direction, counterparty_ruc: identity, limit: 100 } : { direction: d.direction, q: d.name || identity, limit: 100 })}`),
  })
  const invoices = (originals.data ?? []).filter(
    (v) => v.voucher_type === 'invoice' && v.id !== editing?.id && (docType === 'ruc' ? v.counterparty_ruc === identity : v.counterparty_document === identity),
  )

  // Movimiento de finanzas de la empresa cerca de la fecha (salida en compras, entrada en ventas).
  const txFrom = d.issued_on ? addDays(d.issued_on, -20) : ''
  const txTo = d.issued_on ? addDays(d.issued_on, 40) : ''
  const txs = useQuery({
    enabled: Boolean(business && d.issued_on),
    queryKey: ['finance', business?.id ?? '', 'transactions', 'voucher-link', txFrom, txTo],
    queryFn: () => get<Transaction[]>(`/finance/contexts/${business?.id}/transactions${qs({ from: txFrom, to: txTo, limit: 200 })}`),
  })
  const linkable = (txs.data ?? []).filter((t) => !t.voided_at && !t.transfer_group_id && t.currency === 'PYG' && (purchase ? t.amount.startsWith('-') : !t.amount.startsWith('-')))

  const t10 = readPyg(d.taxed_10)
  const t5 = readPyg(d.taxed_5)
  const ex = readPyg(d.exempt)
  const v10 = vatLine(d.taxed_10, d.vat_10, rates.general)
  const v5 = vatLine(d.taxed_5, d.vat_5, rates.reduced)
  const total = t10.ok && t5.ok && ex.ok ? sumBig(t10.value, t5.value, ex.value) : null
  const vatTotal = v10.effective !== null && v5.effective !== null ? sumBig(v10.effective, v5.effective) : null

  const fxRate = d.currency !== 'PYG' ? parseRateInput(d.fx_rate) : null
  const fxAmount = d.currency !== 'PYG' && d.foreign_total ? parseAmountInput(d.foreign_total, d.currency) : null
  const fxTotal = fxRate?.ok && fxAmount?.ok ? multiplyDecimal(fxAmount.value, fxRate.value) : null

  const pickCounterparty = (c: Counterparty) => set({ ruc: c.ruc ?? '', dv: c.ruc_check_digit ?? '', name: d.name || c.name, finance_counterparty_id: c.id })
  const onRuc = (text: string) => {
    const { ruc, dv } = splitRucInput(text)
    const match = cps.find((c) => c.ruc === ruc && (dv === null || c.ruc_check_digit === dv))
    set({
      ruc,
      dv: dv ?? (match?.ruc_check_digit ?? (d.finance_counterparty_id ? '' : d.dv)),
      name: match && !d.name ? match.name : d.name,
      finance_counterparty_id: match ? match.id : '',
    })
  }
  const onCdc = (text: string) => {
    const masked = maskCdc(text)
    const parts = parseCdc(masked)
    const patch: Partial<VoucherDraft> = { cdc: masked }
    // Con los 44 dígitos y el DV bien, completa lo que falte (número, fecha y, en compras, el RUC).
    if (parts?.checkOk) {
      if (!d.number) patch.number = parts.number
      if (!d.issued_on || mode === 'new') patch.issued_on = d.issued_on || parts.issuedOn
      if (purchase && !d.ruc) {
        patch.ruc = parts.emitterRuc
        patch.dv = parts.emitterDv
      }
    }
    set(patch)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const { errors: next } = draftToBody(d, rates)
    setLocalErrors(next)
    if (Object.keys(next).length > 0) {
      const first = document.querySelector<HTMLElement>('[data-voucher-form] [aria-invalid="true"]')
      first?.focus()
      return
    }
    onSubmit(d)
  }

  const api = apiError instanceof ApiError ? apiError : null
  const dupFromApi = api?.code === 'VOUCHER_DUPLICATE' ? (api.details as { voucher_id?: string } | null)?.voucher_id : undefined
  const periodFromApi = api?.code === 'PERIOD_CONFIRMED'
  const generalApiError = api && !dupFromApi && !periodFromApi && !(api.code === 'VALIDATION_ERROR') ? api : null

  return (
    <form onSubmit={submit} noValidate data-voucher-form className="flex flex-col gap-5" aria-label={mode === 'new' ? 'Nuevo comprobante' : 'Editar comprobante'}>
      {confirmedMonth && (
        <Notice tone="warn" title="El registro de este mes está confirmado: solo lectura">
          Los comprobantes de un mes confirmado en Marangatu no se crean, cambian ni anulan (D-089).{' '}
          <Link to={`/impuestos/calendario?mes=${confirmedMonth.dueMonth}#ob-${confirmedMonth.obligationId}`} className="font-medium underline">
            Reabrir el registro
          </Link>{' '}
          para corregirlo, como una rectificativa.
        </Notice>
      )}
      {notesOnly && !confirmedMonth && (
        <Notice tone="warn" title="Tiene un asiento vivo: solo cambian las notas">
          Para cambiar importes, fechas o la contraparte, primero descartá o revertí el asiento del comprobante.
        </Notice>
      )}

      <fieldset disabled={locked} className="flex flex-col gap-4">
        <legend className="sr-only">Comprobante</legend>
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <div>
            <p className="mb-1.5 text-sm font-medium text-ink-2">Es una</p>
            <Segmented<Direction>
              name="Compra o venta"
              value={d.direction}
              disabled={mode === 'edit'}
              options={[
                ['purchase', DIRECTION_LABELS.purchase],
                ['sale', DIRECTION_LABELS.sale],
              ]}
              onChange={(direction) => set({ direction, doc_type: direction === 'purchase' ? 'ruc' : d.doc_type, related_voucher_id: '', transaction_id: '' })}
            />
          </div>
          <Field label="Tipo">
            {(p) => (
              <Select {...p} className="w-44" value={d.voucher_type} onChange={(e) => set({ voucher_type: e.target.value as VoucherType, related_voucher_id: '' })}>
                {(Object.keys(VOUCHER_TYPE_LABELS) as VoucherType[]).map((t) => (
                  <option key={t} value={t}>
                    {VOUCHER_TYPE_LABELS[t]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Fecha" error={errors.issued_on}>
            {(p) => <Input {...p} type="date" className="w-40" value={d.issued_on} onChange={(e) => set({ issued_on: e.target.value })} />}
          </Field>
          <Field label="Condición">
            {(p) => (
              <Select {...p} className="w-32" value={d.condition} onChange={(e) => set({ condition: e.target.value as VoucherDraft['condition'] })}>
                <option value="cash">{CONDITION_LABELS.cash}</option>
                <option value="credit">{CONDITION_LABELS.credit}</option>
              </Select>
            )}
          </Field>
        </div>

        {/* Contraparte */}
        <div className="grid grid-cols-[minmax(0,1.1fr)_4.5rem_minmax(0,1.6fr)] items-start gap-x-3 gap-y-3">
          {!purchase && (
            <div className="col-span-3 sm:col-span-1">
              <Field label="Identificación del cliente">
                {(p) => (
                  <Select {...p} value={d.doc_type} onChange={(e) => set({ doc_type: e.target.value as DocType })}>
                    {(Object.keys(DOC_TYPE_LABELS) as DocType[]).map((t) => (
                      <option key={t} value={t}>
                        {DOC_TYPE_LABELS[t]}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          )}
          {docType === 'ruc' ? (
            <>
              <div className={cx(!purchase && 'col-start-1')}>
                <Field label={purchase ? 'RUC del proveedor' : 'RUC del cliente'} error={errors.ruc} hint={rucCheck?.kind === 'legacy' ? undefined : 'Sin el DV. Elegí de tus contrapartes o escribilo.'}>
                  {(p) => <CounterpartyCombobox {...p} inputRef={firstFieldRef} value={d.ruc} onChange={onRuc} onPick={pickCounterparty} counterparties={cps} />}
                </Field>
              </div>
              <Field label="DV" error={errors.dv ?? (rucCheck?.kind === 'wrong_dv' ? rucMessage : undefined)}>
                {(p) => (
                  <Input
                    {...p}
                    inputMode="numeric"
                    maxLength={1}
                    className="text-center tabular-nums"
                    disabled={rucCheck?.kind === 'legacy'}
                    value={d.dv}
                    onChange={(e) => set({ dv: e.target.value.replace(/\D/g, '').slice(0, 1) })}
                  />
                )}
              </Field>
              <Field label={purchase ? 'Razón social del proveedor' : 'Nombre o razón social'} error={errors.name}>
                {(p) => <Input {...p} maxLength={200} value={d.name} onChange={(e) => set({ name: e.target.value })} />}
              </Field>
              <div className="col-span-3 -mt-1 min-h-5 text-sm" aria-live="polite">
                {rucCheck?.kind === 'ok' && (
                  <span className="inline-flex items-center gap-1 text-ledger">
                    <CircleCheck size={14} aria-hidden />
                    RUC {d.ruc}-{d.dv}: el dígito verificador es correcto.
                    {d.finance_counterparty_id && <span className="text-ink-2"> Vinculado a la contraparte de finanzas.</span>}
                  </span>
                )}
                {rucCheck?.kind === 'missing_dv' && !errors.dv && <span className="text-ink-2">{rucMessage}</span>}
                {rucCheck?.kind === 'legacy' && (
                  <span className="inline-flex items-start gap-1 text-amber">
                    <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden />
                    RUC antiguo terminado en letra: se acepta sin dígito verificador y queda marcado para revisar (D-099).
                  </span>
                )}
                {rucCheck?.kind === 'legacy' && <DoubtNote codes={['D-F4-10']} className="mt-1" />}
              </div>
            </>
          ) : docType === 'unnamed' ? (
            <div className="col-span-2">
              <Field label="Nombre (opcional)" hint="Venta «sin nombre»: va sin número de identificación." error={errors.name}>
                {(p) => <Input {...p} ref={firstFieldRef} maxLength={200} placeholder="Sin nombre" value={d.name} onChange={(e) => set({ name: e.target.value })} />}
              </Field>
            </div>
          ) : (
            <>
              <Field label="Número de documento" error={errors.document}>
                {(p) => <Input {...p} ref={firstFieldRef} maxLength={20} value={d.document} onChange={(e) => set({ document: e.target.value })} />}
              </Field>
              <div className="col-span-2">
                <Field label="Nombre" error={errors.name}>
                  {(p) => <Input {...p} maxLength={200} value={d.name} onChange={(e) => set({ name: e.target.value })} />}
                </Field>
              </div>
            </>
          )}
        </div>

        {/* Timbrado, número y CDC */}
        <div className="grid grid-cols-[9rem_11rem_minmax(0,1fr)] items-start gap-x-3 gap-y-3">
          <Field label="Timbrado" error={errors.timbrado}>
            {(p) => <Input {...p} inputMode="numeric" className="tabular-nums" placeholder="12345678" value={d.timbrado} onChange={(e) => set({ timbrado: maskTimbrado(e.target.value) })} />}
          </Field>
          <Field label="Número" error={errors.number} hint={errors.number ? undefined : '001-001-0000001 o 1-1-1'}>
            {(p) => (
              <Input
                {...p}
                inputMode="numeric"
                className="tabular-nums"
                placeholder="001-001-0000001"
                value={d.number}
                onChange={(e) => set({ number: /-/.test(e.target.value) && e.target.value.split('-').some((x) => x.length > 0 && x.length < 3) ? e.target.value.replace(/[^\d-]/g, '').slice(0, 15) : maskVoucherNumber(e.target.value) })}
                onBlur={() => set({ number: expandVoucherNumber(d.number) })}
              />
            )}
          </Field>
          <div className="flex flex-col gap-2 pt-7">
            <Check label="Es electrónico (tiene CDC)" checked={d.is_electronic} onChange={(v) => set({ is_electronic: v, cdc: v ? d.cdc : '' })} />
          </div>
          {d.is_electronic && (
            <div className="col-span-3">
              <Field
                label="CDC (44 dígitos del KuDE)"
                error={errors.cdc ?? (cdc && !cdc.checkOk ? 'El dígito verificador del CDC no corresponde: revisá los 44 dígitos.' : undefined)}
                hint={
                  cdc?.checkOk
                    ? cdcProblems.length
                      ? undefined
                      : 'CDC válido y coherente con el comprobante.'
                    : `${d.cdc.replace(/\s/g, '').length} de 44 dígitos. Con los 44, completa el número, la fecha y el RUC si faltan.`
                }
              >
                {(p) => <Input {...p} inputMode="numeric" className="font-medium tracking-wide tabular-nums" value={d.cdc} onChange={(e) => onCdc(e.target.value)} />}
              </Field>
              {cdc?.checkOk && cdcProblems.length > 0 && (
                <p className="mt-1 flex items-center gap-1 text-sm text-debit">
                  <CircleAlert size={14} aria-hidden />
                  El CDC no coincide con {cdcProblems.join(', ')} del comprobante.
                </p>
              )}
            </div>
          )}
        </div>

        {duplicate && (
          <Notice tone="bad" title={`Este comprobante ya está cargado: ${VOUCHER_TYPE_LABELS[duplicate.voucher_type].toLowerCase()} ${duplicate.number}, timbrado ${duplicate.timbrado}`}>
            {duplicate.counterparty_name}, {formatBookDate(duplicate.issued_on)}, {formatMoney(duplicate.total, 'PYG')}.{' '}
            <Link to={`/impuestos/comprobantes/${duplicate.id}`} className="font-medium underline">
              Ver el cargado
            </Link>
          </Notice>
        )}

        {/* Importes */}
        <section aria-labelledby="amounts-h" className="rounded-sm border border-line px-4">
          <div className="flex items-center justify-between gap-3 border-b border-line py-2.5">
            <h3 id="amounts-h" className="font-medium">
              Importes, con IVA incluido como en la factura
            </h3>
            <span className="flex items-center gap-2 text-sm text-ink-2">
              Tasas de la regla {rule ? `IVA-GENERAL-TASAS v${rule.version}` : 'de la ley'}
              <UnverifiedMark status={rule?.validation_status ?? 'pending'} />
            </span>
          </div>
          <RateRow
            label="Gravado 10 %"
            rateText="IVA = importe / 11"
            amount={d.taxed_10}
            vat={d.vat_10}
            onAmount={(t) => set({ taxed_10: t })}
            onVat={(t) => set({ vat_10: t })}
            amountError={errors.taxed_10 ?? errors.amounts}
            vatError={errors.vat_10}
            rate={rates.general}
          />
          <RateRow
            label="Gravado 5 %"
            rateText="IVA = importe / 21"
            amount={d.taxed_5}
            vat={d.vat_5}
            onAmount={(t) => set({ taxed_5: t })}
            onVat={(t) => set({ vat_5: t })}
            amountError={errors.taxed_5}
            vatError={errors.vat_5}
            rate={rates.reduced}
          />
          <RateRow label="Exento" rateText="Sin IVA" amount={d.exempt} vat="" onAmount={(t) => set({ exempt: t })} onVat={() => undefined} amountError={errors.exempt} rate={null} />
          <div className="flex items-baseline justify-end gap-6 py-3 text-sm">
            <span className="text-ink-2">
              IVA total <span className="ml-1 font-medium text-ink tabular-nums">{vatTotal !== null ? formatMoney(vatTotal, 'PYG') : '—'}</span>
            </span>
            <span className="text-ink-2">
              Total del comprobante{' '}
              <span className="ledger-rule ml-1 inline-block min-w-28 text-right text-md font-semibold text-ink tabular-nums" data-testid="voucher-total">
                {total !== null ? formatMoney(total, 'PYG') : '—'}
              </span>
            </span>
          </div>
        </section>

        {/* Moneda */}
        <details className="rounded-sm border border-line px-4 py-2.5" open={d.currency !== 'PYG'}>
          <summary className="cursor-pointer text-sm font-medium">Moneda: {CURRENCY_NAMES[d.currency] ?? d.currency}</summary>
          <div className="mt-3 grid grid-cols-3 gap-3 pb-1">
            <Field label="Moneda del comprobante">
              {(p) => (
                <Select {...p} value={d.currency} onChange={(e) => set({ currency: e.target.value, fx_rate: '', foreign_total: '' })}>
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {CURRENCY_NAMES[c]}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            {d.currency !== 'PYG' && (
              <>
                <Field label="Cotización (₲ por unidad)" error={errors.fx_rate}>
                  {(p) => <Input {...p} inputMode="decimal" className="text-right tabular-nums" placeholder="7.300,25" value={d.fx_rate} onChange={(e) => set({ fx_rate: e.target.value })} />}
                </Field>
                <Field label={`Total en ${d.currency}`} error={errors.foreign_total} hint={fxTotal ? `× cotización = ₲ ${formatDecimal(fxTotal)}` : 'Los importes de arriba van en guaraníes.'}>
                  {(p) => <AmountInput {...p} currency={d.currency} value={d.foreign_total} onChange={(t) => set({ foreign_total: t })} />}
                </Field>
              </>
            )}
          </div>
          {d.currency !== 'PYG' && <DoubtNote codes={['D-F4-8']} className="pb-1" />}
        </details>

        {/* Nota: comprobante original */}
        {d.voucher_type !== 'invoice' && (
          <Field
            label="Factura que corrige"
            error={errors.related_voucher_id}
            hint={identity ? `Facturas de ${d.name || identity}${purchase ? '' : ' (misma identificación)'}.` : 'Primero indicá la contraparte.'}
          >
            {(p) => (
              <Select {...p} value={d.related_voucher_id} onChange={(e) => set({ related_voucher_id: e.target.value })}>
                <option value="">{invoices.length ? 'Elegí la factura original' : 'No hay facturas de esta contraparte'}</option>
                {invoices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.number} · {formatBookDate(v.issued_on)} · {formatMoney(v.total, 'PYG')}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}

        {/* Imputación */}
        <fieldset className="flex flex-wrap items-start gap-x-6 gap-y-2">
          <legend className="mb-1.5 text-sm font-medium text-ink-2">Imputa a</legend>
          <Check label="IVA" checked={d.imputes_vat} onChange={(v) => set({ imputes_vat: v })} hint={purchase ? 'Crédito fiscal' : 'Débito fiscal'} />
          <div>
            <Check label="IRE" checked={d.imputes_ire} onChange={(v) => set({ imputes_ire: v })} hint="Según las guías, solo en el IRE SIMPLE" />
            <DoubtNote codes={['D-F4-2']} className="mt-1" />
          </div>
          <Check label="IRP" checked={d.imputes_irp} onChange={(v) => set({ imputes_irp: v })} hint="Renta personal" />
        </fieldset>

        <details className="rounded-sm border border-line px-4 py-2.5" open={Boolean(d.transaction_id)}>
          <summary className="cursor-pointer text-sm font-medium">Vincular a un movimiento de finanzas {d.transaction_id ? '(vinculado)' : '(opcional)'}</summary>
          <div className="mt-3 pb-1">
            <Field
              label="Movimiento"
              hint={business ? `${purchase ? 'Salidas' : 'Entradas'} de la empresa en guaraníes, del ${txFrom ? formatBookDate(txFrom) : '—'} al ${txTo ? formatBookDate(txTo) : '—'}. Con un movimiento, el asiento va contra su banco.` : 'Sin acceso a las finanzas de la empresa.'}
            >
              {(p) => (
                <Select {...p} value={d.transaction_id} disabled={!business} onChange={(e) => set({ transaction_id: e.target.value })}>
                  <option value="">Sin vincular</option>
                  {linkable.map((t) => (
                    <option key={t.id} value={t.id}>
                      {formatBookDate(t.booked_on)} · {t.description} · {formatMoney(t.amount, 'PYG')}
                    </option>
                  ))}
                  {d.transaction_id && !linkable.some((t) => t.id === d.transaction_id) && <option value={d.transaction_id}>Movimiento vinculado (fuera de las fechas)</option>}
                </Select>
              )}
            </Field>
          </div>
        </details>
      </fieldset>

      <Field label="Notas (opcional)">
        {(p) => <Textarea {...p} className="min-h-14" maxLength={500} disabled={Boolean(confirmedMonth)} value={d.notes} onChange={(e) => set({ notes: e.target.value })} />}
      </Field>

      {dupFromApi && (
        <Notice tone="bad" title={api?.message ?? 'Ya está cargado.'}>
          <Link to={`/impuestos/comprobantes/${dupFromApi}`} className="font-medium underline">
            Ver el comprobante cargado
          </Link>
        </Notice>
      )}
      {periodFromApi && <Notice tone="bad" title={api?.message ?? ''} />}
      {generalApiError && !fieldErrorsHas(fieldErrors) && <ApiErrorNotice error={generalApiError} />}
      {api?.code === 'VALIDATION_ERROR' && <ApiErrorNotice error={api} />}

      <div className="flex items-center justify-end gap-2 border-t border-line pt-4">
        <p className="mr-auto text-sm text-ink-3">{mode === 'new' ? 'Enter guarda y deja listo el siguiente: la fecha y la dirección se recuerdan.' : ''}</p>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        )}
        <Button type="submit" busy={busy} disabled={Boolean(confirmedMonth) || Boolean(duplicate)}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

function fieldErrorsHas(e: DraftErrors) {
  return Object.keys(e).length > 0
}
