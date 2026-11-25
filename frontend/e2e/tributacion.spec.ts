/**
 * Tributación, fase 4, de punta a punta: avisos sin perfil, carga de las reglas y los feriados
 * candidatos, perfil fiscal declarado con el asistente, calendario generado, carga de una compra
 * y una venta, IVA del mes (estimación, copia a la obligación y borrador del F120), configuración,
 * verificación de CONTADOR AI (una regla, las demás en bloque y el perfil; D-120) y los límites del rol de consulta.
 *
 * Corre después de `contabilidad-3b.spec.ts` (misma base): la empresa tiene RUC 44444401-7 y el
 * plan propuesto validado. «Hoy» es la fecha del servidor; los comprobantes van en el mes anterior.
 */
import type { Page } from '@playwright/test'
import { expect, OWNER, PASSWORD, signIn, signOut, test, VIEWER } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light' })

const menu = (page: Page) => page.getByRole('navigation', { name: 'Principal' })
const toast = (page: Page, text: string | RegExp) => expect(page.getByText(text).first()).toBeVisible()

/** `section` como RegExp cuando el enlace lleva una marca (la cantidad de avisos entra en su nombre accesible). */
async function open(page: Page, section: string | RegExp, heading = String(section)) {
  await menu(page).getByRole('link', typeof section === 'string' ? { name: section, exact: true } : { name: section }).click()
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
}

function previousMonth(): { month: string; day: string } {
  const now = new Date()
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth() - 1, 15))
  const month = d.toISOString().slice(0, 7)
  return { month, day: `${month}-15` }
}
const { month: PREV_MONTH, day: VOUCHER_DAY } = previousMonth()
const YEAR = new Date().getFullYear()

test('sin perfil fiscal, el resumen lo avisa', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, /^Resumen fiscal/, 'Resumen fiscal')
  await expect(page.getByText('Falta el perfil fiscal').first()).toBeVisible()
})

test('reglas y feriados candidatos: se cargan sin verificar', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Reglas y feriados')
  await expect(page.getByText('Todavía no hay reglas cargadas')).toBeVisible()
  await page.getByRole('button', { name: 'Cargar reglas candidatas' }).click()
  await toast(page, /Reglas candidatas: \d+ reglas nuevas/)
  await expect(page.getByTestId('rule-IVA-GENERAL-TASAS')).toContainText('Sin verificar')
  await expect(page.getByText(/reglas en uso están sin verificar/)).toBeVisible()

  // Cargar otra vez no duplica nada.
  await page.getByRole('button', { name: 'Cargar reglas candidatas' }).click()
  await toast(page, /Reglas candidatas: 0 reglas nuevas/)

  await page.getByRole('tab', { name: 'Feriados' }).click()
  await page.getByRole('button', { name: 'Cargar feriados candidatos' }).click()
  await toast(page, /Feriados: \d+ nuevos/)
  await expect(page.getByTestId(`holiday-${YEAR}-12-25`)).toContainText('Sin verificar')

  // Un feriado a mano necesita su fuente.
  await page.getByRole('button', { name: 'Agregar feriado' }).click()
  const dialog = page.getByRole('dialog', { name: 'Agregar feriado' })
  await dialog.getByLabel('Día').fill(`${YEAR}-11-30`)
  await dialog.getByLabel('Nombre').fill('Asueto de prueba')
  await dialog.getByRole('button', { name: 'Guardar' }).click()
  await expect(dialog.getByText('Indicá la norma o el enlace a la fuente')).toBeVisible()
  await dialog.getByLabel('Norma').fill('Decreto de prueba N° 1')
  await dialog.getByRole('button', { name: 'Guardar' }).click()
  await toast(page, 'Feriado agregado: queda sin verificar.')
  await expect(page.getByTestId(`holiday-${YEAR}-11-30`)).toContainText('Asueto de prueba')

  // Y se puede eliminar.
  await page.getByRole('button', { name: 'Eliminar Asueto de prueba' }).click()
  await page.getByRole('dialog', { name: 'Eliminar feriado' }).getByRole('button', { name: 'Eliminar' }).click()
  await toast(page, 'Feriado eliminado.')
  await expect(page.getByTestId(`holiday-${YEAR}-11-30`)).toBeHidden()
})

