# Estado del proyecto

**Última actualización:** 2026-11-24 · **Fase actual:** 1B — Instalador para Windows 11

## Resumen

| Fase | Estado |
|---|---|
| 0 — Discovery y auditoría | ✅ Completa |
| 1 — Fundación | ✅ Funcional en navegador |
| 1B — Instalador Windows 11 | 🟡 CI verde en Windows real (lanzador, copias, instalador instalado, abierto, cerrado y desinstalado). Falta instalarlo en la PC del propietario |
| 2 — Finanzas empresa/personal | 🟡 Backend y interfaz hechos; probado de punta a punta en navegador (ver tabla). Falta validarlo con extractos reales del propietario |
| 3 — Contabilidad (núcleo) | 🟡 Backend e interfaz hechos; probado de punta a punta en navegador (ver tabla). El plan de cuentas sigue sin validar por un contador |
| 3B — Activos fijos, centros, recurrentes, XLSX | 🟡 Backend hecho (`docs/specs/FASE3B_CONTABILIDAD.md`, D-068 a D-081). Falta la interfaz. Vidas útiles, residuales y cuadro fiscal `pending` hasta que los valide el contador |
| 4 a 8 | ⏳ No iniciadas |

**Destino definido por el propietario:** una PC con Windows 11, uso en una sola máquina (D-016). Desarrollo en esta PC Linux; instaladores generados en GitHub Actions.

## Funcionalidades operativas (probadas de punta a punta)

| Funcionalidad | UI | API | Persistencia | Validación | Permisos | Pruebas | Docs |
|---|---|---|---|---|---|---|---|
| Configuración inicial (empresa + propietario) | ✅ | ✅ | ✅ | ✅ | n/a (solo base vacía) | ✅ + E2E | ✅ |
| Ingreso / cierre de sesión / bloqueo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Cambio de contraseña | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Usuarios y roles | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Datos de la empresa + DV del RUC | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Auditoría inmutable + verificación | ✅ | ✅ | ✅ | n/a | ✅ | ✅ + E2E | ✅ |
| Eventos de seguridad | ✅ | ✅ | ✅ | n/a | ✅ | ✅ + E2E | ✅ |
| Tema claro / oscuro / sistema | ✅ | n/a | preferencia local | n/a | n/a | E2E | ✅ |
| Finanzas: selector de contexto y espacio personal privado | ✅ | ✅ | ✅ | ✅ | ✅ (404 a otros usuarios, también por API) | ✅ + E2E | ✅ |
| Finanzas: cuentas (alta, saldo, moneda) | ✅ | ✅ | ✅ | ✅ | ✅ (Consulta solo lee) | ✅ + E2E | ✅ |
| Finanzas: movimientos manuales y anulación con motivo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Finanzas: transferencia entre cuentas propias (misma moneda) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Finanzas: importar extracto CSV (duplicados, errores, decisión por fila, duplicados nuevos al confirmar) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Finanzas: resumen por moneda y consolidado por contexto | ✅ | ✅ | n/a | n/a | ✅ | ✅ + E2E | ✅ |
| Finanzas: categorías, contrapartes, edición, categoría rápida, transferencia entre monedas, XLSX, `IMPORT_STALE` | ✅ | ✅ | ✅ | ✅ | ✅ | unitarias + prueba manual (sin E2E) | ✅ |
| Contabilidad: plan propuesto, aviso «sin validar», búsqueda, cuenta de resultados, validación con nombre y matrícula | ✅ | ✅ | ✅ | ✅ | ✅ (Administrador no valida) | ✅ + E2E | ✅ |
| Contabilidad: ejercicio con 12 períodos; cierre de período (bloquea con borradores), reapertura con motivo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Contabilidad: asiento manual (desbalanceado no se contabiliza), contabilización con número, reversión, descarte | ✅ | ✅ | ✅ | ✅ | ✅ (Administrador no contabiliza; Consulta solo lee) | ✅ + E2E | ✅ |
| Contabilidad: asiento propuesto desde un movimiento de la empresa (cuentas contables configuradas al proponer, dólares con redondeo elegido), movimiento bloqueado al contabilizar | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Contabilidad: libro diario, mayor, balance de comprobación, balance general, estado de resultados | ✅ | ✅ | n/a | n/a | ✅ | ✅ + E2E | ✅ |
| Contabilidad: cierre del ejercicio con refundición, subcuentas, archivo de cuentas | ✅ | ✅ | ✅ | ✅ | ✅ | backend + prueba manual (sin E2E) | ✅ |

