/**
 * Varias organizaciones (M3): el propietario da de alta una segunda, pasa a ella, no ve nada de la
 * primera, vuelve y lo ve de nuevo; al ingresar con dos organizaciones elige en cuál trabajar.
 *
 * Corre al final de la cadena (misma base): la primera organización ya tiene RUC 44444401-7 y usuarios.
 * La persona física (M4 a M7) carga su perfil con la 715, suma la 956 y registra ingresos y egresos.
 */
import { readFileSync } from 'node:fs'
import { inflateRawSync } from 'node:zlib'
import type { Page } from '@playwright/test'
import { ACCOUNTANT, expect, OWNER, PASSWORD, signIn, signOut, test, VIEWER } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light', expectedConsoleErrors: /status of (404|409)/ })

const SECOND = 'Segunda Organización SA'
let firstName = ''

/** Con dos organizaciones el ingreso pregunta en cuál trabajar. */
async function signInTo(page: Page, name: string) {
  await signIn(page, OWNER.email, PASSWORD)
  await page.getByRole('button', { name: new RegExp(name) }).click()
}

const orgButton = (page: Page) => page.getByRole('button', { name: /Cambiar de organización/ })

test('crear una segunda organización: el RUC repetido se rechaza y luego se pasa a ella', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await expect(page.getByRole('navigation', { name: 'Principal' })).toBeVisible()
  firstName = ((await orgButton(page).innerText()) || '').trim()
  expect(firstName).not.toBe('')

  await orgButton(page).click()
  await page.getByRole('menuitem', { name: 'Nueva organización' }).click()
  const dialog = page.getByRole('dialog', { name: 'Nueva organización' })
  await dialog.getByLabel('Razón social').fill(SECOND)
  await dialog.getByLabel('RUC', { exact: true }).fill('44444401')
  await dialog.getByLabel('Dígito verificador').fill('7')
  await dialog.getByRole('button', { name: 'Crear organización' }).click()
  await expect(dialog.getByText('Ya hay una organización con ese RUC')).toBeVisible()

  await dialog.getByLabel('RUC', { exact: true }).fill('')
  await dialog.getByLabel('Dígito verificador').fill('')
  await dialog.getByRole('button', { name: 'Crear organización' }).click()
  await dialog.getByRole('button', { name: `Pasar a ${SECOND}` }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(orgButton(page)).toContainText(SECOND)
})

test('en la segunda no se ve lo de la primera; se suma un usuario que ya existe', async ({ page }) => {
  await signInTo(page, SECOND)
  await expect(orgButton(page)).toContainText(SECOND)
  await page.goto('/usuarios')
  await expect(page.getByText(OWNER.email)).toBeVisible()
  await expect(page.getByText(ACCOUNTANT.email)).toHaveCount(0)

  await page.getByRole('button', { name: 'Sumar un usuario que ya existe' }).click()
  const dialog = page.getByRole('dialog', { name: 'Sumar un usuario que ya existe' })
  await dialog.getByLabel('Email del usuario').fill('nadie@example.com')
  await dialog.getByRole('button', { name: 'Sumar a la organización' }).click()
  await expect(dialog.getByText('No hay ningún usuario con ese email')).toBeVisible()
  await dialog.getByLabel('Email del usuario').fill(ACCOUNTANT.email)
  await dialog.getByRole('button', { name: 'Sumar a la organización' }).click()
  await expect(page.getByText(ACCOUNTANT.email, { exact: true })).toBeVisible()

  // Sumarlo otra vez es un error claro.
  await page.getByRole('button', { name: 'Sumar un usuario que ya existe' }).click()
  await dialog.getByLabel('Email del usuario').fill(ACCOUNTANT.email)
  await dialog.getByRole('button', { name: 'Sumar a la organización' }).click()
  await expect(dialog.getByText('Ese usuario ya es parte de esta organización')).toBeVisible()
})

test('volver a la primera muestra lo suyo; al ingresar se elige la organización', async ({ page }) => {
  await signInTo(page, SECOND)
  await expect(orgButton(page)).toContainText(SECOND)
  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: new RegExp(firstName) }).click()
  await expect(orgButton(page)).toContainText(firstName)
  await page.goto('/usuarios')
  await expect(page.getByText(VIEWER.email)).toBeVisible()

  // Al ingresar con dos organizaciones, aparece la pregunta; se puede cambiar de organización ahí.
  await signOut(page)
  await signIn(page, OWNER.email, PASSWORD)
  await expect(page.getByRole('heading', { name: '¿En qué organización querés trabajar?' })).toBeVisible()
  await page.getByRole('button', { name: new RegExp(SECOND) }).click()
  await expect(orgButton(page)).toContainText(SECOND)

  // Se deja la primera como la última usada para no alterar nada más.
  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: new RegExp(firstName) }).click()
  await expect(orgButton(page)).toContainText(firstName)
})



