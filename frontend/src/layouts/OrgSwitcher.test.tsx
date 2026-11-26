import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/ui/toast'
import type { Membership } from '../types/api'
import { OrgSwitcher } from './OrgSwitcher'

const state = vi.hoisted(() => ({ switchOrg: vi.fn() }))
const A = { id: 'a', legal_name: 'Alfa S.A.', trade_name: null, legal_form: 'SA', ruc: null, ruc_check_digit: null, role: 'owner', is_current: true } as Membership
const B = { id: 'b', legal_name: 'Beta SRL', trade_name: 'Beta', legal_form: 'SRL', ruc: null, ruc_check_digit: null, role: 'viewer', is_current: false } as Membership
vi.mock('../stores/session', () => ({
  useSession: () => ({ me: { organization: { id: 'a', legal_name: 'Alfa S.A.', trade_name: null } }, switchOrg: state.switchOrg }),
}))

function mockMemberships(list: Membership[]) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(list), { status: 200 }))
}
function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <OrgSwitcher />
        </MemoryRouter>
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
  state.switchOrg.mockReset()
})

describe('selector de organización', () => {
  it('con una sola organización y sin ser propietario, es solo el nombre', async () => {
    mockMemberships([{ ...A, role: 'viewer' }])
    renderIt()
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    expect(screen.getByText('Alfa S.A.')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('con una sola organización siendo propietario, solo ofrece «Nueva organización»', async () => {
    mockMemberships([A])
    const user = userEvent.setup()
    renderIt()
    await user.click(await screen.findByRole('button', { name: /Cambiar de organización/ }))
    expect(screen.getByRole('menuitem', { name: /Nueva organización/ })).toBeTruthy()
    expect(screen.queryAllByRole('menuitemradio')).toHaveLength(0)
  })

  it('con varias lista todas, marca la actual y cambia a la elegida', async () => {
    mockMemberships([A, B])
    state.switchOrg.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderIt()
    await user.click(await screen.findByRole('button', { name: /Cambiar de organización/ }))
    const items = screen.getAllByRole('menuitemradio')
    expect(items).toHaveLength(2)
    expect(items[0].getAttribute('aria-checked')).toBe('true')
    await user.click(items[1])
    expect(state.switchOrg).toHaveBeenCalledWith('b')
  })

  it('un error al cambiar se avisa y no rompe', async () => {
    mockMemberships([A, B])
    const { ApiError } = await import('../services/api')
    state.switchOrg.mockRejectedValue(new ApiError(403, 'ORGANIZATION_NOT_AVAILABLE', 'Esa organización ya no está disponible.'))
    const user = userEvent.setup()
    renderIt()
    await user.click(await screen.findByRole('button', { name: /Cambiar de organización/ }))
    await user.click(screen.getAllByRole('menuitemradio')[1])
    expect(await screen.findByText('Esa organización ya no está disponible.')).toBeTruthy()
  })
})
