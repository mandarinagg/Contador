import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Button, Field, Input, Notice, PageHeader, Select, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { formatDateTime, LEGAL_FORM_LABELS } from '../../lib/format'
import { rucCheckDigit } from '../../lib/ruc'
import { ApiError, get, patch } from '../../services/api'
import { useSession } from '../../stores/session'
import type { LegalForm, Organization } from '../../types/api'

interface Form {
  legal_name: string
  trade_name: string
  legal_form: LegalForm
  ruc: string
  ruc_check_digit: string
}

const toForm = (o: Organization): Form => ({
  legal_name: o.legal_name,
  trade_name: o.trade_name ?? '',
  legal_form: o.legal_form,
  ruc: o.ruc ?? '',
  ruc_check_digit: o.ruc_check_digit ?? '',
})

export function OrganizationPage() {
  const org = useQuery({ queryKey: ['organization'], queryFn: () => get<Organization>('/organization') })
  return (
    <>
      <PageHeader
        title="Datos de la empresa"
        description="Identificación de la organización. Los datos societarios completos (accionistas, actas, libros) llegan con el módulo de gestión empresarial."
      />
      {org.data ? (
        // La key reinicia el formulario cuando cambia la versión guardada.
        <OrganizationForm key={org.data.updated_at} org={org.data} />
      ) : org.isError ? (
        <Notice tone="bad" title="No se pudieron cargar los datos de la empresa." />
      ) : (
        <Skeleton className="h-64 w-full" />
      )}
    </>
  )
}

function OrganizationForm({ org }: { org: Organization }) {
  const { can } = useSession()
  const qc = useQueryClient()
  const toast = useToast()
  const editable = can('organization.manage')
  const [form, setForm] = useState<Form>(() => toForm(org))

  const save = useMutation({
    mutationFn: (f: Form) => {
      const body: Record<string, unknown> = {
        legal_name: f.legal_name,
        trade_name: f.trade_name.trim() || null,
        legal_form: f.legal_form,
      }
      if (f.ruc || f.ruc_check_digit) {
        body.ruc = f.ruc
        body.ruc_check_digit = f.ruc_check_digit
      }
      return patch<Organization>('/organization', body)
    },
    onSuccess: (data) => {
      qc.setQueryData(['organization'], data)
      qc.invalidateQueries({ queryKey: ['me'] })
      toast('ok', 'Datos de la empresa guardados.')
    },
  })

  const rucValid = /^\d{1,8}$/.test(form.ruc)
  const expectedDv = rucValid ? String(rucCheckDigit(form.ruc)) : null
  const dvMismatch = rucValid && form.ruc_check_digit !== '' && form.ruc_check_digit !== expectedDv
  const error = save.error instanceof ApiError ? save.error : null
  const dirty = JSON.stringify(toForm(org)) !== JSON.stringify(form)

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (dvMismatch) return
    save.mutate(form)
  }

  return (
    <Sheet className="p-6">
        <form onSubmit={onSubmit} className="grid max-w-2xl grid-cols-2 gap-x-5 gap-y-4" noValidate>
          {error && (
            <div className="col-span-2">
              <Notice tone="bad" title={error.message}>
                {Object.values(error.fieldErrors()).join(' ')}
              </Notice>
            </div>
          )}
          <div className="col-span-2">
            <Field label="Razón social">
              {(p) => <Input {...p} disabled={!editable} value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} />}
            </Field>
          </div>
          <Field label="Nombre de fantasía">
            {(p) => <Input {...p} disabled={!editable} value={form.trade_name} onChange={(e) => setForm({ ...form, trade_name: e.target.value })} />}
          </Field>
          <Field label="Forma jurídica">
            {(p) => (
              <Select {...p} disabled={!editable} value={form.legal_form} onChange={(e) => setForm({ ...form, legal_form: e.target.value as LegalForm })}>
                {Object.entries(LEGAL_FORM_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="RUC" hint="Sin puntos ni dígito verificador.">
            {(p) => (
              <Input
                {...p}
                disabled={!editable}
                inputMode="numeric"
                maxLength={8}
                value={form.ruc}
                onChange={(e) => setForm({ ...form, ruc: e.target.value.replace(/\D/g, '') })}
              />
            )}
          </Field>
          <Field
            label="Dígito verificador"
            error={dvMismatch ? `Para ese RUC el dígito verificador es ${expectedDv}.` : undefined}
          >
            {(p) => (
              <Input
                {...p}
                disabled={!editable}
                inputMode="numeric"
                maxLength={1}
                className="w-20"
                value={form.ruc_check_digit}
                onChange={(e) => setForm({ ...form, ruc_check_digit: e.target.value.replace(/\D/g, '') })}
              />
            )}
          </Field>
          <p className="col-span-2 text-sm text-ink-3">
            Moneda base: {org.base_currency}. Última modificación: {formatDateTime(org.updated_at)}.
          </p>
          {editable && (
            <div className="col-span-2 flex gap-2 border-t border-line pt-4">
              <Button type="submit" busy={save.isPending} disabled={!dirty || dvMismatch}>
                Guardar cambios
              </Button>
              <Button type="button" variant="ghost" disabled={!dirty} onClick={() => setForm(toForm(org))}>
                Descartar
              </Button>
            </div>
          )}
        </form>
    </Sheet>
  )
}
