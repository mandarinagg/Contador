# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado semántico.

## [Sin publicar]

### Agregado — Fase 0 (2026-11-23)
- `docs/PROMPT_MAESTRO.md`: prompt del propietario convertido a Markdown como documento rector.
- `docs/DISCOVERY.md`: diagnóstico del entorno, repositorios y riesgos.
- `docs/INTEGRATIONS.md`: auditoría del proyecto `facturacion-sifen-zestia` y propuesta de integración.
- Documentación obligatoria: PRD, arquitectura, esquema, reglas, tributación, seguridad, API, pruebas, hoja de ruta, decisiones, estado.

### Agregado — Fase 1B (2026-11-23)
- Plataforma objetivo definida: Windows 11, una sola PC (D-016 a D-020).
- `python -m app`: el backend aplica migraciones y levanta la API (modo empaquetado).
- `backend/packaging/contador-backend.spec`: backend como ejecutable con PyInstaller (verificado en Linux).
- `.github/workflows/ci.yml`: pruebas en Linux y empaquetado + prueba de humo en Windows con PostgreSQL 18.7 portable (sin ejecutar todavía: falta el primer push).

### Agregado — Fase 1 (2026-11-23)
- Backend FastAPI: configuración por entorno, logging JSON con `request_id`, errores con códigos estables.
- Migración `0001`: esquemas `core` y `audit`; usuarios, organizaciones, membresías, roles, permisos, sesiones; auditoría de solo inserción con cadena de hashes; eventos de seguridad; catálogo de roles y permisos.
- Configuración inicial (organización + propietario), ingreso, cierre de sesión, cambio de contraseña, bloqueo por intentos.
- Gestión de usuarios con roles y reglas de propietario; datos de la organización con validación del DV del RUC.
- Consulta y verificación de integridad de la auditoría.
- Frontend: sistema de diseño (tokens claro/oscuro, componentes), configuración inicial, ingreso, inicio con puesta en marcha, empresa, usuarios y roles, auditoría, mi cuenta.
- Tauri 2 configurado (`desktop/`): identidad, ventana, CSP, íconos. Sin compilar.
- PostgreSQL 18 de desarrollo en Docker (`127.0.0.1:55433`).
