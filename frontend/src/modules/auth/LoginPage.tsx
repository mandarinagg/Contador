import { useMutation } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button, Field, Input, Notice } from '../../components/ui'
import { ApiError, post } from '../../services/api'
import { useSession } from '../../stores/session'
import type { LoginResponse } from '../../types/api'
import { AuthFrame } from './AuthFrame'

export function LoginPage() {
  const { start } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const login = useMutation({
    mutationFn: () => post<LoginResponse>('/auth/login', { email, password }),
    onSuccess: (res) => {
      start(res)
      navigate('/', { replace: true })
    },
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate()
  }

  const error = login.error instanceof ApiError ? login.error : null

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
