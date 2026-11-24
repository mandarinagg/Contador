import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Pencil, Plus } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { CURRENCIES, CURRENCY_NAMES, toInputText } from '../../lib/money'
import { ApiError, get, patch, post, qs } from '../../services/api'
import { Amount, AmountInput, ApiErrorNotice, Check, TableSkeleton, Th } from './components'
import { errorMessage, useAmountField } from './forms'
import { financeKeys, useAccounts, useFinance } from './data'
import { ACCOUNT_KIND_LABELS, formatBookDate, todayIso } from './labels'
import type { Account, AccountKind, Transaction } from './types'

interface FormState {
  name: string
  kind: AccountKind
  institution: string
  currency: string
  number_last4: string
  opening_date: string
}

function AccountForm({ account, onDone }: { account?: Account; onDone: () => void }) {
  const { cid } = useFinance()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<FormState>(() => ({
    name: account?.name ?? '',
    kind: account?.kind ?? 'checking',
    institution: account?.institution ?? '',
    currency: account?.currency ?? 'PYG',
    number_last4: account?.number_last4 ?? '',
    opening_date: account?.opening_date ?? todayIso(),
  }))
  const opening = useAmountField(
    account ? (account.opening_balance.startsWith('-') ? '-' : '') + toInputText(account.opening_balance, account.currency) : '0',
  )

  // Si ya tiene movimientos (incluso anulados), la moneda y el saldo inicial quedan fijos.
  const used = useQuery({
    queryKey: [...financeKeys.transactions(cid), 'exists', account?.id],
    queryFn: () =>
      get<Transaction[]>(`/finance/contexts/${cid}/transactions${qs({ account_id: account?.id, include_voided: true, limit: 1 })}`),
    enabled: Boolean(account),
  })
  const locked = Boolean(account) && (used.data?.length ?? 1) > 0

  const save = useMutation({
    mutationFn: (openingBalance: string) => {
      const body: Record<string, unknown> = {
        name: form.name,
        kind: form.kind,
        institution: form.institution.trim() || null,
        number_last4: form.number_last4 || null,
        opening_date: form.opening_date,
      }
      if (!account) {
        return post<Account>(`/finance/contexts/${cid}/accounts`, { ...body, currency: form.currency, opening_balance: openingBalance })
      }
      if (form.currency !== account.currency) body.currency = form.currency
      if (openingBalance !== account.opening_balance) body.opening_balance = openingBalance
      return patch<Account>(`/finance/contexts/${cid}/accounts/${account.id}`, body)
    },
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: financeKeys.context(cid) })
      qc.invalidateQueries({ queryKey: financeKeys.consolidated() })
      toast('ok', account ? `Cuenta «${a.name}» guardada.` : `Cuenta «${a.name}» creada.`)
      onDone()
    },
  })
  const error = save.error instanceof ApiError ? save.error : null
  const fe = error?.fieldErrors() ?? {}
  const last4Invalid = form.number_last4 !== '' && !/^\d{4}$/.test(form.number_last4)

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (last4Invalid) return
    const value = opening.read(form.currency, { allowZero: true })
    if (value === null) return
    save.mutate(value)
  }

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-2 gap-x-4 gap-y-4" noValidate>
      {error && error.status !== 422 && (
        <div className="col-span-2">
          <Notice tone="bad" title={error.message}>
            {error.code === 'ACCOUNT_HAS_TRANSACTIONS' &&
              'Los saldos de los meses anteriores dependen de esos datos. Si la cuenta se cargó mal, creá una nueva y archivá esta.'}
          </Notice>
        </div>
      )}
      <div className="col-span-2">
        <Field label="Nombre" error={fe.name} hint="Como la reconocés: «Itaú cuenta corriente», «Caja chica».">
          {(p) => <Input {...p} autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
        </Field>
      </div>
      <Field label="Tipo">
        {(p) => (
          <Select {...p} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as AccountKind })}>
            {Object.entries(ACCOUNT_KIND_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Banco o entidad" error={fe.institution} hint="Opcional.">
        {(p) => <Input {...p} value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} />}
      </Field>
      <Field
        label="Moneda"
        hint={locked ? 'Fija: la cuenta ya tiene movimientos.' : 'No se mezcla con otras monedas en ningún total.'}
      >
        {(p) => (
          <Select {...p} disabled={locked} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {CURRENCY_NAMES[c]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Últimos 4 dígitos" error={last4Invalid ? 'Son exactamente 4 dígitos.' : fe.number_last4} hint="Opcional. Nunca se guarda el número completo.">
        {(p) => (
          <Input
            {...p}
            inputMode="numeric"
            maxLength={4}
            className="w-28"
            value={form.number_last4}
            onChange={(e) => setForm({ ...form, number_last4: e.target.value.replace(/\D/g, '') })}
          />
        )}
      </Field>
      <Field
        label="Saldo inicial"
        error={opening.error ?? fe.opening_balance}
        hint={locked ? 'Fijo: la cuenta ya tiene movimientos.' : 'Lo que había al abrirla o al empezar a usar Contador AI. Negativo si es deuda.'}
      >
        {(p) => <AmountInput {...p} disabled={locked} currency={form.currency} value={opening.text} onChange={opening.set} />}
      </Field>
      <Field label="Fecha del saldo inicial" error={fe.opening_date}>
        {(p) => <Input {...p} type="date" value={form.opening_date} onChange={(e) => setForm({ ...form, opening_date: e.target.value })} />}
      </Field>
      {locked && (
        <p className="col-span-2 rounded-sm bg-sunken px-3 py-2 text-sm text-ink-2">
          La moneda y el saldo inicial no se pueden cambiar porque la cuenta ya tiene movimientos (incluso anulados): todos los
          saldos se calculan a partir de ellos. Si la cuenta se cargó mal, creá una nueva y archivá esta.
        </p>
      )}
      <div className="col-span-2 flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {account ? 'Guardar cambios' : 'Crear cuenta'}
        </Button>
      </div>
    </form>
  )
}

export function AccountsPage() {
  const { cid, canWrite, readOnlyReason } = useFinance()
  const qc = useQueryClient()
  const toast = useToast()
  const accounts = useAccounts(cid)
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState<Account | 'new' | null>(null)

  const archive = useMutation({
    mutationFn: (a: Account) => patch<Account>(`/finance/contexts/${cid}/accounts/${a.id}`, { archived: a.archived_at === null }),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: financeKeys.context(cid) })
      qc.invalidateQueries({ queryKey: financeKeys.consolidated() })
      toast('ok', a.archived_at ? `Cuenta «${a.name}» archivada.` : `Cuenta «${a.name}» desarchivada.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar el estado de la cuenta.')),
  })

  const all = accounts.data ?? []
  const archivedCount = all.filter((a) => a.archived_at).length
  const rows = all.filter((a) => showArchived || !a.archived_at)

  return (
    <>
      <PageHeader
        title="Cuentas"
        description="Bancos, cajas, tarjetas y billeteras. El saldo es el inicial más los movimientos no anulados."
        actions={
          canWrite && (
            <Button onClick={() => setEditing('new')}>
              <Plus size={16} />
              Nueva cuenta
            </Button>
          )
        }
      />
      {!canWrite && <p className="-mt-3 mb-4 text-sm text-ink-3">{readOnlyReason}</p>}
      <Sheet>
        {accounts.isPending ? (
          <TableSkeleton cols={4} />
        ) : accounts.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={accounts.error} title="No se pudieron cargar las cuentas." />
          </div>
        ) : all.length === 0 ? (
          <EmptyState
            title="Todavía no hay cuentas. Creá la primera"
            action={
              canWrite && (
                <Button onClick={() => setEditing('new')}>
                  <Plus size={16} />
                  Nueva cuenta
                </Button>
              )
            }
          >
            Empezá por la cuenta donde más se mueve la plata: la corriente del banco o la caja. Después vas a poder cargar
            movimientos o importar el extracto.
          </EmptyState>
        ) : (
          <>
            <table className="w-full">
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>Cuenta</Th>
                  <Th>Tipo</Th>
                  <Th>Saldo inicial</Th>
                  <Th align="right">Saldo actual</Th>
                  {canWrite && (
                    <Th>
                      <span className="sr-only">Acciones</span>
                    </Th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((a) => (
                  <tr key={a.id} className={cx(a.archived_at && 'text-ink-3')}>
                    <td className="px-4 py-3">
                      <p className="font-medium">
                        {a.name}
                        {a.archived_at && (
                          <span className="ml-2">
                            <Badge>Archivada</Badge>
                          </span>
                        )}
                      </p>
                      <p className="text-sm text-ink-2">
                        {[a.institution, a.number_last4 && `terminada en ${a.number_last4}`].filter(Boolean).join(', ') || a.currency}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-sm text-ink-2">{ACCOUNT_KIND_LABELS[a.kind]}</td>
                    <td className="px-4 py-3 text-sm text-ink-2">
                      <Amount value={a.opening_balance} currency={a.currency} /> al {formatBookDate(a.opening_date)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Amount value={a.balance} currency={a.currency} strong />
                    </td>
                    {canWrite && (
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" className="h-8 px-2" aria-label={`Editar ${a.name}`} onClick={() => setEditing(a)}>
                            <Pencil size={15} />
                          </Button>
                          <Button
                            variant="ghost"
                            className="h-8 px-2"
                            aria-label={a.archived_at ? `Desarchivar ${a.name}` : `Archivar ${a.name}`}
                            title={a.archived_at ? 'Desarchivar' : 'Archivar: deja de ofrecerse para cargar, pero conserva su historia'}
                            disabled={archive.isPending}
                            onClick={() => archive.mutate(a)}
                          >
                            {a.archived_at ? <ArchiveRestore size={15} /> : <Archive size={15} />}
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {archivedCount > 0 && (
              <div className="border-t border-line px-4 py-3">
                <Check
                  label={`Mostrar archivadas (${archivedCount})`}
                  checked={showArchived}
                  onChange={setShowArchived}
                />
              </div>
            )}
          </>
        )}
      </Sheet>
      <Modal open={editing !== null} title={editing === 'new' ? 'Nueva cuenta' : 'Editar cuenta'} onClose={() => setEditing(null)}>
        {editing !== null && <AccountForm key={editing === 'new' ? 'new' : editing.id} account={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  )
}
