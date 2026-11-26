import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/toast'
import { UsersPage } from './UsersPage'

vi.mock('../../stores/session', () => ({
  useSession: () => ({ can: () => true, me: { role: 'owner', user: { id: 'u1' } } }),
}))

const roles = [{ code: 'accountant', name: 'Contador', description: 'Contabiliza', permissions: [] }]
function mockApi(existing: { status: number; body: unknown }) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input).replace(/^.*\/api\/v1/, '')
    const j = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
    if (path === '/users/existing' && init?.method === 'POST') return j(existing.body, existing.status)
    if (path === '/users/roles') return j(roles)
    if (path === '/users') return j([])
    return j({}, 404)
  })
}
function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <UsersPage />
      </ToastProvider>
    </QueryClientProvider>,
  )
}
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute('open')
  }
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function submit(email: string) {
  const user = userEvent.setup()
  renderIt()
  await user.click(await screen.findByRole('button', { name: 'Sumar un usuario que ya existe' }))
  const dialog = await screen.findByRole('dialog', { name: 'Sumar un usuario que ya existe' })
  await user.type(within(dialog).getByLabelText('Email del usuario'), email)
  await user.click(within(dialog).getByRole('button', { name: 'Sumar a la organización' }))
  return dialog
}

describe('Sumar un usuario que ya existe', () => {
  it('USER_NOT_FOUND: explica que no hay usuario con ese email', async () => {
    mockApi({ status: 404, body: { error: { code: 'USER_NOT_FOUND', message: 'x' } } })
    const dialog = await submit('nadie@example.com')
    expect((await within(dialog).findByRole('alert')).textContent).toContain('No hay ningún usuario con ese email')
  })

  it('ALREADY_MEMBER: explica que ya es parte', async () => {
    mockApi({ status: 409, body: { error: { code: 'ALREADY_MEMBER', message: 'x' } } })
    const dialog = await submit('ya@example.com')
    expect((await within(dialog).findByRole('alert')).textContent).toContain('ya es parte de esta organización')
  })
})
