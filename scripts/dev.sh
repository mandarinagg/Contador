#!/usr/bin/env bash
# Levanta el entorno de desarrollo: PostgreSQL (Docker), migraciones, backend y frontend.
# Ctrl+C detiene backend y frontend (la base queda corriendo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker compose -p contador -f "$ROOT/docker-compose.yml" up -d --wait postgres

cd "$ROOT/backend"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev]"
fi
.venv/bin/alembic upgrade head

cd "$ROOT/frontend"
[[ -d node_modules ]] || npm install

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload) &
(cd "$ROOT/frontend" && npm run dev) &

echo "Backend:  http://127.0.0.1:8765/docs"
echo "Frontend: http://127.0.0.1:5173"
wait
