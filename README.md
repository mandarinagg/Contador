# CONTADOR AI

Plataforma de escritorio para contabilidad, tributación, facturación electrónica y finanzas personales y empresariales en Paraguay.

- Requisitos y visión: [`docs/PROMPT_MAESTRO.md`](docs/PROMPT_MAESTRO.md) · [`docs/PRD.md`](docs/PRD.md)
- Estado actual: [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)
- Arquitectura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Decisiones: [`docs/DECISIONS.md`](docs/DECISIONS.md)

## Requisitos de desarrollo

| Herramienta | Versión probada |
|---|---|
| Python | 3.14 (≥ 3.12) |
| Node.js | 24 |
| Docker + Compose | 29 / v5 (solo para PostgreSQL de desarrollo) |
| Rust + dependencias de Tauri | Solo para la app de escritorio (ver abajo) |

## Puesta en marcha

```bash
# 1. Base de datos (PostgreSQL 18 en 127.0.0.1:55433)
docker compose -p contador up -d

# 2. Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp ../.env.example .env            # ajustar si hace falta
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765

# 3. Frontend (otra terminal)
cd frontend
npm install
npm run dev                         # http://127.0.0.1:5173
```

O todo junto: `scripts/dev.sh`.

La primera vez la aplicación pide registrar la empresa y el usuario propietario.

## Antes del primer commit (repositorio público)

```bash
scripts/check-secrets.sh --install   # revisa cada commit con gitleaks (requiere Docker)
```

Reglas en [`docs/SECURITY.md`](docs/SECURITY.md#repositorio-público).

## Pruebas

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/mypy app
cd frontend && npm test && npm run typecheck && npm run lint
```

## App de escritorio (Tauri 2)

Dependencias del sistema (Ubuntu/Debian), una sola vez:

```bash
sudo apt install pkg-config libwebkit2gtk-4.1-dev librsvg2-dev libssl-dev libayatana-appindicator3-dev build-essential curl file
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Luego, con el backend en marcha:

```bash
cd desktop && npm install && npm run dev      # ventana de escritorio
npm run build                                  # instaladores .deb/.rpm/AppImage
```

En Windows: Visual Studio Build Tools (C++), WebView2 (incluido en Windows 11) y Rust; los instaladores NSIS/MSI se generan en Windows.

## Estructura

```
backend/   API local FastAPI + migraciones Alembic + pruebas
frontend/  React + Vite + Tailwind (sistema de diseño en src/styles y src/components/ui)
desktop/   Tauri 2
docs/      documentación del proyecto
scripts/   utilidades de desarrollo
```
