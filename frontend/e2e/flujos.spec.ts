/**
 * Flujos de punta a punta de CONTADOR AI: navegador real (Chromium) contra la API real y una base
 * PostgreSQL vacía que se recrea en cada corrida. Los flujos comparten esa base y van en orden:
 * cada uno parte de lo que dejó el anterior (empresa y propietario, luego usuarios, etc.).
 */
import { ACCOUNTANT, expect, OWNER, PASSWORD, signIn, signOut, test, VIEWER } from './fixtures.ts'

test.describe.configure({ mode: 'serial' })
test.use({ colorScheme: 'light' })

test('configuración inicial: crea la empresa y el propietario y lleva al inicio', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/configuracion-inicial$/)

  await page.getByLabel('Razón social').fill('Prueba E2E EAS')
  await page.getByLabel('Nombre y apellido').fill(OWNER.name)
  await page.getByLabel('Email').fill(OWNER.email)
  await page.getByLabel('Contraseña', { exact: true }).fill(PASSWORD)
  await page.getByLabel('Repetir contraseña').fill(PASSWORD)
  await page.getByRole('button', { name: 'Crear empresa y propietario' }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Hola, Persona' })).toBeVisible()
  await expect(page.getByText('Íntegra')).toBeVisible()

  // Con la empresa ya creada, la pantalla de configuración inicial deja de estar disponible.
  await page.goto('/configuracion-inicial')
  await expect(page).toHaveURL(/\/$/)
})

test('cierre de sesión y nuevo ingreso', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await expect(page.getByRole('heading', { name: 'Hola, Persona' })).toBeVisible()

  await signOut(page)
  await expect(page.getByRole('heading', { name: 'Ingresar' })).toBeVisible()

  // Sin sesión no se puede entrar a una sección interna.
  await page.goto('/usuarios')
  await expect(page).toHaveURL(/\/login$/)

  await signIn(page, OWNER.email, PASSWORD)
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Hola, Persona' })).toBeVisible()
})

test.describe('ingreso con credenciales incorrectas', () => {
  // El navegador registra el 401 de la API como error de carga de recurso: es lo esperado aquí.
  test.use({ expectedConsoleErrors: /status of 401/ })

  test('no revela si el email existe', async ({ page }) => {
    const message = 'Email o contraseña incorrectos.'

    await signIn(page, OWNER.email, 'Otra-Clave-Segura-99')
    await expect(page.getByText(message)).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)

    // Un email que no existe recibe exactamente el mismo mensaje.
    await signIn(page, 'no-existe@example.com', 'Otra-Clave-Segura-99')
    await expect(page.getByText(message)).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
  })
})

test('datos de la empresa: el dígito verificador del RUC se valida y se guarda', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await page.getByRole('link', { name: 'Datos de la empresa' }).click()

  await page.getByLabel('RUC', { exact: true }).fill('44444401')
  await page.getByLabel('Dígito verificador').fill('3')
  await expect(page.getByText('Para ese RUC el dígito verificador es 7.')).toBeVisible()

  await page.getByLabel('Dígito verificador').fill('7')
  await expect(page.getByText('Para ese RUC el dígito verificador es 7.')).toBeHidden()
  await page.getByRole('button', { name: 'Guardar cambios' }).click()
  await expect(page.getByText('Datos de la empresa guardados.')).toBeVisible()

  // Los datos quedan guardados: se ven al recargar.
  await page.reload()
  await expect(page.getByLabel('RUC', { exact: true })).toHaveValue('44444401')
  await expect(page.getByLabel('Dígito verificador')).toHaveValue('7')
})

