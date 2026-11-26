import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserPlus, Users } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { formatDateTime, ROLE_LABELS } from '../../lib/format'
import { ApiError, get, patch, post } from '../../services/api'
import { useSession } from '../../stores/session'
import type { Member, Role, RoleCode } from '../../types/api'
import { PASSWORD_HINT, passwordProblem } from '../auth/password'

function CreateUserForm({ roles, onDone }: { roles: Role[]; onDone: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { me } = useSession()
  const [form, setForm] = useState({ full_name: '', email: '', password: '', role: 'accountant' as RoleCode })
  const [touched, setTouched] = useState(false)
  const create = useMutation({
    mutationFn: () => post<Member>('/users', form),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      toast('ok', `Usuario ${m.user.email} creado.`)
      onDone()
    },
  })
  const pw = passwordProblem(form.password)
  const error = create.error instanceof ApiError ? create.error : null
  const fe = error?.fieldErrors() ?? {}
  const assignable = roles.filter((r) => r.code !== 'owner' || me?.role === 'owner')

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!pw) create.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      {error && error.status !== 422 && <Notice tone="bad" title={error.message} />}
      <Field label="Nombre y apellido" error={fe.full_name}>
        {(p) => <Input {...p} autoFocus value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}
      </Field>
      <Field label="Email" error={fe.email}>
        {(p) => <Input {...p} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
      </Field>
      <Field label="Contraseña inicial" hint={PASSWORD_HINT} error={(touched && pw) || fe.password}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}
      </Field>
      <Field label="Rol" hint={roles.find((r) => r.code === form.role)?.description}>
        {(p) => (
          <Select {...p} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as RoleCode })}>
            {assignable.map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={create.isPending}>
          Crear usuario
        </Button>
      </div>
    </form>
  )
}

const EXISTING_ERRORS: Record<string, string> = {
  USER_NOT_FOUND: 'No hay ningún usuario con ese email. Si todavía no tiene cuenta, creá el usuario.',
  ALREADY_MEMBER: 'Ese usuario ya es parte de esta organización.',
}

function AddExistingUserForm({ roles, onDone }: { roles: Role[]; onDone: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { me } = useSession()
  const [form, setForm] = useState({ email: '', role: 'accountant' as RoleCode })
  const add = useMutation({
    mutationFn: () => post<Member>('/users/existing', { email: form.email.trim(), role: form.role }),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      toast('ok', `${m.user.email} ya es parte de la organización.`)
      onDone()
    },
  })
  const error = add.error instanceof ApiError ? add.error : null
  const fe = error?.fieldErrors() ?? {}
  const assignable = roles.filter((r) => r.code !== 'owner' || me?.role === 'owner')

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (form.email.trim()) add.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      {error && (error.status !== 422 || Object.keys(fe).length === 0) && (
        <Notice tone="bad" title={EXISTING_ERRORS[error.code] ?? error.message} />
      )}
      <p className="text-sm text-ink-2">
        Para alguien que ya usa Contador AI en otra organización: entra con su misma contraseña, sin cuenta nueva.
      </p>
      <Field label="Email del usuario" error={fe.email}>
        {(p) => <Input {...p} type="email" autoFocus value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
      </Field>
      <Field label="Rol en esta organización" hint={roles.find((r) => r.code === form.role)?.description}>
        {(p) => (
          <Select {...p} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as RoleCode })}>
            {assignable.map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={add.isPending}>
          Sumar a la organización
        </Button>
      </div>
    </form>
  )
}

