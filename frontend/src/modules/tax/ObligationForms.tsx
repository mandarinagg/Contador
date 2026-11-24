/** Formularios de una obligación: presentada, pagada, no aplica y reabrir (D-087, D-105). */
import { useMutation, useQuery } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Button, Field, Input, Select } from '../../components/ui'
import { formatMoney, parseAmountInput, toInputText } from '../../lib/money'
import { get, post, qs } from '../../services/api'
import { AmountInput, ApiErrorNotice } from '../finance/components'
import { useContexts } from '../finance/data'
import { formatBookDate, todayIso } from '../finance/labels'
import type { Transaction } from '../finance/types'
import { ReasonForm } from './components'
import { obligationLabel, periodLabel } from './labels'
import { addDays, isRegister, isVat, type ObligationAction } from './logic'
import type { Obligation } from './types'


function Heading({ o }: { o: Obligation }) {
  return (
    <div className="rounded-sm border border-line px-3.5 py-2.5">
      <p className="font-medium">{obligationLabel(o.code)}</p>
      <p className="text-sm text-ink-2">
        {periodLabel(o.period_start, o.period_end)} · obligación {o.dnit_code} · vence el {formatBookDate(o.due_date)}
      </p>
    </div>
  )
}

/** Importe opcional en guaraníes: `null` si está vacío, `undefined` si es inválido. */
function readOptional(text: string, setError: (e: string | undefined) => void): string | null | undefined {
  if (!text.trim()) return null
  const parsed = parseAmountInput(text, 'PYG')
  if (!parsed.ok) {
    setError(parsed.error)
    return undefined
  }
  if (parsed.value.startsWith('-')) {
    setError('Va sin signo.')
    return undefined
  }
  return parsed.value
}

function FileForm({ o, onDone }: { o: Obligation; onDone: () => void }) {
  const [filedOn, setFiledOn] = useState(todayIso())
  const [reference, setReference] = useState('')
  const [amount, setAmount] = useState(o.calculated_amount && o.calculated_amount !== '0' ? toInputText(o.calculated_amount, 'PYG') : '')
  const [balance, setBalance] = useState(o.calculated_credit_balance && o.calculated_credit_balance !== '0' ? toInputText(o.calculated_credit_balance, 'PYG') : '')
  const [errors, setErrors] = useState<Record<string, string | undefined>>({})
  const register = isRegister(o)
  const run = useMutation({ mutationFn: (body: object) => post(`/tax/obligations/${o.id}/file`, body), onSuccess: onDone })

  const send = (e: FormEvent) => {
    e.preventDefault()
    const next: Record<string, string | undefined> = {}
    if (!filedOn) next.filedOn = 'Indicá la fecha en que se presentó.'
    if (!reference.trim()) next.reference = register ? 'Indicá el número de la constancia de confirmación.' : 'Indicá el número de la constancia o del talón.'
    const declared = readOptional(amount, (m) => (next.amount = m))
    const credit = isVat(o) ? readOptional(balance, (m) => (next.balance = m)) : null
    setErrors(next)
    if (Object.values(next).some(Boolean)) return
    run.mutate({
      filed_on: filedOn,
      filing_reference: reference.trim(),
      ...(declared ? { declared_amount: declared } : {}),
      ...(credit ? { declared_credit_balance: credit } : {}),
    })
  }

  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <Heading o={o} />
      <p className="text-ink-2">
        {register
          ? 'Registrá que confirmaste el registro de comprobantes del mes en Marangatu. Desde ese momento los comprobantes del mes quedan en solo lectura; para corregirlos se reabre (como una rectificativa).'
          : 'Registrá lo que presentaste a mano en Marangatu. La app no presenta nada: solo guarda la fecha, la constancia y lo declarado.'}
      </p>
      <div className="grid grid-cols-2 gap-4">
        <Field label={register ? 'Fecha de confirmación' : 'Fecha de presentación'} error={errors.filedOn}>
          {(p) => <Input {...p} autoFocus type="date" value={filedOn} onChange={(e) => setFiledOn(e.target.value)} />}
        </Field>
        <Field label={register ? 'N° de constancia' : 'N° de constancia o talón'} error={errors.reference}>
          {(p) => <Input {...p} maxLength={60} value={reference} onChange={(e) => setReference(e.target.value)} />}
        </Field>
        {!register && (
          <Field
            label={isVat(o) ? 'Impuesto declarado (casilla 58 o 50)' : 'Importe declarado'}
            hint={o.calculated_amount ? `Estimado: ${formatMoney(o.calculated_amount, 'PYG')}. Poné lo que figura en la declaración.` : 'Opcional: lo que figura en la declaración.'}
            error={errors.amount}
          >
            {(p) => <AmountInput {...p} currency="PYG" value={amount} onChange={setAmount} />}
          </Field>
        )}
        {isVat(o) && (
          <Field
            label="Saldo a favor declarado (casilla 47)"
            hint="El IVA del mes siguiente usa este saldo como «saldo anterior declarado», antes que el estimado (D-105)."
            error={errors.balance}
          >
            {(p) => <AmountInput {...p} currency="PYG" value={balance} onChange={setBalance} />}
          </Field>
        )}
      </div>
      <ApiErrorNotice error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          {register ? 'Marcar confirmado' : 'Marcar presentada'}
        </Button>
      </div>
    </form>
  )
}

