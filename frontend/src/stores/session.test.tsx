import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { session } from '../services/api'
import { SessionProvider, useSession } from './session'

const ME = (orgId: string) => ({
  user: { id: 'u', email: 'a@b.py', full_name: 'A', is_active: true, last_login_at: null },
  organization: { id: orgId, legal_name: orgId, trade_name: null, legal_form: 'SA' },
  role: 'owner',
  permissions: [],
})

function Probe({ onValue }: { onValue: (v: ReturnType<typeof useSession>) => void }) {
  const value = useSession()
  useEffect(() => {
    onValue(value)
  })
  return null
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  session.clear()
})

describe('cambio de organización', () => {
  it('reemplaza el token, descarta lo cargado y deja la nueva organización', async () => {
    session.set('viejo')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input).replace(/^.*\/api\/v1/, '')
      if (path === '/auth/me') return new Response(JSON.stringify(ME('a')), { status: 200 })
      if (path === '/auth/switch') {
        return new Response(JSON.stringify({ ...ME('b'), token: 'nuevo', expires_at: 'x', organizations: [] }), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    qc.setQueryData(['finance', 'transactions'], ['de la organización anterior'])
    qc.setQueryData(['setup'], { needs_setup: false })
    const ctx = {} as { current: ReturnType<typeof useSession> }
    render(
      <QueryClientProvider client={qc}>
        <SessionProvider>
          <Probe onValue={(v) => (ctx.current = v)} />
        </SessionProvider>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(ctx.current.me?.organization.id).toBe('a'))
    await act(() => ctx.current.switchOrg('b'))
    expect(session.token).toBe('nuevo')
    await waitFor(() => expect(ctx.current.me?.organization.id).toBe('b'))
    expect(qc.getQueryData(['finance', 'transactions'])).toBeUndefined()
    expect(qc.getQueryData(['setup'])).toEqual({ needs_setup: false })
  })

  it('si el cambio falla, conserva el token y lo cargado', async () => {
    session.set('viejo')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) =>
      String(input).endsWith('/auth/me')
        ? new Response(JSON.stringify(ME('a')), { status: 200 })
        : new Response(JSON.stringify({ error: { code: 'ORGANIZATION_NOT_AVAILABLE', message: 'no' } }), { status: 403 }),
    )
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    qc.setQueryData(['finance', 'transactions'], ['x'])
    const ctx = {} as { current: ReturnType<typeof useSession> }
    render(
      <QueryClientProvider client={qc}>
        <SessionProvider>
          <Probe onValue={(v) => (ctx.current = v)} />
        </SessionProvider>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(ctx.current.me).not.toBeNull())
    await expect(act(() => ctx.current.switchOrg('b'))).rejects.toThrow()
    expect(session.token).toBe('viejo')
    expect(qc.getQueryData(['finance', 'transactions'])).toEqual(['x'])
  })
})
