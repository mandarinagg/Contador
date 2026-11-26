import { useMutation } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button, Field, Input, Notice } from '../../components/ui'
import { ApiError, post, session } from '../../services/api'
import { ROLE_LABELS } from '../../lib/format'
import { useSession } from '../../stores/session'
import type { LoginResponse, Membership } from '../../types/api'
import { AuthFrame } from './AuthFrame'

export function LoginPage() {
  const { start } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Con más de una organización, la sesión abierta espera a que se elija (o se confirme) en cuál trabajar.
  const [pending, setPending] = useState<LoginResponse | null>(null)

  const login = useMutation({
    mutationFn: () => post<LoginResponse>('/auth/login', { email, password }),
    onSuccess: (res) => {
      if (res.organizations.length > 1) {
        setPending(res)
        return
      }
      start(res)
      navigate('/', { replace: true })
    },
  })

  const choose = useMutation({
    mutationFn: async (m: Membership) => {
      if (!pending) return
      if (m.is_current || m.id === pending.organization.id) return pending
      // El token recién emitido sirve para cambiar; el cambio lo invalida y devuelve el definitivo.
      session.set(pending.token)
      try {
        return await post<LoginResponse>('/auth/switch', { organization_id: m.id })
      } catch (e) {
        session.clear()
        throw e
      }
    },
    onSuccess: (res) => {
      if (!res) return
      start(res)
      navigate('/', { replace: true })
    },
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate()
  }

  const error = login.error instanceof ApiError ? login.error : null
  const chooseError = choose.error instanceof ApiError ? choose.error : null

  if (pending) {
    return (
      <AuthFrame title="¿En qué organización querés trabajar?" intro="Tenés acceso a más de una. Podés cambiar cuando quieras desde el menú de la izquierda.">
        <div className="flex flex-col gap-2">
          {chooseError && <Notice tone="bad" title={chooseError.message} />}
          {pending.organizations.map((m) => (
            <Button
              key={m.id}
              type="button"
              variant={m.id === pending.organization.id ? 'primary' : 'secondary'}
              disabled={choose.isPending}
              onClick={() => choose.mutate(m)}
              className="h-auto justify-between py-2 text-left"
            >
              <span>{m.trade_name ?? m.legal_name}</span>
              <span className="text-sm font-normal opacity-80">{ROLE_LABELS[m.role] ?? m.role}</span>
            </Button>
          ))}
        </div>
      </AuthFrame>
    )
  }

  return (
    <AuthFrame title="Ingresar" intro="Usá el email y la contraseña de tu usuario.">
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {error && (
          <Notice tone="bad" title={error.message}>
            {error.code === 'ACCOUNT_LOCKED' && 'La cuenta se desbloquea sola después de unos minutos.'}
          </Notice>
        )}
        <Field label="Email">
          {(p) => (
            <Input {...p} type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Field>
        <Field label="Contraseña">
          {(p) => (
            <Input {...p} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          )}
        </Field>
        <Button type="submit" busy={login.isPending} disabled={!email || !password} className="mt-2">
          Ingresar
        </Button>
      </form>
    </AuthFrame>
  )
}
