/**
 * Contabilidad, fase 3B, de punta a punta: categorías de activo fijo (las propuestas sin validar,
 * completar y validar), alta de bienes, depreciación del mes (sin saltear meses), baja con acta,
 * centros de costos en las líneas y en el estado de resultados, asientos recurrentes (aviso y
 * generación sin duplicar), balance de comprobación con saldo inicial, exportación a Excel e
 * impresión, cuadro de depreciación que concilia, y el movimiento de origen leído por id (P-9).
 *
 * Corre después de `contabilidad.spec.ts` (misma base, en orden): plan validado, ejercicio 2025
 * cerrado con refundición (saldo inicial de 2026) y 2026 abierto con los asientos N° 1 a 4.
 */
import { readFileSync } from 'node:fs'
import type { APIRequestContext, Page } from '@playwright/test'
import { API_URL } from './env.ts'
import { ACCOUNTANT, expect, OWNER, PASSWORD, signIn, signOut, test, VIEWER } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light' })

const menu = (page: Page) => page.getByRole('navigation', { name: 'Principal' })
const toast = (page: Page, text: string | RegExp) => expect(page.getByText(text).first()).toBeVisible()

async function open(page: Page, section: string, heading = section) {
  await menu(page).getByRole('link', { name: section, exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
}

async function assetsTab(page: Page, tab: string) {
  await open(page, 'Activos fijos')
  await page.getByRole('navigation', { name: 'Secciones de activos fijos' }).getByRole('link', { name: tab }).click()
}

async function reportTab(page: Page, tab: string) {
  await open(page, 'Libros y balances')
  await page.getByRole('navigation', { name: 'Reportes contables' }).getByRole('link', { name: tab }).click()
}

async function pickAccount(page: Page, line: number, code: string) {
  const box = page.getByRole('combobox', { name: `Cuenta de la línea ${line}` })
  await box.fill(code)
  await expect(page.getByRole('listbox', { name: 'Cuentas imputables' }).getByRole('option').first()).toContainText(code)
  await box.press('Enter')
  await expect(box).toHaveValue(new RegExp(`^${code.replaceAll('.', '\\.')} `))
}

async function api(request: APIRequestContext) {
  const login = await request.post(`${API_URL}/auth/login`, { data: { email: OWNER.email, password: PASSWORD } })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).token}` }
  return {
    get: async (path: string) => (await request.get(`${API_URL}${path}`, { headers })).json(),
    post: async (path: string, data?: unknown) => {
      const res = await request.post(`${API_URL}${path}`, { headers, data })
      expect(res.ok(), `${path}: ${await res.text()}`).toBeTruthy()
      return res.json()
    },
  }
}

/** Cuenta imputable por código (el plan llega como árbol). */
async function accountId(client: Awaited<ReturnType<typeof api>>, code: string): Promise<string> {
  type Node = { id: string; code: string; children?: Node[] }
  const chart: { accounts: Node[] } = await client.get('/accounting/chart')
  const stack = [...chart.accounts]
  while (stack.length) {
    const n = stack.pop() as Node
    if (n.code === code) return n.id
    stack.push(...(n.children ?? []))
  }
  throw new Error(`No existe la cuenta ${code}`)
}

/** Un archivo XLSX es un ZIP: no vacío y empieza con «PK». */
function expectXlsx(path: string) {
  const bytes = readFileSync(path)
  expect(bytes.length).toBeGreaterThan(1000)
  expect(bytes.subarray(0, 2).toString('latin1')).toBe('PK')
}

let acquisitionNumber = 0

test('categorías: se cargan las 34 propuestas sin validar, se completa una y el contador valida otra', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await assetsTab(page, 'Categorías')
  await expect(page.getByText('Todavía no hay categorías de activo fijo', { exact: true })).toBeVisible()
  await expect(page.getByText(/Decreto 3182\/2019, art\. 31, con la redacción del Decreto 6105\/2021/)).toBeVisible()
  await page.getByRole('button', { name: 'Cargar las 34 categorías propuestas' }).click()
  await toast(page, 'Se cargaron las 34 categorías propuestas, sin validar.')
  await expect(page.getByText('34 en uso, 0 validadas, 4 incompletas.')).toBeVisible()
  await expect(page.getByRole('note', { name: 'Estado de las vidas útiles' })).toContainText('propuestas sin validar')

  // Fuente y referencia legal de cada una, a la vista.
  await page.getByRole('button', { name: 'Equipos de informática: ver la fuente' }).click()
  await expect(page.getByRole('link', { name: 'Ver el texto oficial en la DNIT' }).first()).toBeVisible()

  // Se completa el software (le falta el residual).
  await page.getByRole('checkbox', { name: 'Solo incompletas (4)' }).check()
  const software = 'Software adquirido (licencias perpetuas o de larga duración)'
  await page.getByRole('button', { name: `Completar ${software}` }).click()
  const dialog = page.getByRole('dialog', { name: `Completar «${software}»` })
  await dialog.getByLabel('Valor residual (% del costo)').fill('0')
  await dialog.getByRole('button', { name: 'Guardar' }).click()
  await toast(page, `Categoría «${software}» guardada: lista para usar.`)
  await expect(page.getByText('34 en uso, 0 validadas, 3 incompletas.')).toBeVisible()
  // Una incompleta no se valida.
  await expect(page.getByRole('button', { name: 'Validar Terrenos (no depreciables)' })).toBeDisabled()

  // El contador valida «Equipos de informática» con nombre y matrícula.
  await signOut(page)
  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await assetsTab(page, 'Categorías')
  await page.getByRole('button', { name: 'Validar Equipos de informática' }).click()
  const validate = page.getByRole('dialog', { name: 'Validar la categoría' })
  await validate.getByLabel('Nombre del contador').fill('Contadora Externa')
  await validate.getByLabel('Matrícula profesional').fill('MAT-1234')
  await validate.getByRole('button', { name: 'Validar la categoría' }).click()
  await toast(page, 'Categoría «Equipos de informática» validada.')
  await expect(page.getByText('34 en uso, 1 validadas, 3 incompletas.')).toBeVisible()
})

test('alta de bienes: la notebook con su asiento de compra y la impresora; avisa antes del 14-10-2021', async ({ page, request }) => {
  test.slow()
  // El asiento de compra de los dos bienes (aporte en especie), para que el cuadro concilie.
  const client = await api(request)
  const draft = await client.post('/accounting/entries', {
    entry_date: '2026-01-20',
    description: 'Aporte de equipos de informática e2e',
    lines: [
      { account_id: await accountId(client, '1.02.04.05.01'), debit: '15000000' },
      { account_id: await accountId(client, '3.01.01.01'), credit: '15000000' },
    ],
  })
  acquisitionNumber = (await client.post(`/accounting/entries/${draft.id}/post`)).number

  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await open(page, 'Activos fijos')
  await expect(page.getByText('Todavía no hay bienes de uso')).toBeVisible()
  await page.getByRole('link', { name: 'Nuevo bien' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Nuevo bien de uso' })).toBeVisible()
  await page.getByLabel('Categoría').selectOption({ label: 'Equipos de informática (2 años, residual 10 %)' })
  await page.getByLabel('Nombre', { exact: true }).fill('Notebook E2E')
  await page.getByLabel('Fecha de adquisición').fill('2021-05-10')
  await expect(page.getByText('Comprado antes del 14-10-2021')).toBeVisible()
  await page.getByLabel('Fecha de adquisición').fill('2026-01-20')
  await expect(page.getByText('Comprado antes del 14-10-2021')).toHaveCount(0)
  await page.getByLabel('Costo de adquisición').fill('12.000.000')
  await expect(page.getByText(/no incluye los intereses de la financiación ni las diferencias de cambio/)).toBeVisible()
  await expect(page.getByText('Desde febrero de 2026, una cuota por mes.')).toBeVisible()
  await expect(page.getByRole('definition').filter({ hasText: '450.000' }).first()).toBeVisible()

  // Si los contables difieren de los fiscales, explica la cuota no deducible.
  const same = page.getByRole('checkbox', { name: 'Los parámetros contables son iguales a los fiscales' })
  await same.uncheck()
  await page.getByLabel('Vida útil contable (meses)').fill('12')
  await page.getByLabel('Valor residual contable').fill('0')
  await expect(page.getByText(/cuota no deducible/).first()).toBeVisible()
  await expect(page.getByText(/el primer año completo deja ₲\s?6\.600\.000 no deducibles/)).toBeVisible()
  await same.check()

  await page.getByLabel('N° del asiento de compra').fill(String(acquisitionNumber))
  await expect(page.getByText(`Asiento N° ${acquisitionNumber} del 20/01/2026: Aporte de equipos de informática e2e.`)).toBeVisible()
  await page.getByRole('button', { name: 'Dar de alta el bien' }).click()
  await toast(page, 'Bien «Notebook E2E» dado de alta: se deprecia desde febrero de 2026.')
  await expect(page.getByRole('heading', { level: 1, name: 'Notebook E2E' })).toBeVisible()
  await expect(page.getByRole('definition').filter({ hasText: 'en 24 cuotas' })).toContainText('10.800.000')
  await expect(page.getByRole('link', { name: `Asiento N° ${acquisitionNumber}` })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Plan de cuotas' }).getByRole('row').filter({ hasText: 'Febrero' }).first()).toContainText('Pendiente')

  // La impresora, por API (el alta por pantalla ya se probó).
  const categories: { id: string; name: string }[] = await client.get('/accounting/asset-categories')
  const it = categories.find((c) => c.name === 'Equipos de informática')
  await client.post('/accounting/fixed-assets', { category_id: it?.id, name: 'Impresora E2E', acquired_on: '2026-01-10', cost: '3000000' })
  await open(page, 'Activos fijos')
  await expect(page.getByRole('row').filter({ hasText: 'Impresora E2E' })).toContainText('3.000.000')
  await expect(page.getByRole('row').filter({ hasText: '2 bienes' })).toContainText('15.000.000')
})

test.describe('con errores esperados de la API', () => {
  test.use({ expectedConsoleErrors: /status of (409|422)/ })

  test('depreciación: marzo no se calcula sin febrero (409); febrero se calcula y se contabiliza', async ({ page }) => {
    test.slow()
    await signIn(page, ACCOUNTANT.email, PASSWORD)
    await assetsTab(page, 'Depreciación del mes')
    await page.getByRole('button', { name: 'Calcular la depreciación de marzo de 2026' }).click()
    const alert = page.getByRole('alert')
    await expect(alert).toContainText('No se puede calcular marzo de 2026: falta febrero de 2026')
    await alert.getByRole('button', { name: 'Ir a febrero de 2026' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)

    await page.getByRole('button', { name: 'Calcular la depreciación de febrero de 2026' }).click()
    await toast(page, 'Borrador de depreciación de febrero de 2026 generado: revisalo y contabilizalo.')
    await expect(page.getByRole('heading', { level: 1, name: 'Borrador de asiento' })).toBeVisible()
    const detail = page.getByRole('table').filter({ hasText: 'Cuota N°' })
    await expect(detail.getByRole('row').filter({ hasText: 'Notebook E2E' })).toContainText('450.000')
    await expect(detail.getByRole('row').filter({ hasText: 'Impresora E2E' })).toContainText('112.500')
    await page.getByRole('button', { name: 'Contabilizar' }).click()
    await toast(page, /Asiento N° \d+ contabilizado\./)
    await expect(page.getByRole('heading', { level: 1, name: /^Asiento N° \d+$/ })).toBeVisible()

    // Una corrida viva por mes: febrero ya no se vuelve a calcular.
    await assetsTab(page, 'Depreciación del mes')
    const february = page.getByRole('table', { name: 'Depreciación por mes' }).getByRole('row').filter({ hasText: 'Febrero' })
    await expect(february).toContainText('Contabilizada')
    await expect(february).toContainText('562.500')
    await expect(february.getByRole('link', { name: 'Ver el asiento' })).toBeVisible()
  })

  test('baja: sin acta no se genera; con acta abre el borrador y al contabilizarlo el bien queda de baja', async ({ page }) => {
    test.slow()
    await signIn(page, ACCOUNTANT.email, PASSWORD)
    await open(page, 'Activos fijos')
    await page.getByRole('link', { name: 'Impresora E2E' }).click()
    await page.getByRole('button', { name: 'Dar de baja' }).click()
    const dialog = page.getByRole('dialog', { name: 'Dar de baja «Impresora E2E»' })
    await dialog.getByLabel('Fecha de la baja').fill('2026-03-15')
    await dialog.getByLabel('Tipo de baja').selectOption({ label: 'Destrucción o desuso' })
    await dialog.getByLabel('Motivo').fill('Rota sin reparación posible')
    await dialog.getByRole('button', { name: 'Generar el borrador de baja' }).click()
    await expect(dialog.getByText(/El acta es obligatoria/)).toBeVisible()
    await dialog.getByLabel('Acta de baja').fill('Acta 3/2026')
    await dialog.getByRole('button', { name: 'Generar el borrador de baja' }).click()
    await toast(page, 'Borrador de baja de «Impresora E2E» generado: revisalo y contabilizalo.')
    await expect(page.getByRole('heading', { level: 1, name: 'Borrador de asiento' })).toBeVisible()
    // Cancela el costo, la acumulada de febrero y lleva el neto a resultados.
    await expect(page.getByRole('row').filter({ hasText: 'Baja: costo del bien' })).toContainText('3.000.000')
    await expect(page.getByRole('row').filter({ hasText: 'Baja: depreciación acumulada' })).toContainText('112.500')
    await expect(page.getByRole('row').filter({ hasText: 'Baja: valor neto contable' })).toContainText('2.887.500')
    await page.getByRole('button', { name: 'Contabilizar' }).click()
    await toast(page, /Asiento N° \d+ contabilizado\./)
    await expect(page.getByRole('heading', { level: 1, name: /^Asiento N° \d+$/ })).toBeVisible()

    await open(page, 'Activos fijos')
    await page.getByRole('combobox', { name: 'Estado' }).selectOption({ label: 'Dados de baja' })
    await page.getByRole('link', { name: 'Impresora E2E' }).click()
    await expect(page.getByText('Dado de baja el 15/03/2026')).toBeVisible()
    await expect(page.getByText(/Acta: Acta 3\/2026/)).toBeVisible()
    await expect(page.getByRole('link', { name: /Ver el asiento de baja N° \d+/ })).toBeVisible()
  })
})

test('centros de costos: solo en líneas de resultado, obligatorios si se configura, y resultados por centro', async ({ page }) => {
  test.slow()
  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await open(page, 'Centros de costos')
  await expect(page.getByText('Todavía no hay centros de costos')).toBeVisible()
  await page.getByRole('button', { name: 'Crear el primero' }).click()
  let dialog = page.getByRole('dialog', { name: 'Nuevo centro de costos' })
  await dialog.getByLabel('Código').fill('ADM')
  await dialog.getByLabel('Nombre').fill('Administración')
  await dialog.getByRole('button', { name: 'Crear centro' }).click()
  await toast(page, 'Centro ADM Administración creado.')
  await page.getByRole('button', { name: 'Nuevo centro' }).click()
  dialog = page.getByRole('dialog', { name: 'Nuevo centro de costos' })
  await dialog.getByLabel('Código').fill('VEN')
  await dialog.getByLabel('Nombre').fill('Ventas')
  await dialog.getByRole('button', { name: 'Crear centro' }).click()
  await toast(page, 'Centro VEN Ventas creado.')

  // En la línea de gasto se elige el centro; en la del banco no se ofrece.
  await open(page, 'Asientos')
  await page.getByRole('link', { name: 'Nuevo asiento' }).first().click()
  await page.getByLabel('Fecha', { exact: true }).fill('2026-04-10')
  await page.getByLabel('Descripción', { exact: true }).fill('Alquiler de abril e2e')
  await pickAccount(page, 1, '11.05')
  await page.getByLabel('Debe de la línea 1', { exact: true }).fill('800.000')
  await page.getByRole('combobox', { name: 'Centro de costos de la línea 1' }).selectOption({ label: 'ADM Administración' })
  await pickAccount(page, 2, '1.01.01.04.01')
  await page.getByLabel('Haber de la línea 2', { exact: true }).fill('800.000')
  await expect(page.getByRole('combobox', { name: 'Centro de costos de la línea 2' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Contabilizar' }).click()
  await toast(page, /Asiento N° \d+ contabilizado\./)
  await expect(page.getByRole('row').filter({ hasText: '11.05' })).toContainText('ADM')

  // Centro obligatorio: sin él, el asiento no se contabiliza.
  await open(page, 'Centros de costos')
  await page.getByRole('checkbox', { name: 'Exigir centro de costos en ingresos y gastos' }).check()
  await toast(page, 'Desde ahora, el centro es obligatorio en ingresos y gastos al contabilizar.')
  await open(page, 'Asientos')
  await page.getByRole('link', { name: 'Nuevo asiento' }).first().click()
  await page.getByLabel('Fecha', { exact: true }).fill('2026-04-12')
  await page.getByLabel('Descripción', { exact: true }).fill('Publicidad de abril e2e')
  await pickAccount(page, 1, '11.05')
  await page.getByLabel('Debe de la línea 1', { exact: true }).fill('200.000')
  await pickAccount(page, 2, '1.01.01.04.01')
  await page.getByLabel('Haber de la línea 2', { exact: true }).fill('200.000')
  await expect(page.getByText('Falta el centro de costos en las líneas de ingreso o gasto marcadas: la configuración lo exige.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Contabilizar' })).toBeDisabled()
  await page.getByRole('combobox', { name: 'Centro de costos de la línea 1' }).selectOption({ label: 'VEN Ventas' })
  await page.getByRole('button', { name: 'Contabilizar' }).click()
  await toast(page, /Asiento N° \d+ contabilizado\./)
  await expect(page.getByRole('row').filter({ hasText: '11.05' })).toContainText('VEN')
  await open(page, 'Centros de costos')
  await page.getByRole('checkbox', { name: 'Exigir centro de costos en ingresos y gastos' }).uncheck()
  await toast(page, 'El centro de costos vuelve a ser opcional.')

  // Estado de resultados por centro: una columna por centro y el total.
  await reportTab(page, 'Estado de resultados')
  await page.getByLabel('Desde', { exact: true }).fill('2026-04-01')
  await page.getByLabel('Hasta', { exact: true }).fill('2026-04-30')
  // La casilla vive en la URL (?por_centro=1): se marca al terminar la navegación.
  const byCenter = page.getByRole('checkbox', { name: 'Ver por centro de costos' })
  await byCenter.click()
  await expect(byCenter).toBeChecked()
  const table = page.getByRole('table', { name: 'Estado de resultados por centro de costos' })
  await expect(table.getByRole('columnheader', { name: /ADM/ })).toBeVisible()
  await expect(table.getByRole('columnheader', { name: /VEN/ })).toBeVisible()
  const row = table.getByRole('row').filter({ has: page.getByRole('link', { name: /11\.05/ }) })
  await expect(row.getByRole('cell').nth(0)).toHaveText('800.000')
  await expect(row.getByRole('cell').nth(1)).toHaveText('200.000')
  await expect(row.getByRole('cell').last()).toHaveText('1.000.000')
})

test('asientos recurrentes: plantilla, aviso del mes y generación sin duplicar', async ({ page }) => {
  test.slow()
  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await open(page, 'Asientos recurrentes')
  await expect(page.getByText('Todavía no hay plantillas')).toBeVisible()
  await page.getByRole('link', { name: 'Crear la primera' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Nueva plantilla recurrente' })).toBeVisible()
  await page.getByLabel('Descripción', { exact: true }).fill('Alquiler oficina E2E')
  await page.getByLabel('Día del mes').fill('5')
  await page.getByLabel('Rige desde').fill('2026-01-01')
  await pickAccount(page, 1, '11.05')
  await page.getByLabel('Debe de la línea 1', { exact: true }).fill('1.500.000')
  await page.getByRole('combobox', { name: 'Centro de costos de la línea 1' }).selectOption({ label: 'ADM Administración' })
  await pickAccount(page, 2, '1.01.01.04.01')
  await page.getByLabel('Haber de la línea 2', { exact: true }).fill('1.500.000')
  await page.getByRole('button', { name: 'Crear la plantilla' }).click()
  await toast(page, 'Plantilla «Alquiler oficina E2E» creada.')
  await expect(page.getByRole('row').filter({ hasText: 'Alquiler oficina E2E' })).toContainText('Activa')

  // El aviso del período actual (si el año en curso es el del ejercicio de las pruebas).
  if (new Date().getFullYear() === 2026) {
    await open(page, 'Inicio', /^Hola,/ as unknown as string)
    const banner = page.getByRole('region', { name: 'Asientos recurrentes pendientes' })
    await expect(banner).toContainText('Alquiler oficina E2E')
    await banner.getByRole('button', { name: /^Generar los de / }).click()
    await toast(page, 'Se generó 1 borrador.')
    await expect(banner).toHaveCount(0)
    await open(page, 'Asientos')
    await expect(page.getByRole('region', { name: 'Asientos recurrentes pendientes' })).toHaveCount(0)
  }

  // Generar abril: crea el borrador; generar de nuevo no lo duplica.
  await open(page, 'Asientos recurrentes')
  await page.getByLabel('Período').selectOption({ label: 'abril de 2026' })
  await page.getByRole('button', { name: 'Generar los borradores' }).click()
  const result = page.getByRole('status', { name: 'Resultado de la generación' })
  await expect(result).toContainText('abril de 2026: Se generó 1 borrador.')
  await expect(result.getByRole('link', { name: 'Alquiler oficina E2E' })).toBeVisible()
  await page.getByRole('button', { name: 'Generar los borradores' }).click()
  await expect(result).toContainText('abril de 2026: 1 ya existía (no se duplicó).')
  await expect(result).toContainText('Ya existían')

  // El borrador generado lleva las líneas de la plantilla (con su centro) y es editable.
  await result.getByRole('link', { name: 'Alquiler oficina E2E' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Borrador de asiento' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Centro de costos de la línea 1' })).toHaveValue(/.+/)
  await expect(page.getByLabel('Fecha', { exact: true })).toHaveValue('2026-04-05')
})

test('balance de comprobación: saldo inicial (refundición de 2025), Excel e impresión', async ({ page }) => {
  await signIn(page, VIEWER.email, PASSWORD)
  await reportTab(page, 'Balance de comprobación')
  await page.getByLabel('Desde', { exact: true }).fill('2026-01-01')
  await page.getByLabel('Hasta', { exact: true }).fill('2026-12-31')
  const table = page.getByRole('table', { name: 'Balance de comprobación' })
  const row = (code: string) => table.getByRole('row').filter({ has: page.getByRole('link', { name: new RegExp(`^${code.replaceAll('.', '\\.')}[^.\\d]`) }) })
  // Columnas: cuenta, saldo inicial (D, A), movimientos (D, A), saldo final (D, A).
  await expect(row('1.01.01.04.01').getByRole('cell').nth(1)).toHaveText('1.000.000')
  await expect(row('3.03.02').getByRole('cell').nth(2)).toHaveText('1.000.000')
  await expect(row('3.03.02').getByRole('cell').nth(6)).toHaveText('1.000.000')
  // Las cuentas de resultado arrancan en cero (las refundió el cierre de 2025).
  await expect(row('4.09').getByRole('cell').nth(1)).toHaveText('·')
  await expect(row('4.09').getByRole('cell').nth(2)).toHaveText('·')
  await expect(row('4.09').getByRole('cell').nth(4)).toHaveText('2.200.000')
  await expect(table.getByRole('row').filter({ hasText: 'Totales' })).toContainText('cuadran')

  // Excel con el nombre de la API.
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Descargar Excel' }).click()
  const file = await downloading
  expect(file.suggestedFilename()).toBe('balance-de-comprobacion-2026-01-01-2026-12-31.xlsx')
  expectXlsx(await file.path())
  await toast(page, 'Excel descargado: balance-de-comprobacion-2026-01-01-2026-12-31.xlsx')

  // Imprimir: solo el reporte, con la empresa y el RUC; sin menú ni botones.
  await page.emulateMedia({ media: 'print' })
  await expect(page.getByRole('heading', { name: 'Balance de comprobación de sumas y saldos' })).toBeVisible()
  await expect(page.getByText(/RUC/).first()).toBeVisible()
  await expect(page.getByText(/^Emitido el /)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Descargar Excel' })).toBeHidden()
  await expect(menu(page)).toBeHidden()
  await page.emulateMedia({ media: 'screen' })
})

test('cuadro de depreciación: columnas de la RG 77/2020, concilia con el balance y se descarga', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await assetsTab(page, 'Cuadro de depreciación')
  await expect(page.getByRole('heading', { name: 'Cuadro de depreciación fiscal del ejercicio 2026' })).toBeVisible()
  await expect(page.getByText('Las columnas de revalúo van en cero', { exact: false })).toBeVisible()
  await expect(page.getByText(/IRE SIMPLE/)).toBeVisible()
  const table = page.getByRole('table', { name: /Cuadro de depreciación, vista fiscal/ })
  await expect(table.getByRole('row').filter({ hasText: 'Notebook E2E' })).toContainText('12.000.000')
  await expect(table.getByRole('row').filter({ hasText: 'Impresora E2E' })).toContainText('De baja el 15/03/2026')
  await expect(page.getByRole('heading', { name: 'Concilia con el balance' })).toBeVisible()

  await page.getByText('Contable (14 a 22)').click()
  await expect(page.getByRole('heading', { name: 'Cuadro de depreciación contable del ejercicio 2026' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: /22\s*Neto contable al cierre/ })).toBeVisible()

  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Descargar Excel' }).click()
  const file = await downloading
  expect(file.suggestedFilename()).toBe('cuadro-de-depreciacion.xlsx')
  expectXlsx(await file.path())
})

test('núcleo: movimiento de origen por id (P-9), nombres en asientos y diario (P-10) y auditoría legible', async ({ page }) => {
  test.slow()
  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await open(page, 'Asientos')
  await page.getByRole('link', { name: 'Cobro servicio contable e2e' }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: 'Asiento N° 3' })).toBeVisible()
  await expect(page.getByText(/por Contadora Externa/).first()).toBeVisible()

  const origin = page.getByRole('link', { name: 'Movimiento de finanzas de origen' })
  await expect(page.getByTestId('movimiento-origen')).toContainText('Cobro servicio contable e2e')
  const href = (await origin.getAttribute('href')) ?? ''
  await origin.click()
  await expect(page.getByRole('dialog', { name: 'Movimiento' })).toContainText('Cobro servicio contable e2e')
  // Aunque los filtros de la lista lo excluyan, el detalle se lee por id.
  await page.goto(`${href}&q=no-coincide-con-nada`)
  const detail = page.getByRole('dialog', { name: 'Movimiento' })
  await expect(detail).toContainText('Cobro servicio contable e2e')
  await page.keyboard.press('Escape')
  await expect(detail).toHaveCount(0)

  await reportTab(page, 'Libro diario')
  await page.getByLabel('Desde', { exact: true }).fill('2026-03-01')
  await page.getByLabel('Hasta', { exact: true }).fill('2026-03-31')
  await expect(page.getByText(/Cargado por .+; contabilizado por Contadora Externa\./).first()).toBeVisible()

  await signOut(page)
  await signIn(page, OWNER.email, PASSWORD)
  await menu(page).getByRole('link', { name: 'Auditoría', exact: true }).click()
  await expect(page.getByText('Bien de uso dado de baja').first()).toBeVisible()
  await expect(page.getByText('Categoría de activo fijo validada').first()).toBeVisible()
})