test('perfil fiscal declarado con el asistente', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Perfil fiscal')
  await page.getByRole('button', { name: 'Empezar' }).click()
  await page.getByLabel('Rige desde').fill(`${YEAR}-01-01`)
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByText('IRE General', { exact: true }).click()
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('button', { name: 'Siguiente' }).click() // cierre en diciembre
  await page.getByText('Sí, es contribuyente del IVA').click()
  await page.getByRole('button', { name: 'Siguiente' }).click()
  for (const code of ['211', '955', '700']) {
    await page.getByRole('checkbox', { name: new RegExp(`^${code} — `) }).check()
    await page.getByLabel(`Fecha de alta de la ${code}`).fill(`${YEAR}-01-01`)
  }
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('button', { name: 'Guardar el perfil' }).click()
  await expect(page.getByText('Declarado, sin verificar contra la constancia de RUC').first()).toBeVisible()
})

test('el calendario genera las obligaciones del perfil', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Calendario')
  await expect(page.getByText('IVA General (Formulario 120)').filter({ visible: true }).first()).toBeVisible()
  await expect(page.getByText('Registro de comprobantes (RG 90)').filter({ visible: true }).first()).toBeVisible()
})

test('carga de una compra y una venta, y el registro del mes', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await expect(menu(page)).toBeVisible() // el token se guarda al terminar de ingresar
  await page.goto(`/impuestos/comprobantes/cargar?mes=${PREV_MONTH}`)
  await expect(page.getByRole('heading', { level: 1, name: 'Cargar comprobantes' })).toBeVisible()

  // Compra: 550.000 con IVA 10 % incluido → IVA 50.000.
  await page.getByRole('radiogroup', { name: 'Compra o venta' }).getByText('Compra').click()
  await page.getByLabel('Fecha').fill(VOUCHER_DAY)
  await page.getByLabel('RUC del proveedor').fill('80012345')
  await page.getByLabel('DV').fill('0')
  await page.getByLabel('Razón social del proveedor').fill('Proveedora de Prueba S.A.')
  await page.getByLabel('Timbrado').fill('12345678')
  await page.getByLabel('Número', { exact: true }).fill('1-1-145')
  await page.getByLabel('Gravado 10 %').fill('550000')
  await page.getByRole('button', { name: 'Guardar y seguir' }).click()
  await toast(page, /Factura 001-001-0000145 cargada/)

  // Venta: 1.100.000 con IVA 10 % incluido → IVA 100.000.
  await page.getByRole('radiogroup', { name: 'Compra o venta' }).getByText('Venta').click()
  await page.getByLabel('Fecha').fill(VOUCHER_DAY)
  await page.getByLabel('RUC del cliente').fill('80099001')
  await page.getByLabel('DV').fill('3')
  await page.getByLabel('Nombre o razón social').fill('Cliente de Prueba S.R.L.')
  await page.getByLabel('Timbrado').fill('87654321')
  await page.getByLabel('Número', { exact: true }).fill('1-1-1')
  await page.getByLabel('Gravado 10 %').fill('1100000')
  await page.getByRole('button', { name: 'Guardar y seguir' }).click()
  await toast(page, /Factura 001-001-0000001 cargada/)

  await page.goto(`/impuestos/comprobantes?mes=${PREV_MONTH}`)
  await expect(page.getByText('Proveedora de Prueba S.A.')).toBeVisible()
  await expect(page.getByText('Cliente de Prueba S.R.L.')).toBeVisible()
})

