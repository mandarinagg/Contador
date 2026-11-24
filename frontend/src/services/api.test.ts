import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, postForm, qs, session } from './api'

const respond = (status: number, body: unknown) =>
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status }))

afterEach(() => {
  vi.restoreAllMocks()
  session.clear()
})

describe('cliente de la API', () => {
  it('envía el token y devuelve el JSON', async () => {
    session.set('tok')
    const spy = respond(200, { ok: true })
    await expect(api('GET', '/x')).resolves.toEqual({ ok: true })
    const init = spy.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })

  it('convierte el error estándar del backend en ApiError con errores por campo', async () => {
    respond(422, {
      error: { code: 'VALIDATION_ERROR', message: 'Hay datos inválidos.', details: [{ field: 'email', message: 'Value error, mal' }] },
    })
    const err = await api('POST', '/x', {}).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('VALIDATION_ERROR')
    expect((err as ApiError).fieldErrors()).toEqual({ email: 'mal' })
  })

  it('un 401 con sesión borra el token y avisa', async () => {
    session.set('vencido')
    const handler = vi.fn()
    session.onUnauthorized(handler)
    respond(401, { error: { code: 'SESSION_EXPIRED', message: 'La sesión venció.' } })
    await expect(api('GET', '/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(session.token).toBeNull()
    expect(handler).toHaveBeenCalled()
  })

  it('sin servicio responde un error de red legible', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(api('GET', '/x')).rejects.toMatchObject({ code: 'NETWORK', status: 0 })
  })
})

describe('subida de archivos y query string', () => {
  it('FormData viaja sin Content-Type JSON', async () => {
    const spy = respond(201, { id: 'x' })
    const form = new FormData()
    form.set('mapping', '{}')
    await postForm('/finance/contexts/c/imports', form)
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.body).toBe(form)
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('qs omite vacíos y falsos', () => {
    expect(qs({ a: 'x y', b: '', c: undefined, d: false, e: true, f: 0 })).toBe('?a=x+y&e=true&f=0')
    expect(qs({})).toBe('')
  })
})
