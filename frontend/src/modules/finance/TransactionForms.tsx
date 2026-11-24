/** Formularios de movimientos: alta/edición, anulación con motivo y transferencia. */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Button, Field, Input, Notice, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatMoney, isNegative, negateAmount, toInputText } from '../../lib/money'
import { ApiError, patch, post } from '../../services/api'
import { Amount, AmountInput } from './components'
import { useAmountField } from './forms'
import { financeKeys, useFinance } from './data'
import { formatBookDate, todayIso } from './labels'
import { AccountSelect, CategorySelect, CounterpartySelect } from './pickers'
import type { Account, Category, Counterparty, Transaction, TransferResult } from './types'
import { postedEntryFromError, postedEntryOf } from '../accounting/entryRefs'
import { PostedEntryNotice } from '../accounting/financeBridge'

function useInvalidateFinance() {
  const qc = useQueryClient()
  const { cid } = useFinance()
  return () => {
    qc.invalidateQueries({ queryKey: financeKeys.context(cid) })
    qc.invalidateQueries({ queryKey: financeKeys.consolidated() })
  }
}

function FormError({ error, action = 'edit' }: { error: unknown; action?: 'edit' | 'void' }) {
  if (!(error instanceof ApiError)) return null
  // 409 TRANSACTION_HAS_POSTED_ENTRY (D-048): además del mensaje, el enlace al asiento.
  const posted = postedEntryFromError(error)
  if (posted) return <PostedEntryNotice entry={posted} action={action} />
  const fields = Object.values(error.fieldErrors())
  return (
    <Notice tone="bad" title={error.message}>
      {fields.length > 0 && fields.join(' ')}
    </Notice>
  )
}

