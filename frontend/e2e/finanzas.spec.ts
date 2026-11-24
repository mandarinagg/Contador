/**
 * Finanzas (fase 2) de punta a punta: cuentas, movimientos, anulación, transferencia, importación
 * de un extracto, resumen por moneda y privacidad del contexto personal.
 *
 * Corre después de `flujos.spec.ts` (misma base, en orden) y parte de lo que dejó: la empresa, el
 * propietario y los usuarios Contador y Consulta. Si la base está vacía (este archivo solo), los
 * crea por la API antes de empezar.
 */
import type { APIRequestContext, Page } from '@playwright/test'
import { API_URL } from './env.ts'
import { ACCOUNTANT, expect, OWNER, PASSWORD, signIn, signOut, test, VIEWER } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light' })

async function ensureOrganization(request: APIRequestContext) {
  const setup = await (await request.get(`${API_URL}/system/setup`)).json()
  if (!setup.needs_setup) return
  const created = await request.post(`${API_URL}/system/setup`, {
    data: {
      organization: { legal_name: 'Prueba E2E EAS', legal_form: 'EAS' },
      owner: { full_name: OWNER.name, email: OWNER.email, password: PASSWORD },
    },
  })
  expect(created.ok()).toBeTruthy()
  const { token } = await created.json()
  for (const [user, role] of [
    [ACCOUNTANT, 'accountant'],
    [VIEWER, 'viewer'],
  ] as const) {
    const res = await request.post(`${API_URL}/users`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { email: user.email, full_name: user.name, password: PASSWORD, role },
    })
    expect(res.ok()).toBeTruthy()
  }
}

test.beforeAll(async ({ request }) => {
  await ensureOrganization(request)
})

const menu = (page: Page) => page.getByRole('navigation', { name: 'Principal' })
const contextBar = (page: Page) => page.getByRole('navigation', { name: 'Contexto financiero' })

async function openFinance(page: Page, section: string) {
  await menu(page).getByRole('link', { name: section, exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: section })).toBeVisible()
}

async function createAccount(page: Page, name: string, currency: string, opening: string) {
  await page.getByRole('button', { name: 'Nueva cuenta' }).first().click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Nombre').fill(name)
  await dialog.getByLabel('Moneda').selectOption(currency)
  await dialog.getByLabel('Saldo inicial', { exact: true }).fill(opening)
  await dialog.getByRole('button', { name: 'Crear cuenta' }).click()
  await expect(page.getByText(`Cuenta «${name}» creada.`)).toBeVisible()
}

function accountRow(page: Page, name: string) {
  return page.getByRole('row').filter({ has: page.getByText(name, { exact: true }) })
}

function txRow(page: Page, description: string) {
  return page.getByRole('row').filter({ has: page.getByText(description, { exact: true }) })
}

