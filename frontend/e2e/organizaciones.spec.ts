/**
 * Varias organizaciones (M3): el propietario da de alta una segunda, pasa a ella, no ve nada de la
 * primera, vuelve y lo ve de nuevo; al ingresar con dos organizaciones elige en cuál trabajar.
 *
 * Corre al final de la cadena (misma base): la primera organización ya tiene RUC 44444401-7 y usuarios.
 */
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


