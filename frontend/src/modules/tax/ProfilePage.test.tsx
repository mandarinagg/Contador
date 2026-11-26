import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/toast'
import { ProfilePage } from './ProfilePage'
import type { Profile, ProfileVersion } from './types'

const session = vi.hoisted(() => ({ legalForm: 'PERSONA_FISICA' }))
vi.mock('../../stores/session', () => ({
  useSession: () => ({
    can: () => true,
    me: { role: 'owner', organization: { id: 'o1', legal_name: 'Benítez, María', trade_name: null, legal_form: session.legalForm } },
  }),
}))

const version = (patch: Partial<ProfileVersion>): ProfileVersion => ({
  id: 'p1',
  valid_from: '2026-01-01',
  ire_regime: 'none',
  fiscal_close_month: 12,
  vat_taxpayer: false,
  origin: 'declared',
  verified_by_name: null,
  verified_license: null,
  verified_document_reference: null,
  verified_at: null,
  notes: null,
  obligations: [],
  ...patch,
})

function mockFetch(profile: Profile) {
  const calls: { method: string; path: string; body: string | undefined }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input).replace(/^.*\/api\/v1/, '')
    const method = init?.method ?? 'GET'
    calls.push({ method, path, body: init?.body as string | undefined })
    const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
    if (path === '/tax/profile') return json(profile)
    return json({ error: { code: 'X', message: 'x' } }, 404)
  })
  return calls
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <ProfilePage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const EMPTY: Profile = { ruc: '1234567', ruc_check_digit: '9', current: null, history: [] }

async function toObligations(regime: RegExp, closeMonth?: string) {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Empezar' }))
  fireEvent.change(screen.getByLabelText('Rige desde'), { target: { value: '2026-01-01' } })
  await user.click(screen.getByRole('button', { name: /Siguiente/ }))
  await user.click(screen.getByRole('radio', { name: regime }))
  await user.click(screen.getByRole('button', { name: /Siguiente/ }))
  if (closeMonth) await user.selectOptions(screen.getByLabelText('Mes de cierre del ejercicio fiscal'), closeMonth)
  await user.click(screen.getByRole('button', { name: /Siguiente/ }))
  await user.click(screen.getByRole('radio', { name: /^No/ }))
  await user.click(screen.getByRole('button', { name: /Siguiente/ }))
  return user
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  session.legalForm = 'PERSONA_FISICA'
})

describe('Impuestos → Perfil fiscal de la persona física', () => {
  it('guarda «Sin IRE» con el IRP-RSP y el registro anual 956', async () => {
    const calls = mockFetch(EMPTY)
    renderPage()
    const user = await toObligations(/^Sin IRE/)
    await user.click(screen.getByRole('checkbox', { name: /^715 — IRP-RSP/ }))
    await user.click(screen.getByRole('checkbox', { name: /^956 — Registro anual de comprobantes/ }))
    expect(screen.getByRole('checkbox', { name: /^716 — IRP-RGC/ })).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: /^702 — RESIMPLE/ })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Fecha de alta de la 715'), { target: { value: '2025-03-01' } })
    fireEvent.change(screen.getByLabelText('Fecha de alta de la 956'), { target: { value: '2025-03-01' } })
    expect(screen.queryByText('Revisá la combinación')).toBeNull()
    await user.click(screen.getByRole('button', { name: /Siguiente/ }))
    expect(screen.getByText('Sin IRE')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Guardar el perfil' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    const body = JSON.parse(calls.find((c) => c.method === 'PUT')?.body ?? '{}')
    expect(body.ire_regime).toBe('none')
    expect(body.fiscal_close_month).toBe(12)
    expect(body.obligations).toEqual([
      { code: '715', registered_on: '2025-03-01' },
      { code: '956', registered_on: '2025-03-01' },
    ])
  })

  it('avisa antes de guardar: IRP con cierre en junio, 956 con IVA', async () => {
    mockFetch(EMPTY)
    renderPage()
    const user = await toObligations(/^Sin IRE/, '6')
    await user.click(screen.getByRole('checkbox', { name: /^715 — IRP-RSP/ }))
    expect(screen.getByText(/El ejercicio del IRP es el año civil \(Ley 6380\/2019, art. 52\)/)).toBeTruthy()
    await user.click(screen.getByRole('checkbox', { name: /^956 — Registro anual/ }))
    await user.click(screen.getByRole('checkbox', { name: /^211 — IVA General/ }))
    expect(screen.getByText(/Con la 211 \(IVA\) el registro de comprobantes es el mensual, 955/)).toBeTruthy()
  })

  it('el RESIMPLE sugiere la 702 y no admite la 211', async () => {
    mockFetch(EMPTY)
    renderPage()
    const user = await toObligations(/^RESIMPLE/)
    expect((screen.getByRole('checkbox', { name: /^702 — RESIMPLE/ }) as HTMLInputElement).checked).toBe(true)
    await user.click(screen.getByRole('checkbox', { name: /^211 — IVA General/ }))
    expect(screen.getByText(/no es contribuyente del IVA \(Ley 6380\/2019, art. 27, último párrafo\)/)).toBeTruthy()
  })

  it('una empresa no ve el RESIMPLE, «Sin IRE» ni las obligaciones del IRP', async () => {
    session.legalForm = 'EAS'
    mockFetch({ ...EMPTY, ruc: '80000005', ruc_check_digit: '1' })
    renderPage()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Empezar' }))
    fireEvent.change(screen.getByLabelText('Rige desde'), { target: { value: '2026-01-01' } })
    await user.click(screen.getByRole('button', { name: /Siguiente/ }))
    expect(screen.queryByRole('radio', { name: /^RESIMPLE/ })).toBeNull()
    expect(screen.queryByRole('radio', { name: /^Sin IRE/ })).toBeNull()
    await user.click(screen.getByRole('radio', { name: /^IRE General/ }))
    await user.click(screen.getByRole('button', { name: /Siguiente/ }))
    await user.click(screen.getByRole('button', { name: /Siguiente/ }))
    await user.click(screen.getByRole('radio', { name: /^Sí/ }))
    await user.click(screen.getByRole('button', { name: /Siguiente/ }))
    expect(screen.getByRole('checkbox', { name: /^700 — IRE General/ })).toBeTruthy()
    expect(screen.queryByRole('checkbox', { name: /^715/ })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: /^956/ })).toBeNull()
  })

  it('sin IRE General, la contabilidad figura como opcional (un aviso, no un bloqueo)', async () => {
    const irp = version({ obligations: [{ code: '715', registered_on: '2025-03-01', supported: true }] })
    mockFetch({ ...EMPTY, current: irp, history: [irp] })
    renderPage()
    expect(await screen.findByText('La contabilidad es opcional')).toBeTruthy()
    expect(screen.getAllByText('Sin IRE').length).toBeGreaterThan(0)
  })

  it('con el IRE General no hay aviso de contabilidad opcional', async () => {
    const general = version({ ire_regime: 'ire_general', obligations: [{ code: '700', registered_on: '2026-01-01', supported: true }] })
    mockFetch({ ...EMPTY, current: general, history: [general] })
    renderPage()
    expect((await screen.findAllByText('IRE General')).length).toBeGreaterThan(0)
    expect(screen.queryByText('La contabilidad es opcional')).toBeNull()
  })
})
