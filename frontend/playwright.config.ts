import { defineConfig, devices } from '@playwright/test'
import { API_PORT, API_URL, BACKEND_DIR, BACKEND_PYTHON, DATABASE_URL, WEB_PORT, WEB_URL } from './e2e/env.ts'

export default defineConfig({
  testDir: './e2e',
  // Los flujos comparten una sola base (empresa, propietario, usuarios) y van en orden.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: WEB_URL,
    locale: 'es-PY',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // Orden explícito: los flujos de finanzas parten de la empresa y los usuarios que crea flujos.spec.ts
  // (por orden alfabético, finanzas.spec.ts correría primero).
  projects: [
    { name: 'chromium', testMatch: 'flujos.spec.ts', use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 } } },
    {
      name: 'finanzas',
      testMatch: 'finanzas.spec.ts',
      dependencies: ['chromium'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 } },
    },
    {
      // La contabilidad parte de las cuentas de la empresa que deja finanzas.spec.ts.
      name: 'contabilidad',
      testMatch: 'contabilidad.spec.ts',
      dependencies: ['finanzas'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 } },
    },
    {
      // La fase 3B parte del plan validado, del 2025 cerrado y de los asientos de contabilidad.spec.ts.
      name: 'contabilidad-3b',
      testMatch: 'contabilidad-3b.spec.ts',
      dependencies: ['contabilidad'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 }, acceptDownloads: true },
    },
    {
      // La tributación parte del RUC de la empresa y del plan validado de las anteriores.
      name: 'tributacion',
      testMatch: 'tributacion.spec.ts',
      dependencies: ['contabilidad-3b'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 }, acceptDownloads: true },
    },
  ],
  webServer: [
    {
      // Base vacía + migraciones + API (uvicorn) con el venv del backend.
      command: `node e2e/reset-db.ts && ${BACKEND_PYTHON} -m app`,
      url: `${API_URL}/system/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        CONTADOR_ENV: 'test',
        CONTADOR_DATABASE_URL: DATABASE_URL,
        CONTADOR_API_HOST: '127.0.0.1',
        CONTADOR_API_PORT: String(API_PORT),
        CONTADOR_CORS_ORIGINS: WEB_URL,
        CONTADOR_LOG_LEVEL: 'WARNING',
        PYTHONPATH: BACKEND_DIR,
      },
    },
    {
      // Build de producción servido con `vite preview`, apuntando a la API E2E.
      command: `npm run build && npx vite preview --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: WEB_URL,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { VITE_API_URL: API_URL },
    },
  ],
})
