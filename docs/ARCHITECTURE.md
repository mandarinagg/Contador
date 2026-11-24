# Arquitectura

## Visión general

CONTADOR AI es una aplicación de escritorio **local-first**: todos los datos viven en una base PostgreSQL de la propia máquina. Solo salen de ella las llamadas explícitas a servicios externos (SIFEN y, en fase 6, Claude API).

```
┌──────────────────────── Tauri 2 (proceso principal, Rust) ────────────────────────┐
│  Ventana (WebView)                                                                │
│   └─ Frontend React + TypeScript (build estático)                                 │
│         │ HTTP 127.0.0.1 + Bearer token                                           │
│  Sidecars administrados por Tauri (fase 8):                                       │
│   ├─ Backend FastAPI  (127.0.0.1:8765)  ── SQLAlchemy ──► PostgreSQL 18 (local)   │
│   │     └─ adaptador de facturación ──HTTP──► Servicio SIFEN (Node, 127.0.0.1:8766)│
│   └─ PostgreSQL 18 portable (datos en la carpeta de la app)                       │
└───────────────────────────────────────────────────────────────────────────────────┘
        Salidas a internet: SIFEN (SOAP + TLS mutuo) · Claude API (HTTPS)
```

**Por qué un backend HTTP local y no comandos Rust:** el prompt maestro fija Python/FastAPI, las reglas contables y tributarias se prueban mejor en Python, y el mismo backend sirve al navegador durante el desarrollo. Tauri solo orquesta procesos, ventanas y el almacén seguro del sistema operativo.

## Estructura

```
Contador/
├── backend/                 FastAPI (Python 3.12+; probado en 3.14)
│   ├── app/
│   │   ├── core/            config, db, errores, logging, seguridad, catálogo de permisos
│   │   ├── api/             dependencias comunes (sesión, autenticación, permisos)
│   │   ├── modules/         un paquete por dominio (rebanada vertical):
│   │   │   ├── identity/        usuarios, sesiones, roles   (models, schemas, service, router)
│   │   │   ├── organizations/   organizaciones, membresías, RUC
│   │   │   ├── audit/           auditoría encadenada, eventos de seguridad
│   │   │   ├── finance/         finanzas (fase 2): contextos, cuentas, movimientos, importación
│   │   │   │                    (models, schemas, service, transactions, imports, importing,
│   │   │   │                     money, normalize, summary, suggested, router)
│   │   │   └── system/          salud y configuración inicial
│   │   ├── integrations/    (fase 5) adaptadores externos: billing/SIFEN, bancos
│   │   ├── ai/              (fase 6) agentes y herramientas controladas
│   │   └── models.py        registro de modelos para Alembic
│   ├── migrations/          Alembic (única fuente del esquema)
│   └── tests/               pytest contra PostgreSQL real
├── frontend/                React 19 + Vite 8 + Tailwind 4
│   └── src/
│       ├── app/             router, guardas, proveedores
│       ├── components/ui/   sistema de diseño
│       ├── layouts/         estructura con sidebar
│       ├── modules/         pantallas por dominio
│       ├── hooks/ services/ stores/ lib/ types/ styles/
├── desktop/                 Tauri 2 (src-tauri/, íconos, CLI)
├── services/sifen/          (fase 5) servicio Node que reutiliza el núcleo SIFEN
├── docs/
├── scripts/
├── docker-compose.yml       PostgreSQL de desarrollo
└── .env.example
```

**Cambios respecto de la estructura sugerida (y por qué):**
- **Sin `database/`**: las migraciones viven en `backend/migrations` (Alembic). Una segunda carpeta de migraciones duplicaría la fuente de verdad. Las semillas son migraciones de datos (ej. roles y permisos en `0001`). La documentación del esquema está en `docs/DATABASE_SCHEMA.md`.
- **Módulos verticales en lugar de capas `models/ schemas/ repositories/ services/` globales**: cada dominio agrupa su modelo, esquemas, servicio y rutas; un cambio contable no toca carpetas de toda la app. No hay capa "repository" separada: SQLAlchemy 2 ya es el repositorio; se agregará cuando un dominio tenga consultas complejas que lo justifiquen.
- **Sin `tests/` raíz todavía**: las pruebas viven con cada aplicación. Las E2E de escritorio llegarán en fase 8.
- **`services/sifen/`**: nuevo, para el servicio de facturación reutilizado (ver `INTEGRATIONS.md`).

