/**
 * Impuestos → Marangatu (B1 del bot, D-127 a D-133), de punta a punta: la pantalla carga, se guarda
 * la clave (queda «guardada» y el campo vacío), se enciende (con confirmación) y se apaga el bot.
 * No se hace ningún reconocimiento: el E2E no lanza un navegador contra Marangatu.
 *
 * Corre después de `tributacion.spec.ts` (misma base): la empresa tiene RUC 44444401-7. La clave
 * va a un almacén de prueba en archivo (ver `playwright.config.ts`), no al del sistema.
 */
import { expect, OWNER, PASSWORD, signIn, test } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light' })

const SECRET = 'Clave-Marangatu-E2E-9'

test('la pantalla carga con el bot apagado y sin clave', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await page.getByRole('navigation', { name: 'Principal' }).getByRole('link', { name: 'Marangatu', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Marangatu' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Encender el bot' })).toBeVisible()
  await expect(page.getByTestId('password-status')).toContainText('No hay clave guardada')
  await expect(page.getByText('Todavía no hubo corridas')).toBeVisible()
})

test('guardar la clave: queda guardada y el campo vacío', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await expect(page.getByRole('navigation', { name: 'Principal' })).toBeVisible() // el token se guarda al terminar de ingresar
  await page.goto('/impuestos/marangatu')
  const field = page.getByLabel('Clave de Marangatu')
  await expect(field).toHaveAttribute('type', 'password')
  await field.fill(SECRET)
  await page.getByRole('button', { name: 'Guardar la clave' }).click()
  await expect(page.getByTestId('password-status')).toContainText('Clave guardada para el RUC')
  await expect(field).toHaveValue('')
  await expect(page.getByText(SECRET)).toHaveCount(0)
})

test('encender (con confirmación) y apagar el bot', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await expect(page.getByRole('navigation', { name: 'Principal' })).toBeVisible() // el token se guarda al terminar de ingresar
  await page.goto('/impuestos/marangatu')
  await page.getByRole('button', { name: 'Encender el bot' }).click()
  const dialog = page.getByRole('dialog', { name: 'Encender el bot' })
  await dialog.getByRole('button', { name: 'Sí, encender' }).click()
  await expect(page.getByRole('heading', { level: 2, name: /Bot encendido/ })).toBeVisible()
  await page.getByRole('button', { name: 'Apagar el bot' }).click()
  await expect(page.getByRole('heading', { level: 2, name: /Bot apagado/ })).toBeVisible()
})
