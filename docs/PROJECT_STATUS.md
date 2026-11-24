# Estado del proyecto

**Última actualización:** 2026-11-24 · **Fase actual:** 1B — Instalador para Windows 11

## Resumen

| Fase | Estado |
|---|---|
| 0 — Discovery y auditoría | ✅ Completa |
| 1 — Fundación | ✅ Funcional en navegador |
| 1B — Instalador Windows 11 | 🟡 Backend + PostgreSQL portable verdes en Windows real; lanzador Rust y copias probados en Linux. **En Windows la prueba del lanzador se colgaba** al arrancar PostgreSQL: corrección en `2c85642`, pendiente de confirmar en el CI (ver "Para retomar") |
| 2 — Finanzas empresa/personal | 🟡 Backend y interfaz hechos; probado de punta a punta en navegador (ver tabla). Falta validarlo con extractos reales del propietario |
| 3 a 8 | ⏳ No iniciadas |

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

## Pruebas ejecutadas (2026-11-24)
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
**Estado de `main`:** fases 0-1 completas; fase 2 (finanzas) integrada, con backend, interfaz y rendimiento. Todo verde en Linux. No quedan worktrees ni agentes abiertos.

**Lo primero:**
1. **CI de Windows:** ver el resultado del job `windows` del último push. El lanzador se colgaba al arrancar PostgreSQL porque `Command::output` esperaba un pipe que `postgres` hereda y nunca cierra. Ya se corrigió en `stack.rs` (`97be887`) y en `tests/backup.rs` (`2c85642`). Si vuelve a fallar, el paso "Lanzador — registros si falló" muestra cada comando ejecutado (`$ ...`) y su resultado (`→`): buscar el último `$` sin `→`.
2. Con Windows en verde, el propietario prueba el instalador NSIS (artefacto del CI) en su PC con Windows 11 (P-8: usuario con tildes o ñ).

**Después:**
- Fase 2: el importador ya se probó con extractos simulados de formato bancario paraguayo (cabecera del banco, débito y crédito, hora en la fecha, `Gs.`, totales al pie, XLSX con fechas numéricas y fórmulas), y se corrigieron 4 casos. Falta probarlo con extractos reales anonimizados del propietario (punto 6 de abajo) y guardar un mapeo por banco.
- Fase 3: el plan de cuentas y las reglas tributarias de `docs/research/` siguen `pending` hasta que los valide el contador.
- Sigue abierto, decisión del propietario: tabla de totales mensuales para el resumen. No se hizo: se revisa solo si en la PC real se nota lento.

**Entorno local:** Postgres de desarrollo en el proyecto docker `contador` (127.0.0.1:55433). Para probar el lanzador sin `sudo` se usan los binarios de PostgreSQL 18 de Ubuntu (`apt download` + `dpkg-deb -x`, con `LD_LIBRARY_PATH`) y las variables `CONTADOR_TEST_PGSQL_BIN` y `CONTADOR_TEST_BACKEND_EXE`. E2E en paralelo con otra corrida: `CONTADOR_E2E_DB_NAME`, `CONTADOR_E2E_API_PORT` y `CONTADOR_E2E_WEB_PORT`.

## Próximo objetivo recomendado
Cerrar la fase 1B (CI de Windows en verde e instalador probado en la PC real) y validar la fase 2 con datos reales.
