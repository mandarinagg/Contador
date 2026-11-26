import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/toast'
import { IrpPage } from './IrpPage'
import { defaultIrpYear, hasIrpServices, irpXlsxName } from './logic'
import type { Form515Box, IrpEstimate } from './types'

const box = (patch: Partial<Form515Box> & { box: string }): Form515Box => ({
  rubro: 1,
  label: `Casilla ${patch.box}`,
  value: '0',
  status: 'calculated',
  doubts: [],
  note: null,
  origin: null,
  ...patch,
})

const ESTIMATE: IrpEstimate = {
  year: 2026,
  period_start: '2026-01-01',
  period_end: '2026-12-31',
  registered_on: '2025-01-01',
  register: { income_taxed: '5300000', income_exempt: '50000', income_count: 2, expenses: '1360000', expense_count: 3, credit_excluded: 0 },
  threshold: { amount: '80000000', reached: false },
  result: { net_income: '3940000', tax: '315200', to_pay: '0' },
  warnings: [
    { code: 'RULE_PENDING', message: 'Las reglas del IRP están sin verificar.' },
    { code: 'BELOW_THRESHOLD', message: 'Los ingresos gravados no superan el monto no alcanzado.' },
  ],
  register_control: {
    method: 'voucher_register',
    available: true,
    matches: true,
    rows: [{ box: '12', draft: '5300000', register: '5300000', difference: '0', matches: true }],
    vouchers: 5,
    message: null,
    stop_code: null,
  },
  form_515: {
    available: true,
    version: 1,
    rule: { id: 'r1', code: 'IRP-RSP-DJ', version: 1, validation_status: 'pending', legal_reference: 'Ley 6380' },
    boxes: [
      box({ box: '12', value: '5300000', origin: 'income' }),
      box({ box: '18', rubro: 2, value: null, status: 'missing_data', note: 'No calculado: falta el dato. Depende de datos personales.', doubts: ['D-PF-16'] }),
      box({ box: '22', rubro: 2, value: '1360000', origin: 'expense' }),
      box({ box: '45', rubro: 5, value: '3940000' }),
      box({ box: '51', rubro: 5, value: null, status: 'not_calculated', note: 'Depende de 40 a 42 y 49.' }),
    ],
    warnings: ['Borrador para copiar a mano en Marangatu.'],
    message: null,
  },
  obligation: null,
  rules_applied: [{ id: 'r1', code: 'IRP-RSP-DJ', version: 1, validation_status: 'pending', legal_reference: 'Ley 6380' }],
  rule_status: 'pending',
  is_estimate: true,
}

function mockFetch(estimate: IrpEstimate) {
  const paths: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input).replace(/^.*\/api\/v1/, '')
    paths.push(path)
    const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
    if (path === '/tax/alerts') return json({ as_of: '2026-11-24', count: 0, alerts: [] })
    if (path === '/tax/rules') return json([])
    if (path.startsWith('/tax/irp/')) return json({ ...estimate, year: Number(path.slice(9, 13)) })
    return json({ error: { code: 'X', message: 'x' } }, 404)
  })
  return paths
}

function renderPage(url = '/impuestos/irp?anio=2026') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[url]}>
          <IrpPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Impuestos → IRP del año', () => {
  it('muestra el banner de reglas pendientes, las casillas con su origen y el cuadre', async () => {
    const paths = mockFetch(ESTIMATE)
    renderPage()
    expect(await screen.findByText('Las reglas del IRP están sin verificar contra la fuente oficial')).toBeTruthy()
    expect(paths).toContain('/tax/irp/2026')
    // El aviso de reglas pendientes va en el banner, no repetido como aviso suelto.
    expect(screen.queryByText('Las reglas del IRP están sin verificar.')).toBeNull()
    expect(screen.getByText('Los ingresos gravados no superan el monto no alcanzado.')).toBeTruthy()
    const income = screen.getByTestId('f515-12')
    const link = within(income).getByRole('link', { name: 'Ingresos y ventas del registro' })
    expect(link.getAttribute('href')).toBe('/impuestos/comprobantes?mes=2026-01&dir=income')
    expect(within(screen.getByTestId('f515-22')).getByRole('link').getAttribute('href')).toContain('dir=expense')
    const missing = screen.getByTestId('f515-18')
    expect(within(missing).getByText('Vacía')).toBeTruthy()
    expect(within(missing).getByText('No calculado: falta el dato')).toBeTruthy()
    expect(within(missing).getByText(/Duda abierta \(D-PF-16\)/)).toBeTruthy()
    expect(within(screen.getByTestId('f515-51')).getByText('Sin calcular')).toBeTruthy()
    expect(screen.getByTestId('irp-cuadre').textContent).toContain('cuadra al guaraní con el registro (5 comprobantes)')
    expect(screen.getByText(/la DJ se presenta igual/)).toBeTruthy()
  })

  it('cambia de año y avisa cuando el borrador no cuadra', async () => {
    const paths = mockFetch({
      ...ESTIMATE,
      rule_status: 'verified',
      register_control: {
        ...ESTIMATE.register_control,
        matches: false,
        rows: [{ box: '22', draft: '1360001', register: '1360000', difference: '1', matches: false }],
        message: 'El borrador no cuadra al guaraní con el registro de comprobantes del año.',
        stop_code: 'LEDGER_MISMATCH',
      },
    })
    renderPage()
    expect((await screen.findByTestId('irp-cuadre')).textContent).toContain('no cuadra al guaraní')
    expect(screen.queryByText('Las reglas del IRP están sin verificar contra la fuente oficial')).toBeNull()
    expect(screen.getByText('(no cuadra)')).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Año anterior' }))
    await waitFor(() => expect(paths).toContain('/tax/irp/2025'))
  })

  it('sin la regla, dice que el borrador del 515 no está disponible', async () => {
    mockFetch({ ...ESTIMATE, result: null, threshold: null, form_515: { available: false, version: null, rule: null, boxes: [], warnings: [], message: 'No hay una versión vigente de la regla IRP-RSP-DJ para 2026.' } })
    renderPage()
    expect(await screen.findByText('Borrador del Formulario 515 no disponible')).toBeTruthy()
    expect(screen.getByText(/IRP-RSP-DJ para 2026/)).toBeTruthy()
    expect(screen.queryByTestId('irp-to-pay')).toBeNull()
  })
})

describe('IRP: lógica', () => {
  it('elige el año del borrador y detecta la 715', () => {
    expect(defaultIrpYear('2026-03-31')).toBe(2025)
    expect(defaultIrpYear('2026-04-01')).toBe(2026)
    expect(hasIrpServices({ current: { obligations: [{ code: '715' }] } })).toBe(true)
    expect(hasIrpServices({ current: { obligations: [{ code: '211' }] } })).toBe(false)
    expect(hasIrpServices(undefined)).toBe(false)
    expect(irpXlsxName(2026)).toBe('irp-2026.xlsx')
  })
})