## Backend

- **FastAPI** con endpoints síncronos y **SQLAlchemy 2 síncrono** (psycopg 3). Una app de escritorio tiene pocos usuarios simultáneos; el modo síncrono simplifica transacciones y pruebas. Los trabajos largos (OCR, importaciones, IA) irán a una cola en `audit.system_jobs` procesada por un worker del mismo backend (fase 2/5). Ver D-004.
- **Errores**: toda respuesta de error tiene la forma `{"error": {"code", "message", "details?"}}` con códigos estables (`docs/API_SPECIFICATION.md`).
- **Transacciones**: un `commit` por operación de negocio; la auditoría se escribe en la **misma** transacción que el cambio.
- **Logging**: JSON por línea a stdout, con `request_id` (cabecera `X-Request-Id`) y redacción de claves sensibles.
- **Dinero**: `Decimal` en Python, `NUMERIC(20,4)` en la base, moneda ISO 4217 explícita en cada importe (fase 2). Nunca `float`. Ver D-005.

## Frontend

- **React 19 + TypeScript 7 + Vite 8**, plantilla oficial `create-vite` (oxlint incluido).
- **TanStack Query** para el estado del servidor (cache, reintentos, invalidación). Sin store global adicional: el estado de sesión es un contexto pequeño.
- **React Router 8** con guardas: sin configurar → configuración inicial; sin sesión → ingreso; sin permiso → aviso.
- **El token de sesión** vive en `sessionStorage` (dura lo que la ventana); ningún dato de negocio se guarda en el navegador. La preferencia de tema sí usa `localStorage` (no es dato de negocio).

### Sistema de diseño

Definido en `frontend/src/styles/index.css` (tokens) y `frontend/src/components/ui/` (componentes).

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `paper` | `#F6F7F5` | `#0F1513` | Fondo |
| `surface` | `#FFFFFF` | `#161E1B` | Hojas, tablas, formularios |
| `sunken` | `#EEF1EE` | `#121A17` | Sidebar, cabeceras de tabla |
| `ink` / `ink-2` / `ink-3` | `#1B2420` / `#4A5752` / `#7A8681` | `#E4EBE7` / `#A9B6B0` / `#74827C` | Texto principal / secundario / terciario |
| `ledger` | `#1F5C4A` | `#5FB596` | Primario: verde de libro mayor |
| `lapacho` | `#C2477A` | `#E07AA5` | Marca. **Solo** el logo y el indicador de navegación activa |
| `debit` | `#B3412E` | `#E57A66` | Negativos, errores, acciones destructivas |
| `amber` | `#946200` | `#E0B155` | Pendiente de verificación |
| `personal` / `personal-soft` | `#43508F` / `#E9EBF6` | `#A9B1EC` / `#222640` | Contexto financiero personal (pestaña, franja "solo vos") |
| `chart-in` / `chart-out` | `#12734F` / `#E58F78` | `#3AA67E` / `#C45A42` | Gráficos de finanzas: entradas / salidas (validados para daltonismo; el gráfico trae vista de tabla) |

- **Finanzas:** los importes son siempre strings (`lib/money.ts` formatea y lee el formato paraguayo sin pasar por `number`); solo la geometría de los gráficos usa números. Los gráficos son SVG propio con los tokens de arriba (sin librería de gráficos). El contexto financiero va en la URL (`/finanzas/:cid/...`); las pantallas de finanzas se cargan aparte (`lazy` de React Router).

- **Tipografía:** IBM Plex Sans Variable (local, sin red), cifras tabulares en toda la app. Escala: 12 / 13 / 14 (base) / 16 / 20 / 28 px.
- **Firma visual:** la doble raya contable (`.ledger-rule`) bajo títulos de página y, en fase 2+, bajo totales — la convención real de los libros contables.
- **Radios:** 4 px controles, 6 px hojas y modales. **Sombras:** una de hoja (casi plana) y una flotante (modales, avisos).
- **Movimiento:** una entrada de 180 ms para modales/avisos; respeta `prefers-reduced-motion`.
- **Componentes:** `Button` (primary, secondary, ghost, danger; estado `busy`), `Field` (etiqueta, ayuda, error accesibles), `Input`, `Select`, `Badge`, `Notice`, `Skeleton`, `EmptyState`, `PageHeader`, `Sheet`, `Modal` (`<dialog>` nativo), `Toast`.
- **Iconografía:** lucide-react, 16 px en navegación y botones.

