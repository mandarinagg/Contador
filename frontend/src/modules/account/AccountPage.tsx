import { useMutation } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Button, Field, Input, Notice, PageHeader, Sheet } from '../../components/ui'
import { cx } from '../../lib/cx'
import { useToast } from '../../components/ui/toast'
import { type ThemePreference, useTheme } from '../../hooks/useTheme'
import { ROLE_LABELS } from '../../lib/format'
import { ApiError, post } from '../../services/api'
import { useSession } from '../../stores/session'
import { PASSWORD_HINT, passwordProblem } from '../auth/password'

function ChangePassword() {
  const toast = useToast()
  const [f, setF] = useState({ current: '', next: '', confirm: '' })
  const [touched, setTouched] = useState(false)
  const change = useMutation({
    mutationFn: () => post('/auth/change-password', { current_password: f.current, new_password: f.next }),
    onSuccess: () => {
      setF({ current: '', next: '', confirm: '' })
      setTouched(false)
      toast('ok', 'Contraseña cambiada. Se cerraron tus otras sesiones.')
    },
  })
  const problem = passwordProblem(f.next)
  const mismatch = f.confirm !== '' && f.confirm !== f.next
  const error = change.error instanceof ApiError ? change.error : null

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!problem && !mismatch && f.confirm && f.current) change.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-sm flex-col gap-4" noValidate>
      {error && <Notice tone="bad" title={error.message} />}
      <Field label="Contraseña actual">
        {(p) => <Input {...p} type="password" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} />}
      </Field>
      <Field label="Contraseña nueva" hint={PASSWORD_HINT} error={touched ? problem : undefined}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} />}
      </Field>
      <Field label="Repetir contraseña nueva" error={mismatch ? 'Las contraseñas no coinciden.' : undefined}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} />}
      </Field>
      <Button type="submit" busy={change.isPending} disabled={!f.current || !f.next || !f.confirm} className="self-start">
        Cambiar contraseña
      </Button>
    </form>
  )
}

const THEMES: [ThemePreference, string][] = [
  ['light', 'Claro'],
  ['dark', 'Oscuro'],
  ['system', 'Como el sistema'],
]

export function AccountPage() {
  const { me } = useSession()
  const { preference, setPreference } = useTheme()
  if (!me) return null
  return (
    <>
      <PageHeader title="Mi cuenta" />
      <div className="flex flex-col gap-6">
        <Sheet className="p-6">
          <dl className="grid max-w-xl grid-cols-[9rem_1fr] gap-y-2">
            <dt className="text-ink-2">Nombre</dt>
            <dd>{me.user.full_name}</dd>
            <dt className="text-ink-2">Email</dt>
            <dd>{me.user.email}</dd>
            <dt className="text-ink-2">Rol</dt>
            <dd>{ROLE_LABELS[me.role]}</dd>
            <dt className="text-ink-2">Organización</dt>
            <dd>{me.organization.legal_name}</dd>
          </dl>
        </Sheet>
        <Sheet className="p-6">
          <h2 className="mb-4 font-semibold">Apariencia</h2>
          <div role="radiogroup" aria-label="Tema" className="inline-flex rounded-sm border border-line-strong p-0.5">
            {THEMES.map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={preference === value}
                onClick={() => setPreference(value)}
                className={cx(
                  'rounded-sm px-3 py-1.5 text-sm',
                  preference === value ? 'bg-ledger text-surface' : 'text-ink-2 hover:text-ink',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </Sheet>
        <Sheet className="p-6">
          <h2 className="mb-4 font-semibold">Contraseña</h2>
          <ChangePassword />
        </Sheet>
      </div>
    </>
  )
}
