import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button, Field, Input, Notice, Select } from '../../components/ui'
import { LEGAL_FORM_LABELS } from '../../lib/format'
import { ApiError, post } from '../../services/api'
import { useSession } from '../../stores/session'
import type { LegalForm, LoginResponse } from '../../types/api'
import { AuthFrame } from './AuthFrame'
import { PASSWORD_HINT, passwordProblem } from './password'

export function SetupPage() {
  const { start } = useSession()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [org, setOrg] = useState({ legal_name: '', trade_name: '', legal_form: 'EAS' as LegalForm })
  const [owner, setOwner] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [touched, setTouched] = useState(false)

  const setup = useMutation({
    mutationFn: () =>
      post<LoginResponse>('/system/setup', {
        organization: { ...org, trade_name: org.trade_name.trim() || null },
        owner: { full_name: owner.full_name, email: owner.email, password: owner.password },
      }),
    onSuccess: (res) => {
      start(res)
      qc.setQueryData(['setup'], { needs_setup: false })
      navigate('/', { replace: true })
    },
  })

  const pwProblem = passwordProblem(owner.password)
  const mismatch = owner.confirm !== '' && owner.confirm !== owner.password
  const error = setup.error instanceof ApiError ? setup.error : null
  const fieldErrors = error?.fieldErrors() ?? {}

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (pwProblem || mismatch || owner.confirm === '') return
    setup.mutate()
  }

  return (
    <AuthFrame
      title="Configurar Contador AI"
      intro="Primer arranque: registrá la empresa y el usuario propietario. Los datos fiscales (RUC, régimen) se cargan después, cuando estén verificados."
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-7" noValidate>
        {error && error.status !== 422 && <Notice tone="bad" title={error.message} />}

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-3 font-semibold">1. Empresa</legend>
          <Field label="Razón social" error={fieldErrors['organization.legal_name']}>
            {(p) => (
              <Input {...p} required autoFocus value={org.legal_name} onChange={(e) => setOrg({ ...org, legal_name: e.target.value })} />
            )}
          </Field>
          <Field label="Nombre de fantasía" hint="Opcional. Es el nombre que se muestra en la aplicación.">
            {(p) => <Input {...p} value={org.trade_name} onChange={(e) => setOrg({ ...org, trade_name: e.target.value })} />}
          </Field>
          <Field label="Forma jurídica">
            {(p) => (
              <Select {...p} value={org.legal_form} onChange={(e) => setOrg({ ...org, legal_form: e.target.value as LegalForm })}>
                {Object.entries(LEGAL_FORM_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="mb-3 font-semibold">2. Usuario propietario</legend>
          <Field label="Nombre y apellido" error={fieldErrors['owner.full_name']}>
            {(p) => <Input {...p} required autoComplete="name" value={owner.full_name} onChange={(e) => setOwner({ ...owner, full_name: e.target.value })} />}
          </Field>
          <Field label="Email" error={fieldErrors['owner.email']}>
            {(p) => <Input {...p} type="email" required autoComplete="username" value={owner.email} onChange={(e) => setOwner({ ...owner, email: e.target.value })} />}
          </Field>
          <Field label="Contraseña" hint={PASSWORD_HINT} error={(touched && pwProblem) || fieldErrors['owner.password']}>
            {(p) => <Input {...p} type="password" required autoComplete="new-password" value={owner.password} onChange={(e) => setOwner({ ...owner, password: e.target.value })} />}
          </Field>
          <Field label="Repetir contraseña" error={mismatch ? 'Las contraseñas no coinciden.' : touched && owner.confirm === '' ? 'Repetí la contraseña.' : undefined}>
            {(p) => <Input {...p} type="password" required autoComplete="new-password" value={owner.confirm} onChange={(e) => setOwner({ ...owner, confirm: e.target.value })} />}
          </Field>
        </fieldset>

        <Button type="submit" busy={setup.isPending}>
          Crear empresa y propietario
        </Button>
      </form>
    </AuthFrame>
  )
}