/** Entra / Sale: el signo del importe elegido con palabras, no con un "-" que se olvida. */
function DirectionToggle({ value, onChange, disabled }: { value: 'in' | 'out'; onChange: (v: 'in' | 'out') => void; disabled?: boolean }) {
  return (
    <fieldset className="flex flex-col gap-1.5" disabled={disabled}>
      <legend className="mb-1.5 text-sm font-medium text-ink-2">Sentido</legend>
      <div className="grid grid-cols-2 gap-1 rounded-sm border border-line-strong p-0.5">
        {(
          [
            ['out', 'Sale', 'pago, gasto', <ArrowUpRight key="o" size={15} aria-hidden />],
            ['in', 'Entra', 'cobro, ingreso', <ArrowDownLeft key="i" size={15} aria-hidden />],
          ] as const
        ).map(([v, label, hint, icon]) => (
          <label
            key={v}
            className={cx(
              'flex cursor-pointer items-center justify-center gap-1.5 rounded-[3px] px-2 py-1.5 text-sm has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
              value === v ? (v === 'out' ? 'bg-debit-soft font-semibold text-debit' : 'bg-ledger-soft font-semibold text-ledger') : 'text-ink-2 hover:bg-sunken',
            )}
          >
            <input type="radio" name="direction" value={v} checked={value === v} onChange={() => onChange(v)} className="sr-only" />
            {icon}
            {label}
            <span className="font-normal opacity-75">({hint})</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function TransactionForm({
  transaction,
  accounts,
  categories,
  counterparties,
  onDone,
}: {
  transaction?: Transaction
  accounts: Account[]
  categories: Category[]
  counterparties: Counterparty[]
  onDone: () => void
}) {
  const { cid } = useFinance()
  const toast = useToast()
  const invalidate = useInvalidateFinance()
  const isTransfer = Boolean(transaction?.transfer_group_id)
  // Fecha, importe y cuenta: solo en movimientos manuales que no sean transferencia.
  // Con asiento contabilizado tampoco (D-048): primero se revierte el asiento.
  const posted = postedEntryOf(transaction?.journal_entry)
  const coreEditable = !transaction || (transaction.source === 'manual' && !isTransfer && !posted)
  const active = accounts.filter((a) => !a.archived_at)
  const [accountId, setAccountId] = useState(transaction?.account_id ?? active[0]?.id ?? '')
  const [direction, setDirection] = useState<'in' | 'out'>(transaction && !isNegative(transaction.amount) ? 'in' : 'out')
  const amount = useAmountField(transaction ? toInputText(transaction.amount, transaction.currency) : '')
  const [form, setForm] = useState({
    booked_on: transaction?.booked_on ?? todayIso(),
    description: transaction?.description ?? '',
    reference: transaction?.reference ?? '',
    category_id: transaction?.category_id ?? '',
    counterparty_id: transaction?.counterparty_id ?? '',
  })
  const account = accounts.find((a) => a.id === accountId)
  const currency = account?.currency ?? transaction?.currency ?? 'PYG'

  const save = useMutation({
    mutationFn: (signed: string | null) => {
      const body: Record<string, unknown> = {
        description: form.description,
        reference: form.reference.trim() || null,
        counterparty_id: form.counterparty_id || null,
      }
      if (!isTransfer) body.category_id = form.category_id || null
      if (coreEditable) {
        body.booked_on = form.booked_on
        body.account_id = accountId
        body.amount = signed
      }
      if (!transaction) return post<Transaction>(`/finance/contexts/${cid}/transactions`, body)
      return patch<Transaction>(`/finance/contexts/${cid}/transactions/${transaction.id}`, body)
    },
    onSuccess: (tx) => {
      invalidate()
      toast('ok', transaction ? 'Movimiento guardado.' : `Movimiento de ${formatMoney(tx.amount, tx.currency, { sign: 'always' })} cargado.`)
      onDone()
    },
  })
  const fe = save.error instanceof ApiError ? save.error.fieldErrors() : {}

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!coreEditable) return save.mutate(null)
    const magnitude = amount.read(currency, { positive: true })
    if (magnitude === null) return
    save.mutate(direction === 'out' ? negateAmount(magnitude) : magnitude)
  }

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-2 gap-x-4 gap-y-4" noValidate>
      {save.error ? (
        <div className="col-span-2">
          <FormError error={save.error} />
        </div>
      ) : null}
      {transaction && posted && (
        <div className="col-span-2">
          <PostedEntryNotice entry={posted} action="edit" />
        </div>
      )}
      {transaction && !coreEditable && !posted && (
        <p className="col-span-2 rounded-sm bg-sunken px-3 py-2 text-sm text-ink-2">
          {isTransfer
            ? 'Es una pata de una transferencia: la fecha, el importe y la cuenta no se cambian. Si está mal, anulala (se anulan las dos patas) y cargala de nuevo.'
            : 'Vino de un extracto importado: la fecha, el importe y la cuenta son los del banco y no se cambian.'}{' '}
          {formatBookDate(transaction.booked_on)} · <Amount value={transaction.amount} currency={transaction.currency} flow />
        </p>
      )}
      {coreEditable && (
        <>
          <div className="col-span-2">
            <DirectionToggle value={direction} onChange={setDirection} />
          </div>
          <Field label="Cuenta" error={fe.account_id}>
            {(p) => <AccountSelect {...p} accounts={accounts} value={accountId} onChange={(e) => setAccountId(e.target.value)} />}
          </Field>
          <Field label="Importe" error={amount.error ?? fe.amount}>
            {(p) => <AmountInput {...p} currency={currency} value={amount.text} onChange={amount.set} autoFocus={!transaction} />}
          </Field>
          <Field label="Fecha" error={fe.booked_on}>
            {(p) => <Input {...p} type="date" value={form.booked_on} onChange={(e) => setForm({ ...form, booked_on: e.target.value })} />}
          </Field>
          <span />
        </>
      )}
      <div className="col-span-2">
        <Field label="Descripción" error={fe.description}>
          {(p) => <Input {...p} maxLength={500} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}
        </Field>
      </div>
      <Field label="Categoría" hint={isTransfer ? 'Las transferencias no llevan categoría: no son ingreso ni gasto.' : undefined}>
        {(p) => (
          <CategorySelect
            {...p}
            disabled={isTransfer}
            categories={categories}
            first={direction === 'in' ? 'income' : 'expense'}
            value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}
          />
        )}
      </Field>
      <Field label="Contraparte">
        {(p) => (
          <CounterpartySelect
            {...p}
            counterparties={counterparties}
            value={form.counterparty_id}
            onChange={(e) => setForm({ ...form, counterparty_id: e.target.value })}
          />
        )}
      </Field>
      <Field label="Referencia" hint="Opcional: número de comprobante u operación." error={fe.reference}>
        {(p) => <Input {...p} maxLength={100} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />}
      </Field>
      <div className="col-span-2 flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {transaction ? 'Guardar cambios' : 'Cargar movimiento'}
        </Button>
      </div>
    </form>
  )
}

export function VoidForm({ transaction, onDone }: { transaction: Transaction; onDone: () => void }) {
  const { cid } = useFinance()
  const toast = useToast()
  const invalidate = useInvalidateFinance()
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const tooShort = reason.trim().length < 3
  const posted = postedEntryOf(transaction.journal_entry)
  const voidTx = useMutation({
    mutationFn: () => post<Transaction[]>(`/finance/contexts/${cid}/transactions/${transaction.id}/void`, { reason: reason.trim() }),
    onSuccess: (list) => {
      invalidate()
      toast('ok', list.length > 1 ? 'Transferencia anulada: se anularon sus dos movimientos.' : 'Movimiento anulado.')
      onDone()
    },
  })
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!tooShort && !posted) voidTx.mutate()
  }
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div className="rounded-sm border border-line px-3.5 py-2.5">
        <p className="font-medium">{transaction.description}</p>
        <p className="text-sm text-ink-2">
          {formatBookDate(transaction.booked_on)} · <Amount value={transaction.amount} currency={transaction.currency} flow />
        </p>
      </div>
      <p className="text-ink-2">
        Nada se borra: el movimiento queda a la vista como anulado, con tu motivo, y deja de contar en saldos y resúmenes.
        {transaction.transfer_group_id && ' Es una transferencia: se anulan sus dos movimientos.'}
      </p>
      {posted && <PostedEntryNotice entry={posted} action="void" />}
      {voidTx.error ? <FormError error={voidTx.error} action="void" /> : null}
      <Field label="Motivo de la anulación" error={touched && tooShort ? 'Escribí el motivo (al menos 3 caracteres).' : undefined}>
        {(p) => <Textarea {...p} autoFocus required maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" busy={voidTx.isPending} disabled={Boolean(posted)}>
          Anular movimiento
        </Button>
      </div>
    </form>
  )
}

