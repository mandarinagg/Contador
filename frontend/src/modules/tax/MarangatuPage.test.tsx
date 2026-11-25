import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/toast'
import { MarangatuPage } from './MarangatuPage'

const perms = vi.hoisted(() => ({ list: [] as string[] }))
vi.mock('../../stores/session', () => ({
  useSession: () => ({ can: (p: string) => perms.list.includes(p), me: { role: 'owner' } }),
}))

const STOP_TEXT = 'Marangatu rechazó el ingreso. El bot no reintenta: revisá la clave.'
let settings = { bot_enabled: false, stages: { consulta: 'reconocimiento', f120: 'ensayo' }, catalog_provisional: true, catalog_updated: null }
let credentials = { ruc: '44444401-7', has_password: false, store_available: true }
const runs = [
  { id: 'r1', task_type: 'general', period: null, stage: 'reconocimiento', status: 'detenida', stop_code: 'LOGIN_FAILED', stop_text: STOP_TEXT, stop_detail: null, started_by: null, started_at: '2026-11-20T10:00:00Z', finished_at: '2026-11-20T10:01:00Z' },
]

function mockFetch() {
  const calls: { method: string; path: string; body: string | undefined }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input).replace(/^.*\/api\/v1/, '')
    const method = init?.method ?? 'GET'
    calls.push({ method, path, body: init?.body as string | undefined })
    const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
    if (path === '/marangatu/settings' && method === 'GET') return json(settings)
    if (path === '/marangatu/settings' && method === 'PUT') {
      settings = { ...settings, bot_enabled: JSON.parse(init?.body as string).bot_enabled }
      return json(settings)
    }
    if (path === '/marangatu/credentials' && method === 'GET') return json(credentials)
    if (path === '/marangatu/credentials' && method === 'PUT') {
      credentials = { ...credentials, has_password: true }
      return json(credentials)
    }
    if (path.startsWith('/marangatu/runs')) return json(runs)
    return json({ error: { code: 'X', message: 'x' } }, 404)
  })
  return calls
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MarangatuPage />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeAll(() => {
  // jsdom no implementa `<dialog>.showModal()`.
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
  settings = { ...settings, bot_enabled: false }
  credentials = { ...credentials, has_password: false }
})

describe('Impuestos → Marangatu', () => {
  it('muestra el texto del motivo de detención que manda el backend', async () => {
    perms.list = ['tax.read']
    mockFetch()
    renderPage()
    expect(await screen.findByText(STOP_TEXT)).toBeTruthy()
    expect(screen.getByText('Reconocimiento general')).toBeTruthy()
  })

  it('con solo tax.read todo lo que cambia algo está deshabilitado', async () => {
    perms.list = ['tax.read']
    mockFetch()
    renderPage()
    await screen.findByText(STOP_TEXT)
    for (const name of ['Encender el bot', 'Guardar la clave', 'Borrar la clave', 'Hacer un reconocimiento']) {
      expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('con tax.manage sin tax.verify puede apagar pero no encender', async () => {
    perms.list = ['tax.read', 'tax.manage']
    settings = { ...settings, bot_enabled: true }
    mockFetch()
    renderPage()
    expect(((await screen.findByRole('button', { name: 'Apagar el bot' })) as HTMLButtonElement).disabled).toBe(false)
    cleanup()
    settings = { ...settings, bot_enabled: false }
    renderPage()
    expect(((await screen.findByRole('button', { name: 'Encender el bot' })) as HTMLButtonElement).disabled).toBe(true)
  })

  it('encender pide confirmación y no llama a la API antes', async () => {
    perms.list = ['tax.read', 'tax.manage', 'tax.verify']
    const calls = mockFetch()
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Encender el bot' }))
    expect(calls.some((c) => c.method === 'PUT' && c.path === '/marangatu/settings')).toBe(false)
    const dialog = await screen.findByRole('dialog', { name: 'Encender el bot' })
    await user.click(within(dialog).getByRole('button', { name: 'Sí, encender' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT' && c.path === '/marangatu/settings')?.body).toBe('{"bot_enabled":true}'))
  })

  it('la clave se envía una vez y el campo queda vacío; nunca se muestra', async () => {
    perms.list = ['tax.read', 'tax.manage', 'tax.verify']
    const calls = mockFetch()
    const user = userEvent.setup()
    const { container } = renderPage()
    const field = (await screen.findByLabelText('Clave de Marangatu')) as HTMLInputElement
    expect(field.type).toBe('password')
    expect(field.autocomplete).toBe('off')
    await user.type(field, 'Secreta-123')
    await user.click(screen.getByRole('button', { name: 'Guardar la clave' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT' && c.path === '/marangatu/credentials')?.body).toBe('{"password":"Secreta-123"}'))
    expect(field.value).toBe('')
    await screen.findByText(/Clave guardada para el RUC/)
    expect(container.innerHTML).not.toContain('Secreta-123')
  })
})
