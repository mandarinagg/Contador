import { expect, test as base, type Page } from '@playwright/test'

/**
 * `test` con una red de seguridad: cualquier `console.error` o error no capturado del navegador
 * hace fallar la prueba. Si un flujo provoca un error de consola esperado (p. ej. un 401 al ingresar
 * con contraseña incorrecta), la prueba lo declara con `test.use({ expectedConsoleErrors: /.../ })`.
 */
export const test = base.extend<{ expectedConsoleErrors: RegExp | null; consoleGuard: void }>({
  expectedConsoleErrors: [null, { option: true }],
  consoleGuard: [
    async ({ page, expectedConsoleErrors }, use) => {
      const problems: string[] = []
      page.on('console', (msg) => {
        if (msg.type() !== 'error') return
        if (expectedConsoleErrors?.test(msg.text())) return
        problems.push(`console.error: ${msg.text()}`)
      })
      page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`))
      await use()
      expect(problems, 'La consola del navegador debe quedar sin errores').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }

export const PASSWORD = 'Clave-Segura-2026'

export const OWNER = { name: 'Persona Prueba', email: 'e2e@example.com' }
export const ACCOUNTANT = { name: 'Contadora Externa', email: 'contadora@example.com' }
export const VIEWER = { name: 'Auditor Consulta', email: 'consulta@example.com' }

export async function signIn(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Contraseña').fill(password)
  await page.getByRole('button', { name: 'Ingresar' }).click()
}

export async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await expect(page).toHaveURL(/\/login$/)
}
