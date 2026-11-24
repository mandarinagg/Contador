# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado semántico.

## [Sin publicar]

### Agregado — Fase 2, backend de finanzas (2026-11-24)
- Migración `0002` (esquema `finance`, reversible): contextos `business`/`personal`, cuentas, categorías (un nivel), contrapartes con RUC y DV, movimientos, lotes y filas de importación. La migración crea el contexto empresarial de cada organización existente y `POST /system/setup` lo crea junto con la organización.
- Separación impuesta en la base (D-025): claves foráneas compuestas `(id, context_id)` y `(account_id, context_id, currency)`; además, restricciones de importe distinto de cero, PYG sin decimales, anulación completa con motivo y transferencias sin categoría.
- Permisos `finance.read` (todos los roles) y `finance.manage` (propietario, administrador, contador). El contexto personal es solo de su dueño (404 para cualquier otro, incluido el propietario); su auditoría (`finance.personal.*`) no aparece en `/audit/logs` de otros usuarios.
- API `/api/v1/finance`: contextos, cuentas con saldo, categorías (con conjunto sugerido), contrapartes con búsqueda, movimientos con filtros y paginación por cursor, anulación, transferencias, importación CSV/XLSX con análisis previo, decisiones por fila, confirmación idempotente y cancelación, resumen por moneda/mes/categoría y consolidado por contexto.
- Importes `Decimal` / `NUMERIC(18,2)` / string en JSON; la API rechaza números JSON. Monedas `PYG` (0 decimales), `USD`, `BRL`, `ARS`, `EUR` (2).
- Dependencias: `openpyxl` 3.1.5, `python-multipart` 0.0.34; en desarrollo, `types-openpyxl`.
- 50 pruebas nuevas (78 en total), incluida una de rendimiento con 100.000 movimientos (`@pytest.mark.slow`).

### Agregado — Pruebas E2E (2026-11-24)
- `frontend/e2e/`: pruebas de punta a punta con `@playwright/test` (Chromium) contra la API real y una base PostgreSQL vacía que se recrea en cada corrida (`reset-db.ts`). Flujos: configuración inicial, cierre de sesión e ingreso, ingreso fallido, RUC con DV, alta de usuarios y permisos por rol, auditoría, tema claro/oscuro y servicio caído. Toda prueba falla ante `console.error` o `pageerror`.
- Scripts `npm run e2e` y `npm run e2e:ui`; `tsconfig.e2e.json` para tipar `e2e/` y `playwright.config.ts`.
- Job `e2e` en `.github/workflows/ci.yml` (reporte HTML como artefacto solo si falla).
- Cierra el pendiente P-3.

### Agregado — Fase 0 (2026-11-23)
- `docs/PROMPT_MAESTRO.md`: prompt del propietario convertido a Markdown como documento rector.
- `docs/DISCOVERY.md`: diagnóstico del entorno, repositorios y riesgos.
- `docs/INTEGRATIONS.md`: auditoría del proyecto `facturacion-sifen-zestia` y propuesta de integración.
- Documentación obligatoria: PRD, arquitectura, esquema, reglas, tributación, seguridad, API, pruebas, hoja de ruta, decisiones, estado.

### Agregado — Fase 1B (2026-11-23)
- Plataforma objetivo definida: Windows 11, una sola PC (D-016 a D-020).
- `python -m app`: el backend aplica migraciones y levanta la API (modo empaquetado).
- `backend/packaging/contador-backend.spec`: backend como ejecutable con PyInstaller (verificado en Linux).
- `.github/workflows/ci.yml`: revisión de secretos, pruebas en Linux, y en Windows real: lanzador, instalador NSIS y prueba de instalación de punta a punta.
- Lanzador Rust (`desktop/src-tauri/src/stack.rs`, `secret.rs`): PostgreSQL portable + backend, contraseña en el Administrador de credenciales, una sola instancia, error visible con la ruta del registro (D-021, D-022).
- La interfaz espera a que la API arranque ("Iniciando Contador AI…") en lugar de mostrar un error.
- Hook pre-commit con gitleaks; repositorio público (`docs/SECURITY.md`).

### Agregado — Fase 1 (2026-11-23)
- Backend FastAPI: configuración por entorno, logging JSON con `request_id`, errores con códigos estables.
- Migración `0001`: esquemas `core` y `audit`; usuarios, organizaciones, membresías, roles, permisos, sesiones; auditoría de solo inserción con cadena de hashes; eventos de seguridad; catálogo de roles y permisos.
- Configuración inicial (organización + propietario), ingreso, cierre de sesión, cambio de contraseña, bloqueo por intentos.
- Gestión de usuarios con roles y reglas de propietario; datos de la organización con validación del DV del RUC.
- Consulta y verificación de integridad de la auditoría.
- Frontend: sistema de diseño (tokens claro/oscuro, componentes), configuración inicial, ingreso, inicio con puesta en marcha, empresa, usuarios y roles, auditoría, mi cuenta.
- Tauri 2 configurado (`desktop/`): identidad, ventana, CSP, íconos. Sin compilar.
- PostgreSQL 18 de desarrollo en Docker (`127.0.0.1:55433`).