test('una persona física se da de alta con nombres y apellidos y aparece como «Apellidos, Nombres»', async ({ page }) => {
  await signInTo(page, firstName)
  await orgButton(page).click()
  await page.getByRole('menuitem', { name: 'Nueva organización' }).click()
  const dialog = page.getByRole('dialog', { name: 'Nueva organización' })
  await dialog.getByLabel('Persona física').check()
  await expect(dialog.getByLabel('Razón social')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Crear organización' }).click()
  await expect(dialog.getByText('Escribí los nombres.')).toBeVisible()
  await dialog.getByLabel('Nombres').fill('María José')
  await dialog.getByLabel('Apellidos').fill('Benítez Duarte')
  await dialog.getByRole('button', { name: 'Crear organización' }).click()
  await dialog.getByRole('button', { name: 'Pasar a Benítez Duarte, María José' }).click()
  await expect(orgButton(page)).toContainText('Benítez Duarte, María José')

  // Su contexto del negocio se llama «Actividad» y sus datos muestran nombres y apellidos.
  await page.goto('/finanzas')
  await expect(page.getByRole('navigation', { name: 'Contexto financiero' }).getByRole('link', { name: 'Actividad' })).toBeVisible()
  await page.goto('/empresa')
  await expect(page.getByLabel('Nombres')).toHaveValue('María José')
  await expect(page.getByLabel('Apellidos')).toHaveValue('Benítez Duarte')

  // Se deja la primera como la última usada para no alterar nada más.
  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: new RegExp(firstName) }).click()
  await expect(orgButton(page)).toContainText(firstName)
})

test('el perfil fiscal de la persona física con IRP-RSP genera su vencimiento en el Calendario (M6)', async ({ page }) => {
  const year = new Date().getFullYear()
  await signInTo(page, firstName)
  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: /Benítez Duarte, María José/ }).click()
  await expect(orgButton(page)).toContainText('Benítez Duarte, María José')

  // RUC = cédula 1234567 (DV 9), terminación 7: el IRP vence el día 21 de la DJ, en marzo.
  await page.goto('/empresa')
  await page.getByLabel('RUC (es tu cédula)').fill('1234567')
  await page.getByLabel('Dígito verificador').fill('9')
  await page.getByRole('button', { name: 'Guardar cambios' }).click()
  await expect(page.getByText('Datos de la organización guardados.')).toBeVisible()

  await page.goto('/impuestos/perfil')
  await page.getByRole('button', { name: 'Empezar' }).click()
  await page.getByLabel('Rige desde').fill(`${year - 1}-01-01`)
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('radio', { name: /^Sin IRE/ }).check()
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('button', { name: 'Siguiente' }).click() // cierre en diciembre
  await page.getByRole('radio', { name: /^No/ }).check()
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('checkbox', { name: /^715 — IRP-RSP/ }).check()
  await page.getByLabel('Fecha de alta de la 715').fill(`${year - 1}-01-01`)
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('button', { name: 'Guardar el perfil' }).click()
  await expect(page.getByText('La contabilidad es opcional')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Principal' }).getByText('· opcional')).toBeVisible()

  // Ejercicio del año pasado: vence en marzo de este año (sábado o domingo pasan al lunes).
  const due = new Date(Date.UTC(year, 2, 21))
  while (due.getUTCDay() === 0 || due.getUTCDay() === 6) due.setUTCDate(due.getUTCDate() + 1)
  const dueText = `${String(due.getUTCDate()).padStart(2, '0')}/03/${year}`
  await page.goto('/impuestos/calendario')
  const row = page.getByRole('listitem', { name: `IRP-RSP: declaración anual (Formulario 515), ejercicio ${year - 1}` })
  await expect(row).toContainText(`Vence el ${dueText}`)
  await expect(row).toContainText('obligación 715')

  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: new RegExp(firstName) }).click()
  await expect(orgButton(page)).toContainText(firstName)
})

/** El primer archivo de un ZIP (cabecera local, sin descriptor de datos, como lo escribe Python). */
function firstZipEntry(path: string): { name: string; text: string } {
  const zip = readFileSync(path)
  expect(zip.readUInt32LE(0)).toBe(0x04034b50)
  const method = zip.readUInt16LE(8)
  const size = zip.readUInt32LE(18)
  const nameLength = zip.readUInt16LE(26)
  const extraLength = zip.readUInt16LE(28)
  const name = zip.subarray(30, 30 + nameLength).toString('utf8')
  const data = zip.subarray(30 + nameLength + extraLength, 30 + nameLength + extraLength + size)
  return { name, text: (method === 8 ? inflateRawSync(data) : data).toString('utf8') }
}