async function newTransaction(
  page: Page,
  tx: { direction: 'Sale' | 'Entra'; account: string; amount: string; description: string; date?: string },
) {
  await page.getByRole('button', { name: 'Nuevo movimiento' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.locator('label').filter({ hasText: tx.direction }).click()
  await dialog.getByLabel('Cuenta').selectOption({ label: tx.account })
  await dialog.getByLabel('Importe').fill(tx.amount)
  if (tx.date) await dialog.getByLabel('Fecha').fill(tx.date)
  await dialog.getByLabel('Descripción').fill(tx.description)
  await dialog.getByRole('button', { name: 'Cargar movimiento' }).click()
  await expect(dialog).toBeHidden()
}

test('cuentas: la empresa empieza sin cuentas y se crean en guaraníes y en dólares', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await openFinance(page, 'Cuentas')

  // El contexto activo se ve siempre: pestaña Empresa y franja de la empresa.
  await expect(contextBar(page).getByRole('link', { name: 'Empresa' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('note', { name: 'Contexto activo' })).toContainText('Finanzas de')
  await expect(page.getByText('Todavía no hay cuentas. Creá la primera')).toBeVisible()

  await createAccount(page, 'Banco E2E', 'PYG', '1.000.000')
  await createAccount(page, 'Caja E2E', 'PYG', '0')
  await createAccount(page, 'Dólares E2E', 'USD', '100,50')

  await expect(accountRow(page, 'Banco E2E')).toContainText('₲ 1.000.000')
  await expect(accountRow(page, 'Dólares E2E')).toContainText('US$ 100,50')

  // El contexto queda en la URL: recargar no lo pierde.
  await page.reload()
  await expect(accountRow(page, 'Banco E2E')).toContainText('₲ 1.000.000')
  await expect(contextBar(page).getByRole('link', { name: 'Empresa' })).toHaveAttribute('aria-current', 'page')
})

test('movimientos: alta manual de una salida y una entrada con formato paraguayo', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await openFinance(page, 'Movimientos')

  await newTransaction(page, { direction: 'Sale', account: 'Banco E2E (PYG)', amount: '150.000', description: 'Pago ANDE e2e' })
  await expect(page.getByText('Movimiento de −₲ 150.000 cargado.')).toBeVisible()
  await expect(txRow(page, 'Pago ANDE e2e')).toContainText('−₲ 150.000')

  await newTransaction(page, {
    direction: 'Entra',
    account: 'Banco E2E (PYG)',
    amount: '2500000',
    description: 'Cobro factura 501',
    date: '2026-03-05',
  })
  await expect(txRow(page, 'Cobro factura 501')).toContainText('+₲ 2.500.000')

  await openFinance(page, 'Cuentas')
  await expect(accountRow(page, 'Banco E2E')).toContainText('₲ 3.350.000')
})

test('anulación: exige motivo, el movimiento queda tachado y deja de contar en el saldo', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await openFinance(page, 'Movimientos')

  await page.getByRole('button', { name: 'Anular: Pago ANDE e2e' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Nada se borra')).toBeVisible()
  await dialog.getByRole('button', { name: 'Anular movimiento' }).click()
  await expect(dialog.getByText('Escribí el motivo (al menos 3 caracteres).')).toBeVisible()

  await dialog.getByLabel('Motivo de la anulación').fill('Se cargó en la cuenta equivocada')
  await dialog.getByRole('button', { name: 'Anular movimiento' }).click()
  await expect(page.getByText('Movimiento anulado.')).toBeVisible()
  await expect(txRow(page, 'Pago ANDE e2e')).toHaveCount(0)

  // Incluyendo anulados vuelve a verse, marcado, tachado y con su motivo.
  // El filtro vive en la URL: el estado de la casilla se actualiza al navegar.
  await page.getByLabel('Incluir anulados').click()
  await expect(page.getByLabel('Incluir anulados')).toBeChecked()
  const row = txRow(page, 'Pago ANDE e2e')
  await expect(row).toContainText('Anulado')
  await expect(row).toContainText('Motivo: Se cargó en la cuenta equivocada')
  await expect(row.getByText('Pago ANDE e2e', { exact: true })).toHaveCSS('text-decoration-line', 'line-through')
  await expect(row.getByRole('button', { name: /Anular/ })).toHaveCount(0)

  await openFinance(page, 'Cuentas')
  await expect(accountRow(page, 'Banco E2E')).toContainText('₲ 3.500.000')
})

test('transferencia entre cuentas propias: dos movimientos enlazados, sin categoría', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await openFinance(page, 'Movimientos')

  await page.getByRole('button', { name: 'Transferencia' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Desde (sale)').selectOption({ label: 'Banco E2E (PYG)' })
  await dialog.getByLabel('Hacia (entra)').selectOption({ label: 'Caja E2E (PYG)' })
  await dialog.getByLabel('Importe').fill('200.000')
  await dialog.getByLabel('Descripción').fill('Reposición de caja e2e')
  await dialog.getByRole('button', { name: 'Registrar transferencia' }).click()
  await expect(page.getByText('Transferencia de ₲ 200.000 registrada.')).toBeVisible()

  const legs = txRow(page, 'Reposición de caja e2e')
  await expect(legs).toHaveCount(2)
  await expect(legs.filter({ hasText: '−₲ 200.000' })).toContainText('Transferencia')
  await expect(legs.filter({ hasText: '+₲ 200.000' })).toContainText('No aplica')

  await openFinance(page, 'Cuentas')
  await expect(accountRow(page, 'Banco E2E')).toContainText('₲ 3.300.000')
  await expect(accountRow(page, 'Caja E2E')).toContainText('₲ 200.000')
})

test('importar extracto: duplicado contra la base, fila con error y nada se crea hasta confirmar', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await openFinance(page, 'Importar extracto')

  const csv = [
    'Banco E2E S.A.;;;;',
    'Extracto de cuenta corriente;;;;',
    'Fecha;Concepto;Nro. Operación;Débito;Crédito',
    '05/03/2026;Cobro factura 501;;;2.500.000',
    '06/03/2026;Comisión mantenimiento;9001;35.000;',
    '31/02/2026;Fecha imposible;9002;10.000;',
    '07/03/2026;Pago proveedor papelería;9003;1.234.500;',
  ].join('\r\n')

  await page.getByLabel('Cuenta del extracto').selectOption({ label: 'Banco E2E (PYG)' })
  await page.locator('input[type=file]').setInputFiles({ name: 'extracto-e2e.csv', mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf-8') })
  await page.getByRole('button', { name: 'Continuar' }).click()

  // El asistente reconoce el encabezado después de los títulos del banco y propone el mapeo.
  await expect(page.getByLabel('Filas a saltear al principio')).toHaveValue('2')
  await expect(page.getByLabel('Débito (sale)')).toHaveValue('Débito')
  await expect(page.getByLabel('Crédito (entra)')).toHaveValue('Crédito')
  await page.getByRole('button', { name: 'Analizar archivo' }).click()

  const counts = page.getByRole('group', { name: 'Filtrar filas' })
  await expect(counts.getByRole('button', { name: /A importar/ })).toContainText('2')
  await expect(counts.getByRole('button', { name: /Duplicadas/ })).toContainText('1')
  await expect(counts.getByRole('button', { name: /Con error/ })).toContainText('1')
  await expect(page.getByText('Fecha inválida: 31/02/2026')).toBeVisible()
  await expect(page.getByText(/Ya hay un movimiento igual en la cuenta/)).toBeVisible()
  await expect(page.getByLabel('Importar la fila 6')).toBeDisabled()

  // Analizar no creó nada: la lista de movimientos sigue igual (el lote queda en la URL).
  const reviewUrl = page.url()
  await openFinance(page, 'Movimientos')
  await expect(txRow(page, 'Comisión mantenimiento')).toHaveCount(0)
  await page.goto(reviewUrl)

  // Se puede cambiar la decisión de una fila: se omite la comisión.
  await page.getByLabel('Importar la fila 5').click()
  await expect(page.getByLabel('Importar la fila 5')).not.toBeChecked()
  await expect(counts.getByRole('button', { name: /A importar/ })).toContainText('1')
  await page.getByRole('button', { name: 'Confirmar importación' }).click()
  await expect(page.getByRole('heading', { name: 'Listo: 1 movimiento importado' })).toBeVisible()

  await page.getByRole('link', { name: 'Revisar los importados' }).click()
  await expect(page.getByLabel('Solo sin revisar')).toBeChecked()
  const imported = txRow(page, 'Pago proveedor papelería')
  await expect(imported).toContainText('Sin revisar')
  await expect(imported).toContainText('Importado')
  await expect(txRow(page, 'Comisión mantenimiento')).toHaveCount(0)
  await imported.getByRole('button', { name: /Marcar revisado/ }).click()
  await expect(page.getByText('Movimiento marcado como revisado.')).toBeVisible()
  await expect(txRow(page, 'Pago proveedor papelería')).toHaveCount(0)
})

test.describe('importar extracto con cambios desde el análisis', () => {
  // La API responde 409 IMPORT_NEW_DUPLICATES: el navegador lo registra como error de carga.
  test.use({ expectedConsoleErrors: /status of 409/ })

  test('si alguien carga un movimiento igual antes de confirmar, avisa, lo marca duplicado y no crea nada', async ({ page }) => {
    await signIn(page, OWNER.email, PASSWORD)
    await openFinance(page, 'Importar extracto')
    const csv = 'Fecha;Concepto;Importe\n08/03/2026;Pago alquiler e2e;-3.000.000\n'
    await page.getByLabel('Cuenta del extracto').selectOption({ label: 'Banco E2E (PYG)' })
    await page.locator('input[type=file]').setInputFiles({ name: 'alquiler.csv', mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf-8') })
    await page.getByRole('button', { name: 'Continuar' }).click()
    // Esta cuenta ya tiene una importación: se ofrece su mapeo, pero este archivo tiene otro formato.
    await expect(page.getByRole('button', { name: 'Usar el mapeo de la última importación' })).toBeVisible()
    await expect(page.getByLabel('Columna del importe')).toHaveValue('Importe')
    await page.getByRole('button', { name: 'Analizar archivo' }).click()
    const counts = page.getByRole('group', { name: 'Filtrar filas' })
    await expect(counts.getByRole('button', { name: /A importar/ })).toContainText('1')

    // Mientras tanto, se carga a mano el mismo movimiento (otra ventana, otra persona).
    const token = await page.evaluate(() => sessionStorage.getItem('contador.session'))
    const headers = { Authorization: `Bearer ${token}` }
    const cid = new URL(page.url()).pathname.split('/')[2]
    const accounts = await (await page.request.get(`${API_URL}/finance/contexts/${cid}/accounts`, { headers })).json()
    const banco = accounts.find((a: { name: string }) => a.name === 'Banco E2E')
    const created = await page.request.post(`${API_URL}/finance/contexts/${cid}/transactions`, {
      headers,
      data: { account_id: banco.id, booked_on: '2026-03-08', amount: '-3000000', description: 'Pago alquiler e2e' },
    })
    expect(created.ok()).toBeTruthy()

    await page.getByRole('button', { name: 'Confirmar importación' }).click()
    await expect(page.getByText('Aparecieron movimientos iguales desde el análisis')).toBeVisible()
    await expect(page.getByText(/no se creó nada todavía/)).toBeVisible()
    await expect(counts.getByRole('button', { name: /A importar/ })).toContainText('0')
    await expect(page.getByRole('button', { name: 'Confirmar importación' })).toBeDisabled()

    await page.getByRole('button', { name: 'Cancelar importación' }).click()
    await expect(page.getByText('Importación cancelada. No se creó ningún movimiento.')).toBeVisible()
    await expect(page.getByLabel('Cuenta del extracto')).toBeVisible()
  })
})

test('resumen: un bloque por moneda, sin mezclar guaraníes con dólares; el consolidado identifica el contexto', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await openFinance(page, 'Movimientos')
  await newTransaction(page, { direction: 'Entra', account: 'Dólares E2E (USD)', amount: '50,25', description: 'Servicio exterior e2e' })

  await openFinance(page, 'Resumen')
  const pyg = page.getByRole('region', { name: 'Guaraníes (₲)' })
  const usd = page.getByRole('region', { name: 'Dólares (US$)' })
  await expect(pyg).toBeVisible()
  await expect(usd).toBeVisible()
  await expect(usd).toContainText('US$ 50,25')
  await expect(usd).toContainText('US$ 150,75')
  await expect(usd).not.toContainText('₲')
  await expect(pyg).not.toContainText('US$')
  await expect(pyg.getByText('Banco E2E')).toBeVisible()

  await contextBar(page).getByRole('link', { name: 'Consolidado' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Consolidado' })).toBeVisible()
  await expect(page.getByText('Empresa').first()).toBeVisible()
  await expect(page.getByRole('row', { name: /Dólares/ })).toContainText('US$ 150,75')
})

test.describe('privacidad del contexto personal', () => {
  // Abrir el contexto personal ajeno da 404 en la API: el navegador lo registra como error de carga.
  test.use({ expectedConsoleErrors: /status of 404/ })

  test('lo personal solo lo ve su dueño; Consulta lee la empresa pero escribe solo en lo suyo', async ({ page }) => {
    // Recorre tres usuarios (tres inicios de sesión con hash de contraseña): con la PC cargada
    // supera los 30 s por defecto aunque cada paso responda bien.
    test.slow()
    await signIn(page, OWNER.email, PASSWORD)
    await openFinance(page, 'Resumen')
    await contextBar(page).getByRole('button', { name: 'Crear mi espacio personal' }).click()
    await expect(page.getByText('Tu espacio personal está listo. Solo vos podés verlo.')).toBeVisible()
    await expect(contextBar(page).getByRole('link', { name: /Personal/ })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('note', { name: 'Contexto activo' })).toContainText('Privadas: nadie más las ve')
    await createAccount(page, 'Ahorro personal e2e', 'PYG', '5.000.000')
    const personalUrl = page.url()
    await signOut(page)

    // El contador (aun con permisos de finanzas) no ve el contexto personal del propietario.
    await signIn(page, ACCOUNTANT.email, PASSWORD)
    await expect(page).toHaveURL(/\/$/)
    await page.goto(personalUrl)
    await expect(page.getByText('Ese contexto financiero no existe')).toBeVisible()
    await expect(page.getByText('Ahorro personal e2e')).toHaveCount(0)
    // Y la API tampoco lo revela: 404, no 403.
    const token = await page.evaluate(() => sessionStorage.getItem('contador.session'))
    const personalId = new URL(personalUrl).pathname.split('/')[2]
    const direct = await page.request.get(`${API_URL}/finance/contexts/${personalId}/accounts`, { headers: { Authorization: `Bearer ${token}` } })
    expect(direct.status()).toBe(404)
    await openFinance(page, 'Resumen')
    await expect(contextBar(page).getByRole('button', { name: 'Crear mi espacio personal' })).toBeVisible()
    await expect(contextBar(page).getByRole('link', { name: /Personal/ })).toHaveCount(0)
    await page.goto('/finanzas/consolidado')
    await expect(page.getByRole('heading', { level: 1, name: 'Consolidado' })).toBeVisible()
    await expect(page.getByText('Tus finanzas personales')).toHaveCount(0)
    await signOut(page)

    // Consulta: lee la empresa sin acciones de escritura y opera su propio espacio personal.
    await signIn(page, VIEWER.email, PASSWORD)
    await openFinance(page, 'Cuentas')
    await expect(accountRow(page, 'Banco E2E')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Nueva cuenta' })).toHaveCount(0)
    await expect(page.getByText('Tu rol puede consultar las finanzas de la empresa, pero no modificarlas.')).toBeVisible()
    await expect(page.getByRole('note', { name: 'Contexto activo' })).toContainText('Solo lectura')
    await openFinance(page, 'Movimientos')
    await expect(page.getByRole('button', { name: 'Nuevo movimiento' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /Anular/ })).toHaveCount(0)

    await contextBar(page).getByRole('button', { name: 'Crear mi espacio personal' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Cuentas' })).toBeVisible()
    await createAccount(page, 'Billetera de consulta', 'PYG', '10.000')
    await expect(accountRow(page, 'Billetera de consulta')).toContainText('₲ 10.000')
    await page.goto(personalUrl)
    await expect(page.getByText('Ese contexto financiero no existe')).toBeVisible()
  })
})