export function UsersPage() {
  const { me, can } = useSession()
  const qc = useQueryClient()
  const toast = useToast()
  const [creating, setCreating] = useState(false)
  const [adding, setAdding] = useState(false)
  const manage = can('users.manage')
  const users = useQuery({ queryKey: ['users'], queryFn: () => get<Member[]>('/users') })
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => get<Role[]>('/users/roles') })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { role?: RoleCode; is_active?: boolean } }) =>
      patch<Member>(`/users/${id}`, body),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      toast('ok', `Usuario ${m.user.email} actualizado.`)
    },
    onError: (e) => toast('bad', e instanceof ApiError ? e.message : 'No se pudo actualizar el usuario.'),
  })

  const canTouch = (m: Member) =>
    manage && m.user.id !== me?.user.id && (m.role !== 'owner' || me?.role === 'owner')

  return (
    <>
      <PageHeader
        title="Usuarios y roles"
        description="Quién puede entrar y qué puede hacer. Cada cambio queda en la auditoría."
        actions={
          manage && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setAdding(true)}>
                <Users size={16} />
                Sumar un usuario que ya existe
              </Button>
              <Button onClick={() => setCreating(true)}>
                <UserPlus size={16} />
                Nuevo usuario
              </Button>
            </div>
          )
        }
      />
      <Sheet>
        {users.isPending ? (
          <div className="flex flex-col gap-3 p-5">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        ) : users.data && users.data.length > 0 ? (
          <table className="w-full text-left">
            <thead className="border-b border-line bg-sunken text-sm text-ink-2">
              <tr>
                <th className="px-5 py-2.5 font-medium">Usuario</th>
                <th className="px-5 py-2.5 font-medium">Rol</th>
                <th className="px-5 py-2.5 font-medium">Último ingreso</th>
                <th className="px-5 py-2.5 font-medium">Estado</th>
                {manage && <th className="px-5 py-2.5"><span className="sr-only">Acciones</span></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.data.map((m) => (
                <tr key={m.user.id} className={m.user.is_active ? '' : 'text-ink-3'}>
                  <td className="px-5 py-3">
                    <p className="font-medium">
                      {m.user.full_name}
                      {m.user.id === me?.user.id && <span className="ml-1.5 text-sm font-normal text-ink-3">(vos)</span>}
                    </p>
                    <p className="text-sm text-ink-2">{m.user.email}</p>
                  </td>
                  <td className="px-5 py-3">
                    {canTouch(m) ? (
                      <Select
                        aria-label={`Rol de ${m.user.full_name}`}
                        className="h-8 w-40"
                        value={m.role}
                        disabled={update.isPending}
                        onChange={(e) => update.mutate({ id: m.user.id, body: { role: e.target.value as RoleCode } })}
                      >
                        {(roles.data ?? [])
                          .filter((r) => r.code !== 'owner' || me?.role === 'owner')
                          .map((r) => (
                            <option key={r.code} value={r.code}>
                              {r.name}
                            </option>
                          ))}
                      </Select>
                    ) : (
                      ROLE_LABELS[m.role]
                    )}
                  </td>
                  <td className="px-5 py-3 text-sm text-ink-2">
                    {m.user.last_login_at ? formatDateTime(m.user.last_login_at) : 'Nunca'}
                  </td>
                  <td className="px-5 py-3">
                    <Badge tone={m.user.is_active ? 'ok' : 'neutral'}>{m.user.is_active ? 'Activo' : 'Desactivado'}</Badge>
                  </td>
                  {manage && (
                    <td className="px-5 py-3 text-right">
                      {canTouch(m) && (
                        <Button
                          variant={m.user.is_active ? 'danger' : 'secondary'}
                          className="h-8"
                          disabled={update.isPending}
                          onClick={() => update.mutate({ id: m.user.id, body: { is_active: !m.user.is_active } })}
                        >
                          {m.user.is_active ? 'Desactivar' : 'Reactivar'}
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="No se pudieron cargar los usuarios">
            {users.error instanceof ApiError ? users.error.message : 'Intentá de nuevo.'}
          </EmptyState>
        )}
      </Sheet>

      {roles.data && (
        <section className="mt-8">
          <h2 className="mb-3 font-semibold">Qué permite cada rol</h2>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3">
            {roles.data.map((r) => (
              <div key={r.code}>
                <dt className="font-medium">{r.name}</dt>
                <dd className="text-sm text-ink-2">{r.description}.</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <Modal open={creating} title="Nuevo usuario" onClose={() => setCreating(false)}>
        <CreateUserForm roles={roles.data ?? []} onDone={() => setCreating(false)} />
      </Modal>
      <Modal open={adding} title="Sumar un usuario que ya existe" onClose={() => setAdding(false)}>
        <AddExistingUserForm roles={roles.data ?? []} onDone={() => setAdding(false)} />
      </Modal>
    </>
  )
}
