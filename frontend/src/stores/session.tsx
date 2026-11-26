import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, use, useCallback, useEffect, useMemo, useState } from 'react'
import { get, post, session } from '../services/api'
import type { LoginResponse, Me } from '../types/api'

interface SessionState {
  me: Me | null
  loading: boolean
  /** Guarda el token devuelto por login/setup y carga el usuario. */
  start: (res: LoginResponse) => void
  /** Cambia de organización: reemplaza el token y descarta todo lo cargado con la anterior. */
  switchOrg: (organizationId: string) => Promise<void>
  logout: () => Promise<void>
  can: (permission: string) => boolean
}

const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  // El token es estado de React (además de sessionStorage) para que la UI reaccione
  // al instante: sin token, las rutas protegidas redirigen solas al ingreso.
  const [token, setToken] = useState<string | null>(() => session.token)

  const meQuery = useQuery({
    queryKey: ['me', token],
    queryFn: () => get<Me>('/auth/me'),
    enabled: token !== null,
    retry: false,
    staleTime: 60_000,
  })

  // Se descarta todo lo cargado con la sesión, salvo el estado de configuración.
  const dropCache = useCallback(() => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'setup' }), [qc])

  const end = useCallback(() => {
    session.clear()
    setToken(null)
    dropCache()
  }, [dropCache])

  useEffect(() => session.onUnauthorized(end), [end])

  const start = useCallback(
    (res: LoginResponse) => {
      const { token: newToken, expires_at: _exp, organizations, ...me } = res
      session.set(newToken)
      qc.setQueryData(['me', newToken], me)
      qc.setQueryData(['organizations'], organizations)
      setToken(newToken)
    },
    [qc],
  )

  const switchOrg = useCallback(
    async (organizationId: string) => {
      const res = await post<LoginResponse>('/auth/switch', { organization_id: organizationId })
      // El token anterior ya no sirve: nada de lo cargado con él se conserva.
      dropCache()
      start(res)
    },
    [dropCache, start],
  )

  const logout = useCallback(async () => {
    try {
      await post('/auth/logout')
    } finally {
      end()
    }
  }, [end])

  const me = token ? (meQuery.data ?? null) : null
  const value = useMemo<SessionState>(
    () => ({
      me,
      loading: token !== null && meQuery.isPending,
      start,
      switchOrg,
      logout,
      can: (p) => me?.permissions.includes(p) ?? false,
    }),
    [me, token, meQuery.isPending, start, switchOrg, logout],
  )
  return <SessionContext value={value}>{children}</SessionContext>
}

export function useSession(): SessionState {
  const ctx = use(SessionContext)
  if (!ctx) throw new Error('useSession fuera de SessionProvider')
  return ctx
}
