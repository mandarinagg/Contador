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

function FullPage({ children }: { children: ReactNode }) {
  return <div className="grid h-full place-items-center">{children}</div>
}

/** Decide a dónde ir según el estado: sin configurar → setup; sin sesión → login. */
function Gate({ need }: { need: 'setup' | 'anonymous' | 'session' }) {
  const setup = useQuery({ queryKey: ['setup'], queryFn: () => get<{ needs_setup: boolean }>('/system/setup') })
  const { me, loading } = useSession()

  if (setup.isPending || loading) {
    return (
      <FullPage>
        <Skeleton className="h-4 w-40" />
      </FullPage>
    )
  }
  if (setup.isError) {
    return (
      <FullPage>
        <EmptyState title="El servicio local no responde">
          {setup.error instanceof ApiError ? setup.error.message : ''} Verificá que el backend esté en ejecución y volvé a abrir la
          aplicación.
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

const router = createBrowserRouter([
  { element: <Gate need="setup" />, children: [{ path: '/configuracion-inicial', element: <SetupPage /> }] },
  { element: <Gate need="anonymous" />, children: [{ path: '/login', element: <LoginPage /> }] },
  {
    element: <Gate need="session" />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/empresa', element: <RequirePermission permission="organization.read"><OrganizationPage /></RequirePermission> },
          { path: '/usuarios', element: <RequirePermission permission="users.read"><UsersPage /></RequirePermission> },
          { path: '/auditoria', element: <RequirePermission permission="audit.read"><AuditPage /></RequirePermission> },
          { path: '/cuenta', element: <AccountPage /> },
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
