/**
 * Contabilidad (fase 3, núcleo) de punta a punta: plan de cuentas propuesto, ejercicio, asientos
 * manuales (desbalanceado, contabilizado, revertido), asientos propuestos desde finanzas (con cuentas
 * contables configuradas en el momento y en moneda extranjera), libros y balances, cierre de un
 * período y permisos (el Administrador prepara pero no contabiliza; Consulta solo lee).
 *
 * Corre después de `finanzas.spec.ts` (misma base, en orden). Usa la empresa, el propietario, el
 * Contador y Consulta que crea `flujos.spec.ts`, y las cuentas «Banco E2E» y «Dólares E2E» que crea
 * `finanzas.spec.ts`. Crea un Administrador propio.
 */
import type { APIRequestContext, Page } from '@playwright/test'
import { API_URL } from './env.ts'
import { ACCOUNTANT, expect, OWNER, PASSWORD, signIn, signOut, test, VIEWER } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light' })

const ADMIN = { name: 'Administradora E2E', email: 'admin-conta@example.com' }

async function ownerToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/auth/login`, { data: { email: OWNER.email, password: PASSWORD } })
  expect(res.ok()).toBeTruthy()
  return (await res.json()).token
}

test.beforeAll(async ({ request }) => {
  const token = await ownerToken(request)
  const users = await (await request.get(`${API_URL}/users`, { headers: { Authorization: `Bearer ${token}` } })).json()
  if (!users.some((u: { email: string }) => u.email === ADMIN.email)) {
    const res = await request.post(`${API_URL}/users`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { email: ADMIN.email, full_name: ADMIN.name, password: PASSWORD, role: 'admin' },
    })
    expect(res.ok()).toBeTruthy()
  }
})

const menu = (page: Page) => page.getByRole('navigation', { name: 'Principal' })

async function open(page: Page, section: string, heading = section) {
  await menu(page).getByRole('link', { name: section, exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
}

/** Elige la cuenta de una línea escribiendo su código y confirmando con Enter. */
async function pickAccount(page: Page, line: number, code: string) {
  const box = page.getByRole('combobox', { name: `Cuenta de la línea ${line}` })
  await box.fill(code)
  await expect(page.getByRole('listbox', { name: 'Cuentas imputables' }).getByRole('option').first()).toContainText(code)
  await box.press('Enter')
  await expect(box).toHaveValue(new RegExp(`^${code.replaceAll('.', '\\.')} `))
}

const balanceBar = (page: Page) => page.getByRole('status', { name: 'Balance del asiento' })
const toast = (page: Page, text: string | RegExp) => expect(page.getByText(text).first()).toBeVisible()

test('plan de cuentas: se carga el propuesto y avisa que no está validado', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Plan de cuentas')
  await expect(page.getByText('Todavía no hay plan de cuentas')).toBeVisible()
  await expect(page.getByText(/RG N° 49\/2014/).first()).toBeVisible()
  await page.getByRole('button', { name: 'Cargar el plan propuesto' }).click()
  await toast(page, 'Plan propuesto cargado: 173 cuentas, sin validar.')

  // El estado del plan siempre a la vista.
  await expect(page.getByText('Plan de cuentas sin validar por un contador').first()).toBeVisible()
  await expect(page.getByText('173 cuentas, 122 imputables')).toBeVisible()

  // Búsqueda por código.
  await page.getByPlaceholder('Buscar por código o nombre').fill('1.01.01.04.01')
  await expect(page.getByRole('row').filter({ hasText: 'BANCO - CUENTA CORRIENTE GUARANÍES' })).toBeVisible()
  await page.getByPlaceholder('Buscar por código o nombre').fill('')

  // Cuenta de resultados del ejercicio (para la refundición).
  await page.getByLabel('Cuenta de resultados del ejercicio').selectOption({ label: '3.03.02 RESULTADO DEL EJERCICIO' })
  await page.getByRole('button', { name: 'Guardar' }).click()
  await toast(page, 'Cuenta de resultados del ejercicio guardada.')

  // Otras pantallas de contabilidad también avisan.
  await open(page, 'Asientos')
  await expect(page.getByRole('note', { name: 'Estado del plan de cuentas' })).toContainText('sin validar')
})

test('ejercicio 2026: se crea con sus 12 períodos mensuales', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Ejercicios y períodos')
  // Sin ejercicios, la pantalla invita a crear el del año en curso; se elige 2026 explícitamente.
  await expect(page.getByText('Todavía no hay ejercicios')).toBeVisible()
  await page.getByRole('button', { name: /Crear el ejercicio \d{4}/ }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Año' }).fill('2026')
  await dialog.getByRole('button', { name: 'Crear ejercicio' }).click()
  await toast(page, 'Ejercicio 2026 creado con 12 períodos mensuales.')
  await expect(page.getByRole('button', { name: 'Cerrar Enero' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cerrar Diciembre' })).toBeVisible()
})

test.describe('con errores esperados de la API', () => {
  test.use({ expectedConsoleErrors: /status of (409|422)/ })

  test('asiento manual: desbalanceado no se contabiliza; balanceado recibe el N° 1; después se revierte', async ({ page }) => {
    test.slow()
    await signIn(page, ACCOUNTANT.email, PASSWORD)
    await open(page, 'Asientos')
    await page.getByRole('link', { name: 'Nuevo asiento' }).first().click()
    await expect(page.getByRole('heading', { level: 1, name: 'Nuevo asiento' })).toBeVisible()

    await page.getByLabel('Fecha', { exact: true }).fill('2026-03-10')
    await page.getByLabel('Descripción', { exact: true }).fill('Aporte de capital e2e')
    await page.getByLabel('Comprobante', { exact: true }).fill('Acta 1')
    await pickAccount(page, 1, '1.01.01.04.01')
    await page.getByLabel('Debe de la línea 1', { exact: true }).fill('5.000.000')
    await pickAccount(page, 2, '3.01.01.01')
    await page.getByLabel('Haber de la línea 2', { exact: true }).fill('4.000.000')

    // Desbalanceado: se ve la diferencia y no se puede contabilizar.
    await expect(page.getByTestId('diferencia')).toHaveText(/1\.000\.000/)
    await expect(balanceBar(page)).toContainText('Sobra debe')
    await expect(page.getByRole('button', { name: 'Contabilizar' })).toBeDisabled()

    // Se corrige y se contabiliza.
    await page.getByLabel('Haber de la línea 2', { exact: true }).fill('5.000.000')
    await expect(balanceBar(page)).toContainText(/Balancea: el debe y el haber suman ₲\s?5\.000\.000/)
    await page.getByRole('button', { name: 'Contabilizar' }).click()
    await toast(page, 'Asiento N° 1 contabilizado.')
    await expect(page.getByRole('heading', { level: 1, name: 'Asiento N° 1' })).toBeVisible()
    await expect(page.getByText('Contabilizado', { exact: true }).first()).toBeVisible()

    // Reversión con motivo: genera el N° 2 y el N° 1 queda revertido.
    await page.getByRole('button', { name: 'Revertir' }).first().click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Motivo de la reversión').fill('Se cargó a la cuenta equivocada')
    await dialog.getByRole('button', { name: 'Revertir el asiento N° 1' }).click()
    await toast(page, 'Reversión contabilizada: asiento N° 2. El N° 1 quedó revertido.')
    await expect(page.getByRole('heading', { level: 1, name: 'Asiento N° 2' })).toBeVisible()
    await page.getByRole('link', { name: 'Revierte el asiento N° 1' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Asiento N° 1' })).toBeVisible()
    await expect(page.getByText('Revertido', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'Revertido por el asiento N° 2' })).toBeVisible()
  })

  test('desde finanzas: se configuran las cuentas contables al proponer, se contabiliza y el movimiento ya no se anula', async ({ page }) => {
    test.slow()
    await signIn(page, ACCOUNTANT.email, PASSWORD)
    await menu(page).getByRole('link', { name: 'Categorías', exact: true }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Categorías' })).toBeVisible()
    // finanzas.spec.ts no crea categorías en la empresa: se crean las sugeridas.
    await page.getByRole('button', { name: 'Crear categorías sugeridas' }).click()
    await toast(page, /Se crearon \d+ categorías sugeridas/)

    await menu(page).getByRole('link', { name: 'Movimientos', exact: true }).click()
    await page.getByRole('button', { name: 'Nuevo movimiento' }).click()
    let dialog = page.getByRole('dialog')
    await dialog.locator('label').filter({ hasText: 'Entra' }).click()
    await dialog.getByLabel('Cuenta', { exact: true }).selectOption({ label: 'Banco E2E (PYG)' })
    await dialog.getByLabel('Importe').fill('2.200.000')
    await dialog.getByLabel('Fecha', { exact: true }).fill('2026-03-15')
    await dialog.getByLabel('Descripción', { exact: true }).fill('Cobro servicio contable e2e')
    await dialog.getByLabel('Categoría').selectOption({ label: 'Ventas' })
    await dialog.getByRole('button', { name: 'Cargar movimiento' }).click()
    await toast(page, /Movimiento de \+₲\s?2\.200\.000 cargado/)

    // Un movimiento personal nunca ofrece «Proponer asiento»; uno de la empresa, sí.
    await page.getByRole('button', { name: 'Proponer asiento: Cobro servicio contable e2e' }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Proponer asiento' }).click()
    await expect(dialog.getByText('Falta configurar las cuentas contables')).toBeVisible()
    await dialog.getByLabel('Cuenta contable de la cuenta «Banco E2E»').selectOption({ label: '1.01.01.04.01 BANCO - CUENTA CORRIENTE GUARANÍES' })
    await dialog.getByLabel('Cuenta contable de la categoría «Ventas»').selectOption({ label: '4.09 VENTAS DE SERVICIOS GRAVADOS' })
    await dialog.getByRole('button', { name: 'Guardar y proponer' }).click()
    await toast(page, 'Borrador de asiento creado. Revisalo y contabilizalo cuando esté bien.')
    await expect(page.getByRole('heading', { level: 1, name: 'Borrador de asiento' })).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Cuenta de la línea 1' })).toHaveValue(/^1\.01\.01\.04\.01 /)
    await expect(page.getByRole('combobox', { name: 'Cuenta de la línea 2' })).toHaveValue(/^4\.09 /)
    await expect(balanceBar(page)).toContainText(/₲\s?2\.200\.000/)
    await page.getByRole('button', { name: 'Contabilizar' }).click()
    await toast(page, 'Asiento N° 3 contabilizado.')
    await expect(page.getByRole('link', { name: 'Movimiento de finanzas de origen' })).toBeVisible()

    // De vuelta en el movimiento: muestra el asiento y no se puede anular hasta revertirlo.
    await page.getByRole('link', { name: 'Movimiento de finanzas de origen' }).click()
    dialog = page.getByRole('dialog', { name: 'Movimiento' })
    await expect(dialog.getByText('Cobro servicio contable e2e')).toBeVisible()
    await expect(dialog.getByRole('link', { name: 'Asiento N° 3' })).toBeVisible()
    await dialog.getByRole('button', { name: 'Anular' }).click()
    dialog = page.getByRole('dialog', { name: 'Anular movimiento' })
    await expect(dialog.getByText('Tiene el asiento N° 3 contabilizado')).toBeVisible()
    await expect(dialog.getByRole('link', { name: 'Ir al asiento N° 3' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Anular movimiento' })).toBeDisabled()
    await dialog.getByRole('button', { name: 'Cancelar' }).click()

    // La cuenta quedó configurada y se ve en Cuentas.
    await menu(page).getByRole('link', { name: 'Cuentas', exact: true }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Cuentas' })).toBeVisible()
    await expect(page.getByRole('row').filter({ has: page.getByText('Banco E2E', { exact: true }) })).toContainText('1.01.01.04.01')
  })

  test('desde finanzas en dólares: pide la cotización y deja elegir el redondeo', async ({ page }) => {
    await signIn(page, OWNER.email, PASSWORD)
    await menu(page).getByRole('link', { name: 'Movimientos', exact: true }).click()
    await page.getByRole('button', { name: 'Nuevo movimiento' }).click()
    let dialog = page.getByRole('dialog')
    await dialog.locator('label').filter({ hasText: 'Entra' }).click()
    await dialog.getByLabel('Cuenta', { exact: true }).selectOption({ label: 'Dólares E2E (USD)' })
    await dialog.getByLabel('Importe').fill('120,35')
    await dialog.getByLabel('Fecha', { exact: true }).fill('2026-03-20')
    await dialog.getByLabel('Descripción', { exact: true }).fill('Servicio al exterior contable e2e')
    await dialog.getByLabel('Categoría').selectOption({ label: 'Ventas' })
    await dialog.getByRole('button', { name: 'Cargar movimiento' }).click()
    await toast(page, /Movimiento de \+US\$\s?120,35 cargado/)

    await page.getByRole('button', { name: 'Proponer asiento: Servicio al exterior contable e2e' }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('Cotización: guaraníes por 1 USD').fill('7300,25')
    await dialog.getByRole('button', { name: 'Proponer asiento' }).click()
    // Falta la cuenta contable de la cuenta en dólares (la categoría ya la tiene).
    await expect(dialog.getByText('Falta configurar una cuenta contable')).toBeVisible()
    await dialog.getByLabel('Cuenta contable de la cuenta «Dólares E2E»').selectOption({ label: '1.01.01.04.03 BANCO - CUENTA EN DÓLARES' })
    await dialog.getByRole('button', { name: 'Guardar y proponer' }).click()
    // 120,35 × 7.300,25 = 878.585,0875: no es entero, se elige el redondeo.
    await expect(dialog.getByText('El importe en guaraníes no es entero')).toBeVisible()
    await expect(dialog.getByText(/878\.585,0875/)).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Proponer asiento' })).toBeDisabled()
    await dialog.getByLabel(/Hacia abajo/).check()
    await dialog.getByRole('button', { name: 'Proponer asiento' }).click()
    await toast(page, 'Borrador de asiento creado. Revisalo y contabilizalo cuando esté bien.')
    await expect(balanceBar(page)).toContainText(/₲\s?878\.585/)
    // Queda en borrador: lo usa la prueba del cierre del período.
  })

  test('libros y balances: diario, mayor, comprobación, balance general y resultados cuadran', async ({ page }) => {
    await signIn(page, VIEWER.email, PASSWORD)
    await open(page, 'Libros y balances')
    const sheet = page.locator('main')

    // Libro diario: N° 1, su reversión N° 2 y el N° 3 (el borrador no cuenta).
    await page.getByLabel('Desde', { exact: true }).fill('2026-01-01')
    await page.getByLabel('Hasta', { exact: true }).fill('2026-12-31')
    await expect(sheet.getByText('Asiento N° 1', { exact: true })).toBeVisible()
    await expect(sheet.getByText('Asiento N° 3', { exact: true })).toBeVisible()
    await expect(sheet.getByText('Servicio al exterior contable e2e')).toHaveCount(0)
    const journalTotals = page.getByRole('row').filter({ hasText: 'Totales del período' })
    await expect(journalTotals).toContainText('12.200.000')
    await expect(sheet.getByText('Plan de cuentas sin validar por un contador').first()).toBeVisible()

    // Libro mayor del banco: saldo final 2.200.000 deudor.
    await page.getByRole('navigation', { name: 'Reportes contables' }).getByRole('link', { name: 'Libro mayor' }).click()
    const account = page.getByRole('combobox', { name: 'Cuenta' })
    await account.fill('1.01.01.04.01')
    await account.press('Enter')
    const ledgerTotals = page.getByRole('row').filter({ hasText: 'Totales y saldo final' })
    await expect(ledgerTotals).toContainText('7.200.000')
    await expect(ledgerTotals).toContainText('5.000.000')
    await expect(ledgerTotals).toContainText('2.200.000')

    // Balance de comprobación: sumas iguales.
    await page.getByRole('navigation', { name: 'Reportes contables' }).getByRole('link', { name: 'Balance de comprobación' }).click()
    const trialTotals = page.getByRole('row').filter({ hasText: 'Totales' }).last()
    await expect(trialTotals).toContainText('cuadran')
    await expect(trialTotals).toContainText('12.200.000')

    // Balance general: activo 2.200.000 = pasivo 0 + patrimonio 0 + resultado 2.200.000.
    await page.getByRole('navigation', { name: 'Reportes contables' }).getByRole('link', { name: 'Balance general' }).click()
    await page.getByLabel('Al', { exact: true }).fill('2026-12-31')
    await expect(sheet.getByText(/Cuadra: activo = pasivo \+ patrimonio \+ resultado = ₲\s?2\.200\.000/)).toBeVisible()

    // Estado de resultados: ganancia 2.200.000.
    await page.getByRole('navigation', { name: 'Reportes contables' }).getByRole('link', { name: 'Estado de resultados' }).click()
    await expect(sheet.getByText('4.09')).toBeVisible()
    const outcome = sheet.getByRole('term').filter({ hasText: 'Ganancia del período' })
    await expect(outcome).toBeVisible()
    await expect(sheet.getByRole('definition').last()).toContainText('2.200.000')
  })

  test('cierre de período: no cierra con borradores; cerrado no recibe asientos; se reabre con motivo', async ({ page }) => {
    test.slow()
    await signIn(page, ACCOUNTANT.email, PASSWORD)
    await open(page, 'Ejercicios y períodos')
    await page.getByRole('button', { name: 'Cerrar Marzo' }).click()
    let dialog = page.getByRole('dialog', { name: 'El período tiene borradores' })
    await expect(dialog.getByRole('link', { name: /Servicio al exterior contable e2e/ })).toBeVisible()

    // Se descarta el borrador (con motivo) y se cierra marzo.
    await dialog.getByRole('link', { name: /Servicio al exterior contable e2e/ }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Borrador de asiento' })).toBeVisible()
    await page.getByRole('button', { name: 'Descartar borrador' }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('Motivo', { exact: true }).fill('Se carga el mes que viene con la cotización correcta')
    await dialog.getByRole('button', { name: 'Descartar borrador' }).click()
    await toast(page, 'Borrador descartado. Queda en el listado como descartado, con tu motivo.')

    await open(page, 'Ejercicios y períodos')
    await page.getByRole('button', { name: 'Cerrar Marzo' }).click()
    await toast(page, 'Marzo cerrado: ya no se contabiliza con fecha en ese mes.')
    await expect(page.getByRole('button', { name: 'Reabrir Marzo' })).toBeVisible()

    // Un asiento con fecha en marzo ya no se contabiliza.
    await open(page, 'Asientos')
    await page.getByRole('link', { name: 'Nuevo asiento' }).first().click()
    await page.getByLabel('Fecha', { exact: true }).fill('2026-03-25')
    await page.getByLabel('Descripción', { exact: true }).fill('Ajuste de marzo e2e')
    await pickAccount(page, 1, '11.05')
    await page.getByLabel('Debe de la línea 1', { exact: true }).fill('300.000')
    await pickAccount(page, 2, '1.01.01.04.01')
    await page.getByLabel('Haber de la línea 2', { exact: true }).fill('300.000')
    await expect(balanceBar(page)).toContainText('Balancea')
    await expect(page.getByRole('button', { name: 'Contabilizar' })).toBeDisabled()
    await expect(page.getByText('Marzo está cerrado: no se contabiliza con fecha en ese mes.')).toBeVisible()
    await page.getByRole('button', { name: 'Guardar borrador' }).click()
    await toast(page, 'Borrador creado. Todavía no está en los libros: falta contabilizarlo.')

    // Se reabre con motivo y el borrador se puede contabilizar.
    await open(page, 'Ejercicios y períodos')
    await page.getByRole('button', { name: 'Reabrir Marzo' }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('Motivo de la reapertura').fill('Falta el ajuste de alquiler')
    await dialog.getByRole('button', { name: 'Reabrir período' }).click()
    await toast(page, 'Marzo reabierto.')
    await open(page, 'Asientos')
    await page.getByRole('link', { name: 'Ajuste de marzo e2e' }).click()
    await page.getByRole('button', { name: 'Contabilizar' }).click()
    await toast(page, 'Asiento N° 4 contabilizado.')
  })
})

test('permisos: el Administrador prepara borradores pero no contabiliza ni valida; Consulta solo lee', async ({ page }) => {
  await signIn(page, ADMIN.email, PASSWORD)
  await open(page, 'Asientos')
  await page.getByRole('link', { name: 'Nuevo asiento' }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: 'Nuevo asiento' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Guardar borrador' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Contabilizar' })).toHaveCount(0)
  await expect(page.getByText(/Tu rol \(Administrador\) prepara el plan y los borradores/)).toBeVisible()
  await open(page, 'Plan de cuentas')
  await expect(page.getByRole('button', { name: 'Marcar como validado' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Cuenta de primer nivel' })).toBeVisible()
  await signOut(page)

  await signIn(page, VIEWER.email, PASSWORD)
  await open(page, 'Asientos')
  await expect(page.getByRole('link', { name: 'Nuevo asiento' })).toHaveCount(0)
  await page.getByRole('link', { name: 'Aporte de capital e2e' }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: /Asiento N° \d/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Revertir' })).toHaveCount(0)
})

test('validación del plan: el contador lo marca como validado con nombre y matrícula', async ({ page }) => {
  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await open(page, 'Plan de cuentas')
  await page.getByRole('button', { name: 'Marcar como validado' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Nombre del contador').fill('Contadora Externa')
  await dialog.getByLabel('Matrícula profesional').fill('MAT-1234')
  await dialog.getByRole('button', { name: 'Marcar como validado' }).click()
  await toast(page, 'Plan de cuentas marcado como validado.')
  await expect(page.getByRole('heading', { name: 'Plan de cuentas validado' })).toBeVisible()
  await expect(page.getByText(/Lo validó Contadora Externa, matrícula MAT-1234/)).toBeVisible()
  await open(page, 'Libros y balances')
  await expect(page.getByText('Plan de cuentas sin validar por un contador')).toHaveCount(0)
})
