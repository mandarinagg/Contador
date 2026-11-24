import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from 'react-router'
import { EmptyState, Skeleton } from '../components/ui'
import { ToastProvider } from '../components/ui/toast'
import { AppLayout } from '../layouts/AppLayout'
import { AccountPage } from '../modules/account/AccountPage'
import { AuditPage } from '../modules/audit/AuditPage'
import { LoginPage } from '../modules/auth/LoginPage'
import { SetupPage } from '../modules/auth/SetupPage'
import { HomePage } from '../modules/home/HomePage'
import { OrganizationPage } from '../modules/organization/OrganizationPage'
import { UsersPage } from '../modules/users/UsersPage'
import { ApiError, get } from '../services/api'
import { SessionProvider, useSession } from '../stores/session'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
})

/** Hasta 3 minutos: el lanzador espera lo mismo antes de declarar un error. */
const STARTUP_RETRIES = 180

function isStarting(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'NETWORK'
}

function FullPage({ children }: { children: ReactNode }) {
  return <div className="grid h-full place-items-center">{children}</div>
}

/** Decide a dónde ir según el estado: sin configurar → setup; sin sesión → login. */
function Gate({ need }: { need: 'setup' | 'anonymous' | 'session' }) {
  const setup = useQuery({
    queryKey: ['setup'],
    queryFn: () => get<{ needs_setup: boolean }>('/system/setup'),
    // En la app instalada la API tarda unos segundos en arrancar (más la primera vez,
    // cuando se crea la base): mientras no haya conexión, se sigue esperando.
    retry: (count, err) => (isStarting(err) ? count < STARTUP_RETRIES : count < 2),
    retryDelay: (count, err) => (isStarting(err) ? 1000 : Math.min(1000 * 2 ** count, 8000)),
  })
  const { me, loading } = useSession()

  if (setup.isPending || loading) {
    return (
      <FullPage>
        {setup.failureCount > 0 && isStarting(setup.failureReason) ? (
          <p role="status" className="text-sm text-ink-2">
            Iniciando Contador AI…
          </p>
        ) : (
          <Skeleton className="h-4 w-40" />
        )}
      </FullPage>
    )
  }
  if (setup.isError) {
    return (
      <FullPage>
        <EmptyState title="El servicio local no responde">
          {setup.error instanceof ApiError ? setup.error.message : ''} Cerrá y volvé a abrir la aplicación. Si se repite, el
          motivo queda registrado en la carpeta de datos de Contador AI, subcarpeta logs.
        </EmptyState>
      </FullPage>
    )
  }
  const needsSetup = setup.data.needs_setup
  if (need === 'setup') return needsSetup ? <Outlet /> : <Navigate to="/" replace />
  if (needsSetup) return <Navigate to="/configuracion-inicial" replace />
  if (need === 'anonymous') return me ? <Navigate to="/" replace /> : <Outlet />
  return me ? <Outlet /> : <Navigate to="/login" replace />
}

function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useSession()
  if (!can(permission)) {
    return <EmptyState title="Sin acceso">Tu rol no tiene permiso para ver esta sección. Pedíselo a un administrador.</EmptyState>
  }
  return children
}

/**
 * Finanzas se carga aparte (división de código): no pesa en el arranque de quien no la usa.
 * Cada pantalla es su propio fragmento; el marco y las utilidades comunes se comparten.
 */
const financeLayout = () => import('../modules/finance/FinanceLayout')
const finance = {
  index: () => financeLayout().then((m) => ({ Component: m.FinanceIndex })),
  layout: () => financeLayout().then((m) => ({ Component: m.FinanceLayout })),
  consolidated: () => import('../modules/finance/ConsolidatedPage').then((m) => ({ Component: m.ConsolidatedPage })),
  summary: () => import('../modules/finance/SummaryPage').then((m) => ({ Component: m.SummaryPage })),
  transactions: () => import('../modules/finance/TransactionsPage').then((m) => ({ Component: m.TransactionsPage })),
  accounts: () => import('../modules/finance/AccountsPage').then((m) => ({ Component: m.AccountsPage })),
  imports: () => import('../modules/finance/ImportPage').then((m) => ({ Component: m.ImportPage })),
  categories: () => import('../modules/finance/CategoriesPage').then((m) => ({ Component: m.CategoriesPage })),
  counterparties: () => import('../modules/finance/CounterpartiesPage').then((m) => ({ Component: m.CounterpartiesPage })),
}