test('alta de usuarios con rol Contador y Consulta', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await page.getByRole('link', { name: 'Usuarios y roles' }).click()

  for (const [user, role] of [
    [ACCOUNTANT, 'Contador'],
    [VIEWER, 'Consulta'],
  ] as const) {
    await page.getByRole('button', { name: 'Nuevo usuario' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Nombre y apellido').fill(user.name)
    await dialog.getByLabel('Email').fill(user.email)
    await dialog.getByLabel('Contraseña inicial').fill(PASSWORD)
    await dialog.getByLabel('Rol').selectOption({ label: role })
    await dialog.getByRole('button', { name: 'Crear usuario' }).click()

    await expect(page.getByText(`Usuario ${user.email} creado.`)).toBeVisible()
    await expect(page.getByRole('cell', { name: user.name })).toBeVisible()
    await expect(page.getByLabel(`Rol de ${user.name}`)).toHaveValue(role === 'Contador' ? 'accountant' : 'viewer')
  }
})

test('el rol Contador ingresa pero no gestiona usuarios ni edita la empresa', async ({ page }) => {
  await signIn(page, ACCOUNTANT.email, PASSWORD)
  await expect(page).toHaveURL(/\/$/)

  await page.getByRole('link', { name: 'Usuarios y roles' }).click()
  await expect(page.getByRole('button', { name: 'Nuevo usuario' })).toHaveCount(0)

  await page.getByRole('link', { name: 'Datos de la empresa' }).click()
  await expect(page.getByLabel('Razón social')).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Guardar cambios' })).toHaveCount(0)
})

test('el rol Consulta no ve la administración de usuarios', async ({ page }) => {
  await signIn(page, VIEWER.email, PASSWORD)
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Hola, Auditor' })).toBeVisible()

  const menu = page.getByRole('navigation', { name: 'Principal' })
  await expect(menu.getByRole('link', { name: 'Inicio' })).toBeVisible()
  await expect(menu.getByRole('link', { name: 'Usuarios y roles' })).toHaveCount(0)

  // Tampoco entra escribiendo la dirección a mano.
  await page.goto('/usuarios')
  await expect(page.getByText('Sin acceso')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Nuevo usuario' })).toHaveCount(0)
})

test('auditoría: muestra los cambios y la verificación de integridad da válida', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  await page.getByRole('link', { name: 'Auditoría' }).click()

  await expect(page.getByText('Cadena íntegra')).toBeVisible()
  await expect(page.getByText('Usuario creado').first()).toBeVisible()

  await page.getByRole('button', { name: 'Verificar integridad' }).click()
  await expect(page.getByText('Cadena íntegra')).toBeVisible()
  await expect(page.getByText('Cadena alterada')).toHaveCount(0)

  await page.getByRole('tab', { name: 'Seguridad' }).click()
  await expect(page.getByText('Configuración inicial').first()).toBeVisible()
})

test('tema claro y oscuro: se cambia desde Mi cuenta y se recuerda', async ({ page }) => {
  await signIn(page, OWNER.email, PASSWORD)
  const html = page.locator('html')
  await expect(html).toHaveAttribute('data-theme', 'light')

  await page.getByRole('link', { name: OWNER.name }).click()
  await page.getByRole('radio', { name: 'Oscuro' }).click()
  await expect(page.getByRole('radio', { name: 'Oscuro' })).toBeChecked()
  await expect(html).toHaveAttribute('data-theme', 'dark')

  // Persiste al recargar y al navegar a otra sección.
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('link', { name: 'Inicio' }).click()
  await expect(html).toHaveAttribute('data-theme', 'dark')

  await page.getByRole('link', { name: OWNER.name }).click()
  await page.getByRole('radio', { name: 'Claro' }).click()
  await expect(html).toHaveAttribute('data-theme', 'light')
})

test.describe('servicio local caído', () => {
  // Las llamadas abortadas aparecen en la consola del navegador: es lo esperado aquí.
  test.use({ expectedConsoleErrors: /Failed to load resource/ })

  test('la app avisa que está iniciando en lugar de fallar con errores', async ({ page }) => {
    await page.route('**/api/v1/**', (route) => route.abort('connectionrefused'))
    await page.goto('/')
    await expect(page.getByRole('status')).toHaveText('Iniciando Contador AI…')
  })
})