## Pruebas ejecutadas (2026-11-24)
- Backend 3B (rama del agente): 239/239 pytest (4 `slow`); ruff, `ruff format` y mypy estricto sin errores; `alembic check` limpio; `downgrade 0003` → `upgrade head` con datos OK. Las 22 reglas nuevas de la base se quitaron una por una y su prueba falló cada vez. Backend empaquetado (PyInstaller, Linux): migró una base nueva a la 0004, cargó las 34 categorías y exportó XLSX. Corrida de 2.000 bienes ~0,4 s; XLSX del diario con 20.000 líneas ~2,1 s.
- Interfaz de contabilidad: Vitest 90/90 (36 nuevas); `tsc -b` y build OK (414 kB JS inicial; contabilidad en fragmentos aparte); oxlint sin advertencias nuevas; E2E 27/27 (10 + 8 + 9 de `contabilidad.spec.ts`), dos corridas seguidas en verde (52 y 62 s). Cierre del ejercicio con refundición probado a mano.
- Interfaz de finanzas: Vitest 53/53; `tsc -b` y build OK (409 kB JS inicial; finanzas en fragmentos aparte); oxlint sin advertencias nuevas; E2E 18/18 (10 de `flujos.spec.ts` + 8 de `finanzas.spec.ts`), dos corridas seguidas en verde (50 y 58 s). La prueba de privacidad (tres usuarios) va con `test.slow()`: con la PC cargada superaba los 30 s por defecto.
- Backend: 87/87 pytest (86 + 1 `slow`; incluye las 3 nuevas de extractos reales); resumen anual con 100.000 movimientos en ~48 ms con la máquina libre y 153-289 ms cargada (límite 300; D-033). Importaciones simultáneas sin duplicados (D-034).
- Lanzador en Linux (PostgreSQL 18 de Ubuntu + backend empaquetado): `first_run_restart_and_recovery` y `daily_backup_retention_and_restore` OK; `cargo fmt` y `clippy -D warnings` sin errores.
- CI (push `66b729c`): secretos ✅, Linux ✅, Windows real ✅ (backend empaquetado + PostgreSQL 18.7 portable: migración, configuración inicial, ingreso, auditoría).
- Lanzador con PostgreSQL 18.6 de Ubuntu + backend empaquetado: primer arranque, reinicio con datos persistidos e ingreso, rechazo sin contraseña sin tocar datos, rechazo de carpeta ajena sin borrarla.
- App de escritorio en modo release en Linux: crea la base, levanta todo en 4 s; contraseña con permisos 600.
- `cargo fmt`, `clippy -D warnings` (Linux) sin errores.

## Pruebas ejecutadas (2026-11-23)
- Backend empaquetado (PyInstaller, Linux): migró una base vacía, configuración inicial e ingreso OK; usa psycopg binario.
- Ruedas para Windows + Python 3.14 verificadas para todas las dependencias del backend; zip de PostgreSQL 18.7 para Windows verificado (estructura `pgsql/bin|lib|share`).
- Backend: 28/28 pytest contra PostgreSQL 18.7; ruff y mypy estricto sin errores; `alembic check` sin diferencias; `downgrade base` → `upgrade head` OK.
- Frontend: 10/10 Vitest; `tsc -b` OK; build de producción OK (397 kB JS, 123 kB gzip).
- E2E: 10 pruebas de Playwright en `frontend/e2e/` (Chromium, base aislada, sin errores de consola), en el job `e2e` del CI (ver `TESTING_STRATEGY.md`).

## Problemas conocidos / pendientes técnicos
| # | Pendiente | Motivo |
|---|---|---|
| P-1 | Código Windows del lanzador sin compilar localmente | Falta `llvm-rc` (requiere `sudo`); lo compila y prueba el CI en Windows |
| P-2 | Instalador sin firma de código | Windows muestra "Windows protegió su PC" → "Más información" → "Ejecutar de todas formas" |
| P-8 | Ruta de datos con caracteres no ASCII | Si el usuario de Windows tiene tildes o ñ en el nombre, PostgreSQL podría fallar en `initdb`; a verificar en la PC real |
| P-7 | Advertencia de PyInstaller `psycopg_binary._uuid` | Inofensiva: la receta de psycopg menciona un módulo que no existe en 3.3.9; el ejecutable usa la implementación binaria (verificado) |
| P-3 | ~~Script E2E fuera del repo~~ | **Resuelto**: `frontend/e2e/` con `@playwright/test` y job `e2e` en el CI |
| P-4 | 2 advertencias de oxlint (`only-export-components`) | Hooks junto a sus providers; solo afecta la recarga en caliente |
| P-6 | La política de contraseñas del frontend cuenta como "símbolo" las letras con tilde | El backend es quien decide (Unicode); solo cambia el aviso previo |
| P-9 | ~~La API no tiene `GET /finance/contexts/{cid}/transactions/{id}`~~ | **Resuelto en la API**: existe, con las reglas de acceso del listado y los anulados incluidos (`test_finance_transaction_detail.py`). Falta que la interfaz lo use en lugar de buscar en la lista |
| P-10 | ~~Los asientos traen el id de quien creó/contabilizó, no el nombre~~ | **Resuelto en la API**: `created_by_name` y `posted_by_name` en los asientos y el libro diario, sin otro dato del usuario (`test_accounting_entry_user_names.py`). Falta que la interfaz los muestre en lugar de leer `/users` |

