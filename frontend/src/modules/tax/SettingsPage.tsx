/**
 * Configuración tributaria (D-091, D-092, D-101): las cuentas contables que usan los asientos
 * propuestos desde comprobantes y el control del IVA contra el mayor, y con cuántos días de
 * anticipación avisar los vencimientos. Sin configurar, cada cuenta es la del plan propuesto.
 */
import { useMutation } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'
import { Button, Field, Input, Notice, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { put } from '../../services/api'
import { LedgerAccountSelect } from '../accounting/components'
import { useChart } from '../accounting/data'
import type { LedgerAccount } from '../accounting/types'
import { ApiErrorNotice, ReadOnlyHint } from '../finance/components'
import { useInvalidateTax, useTaxPerms, useTaxSettings } from './data'
import type { TaxSettings } from './types'

/** Tipo de cuenta admitido por campo (igual que `ACCOUNT_FIELDS` en `tax_settings.py`). */
const FIELD_KINDS: Record<string, LedgerAccount['kind'][]> = {
  vat_credit_10_account_id: ['asset'],
  vat_credit_5_account_id: ['asset'],
  vat_debit_10_account_id: ['liability'],
  vat_debit_5_account_id: ['liability'],
  suppliers_account_id: ['liability'],
  customers_account_id: ['asset'],
}

type Draft = { accounts: Record<string, string>; alertDays: string }

const draftOf = (s: TaxSettings): Draft => ({
  accounts: Object.fromEntries(s.accounts.map((a) => [a.field, a.configured_id ?? ''])),
  alertDays: String(s.alert_days),
})

export function TaxSettingsPage() {
  const settings = useTaxSettings()
  return (
    <>
      <PageHeader
        title="Configuración de impuestos"
        description="Las cuentas que usan los asientos propuestos desde comprobantes y el control del IVA contra el mayor. Si una queda en «la del plan», se usa la cuenta con ese código del plan propuesto."
      />
      {settings.isError ? (
        <ApiErrorNotice error={settings.error} title="No se pudo leer la configuración." />
      ) : !settings.data ? (
        <Skeleton className="h-80" />
      ) : (
        <SettingsForm initial={settings.data} />
      )}
    </>
  )
}

function SettingsForm({ initial }: { initial: TaxSettings }) {
  const perms = useTaxPerms()
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const chart = useChart()
  const [current, setCurrent] = useState(initial)
  const [draft, setDraft] = useState<Draft>(() => draftOf(initial))
  const [daysError, setDaysError] = useState<string>()

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => put<TaxSettings>('/tax/settings', body),
    onSuccess: (s) => {
      invalidate()
      setCurrent(s)
      setDraft(draftOf(s))
      toast('ok', 'Configuración guardada.')
    },
  })

  const accounts = chart.data?.accounts ?? []
  const disabled = !perms.canManage

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const days = Number(draft.alertDays)
    if (!Number.isInteger(days) || days < 1 || days > 60) {
      setDaysError('Entre 1 y 60 días.')
      return
    }
    setDaysError(undefined)
    save.mutate({ ...Object.fromEntries(Object.entries(draft.accounts).map(([k, v]) => [k, v || null])), alert_days: days })
  }

  return (
        <form onSubmit={submit} noValidate className="flex max-w-3xl flex-col gap-6">
          <Sheet>
            <h2 className="border-b border-line px-5 py-3.5 font-semibold">Cuentas contables</h2>
            {chart.isSuccess && accounts.length === 0 && (
              <div className="px-5 pt-4">
                <Notice tone="warn" title="Todavía no hay plan de cuentas">
                  Cargá el plan propuesto en{' '}
                  <Link to="/contabilidad/plan" className="font-medium underline">
                    Contabilidad
                  </Link>{' '}
                  para que los asientos y el control del IVA tengan cuentas.
                </Notice>
              </div>
            )}
            <div className="flex flex-col gap-5 p-5">
              {current.accounts.map((a) => (
                <div key={a.field} className="grid grid-cols-[14rem_minmax(0,1fr)] items-start gap-4">
                  <div>
                    <p className="font-medium first-letter:uppercase">{a.label}</p>
                    <p className="text-sm text-ink-3">
                      En uso:{' '}
                      {a.effective_code ? (
                        <span className="tabular-nums">
                          {a.effective_code} {a.effective_name}
                        </span>
                      ) : (
                        <span className="text-amber">ninguna (falta la cuenta {a.default_code})</span>
                      )}
                    </p>
                  </div>
                  <Field label={`Cuenta de ${a.label}`}>
                    {(p) => (
                      <LedgerAccountSelect
                        {...p}
                        accounts={accounts}
                        kinds={FIELD_KINDS[a.field] ?? ['asset', 'liability']}
                        value={draft.accounts[a.field] ?? ''}
                        disabled={disabled}
                        empty={`La del plan (${a.default_code})`}
                        onChange={(id) => setDraft({ ...draft, accounts: { ...draft.accounts, [a.field]: id } })}
                      />
                    )}
                  </Field>
                </div>
              ))}
            </div>
          </Sheet>

          <Sheet className="p-5">
            <h2 className="font-semibold">Avisos</h2>
            <div className="mt-3 w-48">
              <Field label="Días de anticipación" error={daysError} hint="Cuántos días antes del vencimiento avisar (1 a 60).">
                {(p) => (
                  <Input
                    {...p}
                    type="number"
                    min={1}
                    max={60}
                    disabled={disabled}
                    value={draft.alertDays}
                    onChange={(e) => setDraft({ ...draft, alertDays: e.target.value })}
                  />
                )}
              </Field>
            </div>
          </Sheet>

          <ApiErrorNotice error={save.error} />
          <div className="flex items-center justify-end gap-3">
            <ReadOnlyHint reason={perms.manageReason} />
            <Button type="submit" busy={save.isPending} disabled={disabled}>
              Guardar
            </Button>
          </div>
        </form>
  )
}