function PayForm({ o, onDone }: { o: Obligation; onDone: () => void }) {
  const contexts = useContexts()
  const business = contexts.data?.find((c) => c.kind === 'business')
  const from = addDays(o.due_date, -45)
  const to = addDays(o.due_date, 45)
  const txs = useQuery({
    enabled: Boolean(business),
    queryKey: ['finance', business?.id ?? '', 'transactions', 'tax-payment', from, to],
    queryFn: () => get<Transaction[]>(`/finance/contexts/${business?.id}/transactions${qs({ from, to, limit: 200 })}`),
  })
  const outflows = (txs.data ?? []).filter((t) => t.amount.startsWith('-') && t.currency === 'PYG' && !t.voided_at)
  const [paidOn, setPaidOn] = useState(todayIso())
  const [amount, setAmount] = useState(o.declared_amount ? toInputText(o.declared_amount, 'PYG') : '')
  const [txId, setTxId] = useState('')
  const [errors, setErrors] = useState<Record<string, string | undefined>>({})
  const run = useMutation({ mutationFn: (body: object) => post(`/tax/obligations/${o.id}/pay`, body), onSuccess: onDone })

  const send = (e: FormEvent) => {
    e.preventDefault()
    const next: Record<string, string | undefined> = {}
    if (!paidOn) next.paidOn = 'Indicá la fecha del pago.'
    let value: string | null | undefined = readOptional(amount, (m) => (next.amount = m))
    if (value === null) {
      next.amount = 'Indicá el importe pagado.'
      value = undefined
    }
    setErrors(next)
    if (Object.values(next).some(Boolean) || !value) return
    run.mutate({ paid_on: paidOn, paid_amount: value, ...(txId ? { transaction_id: txId } : {}) })
  }

  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <Heading o={o} />
      <div className="grid grid-cols-2 gap-4">
        <Field label="Fecha del pago" error={errors.paidOn}>
          {(p) => <Input {...p} autoFocus type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />}
        </Field>
        <Field label="Importe pagado" error={errors.amount} hint={o.declared_amount ? `Declarado: ${formatMoney(o.declared_amount, 'PYG')}.` : undefined}>
          {(p) => <AmountInput {...p} currency="PYG" value={amount} onChange={setAmount} />}
        </Field>
      </div>
      <Field
        label="Movimiento de finanzas (opcional)"
        hint={
          business
            ? `Salidas de la empresa en guaraníes entre el ${formatBookDate(from)} y el ${formatBookDate(to)}. Vincularlo deja el pago trazable.`
            : 'Sin acceso a las finanzas de la empresa no se puede vincular un movimiento.'
        }
      >
        {(p) => (
          <Select {...p} value={txId} disabled={!business} onChange={(e) => setTxId(e.target.value)}>
            <option value="">Sin vincular</option>
            {outflows.map((t) => (
              <option key={t.id} value={t.id}>
                {formatBookDate(t.booked_on)} · {t.description} · {formatMoney(t.amount, 'PYG')}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <ApiErrorNotice error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          Marcar pagada
        </Button>
      </div>
    </form>
  )
}

export function ObligationActionForm({ action, o, onDone }: { action: ObligationAction; o: Obligation; onDone: (changed: boolean) => void }) {
  if (action === 'file') return <FileForm o={o} onDone={() => onDone(true)} />
  if (action === 'pay') return <PayForm o={o} onDone={() => onDone(true)} />
  if (action === 'not_applicable') {
    return (
      <ReasonForm
        intro={
          <>
            <Heading o={o} />
            <p className="text-ink-2">Una obligación marcada «no aplica» a mano no vuelve a pendiente: si después corresponde, se corrige el perfil fiscal.</p>
          </>
        }
        submit="Marcar no aplica"
        onCancel={() => onDone(false)}
        onSubmit={async (reason) => {
          await post(`/tax/obligations/${o.id}/not-applicable`, { reason })
          onDone(true)
        }}
      />
    )
  }
  return (
    <ReasonForm
      intro={
        <>
          <Heading o={o} />
          <p className="text-ink-2">
            {isRegister(o)
              ? 'Reabrir el registro desbloquea los comprobantes del mes para corregirlos (como una rectificativa en Marangatu). Queda auditado con el motivo.'
              : 'Vuelve a pendiente, por ejemplo si presentaste una rectificativa o hubo un error de carga. Queda auditado con el motivo.'}
          </p>
        </>
      }
      label="Motivo de la reapertura"
      submit="Reabrir"
      onCancel={() => onDone(false)}
      onSubmit={async (reason) => {
        await post(`/tax/obligations/${o.id}/reopen`, { reason })
        onDone(true)
      }}
    />
  )
}
