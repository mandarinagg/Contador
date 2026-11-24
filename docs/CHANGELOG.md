# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado semántico.

## [Sin publicar]

### Corregido — Importación de extractos con formatos reales (2026-11-24)
- Se probó el importador con extractos armados como los de los bancos paraguayos. Cuatro casos válidos daban error de fila y ahora se leen bien:
  - fecha con la hora de la operación (`15/01/2026 10:23`);
  - moneda escrita junto al importe (`Gs. 1.500.000`, `US$ 20,00`), aceptada solo si es la de la cuenta;
  - fecha de XLSX guardada como número de serie;
  - importe de XLSX calculado con decimales fantasma (`1234.5600000000001` → `1234,56`, 15 dígitos como Excel).
- La interfaz reconoce el formato de fecha aunque traiga la hora.
- Pruebas nuevas: `test_parse_amount_with_written_currency`, `test_parse_date_ignores_time_and_reads_excel_serials` y `test_realistic_bank_statements` (por la API); en Vitest, la fecha con hora.

### Corregido — Lanzador en Windows (2026-11-24)
- La prueba de copias (`tests/backup.rs`) arrancaba `pg_ctl` con `Command::output`: en Windows `postgres` hereda los handles del pipe y la prueba esperaba para siempre. Ahora la salida va a un archivo, igual que en `stack.rs`.
- CI: límites de tiempo en el job `windows` y registros del lanzador cuando la prueba falla o se cuelga.

### Agregado — Fase 2, interfaz de finanzas (2026-11-24)
- Menú **Finanzas** (Resumen, Movimientos, Cuentas, Importar extracto, Categorías, Contrapartes) y selector de contexto permanente: pestañas Empresa / Personal ("solo vos") / Consolidado, franja que dice dónde se opera y si es solo lectura, y botón para crear el espacio personal. El contexto va en la URL (`/finanzas/:cid/...`); `localStorage` solo recuerda cuál abrir (`contador.finanzas.contexto.<usuario>`).
- **Resumen**: período (últimos 12 meses, este año, año anterior o fechas), un bloque por moneda (nunca se suman monedas), saldo en cuentas, entradas, salidas y neto, gráfico propio en SVG de entradas/salidas/neto por mes con vista de tabla y tooltip accesible por teclado, gastos por categoría y saldo por cuenta. **Consolidado** por contexto y moneda, identificando Empresa y Personal (BR-FIN-02).
- **Cuentas**: alta, edición, archivo; solo los últimos 4 dígitos; moneda y saldo inicial bloqueados con explicación cuando la cuenta tiene movimientos (y el 409 de la API si igual se intenta).
- **Movimientos**: filtros en la URL (cuenta, categoría, contraparte, fechas, texto, sin revisar, anulados), paginación por cursor, alta manual con sentido entra/sale, edición, marcar revisado, categoría rápida desde la lista, anulación con motivo obligatorio (tachado y atenuado, nunca se borra) y transferencias entre cuentas propias (misma moneda o con importe de salida y de entrada).
- **Importar extracto** en 4 pasos: archivo (CSV/XLSX) → columnas (lectura local del archivo para proponer el mapeo y previsualizarlo, reuso del mapeo de la última importación de la cuenta) → revisión (válidas, duplicadas contra la base y dentro del archivo, con error; importar u omitir por fila) → confirmar o cancelar. Maneja `IMPORT_NEW_DUPLICATES` e `IMPORT_STALE` explicando qué hacer. Nada se crea hasta confirmar.
- **Categorías** (gastos/ingresos, un nivel de subcategorías, archivo, conjunto sugerido) y **Contrapartes** (búsqueda, RUC con DV validado en vivo, archivo).
- `lib/money.ts`: importes siempre como string; formato paraguayo (`₲ 1.234.567`, `US$ 1.234,50`) y entrada que acepta `1.234.567` o `1234567,50` y envía el string normalizado. Positivo entra, negativo sale: color **y** signo.
- Rol Consulta: lee la empresa sin acciones de escritura (con explicación); cualquier rol opera su propio espacio personal.
- Tokens nuevos `personal`, `personal-soft`, `chart-in`, `chart-out` (claro y oscuro). Finanzas se carga aparte (división de código por pantalla). Sin dependencias nuevas: el gráfico es SVG propio y el XLSX se lee con `DecompressionStream` nativo.
- Auditoría: nombres legibles para las acciones de finanzas.
- Pruebas: 43 unitarias nuevas (53 en total) y `e2e/finanzas.spec.ts` con 8 flujos (18 E2E en total). `e2e/env.ts` acepta `CONTADOR_E2E_API_PORT` y `CONTADOR_E2E_WEB_PORT`.

### Cambiado — Rendimiento del resumen financiero y concurrencia de importaciones (2026-11-24)
- `GET /finance/contexts/{cid}/summary` y el consolidado leen los movimientos **una sola vez** (una consulta agrupada con una suma por (cuenta, mes, categoría, signo)) en lugar de tres, y calculan el mes con `date_trunc` en vez de `to_char` por fila. Mismos resultados (prueba de equivalencia nueva); ≈ 40 % menos CPU: con 100.000 movimientos el resumen pasó de ~82 a ~47 ms con la máquina libre y de 222-414 a 153-289 ms con la máquina cargada (D-033).
- Sin índices nuevos ni migración `0003`: los candidatos (índices parciales cubrientes) no dieron mejora medible; planes y mediciones en `docs/DATABASE_SCHEMA.md`.
- `tests/test_finance_performance.py`: 2 corridas de calentamiento y mediana de 9; imprime mediana, mínimo y máximo y si se cumple el objetivo de margen de 120 ms; el límite se puede endurecer con `CONTADOR_PERF_LIMIT_MS`.
- Pruebas nuevas: `test_finance_summary_reference.py` (resumen y consolidado contra un cálculo de referencia en Python sobre ~600 movimientos variados) y `test_finance_import_concurrency.py` (confirmaciones simultáneas con conexiones reales sobre una base propia: mismo lote → uno crea y el otro recibe 409 sin duplicar; dos lotes con filas iguales → el segundo recibe `IMPORT_NEW_DUPLICATES`). No se encontró ninguna carrera en `imports.commit` (D-034).

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
