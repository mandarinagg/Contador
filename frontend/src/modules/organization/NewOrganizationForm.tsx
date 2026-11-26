import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Button, Notice } from '../../components/ui'
import { ApiError, post } from '../../services/api'
import type { Organization } from '../../types/api'
import { OrganizationFields } from '../auth/OrganizationFields'
import { EMPTY_ORGANIZATION, hasCheckDigitMismatch, identityBody, identityProblems, newOrganizationMessage, type OrganizationDraft } from '../auth/organizationDraft'

/**
 * Alta de otra organización (D-136). No cambia de organización: al terminar ofrece pasar a la nueva
 * (`onSwitch`) o quedarse en la actual (`onDone`).
 */
export function NewOrganizationForm({ onDone, onSwitch }: { onDone: () => void; onSwitch: (org: Organization) => Promise<void> }) {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<OrganizationDraft>(EMPTY_ORGANIZATION)
  const [touched, setTouched] = useState(false)
  const [created, setCreated] = useState<Organization | null>(null)

  const create = useMutation({
    mutationFn: () =>
      post<Organization>('/organizations', {
        ...identityBody(draft),
        ...(draft.ruc ? { ruc: draft.ruc, ruc_check_digit: draft.ruc_check_digit } : {}),
      }),
    onSuccess: (org) => {
      setCreated(org)
      qc.invalidateQueries({ queryKey: ['organizations'] })
    },
  })
  const goTo = useMutation({ mutationFn: (org: Organization) => onSwitch(org) })

  const error = create.error instanceof ApiError ? create.error : null
  const fe = error?.fieldErrors() ?? {}
  const switchError = goTo.error instanceof ApiError ? goTo.error : null

  if (created) {
    const name = created.trade_name ?? created.legal_name
    return (
      <div className="flex flex-col gap-4">
        <Notice tone="ok" title={`Se creó «${name}».`}>
          Quedaste como su propietario. ¿Querés pasar a trabajar en ella ahora?
        </Notice>
        {switchError && <Notice tone="bad" title={switchError.message} />}
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" variant="ghost" onClick={onDone}>
            Quedarme acá
          </Button>
          <Button type="button" busy={goTo.isPending} onClick={() => goTo.mutate(created)}>
            Pasar a {name}
          </Button>
        </div>
      </div>
    )
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (Object.keys(identityProblems(draft)).length > 0) return
    if (hasCheckDigitMismatch(draft) || (draft.ruc && !draft.ruc_check_digit)) return
    create.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      {error && (error.status !== 422 || Object.keys(fe).length === 0) && <Notice tone="bad" title={newOrganizationMessage(error)} />}
      <OrganizationFields value={draft} onChange={setDraft} errors={{ ...fe, ...(touched ? identityProblems(draft) : {}) }} withRuc autoFocus />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={create.isPending}>
          Crear organización
        </Button>
      </div>
    </form>
  )
}