test('la persona física con la 956 carga un ingreso y un egreso sin timbrado y descarga el registro anual (M7)', async ({ page }) => {
  const year = new Date().getFullYear()
  await signInTo(page, firstName)
  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: /Benítez Duarte, María José/ }).click()
  await expect(orgButton(page)).toContainText('Benítez Duarte, María José')

  // Desde enero suma el registro anual de comprobantes (956).
  await page.goto('/impuestos/perfil')
  await page.getByRole('button', { name: 'Cargar un cambio' }).click()
  await page.getByLabel('Rige desde').fill(`${year}-01-01`)
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('radio', { name: /^Sin IRE/ }).check()
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('button', { name: 'Siguiente' }).click() // cierre en diciembre
  await page.getByRole('radio', { name: /^No/ }).check()
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('checkbox', { name: /^956 — Registro anual/ }).check()
  await page.getByLabel('Fecha de alta de la 956').fill(`${year}-01-01`)
  await page.getByRole('button', { name: 'Siguiente' }).click()
  await page.getByRole('button', { name: 'Guardar el perfil' }).click()
  await expect(page.getByRole('button', { name: 'Cargar un cambio' })).toBeVisible()

  // Ingreso: honorarios cobrados con un recibo (210), a una persona con cédula.
  await page.goto(`/impuestos/comprobantes/cargar?mes=${year}-01`)
  const kind = page.getByRole('radiogroup', { name: 'Compra, venta, ingreso o egreso' })
  await kind.getByText('Ingreso').click()
  await page.getByLabel('Tipo', { exact: true }).selectOption('other_income')
  await page.getByLabel('Fecha').fill(`${year}-01-15`)
  await page.getByLabel('Número', { exact: true }).fill('R-15')
  await page.getByLabel('Identificación').selectOption('identity_card')
  await page.getByLabel('Número de documento').fill('2345678')
  await page.getByLabel('Nombre de quien paga').fill('Juan Pérez')
  await page.getByLabel('Tipo de documento').fill('Recibo de honorarios')
  await page.getByLabel('Monto gravado (IRP)').fill('300000')
  await page.getByLabel('Monto no gravado o exonerado').fill('50000')
  await expect(page.getByTestId('voucher-total')).toHaveText(/350\.000/)
  await page.getByRole('button', { name: 'Guardar y seguir' }).click()
  await expect(page.getByText(/Ingreso cargado: Otro comprobante de ingreso \(210\) R-15/).first()).toBeVisible()

  // Egreso sin número ni contraparte: el extracto de la tarjeta (207).
  await kind.getByText('Egreso').click()
  await page.getByLabel('Tipo', { exact: true }).selectOption('card_statement')
  await page.getByLabel('Fecha').fill(`${year}-01-20`)
  await expect(page.getByRole('checkbox', { name: /Sin identificación de la contraparte/ })).toBeChecked()
  await expect(page.getByLabel('Timbrado')).toHaveCount(0)
  await page.getByLabel('Nombre o descripción').fill('Gastos médicos')
  await page.getByLabel('Número de cuenta o de tarjeta').fill('4111-XXXX-1234')
  await page.getByLabel('Banco, financiera o cooperativa').fill('Banco Uno')
  await page.getByLabel('Monto total').fill('800000')
  await page.getByRole('button', { name: 'Guardar y seguir' }).click()
  await expect(page.getByText(/Egreso cargado: Extracto de tarjeta de crédito o débito \(207\) 20\/01/).first()).toBeVisible()

  // En la lista, por registro; y el archivo del año.
  await page.goto(`/impuestos/comprobantes?mes=${year}-01`)
  await expect(page.getByRole('rowheader', { name: 'Ingresos', exact: true })).toBeVisible()
  await expect(page.getByRole('rowheader', { name: 'Egresos', exact: true })).toBeVisible()
  await page.getByLabel('Dirección').selectOption('expense')
  await expect(page.getByText('Gastos médicos')).toBeVisible()
  await expect(page.getByText('Juan Pérez')).toHaveCount(0)
  await page.getByRole('button', { name: 'Descargar registro anual (956)' }).click()
  const dialog = page.getByRole('dialog', { name: 'Registro anual de comprobantes (956)' })
  await expect(dialog.getByLabel('Año')).toHaveValue(String(year))
  await expect(dialog.getByText(/comprobantes van en el archivo de/)).toContainText(`${year} (registro anual)`)
  const downloading = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Descargar el archivo' }).click()
  const file = await downloading
  expect(file.suggestedFilename()).toBe(`1234567_REG_${year}_00001.zip`)
  const entry = firstZipEntry(await file.path())
  expect(entry.name).toBe(`1234567_REG_${year}_00001.csv`)
  const lines = entry.text.split('\r\n')
  expect(lines.at(-1)).toBe('')
  expect(lines.slice(0, -1)).toEqual([
    `3;210;15/01/${year};R-15;12;2345678;Juan Pérez;300000;50000;350000;N;S;Recibo de honorarios;;`,
    `4;207;20/01/${year};;;;Gastos médicos;800000;N;N;S;N;4111-XXXX-1234;Banco Uno;;;;`,
  ])

  await page.keyboard.press('Escape')
  await orgButton(page).click()
  await page.getByRole('menuitemradio', { name: new RegExp(firstName) }).click()
  await expect(orgButton(page)).toContainText(firstName)
})
