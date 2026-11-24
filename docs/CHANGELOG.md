# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado semántico.

## [Sin publicar]

### Agregado — Investigación tributaria (2026-11-24)
- `docs/research/TRIBUTACION_PY.md`: investigación con fuentes oficiales sobre:
  - EAS (Ley 6480 y Decreto 3998)
  - IVA, IRE (General, SIMPLE y RESIMPLE), IDU, IRP y anticipos
  - calendario por terminación de RUC
  - registro de comprobantes (RG 90/2021)
  - estados financieros y SIFEN
  - IPS y MTESS.
  Incluye contradicciones y dudas para el contador, y lo no verificado.
- `docs/research/tax_rules_candidatas.yaml`: 25 reglas candidatas en formato `tax_rule_versions`, todas `pending`.
- `docs/research/PLAN_DE_CUENTAS_PY.md` y `docs/research/plan_de_cuentas_propuesto.yaml`:
  - no hay un plan de cuentas oficial obligatorio
  - se propone un plan de 159 cuentas sobre los códigos de la RG 49/2014, a validar.
- `docs/TAX_COMPLIANCE_PARAGUAY.md`: enlaza la investigación y resume su estado. Nada se marca como verificado.

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