test('IVA del mes: estimación, copia a la obligación y borrador del F120', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await expect(menu(page)).toBeVisible() // el token se guarda al terminar de ingresar
  await page.goto(`/impuestos/iva?mes=${PREV_MONTH}`)
  await expect(page.getByRole('heading', { level: 1, name: 'IVA del mes' })).toBeVisible()
  await expect(page.getByRole('note', { name: 'Estimación interna' })).toBeVisible()
  await expect(page.getByTestId('vat-to-pay')).toHaveText('50.000')
  await expect(page.getByTestId('vat-credit-balance')).toHaveText('0')
  await expect(page.getByText('Sin verificar').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: /Borrador del Formulario 120/ })).toBeVisible()

  await page.getByRole('button', { name: 'Copiar a la obligación' }).click()
  await toast(page, 'Estimación copiada a la obligación del IVA del mes.')
})

test('configuración: días de aviso', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Configuración', 'Configuración de impuestos')
  await expect(page.getByText(/En uso: 1\.01\.03\.05\.03\.01/)).toBeVisible()
  const days = page.getByLabel('Días de anticipación')
  await days.fill('90')
  await page.getByRole('button', { name: 'Guardar' }).click()
  await expect(page.getByText('Entre 1 y 60 días.')).toBeVisible()
  await days.fill('15')
  await page.getByRole('button', { name: 'Guardar' }).click()
  await toast(page, 'Configuración guardada.')
  await signOut(page)
})

test('CONTADOR AI verifica una regla, las demás con fuente oficial en bloque y el perfil (D-120)', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await open(page, 'Reglas y feriados')
  const rule = page.getByTestId('rule-IVA-GENERAL-TASAS')
  await rule.getByRole('button', { name: 'Verificar' }).click()
  const dialog = page.getByRole('dialog', { name: /Verificar IVA-GENERAL-TASAS/ })
  await expect(dialog.getByLabel('Matrícula profesional')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Verificar regla' }).click()
  await toast(page, 'Regla IVA-GENERAL-TASAS verificada.')
  await expect(rule).toContainText('Verificada por CONTADOR AI contra')

  // El clic único: verifica las que tienen la fuente oficial leída y lista las que no.
  await page.getByLabel('Solo las que usa la app').uncheck()
  await page.getByRole('button', { name: /^Verificar las \d+ con fuente oficial$/ }).click()
  await toast(page, /reglas verificadas; \d+ quedan sin verificar\./)
  await expect(page.getByText(/reglas quedaron sin verificar/)).toBeVisible()
  await expect(page.getByText(/CONTADOR AI no puede verificarla: La fuente oficial no se leyó/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Verificar con fuente oficial' })).toBeDisabled()

  await open(page, 'Perfil fiscal')
  await page.getByRole('button', { name: 'Verificar' }).first().click()
  const profile = page.getByRole('dialog', { name: 'Verificar el perfil fiscal' })
  await expect(profile.getByLabel('Matrícula profesional')).toHaveCount(0)
  await profile.getByRole('button', { name: 'Verificar perfil' }).click()
  await expect(profile.getByText('Indicá la referencia del documento.')).toBeVisible()
  await profile.getByLabel('Referencia de la constancia de RUC').fill('Constancia 2026-001')
  await profile.getByRole('button', { name: 'Verificar perfil' }).click()
  await toast(page, 'Perfil fiscal verificado.')
  await expect(page.getByText(/Verificado por CONTADOR AI contra la Constancia de RUC \(DNIT\): Constancia 2026-001/)).toBeVisible()
  await signOut(page)
})

test('el rol de consulta lee los impuestos pero no carga nada', async ({ page }) => {
  await signIn(page, VIEWER.email, PASSWORD)
  await open(page, 'Reglas y feriados')
  await expect(page.getByRole('button', { name: 'Cargar reglas candidatas' })).toBeDisabled()
  await expect(page.getByTestId('rule-IVA-GENERAL-TASAS').getByRole('button', { name: 'Verificar' })).toHaveCount(0)
  await page.goto('/impuestos/comprobantes/cargar')
  await expect(page.getByText('No podés cargar comprobantes')).toBeVisible()
  await page.goto(`/impuestos/iva?mes=${PREV_MONTH}`)
  await expect(page.getByTestId('vat-to-pay')).toHaveText('50.000')
  await expect(page.getByRole('button', { name: 'Copiar a la obligación' })).toBeDisabled()
})
