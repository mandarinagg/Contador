/**
 * "Proponer asiento" desde un movimiento de la empresa (D-041, D-052): arma un borrador y abre
 * el editor. Si falta la cuenta contable del banco o de la categoría, se configura acá mismo;
 * en otra moneda se pide la cotización y, si el producto no es entero, se elige el redondeo.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BookPlus } from 'lucide-react'
import { type FormEvent, type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Button, Field, Input, Notice } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatMoney } from '../../lib/money'
import { ApiError, patch, post } from '../../services/api'
import { Amount, ApiErrorNotice } from '../finance/components'
import { financeKeys } from '../finance/data'
import { categoryLabel, formatBookDate } from '../finance/labels'
import { CategorySelect } from '../finance/pickers'
import type { Account, Category, Transaction } from '../finance/types'
import { formatDecimal, parseRateInput } from './amounts'
import { LedgerAccountSelect } from './components'
import { accountingKeys, useChart, useInvalidateAccounting } from './data'
import type { Entry } from './types'

interface Missing {
  kind: 'account' | 'category'
  id: string
  name: string
}

interface Rounding {
  exact: string
  floor: string
  ceil: string
}

export function ProposeEntryForm({
  tx,
  cid,
  accounts,
  categories,
  onDone,
}: {
  tx: Transaction
  cid: string
  accounts: Account[]
  categories: Category[]
  onDone: () => void
}) {
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const invalidate = useInvalidateAccounting()
  const chart = useChart()
  const foreign = tx.currency !== 'PYG'
  const [rateText, setRateText] = useState('')
  const [rateError, setRateError] = useState<string>()
  const [rounding, setRounding] = useState<Rounding | null>(null)
  const [roundChoice, setRoundChoice] = useState<'floor' | 'ceil' | ''>('')
  const [missing, setMissing] = useState<Missing[]>([])
  const [picks, setPicks] = useState<Record<string, string>>({})
  const [needsCategory, setNeedsCategory] = useState(false)
  const [categoryId, setCategoryId] = useState('')
  const account = accounts.find((a) => a.id === tx.account_id)
  const income = !tx.amount.startsWith('-')

  const propose = useMutation({
    mutationFn: async () => {
      // 1) Lo que haya que configurar antes (cuentas contables, categoría).
      for (const m of missing) {
        const value = picks[m.id]
        if (!value) continue
        const path = m.kind === 'account' ? `/finance/contexts/${cid}/accounts/${m.id}` : `/finance/contexts/${cid}/categories/${m.id}`
        await patch(path, { ledger_account_id: value })
      }
      if (needsCategory && categoryId) await patch(`/finance/contexts/${cid}/transactions/${tx.id}`, { category_id: categoryId })
      // Ya quedó guardado: si el borrador todavía pide algo (p. ej. el redondeo), no se repite.
      if (missing.length > 0) {
        setMissing([])
        setPicks({})
      }
      if (needsCategory) setNeedsCategory(false)
      // 2) El borrador.
      const body: Record<string, string> = {}
      if (foreign) {
        const rate = parseRateInput(rateText)
        if (!rate.ok) throw new RateError(rate.error)
        body.fx_rate = rate.value
        if (rounding && roundChoice) body.amount_pyg = rounding[roundChoice]
      }
      return post<Entry>(`/accounting/entries/from-transaction/${tx.id}`, body)
    },
    onSuccess: (entry) => {
      qc.setQueryData(accountingKeys.entry(entry.id), entry)
      invalidate()
      toast('ok', 'Borrador de asiento creado. Revisalo y contabilizalo cuando esté bien.')
      onDone()
      navigate(`/contabilidad/asientos/${entry.id}`)
    },
    onError: (e) => {
      if (e instanceof RateError) {
        setRateError(e.message)
        return
      }
      if (!(e instanceof ApiError)) return
      // Lo configurado en este intento ya quedó guardado aunque el borrador falle.
      qc.invalidateQueries({ queryKey: financeKeys.context(cid) })
      if (e.code === 'LEDGER_ACCOUNT_MISSING') {
        const list = ((e.details as { missing?: Missing[] } | null)?.missing ?? []) as Missing[]
        setMissing(list)
        setPicks((p) => Object.fromEntries(list.map((m) => [m.id, p[m.id] ?? ''])))
      } else if (e.code === 'CATEGORY_REQUIRED') {
        setNeedsCategory(true)
      } else if (e.code === 'FX_ROUNDING_REQUIRED') {
        setRounding(e.details as Rounding)
        setRoundChoice('')
      } else if (e.code === 'FX_RATE_REQUIRED') {
        setRateError(e.message)
      }
    },
  })
  const err = propose.error instanceof ApiError ? propose.error : null
  const handled = err && ['LEDGER_ACCOUNT_MISSING', 'CATEGORY_REQUIRED', 'FX_ROUNDING_REQUIRED', 'FX_RATE_REQUIRED'].includes(err.code)
  const pendingPicks = missing.some((m) => !picks[m.id])
  const blocked = pendingPicks || (needsCategory && !categoryId) || (rounding !== null && !roundChoice)

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setRateError(undefined)
    if (foreign && !parseRateInput(rateText).ok) {
      const r = parseRateInput(rateText)
      setRateError(r.ok ? undefined : r.error)
      return
    }
    propose.mutate()
  }

  const ledgerAccounts = chart.data?.accounts ?? []
  const catKind = (id: string) => categories.find((c) => c.id === id)?.kind ?? (income ? 'income' : 'expense')

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div className="rounded-sm border border-line px-3.5 py-2.5">
        <p className="font-medium">{tx.description}</p>
        <p className="text-sm text-ink-2">
          {formatBookDate(tx.booked_on)} · {account?.name ?? 'Cuenta'} · <Amount value={tx.amount} currency={tx.currency} flow />
          {tx.category_id && <> · {categoryLabel(categories, tx.category_id)}</>}
        </p>
      </div>
      <p className="text-ink-2">
        Se arma un <span className="font-medium text-ink">borrador</span> fechado el {formatBookDate(tx.booked_on)}:{' '}
        {income ? 'debe en la cuenta contable del banco y haber en la de la categoría' : 'debe en la cuenta contable de la categoría y haber en la del banco'}. No
        entra en los libros hasta que alguien lo revise y lo contabilice.
      </p>

      {foreign && (
        <Field
          label={`Cotización: guaraníes por 1 ${tx.currency}`}
          error={rateError}
          hint={`La contabilidad se lleva en guaraníes. Escribí la cotización que corresponde (por ejemplo, la del comprobante); la app no la busca.`}
        >
          {(p) => (
            <div className="w-48">
              <Input
                {...p}
                autoFocus
                inputMode="decimal"
                className="text-right tabular-nums"
                placeholder="7.300,25"
                value={rateText}
                onChange={(e) => {
                  setRateText(e.target.value)
                  setRounding(null)
                  setRoundChoice('')
                }}
              />
            </div>
          )}
        </Field>
      )}

      {rounding && (
        <fieldset className="flex flex-col gap-2 rounded-sm border border-amber/50 bg-amber-soft px-3.5 py-3">
          <legend className="px-1 text-sm font-medium text-amber">El importe en guaraníes no es entero</legend>
          <p className="text-sm text-ink">
            {formatMoney(tx.amount.replace(/^-/, ''), tx.currency)} × {formatDecimal(parseRateInput(rateText).ok ? (parseRateInput(rateText) as { value: string }).value : rateText)} ={' '}
            <span className="font-medium tabular-nums">₲ {formatDecimal(rounding.exact)}</span>. Los guaraníes no llevan decimales: elegí cómo redondear (no se redondea
            solo).
          </p>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ['floor', 'Hacia abajo'],
                ['ceil', 'Hacia arriba'],
              ] as const
            ).map(([k, label]) => (
              <label
                key={k}
                className={cx(
                  'flex cursor-pointer items-center gap-2 rounded-sm border px-3 py-2 has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
                  roundChoice === k ? 'border-ledger bg-surface font-medium' : 'border-line-strong bg-surface/60',
                )}
              >
                <input type="radio" name="rounding" className="accent-(--ledger)" checked={roundChoice === k} onChange={() => setRoundChoice(k)} />
                {label}: <span className="tabular-nums">{formatMoney(rounding[k], 'PYG')}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {missing.length > 0 && (
        <div className="flex flex-col gap-3 rounded-sm border border-amber/50 bg-amber-soft px-3.5 py-3">
          <p className="font-medium text-amber">Falta configurar {missing.length === 1 ? 'una cuenta contable' : 'las cuentas contables'}</p>
          <p className="-mt-2 text-sm text-ink">
            Se configura una sola vez: los próximos movimientos de {missing.length === 1 ? 'esa cuenta o categoría' : 'esas cuentas y categorías'} la usan solos.
          </p>
          {ledgerAccounts.length === 0 ? (
            <p className="text-sm">
              Todavía no hay plan de cuentas.{' '}
              <Link to="/contabilidad/plan" className="font-medium text-ledger underline">
                Cargalo primero
              </Link>
              .
            </p>
          ) : (
            missing.map((m) => (
              <Field
                key={m.id}
                label={m.kind === 'account' ? `Cuenta contable de la cuenta «${m.name}»` : `Cuenta contable de la categoría «${m.name}»`}
                hint={m.kind === 'account' ? 'Activo (banco, caja) o pasivo (tarjeta de crédito).' : catKind(m.id) === 'income' ? 'Una cuenta de ingreso.' : 'Una cuenta de gasto.'}
              >
                {(p) => (
                  <LedgerAccountSelect
                    {...p}
                    accounts={ledgerAccounts}
                    kinds={m.kind === 'account' ? ['asset', 'liability'] : [catKind(m.id)]}
                    value={picks[m.id] ?? ''}
                    onChange={(v) => setPicks({ ...picks, [m.id]: v })}
                    empty="Elegí una cuenta contable"
                  />
                )}
              </Field>
            ))
          )}
        </div>
      )}

      {needsCategory && (
        <Field label="Categoría del movimiento" hint="Sin categoría no se sabe a qué cuenta de resultado va. Se guarda en el movimiento.">
          {(p) => <CategorySelect {...p} categories={categories} first={income ? 'income' : 'expense'} empty="Elegí una categoría" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} />}
        </Field>
      )}

      {err && !handled && <ProposeError error={err} />}
      {propose.error && !(propose.error instanceof ApiError) && !(propose.error instanceof RateError) ? <ApiErrorNotice error={propose.error} /> : null}

      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={propose.isPending} disabled={blocked}>
          <BookPlus size={16} />
          {missing.length > 0 || needsCategory ? 'Guardar y proponer' : 'Proponer asiento'}
        </Button>
      </div>
    </form>
  )
}

class RateError extends Error {}

function ProposeError({ error }: { error: ApiError }) {
  let extra: ReactNode = null
  if (error.code === 'TRANSACTION_HAS_ENTRY') {
    const id = (error.details as { entry_id?: string } | null)?.entry_id
    if (id)
      extra = (
        <Link to={`/contabilidad/asientos/${id}`} className="font-medium underline">
          Ver el asiento
        </Link>
      )
  } else if (error.code === 'FISCAL_YEAR_NOT_FOUND' || error.code === 'FISCAL_YEAR_CLOSED') {
    extra = (
      <Link to="/contabilidad/ejercicios" className="font-medium underline">
        Ir a Ejercicios y períodos
      </Link>
    )
  } else if (error.code === 'TRANSFER_NOT_SUPPORTED') {
    extra = 'Cargala como asiento manual: las dos patas van en el mismo asiento.'
  }
  return (
    <Notice tone="bad" title={error.message}>
      {extra}
    </Notice>
  )
}