## Desktop (Tauri 2)

- `desktop/src-tauri/tauri.conf.json`: identificador `py.contadorai.desktop`, ventana 1366×860 (mín. 1100×700), **CSP estricta** (solo recursos propios y `http://127.0.0.1:8765`), CSP de desarrollo separada para Vite.
- Hoy la app de escritorio solo muestra el frontend; el backend se levanta aparte. En fase 8 Tauri lanzará y supervisará los sidecars (backend, servicio SIFEN, PostgreSQL) y les pasará un secreto por proceso.
- **No compilado todavía**: faltan Rust y las librerías de desarrollo de WebKitGTK (ver README).

## Asistente (fase 6, diseño)

- El backend llama a Claude API con **herramientas definidas por el backend** (las de `PROMPT_MAESTRO.md §4 Módulo 10`). Cada herramienta valida permisos del usuario que conversa, filtra por organización y contexto financiero, y devuelve datos mínimos etiquetados (`real`, `estimado`, `incompleto`, `regla verificada/pendiente`).
- Las herramientas de escritura solo crean **borradores** y una fila en `ai.ai_approvals`; un humano con permiso aprueba.
- Cada llamada y resultado se registra en `ai.ai_tool_executions`. No existe una herramienta de SQL libre.

## Dependencias

### Backend (versiones fijas en `backend/pyproject.toml`)
| Paquete | Versión | Por qué |
|---|---|---|
| fastapi | 0.165.0 | Framework fijado por el prompt maestro |
| uvicorn[standard] | 0.54.0 | Servidor ASGI |
| pydantic[email] | 2.14.4 | Validación de entradas (incluye validación de email) |
| pydantic-settings | 2.16.3 | Configuración desde variables de entorno |
| sqlalchemy | 2.1.9 | ORM fijado por el prompt |
| alembic | 1.20.1 | Migraciones versionadas |
| psycopg[binary] | 3.3.9 | Driver PostgreSQL (wheels binarios, sin compilar) |
| argon2-cffi | 25.1.0 | Hash de contraseñas Argon2id |
| openpyxl | 3.1.5 | Lectura de extractos XLSX (fase 2), en modo `read_only` y `data_only`: no evalúa fórmulas ni ejecuta macros |
| python-multipart | 0.0.34 | Formularios `multipart/form-data` de FastAPI (subida de extractos) |
| *dev:* pytest 9.2.0, httpx2 2.16.2, ruff 0.17.6, mypy 2.4.1, types-openpyxl 3.1.5.20261122 | | Pruebas, cliente de pruebas, lint, tipos estrictos (openpyxl no trae tipos propios: sin el paquete de tipos, `mypy --strict` falla) |

### Frontend (versiones exactas en `frontend/package.json`)
| Paquete | Versión | Por qué |
|---|---|---|
| react, react-dom | 19.3.1 | Fijado por el prompt |
| react-router | 8.5.2 | Navegación y guardas |
| @tanstack/react-query | 5.108.4 | Estado del servidor sin reinventar cache/reintentos |
| lucide-react | 1.78.0 | Iconografía consistente |
| @fontsource-variable/ibm-plex-sans | 5.3.0 | Fuente local (la app funciona sin internet) |
| tailwindcss, @tailwindcss/vite | 4.3.5 | Fijado por el prompt |
| *dev:* vite 8.3.8, typescript 7.0.2, oxlint, vitest 5.1.1, @testing-library/react, jsdom | | Build, tipos, lint, pruebas |
| *pendiente (fase 2):* recharts 3.x | | Gráficos del dashboard; se instala cuando haya datos que graficar |

### Desktop
| Paquete | Versión | Por qué |
|---|---|---|
| @tauri-apps/cli | 2.12.6 | Fijado por el prompt |
| tauri (crate) | 2.12.x | Idem; requiere Rust ≥ 1.90 |

