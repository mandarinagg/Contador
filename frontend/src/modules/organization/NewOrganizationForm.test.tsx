import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NewOrganizationForm } from './NewOrganizationForm'

function mockPost(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(body), { status }))
}
function renderIt(onSwitch = vi.fn().mockResolvedValue(undefined), onDone = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <NewOrganizationForm onDone={onDone} onSwitch={onSwitch} />
    </QueryClientProvider>,
  )
  return { onSwitch, onDone }
}
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Nueva organización', () => {
  it('RUC_TAKEN: dice que ya existe esa organización', async () => {
    mockPost(409, { error: { code: 'RUC_TAKEN', message: 'x' } })
    const user = userEvent.setup()
    renderIt()
    await user.type(screen.getByLabelText('Razón social'), 'Gamma SA')
    await user.click(screen.getByRole('button', { name: 'Crear organización' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Ya hay una organización con ese RUC')
  })

  it('OWNER_ONLY: dice que solo el propietario puede', async () => {
    mockPost(403, { error: { code: 'OWNER_ONLY', message: 'x' } })
    const user = userEvent.setup()
    renderIt()
    await user.type(screen.getByLabelText('Razón social'), 'Gamma SA')
    await user.click(screen.getByRole('button', { name: 'Crear organización' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Solo el propietario')
  })

  it('al crear ofrece pasar a la nueva y la usa', async () => {
    const f = mockPost(201, { id: 'n1', legal_name: 'Gamma SA', trade_name: null, legal_form: 'EAS' })
    const user = userEvent.setup()
    const { onSwitch } = renderIt()
    await user.type(screen.getByLabelText('Razón social'), 'Gamma SA')
    await user.click(screen.getByRole('button', { name: 'Crear organización' }))
    await user.click(await screen.findByRole('button', { name: 'Pasar a Gamma SA' }))
    await waitFor(() => expect(onSwitch).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1' })))
    expect(String(f.mock.calls[0][0])).toContain('/organizations')
  })

  it('no envía si el dígito verificador no corresponde', async () => {
    const f = mockPost(201, {})
    const user = userEvent.setup()
    renderIt()
    await user.type(screen.getByLabelText('Razón social'), 'Gamma SA')
    await user.type(screen.getByLabelText('RUC'), '4444440')
    await user.type(screen.getByLabelText('Dígito verificador'), '9')
    await user.click(screen.getByRole('button', { name: 'Crear organización' }))
    expect(f).not.toHaveBeenCalled()
  })
})

describe('Persona física', () => {
  it('el interruptor cambia razón social y forma jurídica por nombres y apellidos', async () => {
    const user = userEvent.setup()
    renderIt()
    expect(screen.getByLabelText('Razón social')).toBeTruthy()
    expect(screen.getByLabelText('Forma jurídica')).toBeTruthy()
    await user.click(screen.getByLabelText('Persona física'))
    expect(screen.queryByLabelText('Razón social')).toBeNull()
    expect(screen.queryByLabelText('Forma jurídica')).toBeNull()
    expect(screen.getByLabelText('Nombres')).toBeTruthy()
    expect(screen.getByLabelText('Apellidos')).toBeTruthy()
    expect(screen.getByLabelText(/RUC \(es tu cédula\)/)).toBeTruthy()
    await user.click(screen.getByLabelText('Empresa'))
    expect(screen.getByLabelText('Razón social')).toBeTruthy()
  })

  it('pide nombres y apellidos antes de enviar y manda solo eso', async () => {
    const f = mockPost(201, { id: 'p1', legal_name: 'Benítez, Ana', trade_name: null, legal_form: 'PERSONA_FISICA' })
    const user = userEvent.setup()
    renderIt()
    await user.click(screen.getByLabelText('Persona física'))
    await user.click(screen.getByRole('button', { name: 'Crear organización' }))
    expect(screen.getByText('Escribí los nombres.')).toBeTruthy()
    expect(screen.getByText('Escribí los apellidos.')).toBeTruthy()
    expect(f).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('Nombres'), 'Ana')
    await user.type(screen.getByLabelText('Apellidos'), 'Benítez')
    await user.click(screen.getByRole('button', { name: 'Crear organización' }))
    await screen.findByRole('button', { name: 'Pasar a Benítez, Ana' })
    const sent = JSON.parse(String((f.mock.calls[0]?.[1] as RequestInit).body))
    expect(sent).toEqual({ first_names: 'Ana', last_names: 'Benítez', legal_form: 'PERSONA_FISICA', trade_name: null })
  })
})
