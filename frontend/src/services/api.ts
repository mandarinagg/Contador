/**
 * Cliente HTTP de la API local. Único lugar que conoce la URL y el token.
 *
 * El token vive en sessionStorage: dura lo que la ventana (en Tauri, lo que la app
 * esté abierta) y no se comparte entre ventanas. No es almacenamiento de datos de
 * negocio: todo dato de negocio vive en PostgreSQL detrás de la API.
 */
import type { ApiErrorBody } from '../types/api'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://127.0.0.1:8765/api/v1'
const TOKEN_KEY = 'contador.session'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  /** Mensajes de validación por campo, si el backend los envió. */
  fieldErrors(): Record<string, string> {
    if (!Array.isArray(this.details)) return {}
    const out: Record<string, string> = {}
    for (const d of this.details as { field?: string; message?: string }[]) {
      if (d.field && d.message) out[d.field] = d.message.replace(/^Value error, /, '')
    }
    return out
  }
}

let onUnauthorized: (() => void) | null = null

export const session = {
  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY)
  },
  set(token: string) {
    sessionStorage.setItem(TOKEN_KEY, token)
  },
  clear() {
    sessionStorage.removeItem(TOKEN_KEY)
  },
  onUnauthorized(handler: () => void) {
    onUnauthorized = handler
  },
}

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export async function api<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = session.token
  if (token) headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'NETWORK', 'No se pudo conectar con el servicio local de CONTADOR AI.')
  }

  if (res.status === 204) return undefined as T
  const data: unknown = await res.json().catch(() => null)
  if (!res.ok) {
    const err = (data as ApiErrorBody | null)?.error
    const apiError = new ApiError(
      res.status,
      err?.code ?? `HTTP_${res.status}`,
      err?.message ?? 'Respuesta inesperada del servicio.',
      err?.details,
    )
    if (res.status === 401 && token && path !== '/auth/login') {
      session.clear()
      onUnauthorized?.()
    }
    throw apiError
  }
  return data as T
}

export const get = <T>(path: string) => api<T>('GET', path)
export const post = <T>(path: string, body?: unknown) => api<T>('POST', path, body ?? {})
export const patch = <T>(path: string, body: unknown) => api<T>('PATCH', path, body)