export function TransferForm({ accounts, onDone }: { accounts: Account[]; onDone: () => void }) {
  const { cid } = useFinance()
  const toast = useToast()
  const invalidate = useInvalidateFinance()
  const active = accounts.filter((a) => !a.archived_at)
  const [fromId, setFromId] = useState(active[0]?.id ?? '')
  const [toId, setToId] = useState(active[1]?.id ?? '')
  const out = useAmountField()
  const inn = useAmountField()
  const [form, setForm] = useState({ booked_on: todayIso(), description: 'Transferencia entre cuentas propias', reference: '' })
  const from = accounts.find((a) => a.id === fromId)
  const to = accounts.find((a) => a.id === toId)
  const sameCurrency = from && to && from.currency === to.currency
  const sameAccount = fromId !== '' && fromId === toId

  const save = useMutation({
    mutationFn: (amounts: { amount_out: string; amount_in: string }) =>
      post<TransferResult>(`/finance/contexts/${cid}/transfers`, {
        from_account_id: fromId,
        to_account_id: toId,
        booked_on: form.booked_on,
        description: form.description,
        reference: form.reference.trim() || null,
        ...amounts,
      }),
    onSuccess: (r) => {
      invalidate()
      toast('ok', `Transferencia de ${formatMoney(negateAmount(r.outgoing.amount), r.outgoing.currency)} registrada.`)
      onDone()
    },
  })
  const fe = save.error instanceof ApiError ? save.error.fieldErrors() : {}

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!from || !to || sameAccount) return
    const amountOut = out.read(from.currency, { positive: true })
    if (amountOut === null) return
    // Misma moneda: sale y entra lo mismo (las comisiones se cargan aparte).
    const amountIn = sameCurrency ? amountOut : inn.read(to.currency, { positive: true })
    if (amountIn === null) return
    save.mutate({ amount_out: amountOut, amount_in: amountIn })
  }

  if (active.length < 2) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-ink-2">Para transferir hacen falta al menos dos cuentas activas en este contexto. Creá otra cuenta primero.</p>
        <div className="flex justify-end border-t border-line pt-4">
          <Button variant="secondary" onClick={onDone}>
            Entendido
          </Button>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-2 gap-x-4 gap-y-4" noValidate>
      <p className="col-span-2 text-ink-2">
        Mueve plata entre dos cuentas propias de este contexto. No es ingreso ni gasto: no aparece en los resúmenes, pero sí en los
        saldos. Un aporte entre la empresa y lo personal no es una transferencia: se carga en cada contexto por separado.
      </p>
      {save.error ? (
        <div className="col-span-2">
          <FormError error={save.error} />
        </div>
      ) : null}
      <Field label="Desde (sale)" error={fe.from_account_id}>
        {(p) => <AccountSelect {...p} accounts={accounts} value={fromId} onChange={(e) => setFromId(e.target.value)} />}
      </Field>
      <Field label="Hacia (entra)" error={sameAccount ? 'Elegí una cuenta distinta de la de origen.' : fe.to_account_id}>
        {(p) => <AccountSelect {...p} accounts={accounts} value={toId} onChange={(e) => setToId(e.target.value)} />}
      </Field>
      <Field label={sameCurrency ? 'Importe' : `Sale de ${from?.name ?? 'origen'}`} error={out.error ?? fe.amount_out}>
        {(p) => <AmountInput {...p} autoFocus currency={from?.currency ?? 'PYG'} value={out.text} onChange={out.set} />}
      </Field>
      {sameCurrency ? (
        <Field label="Fecha" error={fe.booked_on}>
          {(p) => <Input {...p} type="date" value={form.booked_on} onChange={(e) => setForm({ ...form, booked_on: e.target.value })} />}
        </Field>
      ) : (
        <Field label={`Entra en ${to?.name ?? 'destino'}`} error={inn.error ?? fe.amount_in} hint="Monedas distintas: el importe que efectivamente llegó.">
          {(p) => <AmountInput {...p} currency={to?.currency ?? 'PYG'} value={inn.text} onChange={inn.set} />}
        </Field>
      )}
      {!sameCurrency && (
        <Field label="Fecha" error={fe.booked_on}>
          {(p) => <Input {...p} type="date" value={form.booked_on} onChange={(e) => setForm({ ...form, booked_on: e.target.value })} />}
        </Field>
      )}
      <div className={sameCurrency ? 'col-span-2' : ''}>
        <Field label="Referencia" hint="Opcional." error={fe.reference}>
          {(p) => <Input {...p} maxLength={100} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />}
        </Field>
      </div>
      <div className="col-span-2">
        <Field label="Descripción" error={fe.description}>
          {(p) => <Input {...p} maxLength={500} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}
        </Field>
      </div>
      <div className="col-span-2 flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending} disabled={sameAccount}>
          Registrar transferencia
        </Button>
      </div>
    </form>
  )
}
