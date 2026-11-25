/**
 * Recrea la base E2E vacía (DROP + CREATE). Las migraciones las aplica la API al arrancar
 * (`python -m app` ejecuta `alembic upgrade head`).
 *
 * Usa psycopg del venv del backend para no sumar un driver de PostgreSQL al frontend.
 * Se ejecuta desde el `webServer` de Playwright, antes de levantar la API.
 */
import { execFileSync } from 'node:child_process'
import { rmSync } from 'node:fs'
import { BACKEND_DIR, BACKEND_PYTHON, DATABASE_URL, DB_NAME, KEYRING_FILE } from './env.ts'

const SCRIPT = `
import sys
from psycopg import connect, sql
from sqlalchemy.engine import make_url

url = make_url(sys.argv[1])
if not url.database.startswith("contador_e2e"):
    raise SystemExit(f"Por seguridad solo se recrean bases contador_e2e*, no {url.database!r}")
with connect(host=url.host, port=url.port, user=url.username, password=url.password,
             dbname="postgres", autocommit=True) as conn:
    name = sql.Identifier(url.database)
    conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
    conn.execute(sql.SQL("CREATE DATABASE {}").format(name))
`

execFileSync(BACKEND_PYTHON, ['-c', SCRIPT, DATABASE_URL], { cwd: BACKEND_DIR, stdio: 'inherit' })
rmSync(KEYRING_FILE, { force: true })
console.log(`Base E2E ${DB_NAME} recreada vacía.`)