/** Contabilidad (fase 3), también en fragmentos aparte. El acceso: `accounting.read` (todos los roles). */
const accounting = {
  layout: () => import('../modules/accounting/AccountingLayout').then((m) => ({ Component: m.AccountingLayout })),
  chart: () => import('../modules/accounting/ChartPage').then((m) => ({ Component: m.ChartPage })),
  years: () => import('../modules/accounting/FiscalYearsPage').then((m) => ({ Component: m.FiscalYearsPage })),
  entries: () => import('../modules/accounting/EntriesPage').then((m) => ({ Component: m.EntriesPage })),
  entry: () => import('../modules/accounting/EntryPage').then((m) => ({ Component: m.EntryPage })),
  reports: () => import('../modules/accounting/reports/ReportsPage').then((m) => ({ Component: m.ReportsPage })),
  // Fase 3B
  assetsLayout: () => import('../modules/accounting/assets/AssetsLayout').then((m) => ({ Component: m.AssetsLayout })),
  assets: () => import('../modules/accounting/assets/AssetsPage').then((m) => ({ Component: m.AssetsPage })),
  assetForm: () => import('../modules/accounting/assets/AssetFormPage').then((m) => ({ Component: m.AssetFormPage })),
  asset: () => import('../modules/accounting/assets/AssetDetailPage').then((m) => ({ Component: m.AssetDetailPage })),
  categories: () => import('../modules/accounting/assets/CategoriesPage').then((m) => ({ Component: m.AssetCategoriesPage })),
  depreciation: () => import('../modules/accounting/assets/DepreciationPage').then((m) => ({ Component: m.DepreciationPage })),
  schedule: () => import('../modules/accounting/assets/SchedulePage').then((m) => ({ Component: m.SchedulePage })),
  centers: () => import('../modules/accounting/CostCentersPage').then((m) => ({ Component: m.CostCentersPage })),
  recurring: () => import('../modules/accounting/recurring/RecurringPage').then((m) => ({ Component: m.RecurringPage })),
  template: () => import('../modules/accounting/recurring/TemplatePage').then((m) => ({ Component: m.TemplatePage })),
}

const router = createBrowserRouter([
  { element: <Gate need="setup" />, children: [{ path: '/configuracion-inicial', element: <SetupPage /> }] },
  { element: <Gate need="anonymous" />, children: [{ path: '/login', element: <LoginPage /> }] },
  {
    element: <Gate need="session" />,
    // Mientras llega el fragmento de una pantalla cargada aparte (al abrir la app directo en ella).
    hydrateFallbackElement: <FullPage><Skeleton className="h-4 w-40" /></FullPage>,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/empresa', element: <RequirePermission permission="organization.read"><OrganizationPage /></RequirePermission> },
          { path: '/usuarios', element: <RequirePermission permission="users.read"><UsersPage /></RequirePermission> },
          { path: '/auditoria', element: <RequirePermission permission="audit.read"><AuditPage /></RequirePermission> },
          { path: '/cuenta', element: <AccountPage /> },
          // Finanzas: el contexto va en la URL. El acceso lo decide la API (empresa con
          // finance.read; el personal solo para su dueño, cualquiera sea el rol).
          { path: '/finanzas', lazy: finance.index },
          { path: '/finanzas/consolidado', lazy: finance.consolidated },
          {
            path: '/finanzas/:cid',
            lazy: finance.layout,
            children: [
              { index: true, lazy: finance.summary },
              { path: 'movimientos', lazy: finance.transactions },
              { path: 'cuentas', lazy: finance.accounts },
              { path: 'importar', lazy: finance.imports },
              { path: 'categorias', lazy: finance.categories },
              { path: 'contrapartes', lazy: finance.counterparties },
            ],
          },
          {
            path: '/contabilidad',
            element: (
              <RequirePermission permission="accounting.read">
                <Outlet />
              </RequirePermission>
            ),
            children: [
              {
                lazy: accounting.layout,
                children: [
                  { index: true, element: <Navigate to="/contabilidad/plan" replace /> },
                  { path: 'plan', lazy: accounting.chart },
                  { path: 'ejercicios', lazy: accounting.years },
                  { path: 'asientos', lazy: accounting.entries },
                  { path: 'asientos/nuevo', lazy: accounting.entry },
                  { path: 'asientos/:id', lazy: accounting.entry },
                  { path: 'reportes', element: <Navigate to="/contabilidad/reportes/diario" replace /> },
                  { path: 'reportes/:report', lazy: accounting.reports },
                  {
                    path: 'activos',
                    lazy: accounting.assetsLayout,
                    children: [
                      { index: true, lazy: accounting.assets },
                      { path: 'categorias', lazy: accounting.categories },
                      { path: 'depreciacion', lazy: accounting.depreciation },
                      { path: 'cuadro', lazy: accounting.schedule },
                    ],
                  },
                  { path: 'activos/nuevo', lazy: accounting.assetForm },
                  { path: 'activos/:id', lazy: accounting.asset },
                  { path: 'activos/:id/editar', lazy: accounting.assetForm },
                  { path: 'centros', lazy: accounting.centers },
                  { path: 'recurrentes', lazy: accounting.recurring },
                  { path: 'recurrentes/nueva', lazy: accounting.template },
                  { path: 'recurrentes/:id', lazy: accounting.template },
                ],
              },
            ],
          },
          { path: '*', element: <EmptyState title="Página inexistente">La dirección no corresponde a ninguna sección.</EmptyState> },
        ],
      },
    ],
  },
])

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </SessionProvider>
    </QueryClientProvider>
  )
}