## Distribución (Windows 11, una sola PC)

Desarrollo en Linux; uso real en **una PC con Windows 11** (D-016). Los instaladores de Windows se arman en GitHub Actions (D-018).

| Pieza | En la PC con Windows 11 | Cómo se arma |
|---|---|---|
| Instalador | NSIS (`.exe`) por usuario, sin permisos de administrador | `tauri build` en `windows-latest` |
| Interfaz | WebView2 (viene con Windows 11) | Build de Vite incluido en Tauri |
| Backend | `contador-backend\contador-backend.exe` (PyInstaller, modo carpeta) como recurso de Tauri | `backend/packaging/contador-backend.spec` (D-019) |
| Base de datos | PostgreSQL 18.7 portable; datos en `%LOCALAPPDATA%\ContadorAI\pgdata` | Zip oficial de EDB recortado (D-020) |
| Secretos | Administrador de credenciales de Windows (contraseña de la base, clave de cifrado, API key de Claude) | Crate `keyring` en el proceso Rust |
| Copias de seguridad | Diaria y automática: `pg_dump -Fc` en `%LOCALAPPDATA%\ContadorAI\backups\auto` (últimas 14), verificada con `pg_restore --list`. **Sin cifrar**; destino externo y cifrado pendientes | `src/backup.rs` (D-029); restauración manual en `docs/RESTAURACION.md` |
| Actualizaciones | Instalar el `.exe` nuevo encima (fase 1B); luego, actualizador de Tauri con paquetes firmados | |
| Firma de código | Sin certificado, Windows muestra "Windows protegió su PC" → "Más información" → "Ejecutar de todas formas". Para uso propio es aceptable; un certificado de firma lo elimina | Opcional |

### Arranque en Windows (diseño de la fase 1B)
1. Tauri muestra la ventana con un estado de "Iniciando…".
2. **Primer arranque:** genera una contraseña aleatoria para la base, la guarda en el Administrador de credenciales, ejecuta `initdb` (UTF-8, `scram-sha-256`) y crea la base `contador`.
3. Inicia PostgreSQL con `pg_ctl` (solo `127.0.0.1`, puerto fijo 55440) y espera a que responda.
4. Lanza `contador-backend.exe` con `CONTADOR_ENV=production` y la URL de la base por variable de entorno; el backend aplica migraciones y escucha en `127.0.0.1:8765`.
5. Cuando `/system/health` responde, carga la interfaz. Si algo falla, muestra el motivo y la ruta del log (`%LOCALAPPDATA%\ContadorAI\logs`).
6. **Copia de seguridad:** una vez que los servicios responden, un hilo aparte (sin demorar la apertura) revisa si existe una copia automática de hoy en `%LOCALAPPDATA%\ContadorAI\backups\auto`; si no, ejecuta `pg_dump -Fc` hacia `contador-AAAAMMDD-HHMMSS.dump.partial` (contraseña por `PGPASSWORD`), la verifica con `pg_restore --list`, la renombra y deja las últimas 14. Si falla, borra solo el `.partial`, anota el error en `logs\backup.log` y la app sigue; reintenta cada 30 minutos mientras esté abierta. Nunca escribe en `pgdata`.
7. Al cerrar la app: detiene el backend y luego PostgreSQL (`pg_ctl stop -m fast`). Una copia en curso se interrumpe y su `.partial` se limpia en la próxima.

Implementado en `desktop/src-tauri/src/stack.rs` (D-022) y `backup.rs` (D-029). Registros en `%LOCALAPPDATA%\ContadorAI\logs` (`backend.log`, `postgresql.log`, `initdb.log`, `pg_ctl.log`, `backup.log`; el anterior queda como `.log.1`).

**Verificación continua (job `windows` del CI, Windows real):** prueba del lanzador con binarios reales (primer arranque, reinicio con datos, falta de contraseña, carpeta ajena), Administrador de credenciales, y luego el instalador NSIS: instalación silenciosa, primer arranque, cierre forzado (el backend muere con la app), reapertura reutilizando PostgreSQL, cierre normal (todo detenido) y desinstalación sin pérdida de datos.

Linux (`.deb`, AppImage) queda como opción secundaria con el mismo diseño.
