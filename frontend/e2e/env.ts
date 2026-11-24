/** Configuración común de las pruebas E2E: puertos y base de datos propios, aparte de la app de uso diario. */
import { resolve } from 'node:path'

export const API_PORT = Number(process.env.CONTADOR_E2E_API_PORT ?? 8794)
export const WEB_PORT = Number(process.env.CONTADOR_E2E_WEB_PORT ?? 5174)
export const API_URL = `http://127.0.0.1:${API_PORT}/api/v1`
export const WEB_URL = `http://127.0.0.1:${WEB_PORT}`

const DB_HOST = process.env.CONTADOR_E2E_DB_HOST ?? '127.0.0.1:55433'
const DB_CREDENTIALS = process.env.CONTADOR_E2E_DB_CREDENTIALS ?? 'contador:contador_dev'
export const DB_NAME = process.env.CONTADOR_E2E_DB_NAME ?? 'contador_e2e'
export const DATABASE_URL = `postgresql+psycopg://${DB_CREDENTIALS}@${DB_HOST}/${DB_NAME}`

export const BACKEND_DIR = resolve(import.meta.dirname, '../../backend')
export const BACKEND_PYTHON = resolve(BACKEND_DIR, '.venv/bin/python')
