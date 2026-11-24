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
  const isForm = body instanceof FormData
  // FormData (subida de archivos): el navegador pone el Content-Type con su separador.
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  const token = session.token
  if (token) headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
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
export const put = <T>(path: string, body: unknown) => api<T>('PUT', path, body)
export const postForm = <T>(path: string, form: FormData) => api<T>('POST', path, form)

/** Arma un query string omitiendo los valores vacíos: `qs({a: 1, b: ''})` → `?a=1`. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue
    search.set(k, String(v))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/**
 * Descarga binaria autenticada (XLSX de los reportes). Devuelve el archivo y el nombre que
 * manda la API en `Content-Disposition`, si el navegador lo deja leer: en un pedido entre
 * orígenes solo se ve si la API lo expone en `Access-Control-Expose-Headers`.
 */
export async function getBlob(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const headers: Record<string, string> = {}
  const token = session.token
  if (token) headers.Authorization = `Bearer ${token}`
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, { headers })
  } catch {
    throw new ApiError(0, 'NETWORK', 'No se pudo conectar con el servicio local de CONTADOR AI.')
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as ApiErrorBody | null
    if (res.status === 401 && token) {
      session.clear()
      onUnauthorized?.()
    }
    throw new ApiError(res.status, data?.error?.code ?? `HTTP_${res.status}`, data?.error?.message ?? 'Respuesta inesperada del servicio.', data?.error?.details)
  }
  return { blob: await res.blob(), filename: filenameFromDisposition(res.headers.get('Content-Disposition')) }
}

/** `attachment; filename="libro-diario-2026-01-01-2026-12-31.xlsx"` → el nombre (también `filename*=UTF-8''…`). */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(header)
  if (star) {
    try {
      return safeName(decodeURIComponent(star[1].trim().replace(/^"|"$/g, '')))
    } catch {
      // Codificación rota: sigue con `filename=`.
    }
  }
  const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/.exec(header)
  return safeName((plain?.[1] ?? plain?.[2] ?? '').trim())
}

/** Nunca una ruta: solo el nombre del archivo. */
function safeName(name: string): string | null {
  const base = name.replace(/^.*[\\/]/, '').trim()
  return base && base !== '.' && base !== '..' ? base : null
}
