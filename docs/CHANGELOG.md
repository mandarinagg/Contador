# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado semántico.

## [Sin publicar]

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

### Agregado — Copias de seguridad (2026-11-24)
- Copia automática diaria de la base (`pg_dump -Fc`) en `%LOCALAPPDATA%\ContadorAI\backups\auto`, verificada con `pg_restore --list`, retención de 14 copias y errores en `logs/backup.log` (D-029).
- `restore_dump`: restauración en una base nueva y vacía; procedimiento manual para el propietario en `docs/RESTAURACION.md`.
- Prueba `desktop/src-tauri/tests/backup.rs`: copia, verificación, retención, restauración en un clúster nuevo y backend arrancando sobre la base restaurada.
- Las copias **no están cifradas** todavía (pendiente, `docs/SECURITY.md`).

### Agregado — Fase 1 (2026-11-23)
- Backend FastAPI: configuración por entorno, logging JSON con `request_id`, errores con códigos estables.
- Migración `0001`: esquemas `core` y `audit`; usuarios, organizaciones, membresías, roles, permisos, sesiones; auditoría de solo inserción con cadena de hashes; eventos de seguridad; catálogo de roles y permisos.
- Configuración inicial (organización + propietario), ingreso, cierre de sesión, cambio de contraseña, bloqueo por intentos.
- Gestión de usuarios con roles y reglas de propietario; datos de la organización con validación del DV del RUC.
- Consulta y verificación de integridad de la auditoría.
- Frontend: sistema de diseño (tokens claro/oscuro, componentes), configuración inicial, ingreso, inicio con puesta en marcha, empresa, usuarios y roles, auditoría, mi cuenta.
- Tauri 2 configurado (`desktop/`): identidad, ventana, CSP, íconos. Sin compilar.
- PostgreSQL 18 de desarrollo en Docker (`127.0.0.1:55433`).