## Decisiones tomadas en esta sesión
D-001 a D-034 en `DECISIONS.md`. **D-007 (facturación como servicio Node) requiere tu confirmación.**

## Información requerida del propietario
1. **Confirmar D-007**: reutilizar el núcleo SIFEN como servicio Node (recomendado) en lugar de portarlo a Python.
2. **Repositorio original del CRM de Zestia** (el que contiene `@crm/contracts`, `test/helpers/certificate.ts`, etc.). El extracto no trae los helpers de prueba ni `contracts/invoicing.ts`; sin ellos hay que recrearlos.
3. **Constancia de RUC** de la EAS: RUC, DV, obligaciones inscriptas, actividades económicas, fecha de cierre del ejercicio.
4. **Facturación electrónica**: estado de la habilitación, timbrado de pruebas, certificado de firma (prestador habilitado), IdCSC/CSC de pruebas.
5. **Contador/a responsable** que validará las reglas tributarias (nombre/matrícula para el campo "revisado por").
6. **Bancos** con los que opera (para preparar los adaptadores de extractos) y un extracto de ejemplo anonimizado.
7. **Probar el instalador** en la PC con Windows 11 y avisar el resultado (y si el nombre de usuario de Windows tiene tildes o ñ).
8. Revisar los hallazgos R-10 y R-11 de `DISCOVERY.md` (repositorio git en la carpeta personal con `.git-credentials`).

## Para retomar (traspaso, 2026-11-24)
**Estado de `main`:** fases 0-1 completas; fase 2 (finanzas) integrada, con backend, interfaz y rendimiento. Todo verde en Linux y en Windows. Fase 3 (núcleo): backend e interfaz hechos (`docs/specs/FASE3_CONTABILIDAD.md`); falta que el contador valide el plan de cuentas.

**Lo primero:**
1. **CI de Windows: ✅ todo verde desde `7c98639`** (ejecución 45390713831). Pasan el lanzador, las copias, el Administrador de credenciales, el instalador NSIS y su prueba completa en Windows real.
   - Con la migración 0003 (`btree_gist`), el primer arranque en Windows funciona. Apareció una carrera: cerrar la app durante el arranque dejaba PostgreSQL en marcha. Se corrigió en `lib.rs` (la salida espera al hilo de arranque) y se agregó el paso 4b a la prueba del instalador.
   - Causas que se resolvieron: el pipe que `postgres` hereda (`stack.rs`, `tests/backup.rs`), la ruta `\\?\` que `initdb` no entiende (`stack::plain_path`) y el código 3 de `pg_ctl status` al final del script.
   - Si algo vuelve a fallar, el paso "Lanzador — registros si falló" muestra cada comando ejecutado (`$ ...`) y su resultado (`→`). La prueba del instalador vuelca `%LOCALAPPDATA%\ContadorAI\logs`. `gh run view --log` a veces sale vacío; usar `gh api repos/mandarinagg/Contador/actions/jobs/<id>/logs`.
2. El propietario prueba el instalador NSIS (artefacto `contador-ai-windows-instalador` del CI, vence a los 30 días) en su PC con Windows 11 (P-8: usuario con tildes o ñ).

**Después:**
- Fase 2: el importador ya se probó con extractos simulados de formato bancario paraguayo (cabecera del banco, débito y crédito, hora en la fecha, `Gs.`, totales al pie, XLSX con fechas numéricas y fórmulas), y se corrigieron 4 casos. Falta probarlo con extractos reales anonimizados del propietario (punto 6 de abajo) y guardar un mapeo por banco.
- Fase 3: el plan de cuentas y las reglas tributarias de `docs/research/` siguen `pending` hasta que los valide el contador.
- Sigue abierto, decisión del propietario: tabla de totales mensuales para el resumen. No se hizo: se revisa solo si en la PC real se nota lento.

**Entorno local:** Postgres de desarrollo en el proyecto docker `contador` (127.0.0.1:55433). Para probar el lanzador sin `sudo` se usan los binarios de PostgreSQL 18 de Ubuntu (`apt download` + `dpkg-deb -x`, con `LD_LIBRARY_PATH`) y las variables `CONTADOR_TEST_PGSQL_BIN` y `CONTADOR_TEST_BACKEND_EXE`. E2E en paralelo con otra corrida: `CONTADOR_E2E_DB_NAME`, `CONTADOR_E2E_API_PORT` y `CONTADOR_E2E_WEB_PORT`.

## Próximo objetivo recomendado
Cerrar la fase 1B (CI de Windows en verde e instalador probado en la PC real) y validar la fase 2 con datos reales.
