# Estado del proyecto

**Última actualización:** 2026-11-25 · **Fase actual:** 1B — Instalador para Windows 11

## Resumen

| Fase | Estado |
|---|---|
| 0 — Discovery y auditoría | ✅ Completa |
| 1 — Fundación | ✅ Funcional en navegador |
| 1B — Instalador Windows 11 | 🟡 CI verde en Windows real (lanzador, copias, instalador instalado, abierto, cerrado y desinstalado). Falta instalarlo en la PC del propietario |
| 2 — Finanzas empresa/personal | 🟡 Backend y interfaz hechos; probado de punta a punta en navegador (ver tabla). Falta validarlo con extractos reales del propietario |
| 3 — Contabilidad (núcleo) | ✅ Backend e interfaz hechos; probado de punta a punta en navegador (ver tabla). El plan de cuentas sigue sin validar por un contador |
| 3B — Activos fijos, centros, recurrentes, XLSX | ✅ Backend e interfaz hechos; probado de punta a punta en navegador (ver tabla). Vidas útiles, residuales y cuadro fiscal `pending` hasta que los valide el contador; descarga de Excel en la app de escritorio sin probar |
| 4 — Tributación (núcleo) | 🟡 Backend e interfaz hechos; probado de punta a punta en navegador (ver tabla). Las 39 reglas y los feriados quedan `pending` hasta que los verifique el contador; nada se presenta en Marangatu. Falta probarlo con datos reales y el perfil del propietario |
| 5 a 8 | ⏳ No iniciadas |

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
| Contabilidad: cierre del ejercicio con refundición, subcuentas, archivo de cuentas | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Activos fijos: 34 categorías propuestas sin validar, completar, validar (solo `accounting.post`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Activos fijos: alta de bienes (fiscal/contable, aviso pre 14-10-2021), plan de cuotas | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Activos fijos: depreciación del mes (409 por mes salteado), contabilización, baja con acta | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Activos fijos: cuadro de depreciación (RG 77/2020) conciliado con el balance | ✅ | ✅ | n/a | n/a | ✅ | ✅ + E2E | ✅ |
| Activos fijos: edición de bienes y categorías, archivo, configuración por defecto | ✅ | ✅ | ✅ | ✅ | ✅ | unitarias + prueba manual (sin E2E) | ✅ |
| Activos fijos: aviso del 422 por categoría incompleta al calcular la depreciación | ✅ | ✅ | n/a | ✅ | ✅ | sin E2E ni prueba manual (el alta ya rechaza categorías incompletas) | ✅ |
| Centros de costos: alta, solo en líneas de resultado, obligatorios si se configura, resultados por centro | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Centros de costos: edición y archivo | ✅ | ✅ | ✅ | ✅ | ✅ | unitarias + prueba manual (sin E2E) | ✅ |
| Asientos recurrentes: plantilla, aviso del mes, generación sin duplicar | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Asientos recurrentes: edición, pausa y reactivación | ✅ | ✅ | ✅ | ✅ | ✅ | prueba manual (sin E2E) | ✅ |
| Balance de comprobación con saldo inicial (refundición del ejercicio anterior) | ✅ | ✅ | n/a | n/a | ✅ | ✅ + E2E | ✅ |
| Exportar a Excel (navegador) e imprimir / PDF | ✅ | ✅ | n/a | n/a | ✅ | ✅ + E2E (comprobación y cuadro; el resto, a mano) | ✅ |
| Exportar a Excel en la app de escritorio (Tauri) | 🟡 | ✅ | n/a | n/a | ✅ | sin probar | ✅ |
| Tributación: reglas y feriados candidatos (sin verificar), verificación del contador, feriado con fuente, excepciones | ✅ | ✅ | ✅ | ✅ | ✅ (Administrador no verifica; Consulta solo lee) | ✅ + E2E (excepciones y deprecar: sin E2E) | ✅ |
| Tributación: perfil fiscal con el asistente, versiones, verificación con la constancia | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Tributación: calendario (sincronizado, corrimientos, `remind_by`), presentar, pagar, no aplica, reabrir | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E (generación; las acciones, sin E2E) | ✅ |
| Tributación: carga de comprobantes en tanda, registro del mes, anulación, asiento propuesto, Excel y Marangatu | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E (carga y registro; el resto, sin E2E) | ✅ |
| Tributación: IVA del mes, control contra el mayor, F120 en borrador, copia a la obligación; avisos; configuración | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |

## Pruebas ejecutadas (2026-11-24)
- Interfaz fase 4: Vitest 212/212; `tsc -b` y build OK; oxlint sin advertencias nuevas en tributación salvo la ya conocida de `VoucherForm.tsx` (exporta un hook); E2E 47/47 (38 previas + 9 de `tributacion.spec.ts`) en una base propia (`contador_e2e_f4`).
- Backend fase 4 (integrado en `main`, CI verde): `pytest` 322 aprobadas (241 previas + 81 nuevas de tributación, incluidas las lentas) contra PostgreSQL 18, 6 min 30 s; ruff, `ruff format` y mypy estricto sin errores; `alembic check` limpio; `downgrade 0004` → `upgrade head` con datos OK y la bajada se niega con comprobantes u obligaciones presentadas. Los 18 triggers nuevos se quitaron uno por uno (dentro de la transacción de la prueba) y su prueba falló cada vez. Estimación de IVA de un mes con 20.000 comprobantes ~44 ms; XLSX del año ~1,3 s. Ejecutable PyInstaller (`packaging/contador-backend.spec`, compila en ~31 s) probado sobre una base vacía: migra hasta 0005 al arrancar, `POST /tax/rules/load-candidates` carga 39 reglas (y 7 excepciones), feriados 45, el perfil con 211 y 955 genera 28 obligaciones (la sincronización siguiente no crea ninguna), las alertas responden y el XLSX del registro abre.
- Interfaz 3B: Vitest 124/124 (34 nuevas); `tsc -b` y build OK; oxlint con las mismas 2 advertencias; E2E 38/38 (10 + 8 + 11 de `contabilidad.spec.ts` + 9 de `contabilidad-3b.spec.ts`), dos corridas seguidas en verde (~75 s cada una).
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
| P-9 | ~~La API no tiene `GET /finance/contexts/{cid}/transactions/{id}`~~ | **Resuelto**: en la API (`test_finance_transaction_detail.py`) y en la interfaz, que lee el movimiento de origen por id aunque los filtros de la lista lo excluyan (E2E en `contabilidad-3b.spec.ts`) |
| P-11 | Detalles menores de la API | El 422 `ASSET_CATEGORY_INCOMPLETE` trae nombres pero no ids (la interfaz enlaza por nombre); las plantillas recurrentes no admiten moneda extranjera (`RecurringLineOut` sin `fx_*`, la interfaz lo deshabilita) |
| P-12 | Descarga de Excel dentro de la app de escritorio sin probar | Probada en el navegador; en WebView2 debería abrir la descarga normal (`saveBlob`). Probarla al instalar en la PC real |
| P-13 | El aviso de recurrentes en el E2E solo se verifica en 2026 | `contabilidad-3b.spec.ts` lo condiciona a `getFullYear() === 2026`; desde 2027 esa parte se saltea hasta ajustar las fechas de la prueba |
| P-10 | ~~Los asientos traen el id de quien creó/contabilizó, no el nombre~~ | **Resuelto**: en la API (`test_accounting_entry_user_names.py`) y en la interfaz (asiento y libro diario, sin leer `/users`) |

## Decisiones tomadas en esta sesión
D-001 a D-123 en `DECISIONS.md`. **D-007 (facturación como servicio Node) requiere tu confirmación.**

## Información requerida del propietario
1. **Confirmar D-007**: reutilizar el núcleo SIFEN como servicio Node (recomendado) en lugar de portarlo a Python.
2. **Repositorio original del CRM de Zestia** (el que contiene `@crm/contracts`, `test/helpers/certificate.ts`, etc.). El extracto no trae los helpers de prueba ni `contracts/invoicing.ts`; sin ellos hay que recrearlos.
3. **Constancia de RUC** de la EAS: RUC, DV, obligaciones inscriptas, actividades económicas, fecha de cierre del ejercicio.
4. **Facturación electrónica**: estado de la habilitación, timbrado de pruebas, certificado de firma (prestador habilitado), IdCSC/CSC de pruebas.
5. ~~Contador/a responsable~~ **No hay (D-118):** la herramienta cumple ese rol y verifica contra las fuentes oficiales, con tu aprobación.
6. **Bancos** con los que opera (para preparar los adaptadores de extractos) y un extracto de ejemplo anonimizado.
7. **Probar el instalador** en la PC con Windows 11 y avisar el resultado (y si el nombre de usuario de Windows tiene tildes o ñ).
8. Revisar los hallazgos R-10 y R-11 de `DISCOVERY.md` (repositorio git en la carpeta personal con `.git-credentials`).
9. **Credenciales de Marangatu** para el bot (D-119), cuando lleguemos a esa fase. Se guardan en el almacén de credenciales de Windows, nunca en el repositorio.
10. ~~Confirmar la D-119~~ **Decidido (2026-11-25):** el bot presenta solo, sin pedir aprobación, con las 12 condiciones de la D-119 (ante la duda no presenta y avisa). Falta confirmar si el bot también paga (por ahora no).
11. **Estatuto de la EAS** (D-3): el plazo que fija para poner las utilidades a disposición. De eso depende cuándo nace la retención del IDU.
12. **Municipio de la EAS**, para la patente municipal.

## Para retomar (traspaso, 2026-11-25)
**Estado de `main`:** fases 0 a 3B y la fase 4 (tributación, backend e interfaz) integradas. Pruebas: backend 0 (pytest contra PostgreSQL real, incluidas las `slow`), Vitest 212, E2E 47 (`flujos`, `finanzas`, `contabilidad`, `contabilidad-3b`, `tributacion`). Migraciones hasta `0005_tributacion`. Último CI (`dbb1933`, corrida 45667778513, con las D-121 a D-123) verde en los 5 jobs; el diario XLSX de 20.000 líneas tarda 0,48 s en el runner (antes 3,0 a 3,1 s): `secrets`, `test`, `e2e`, `performance` y `windows` (instalador NSIS generado y probado, ya con la tributación).

**Fase 4:** menú Impuestos (Resumen fiscal, Calendario, Comprobantes, IVA del mes, Perfil fiscal, Reglas y feriados, Configuración) y avisos en Inicio. Decisiones D-082 a D-116.
- **Antes de usarlo en serio** (lo hace la herramienta con tu aprobación, D-118): cargar y verificar las reglas en uso y los feriados (Impuestos → Reglas y feriados), declarar y verificar el perfil fiscal con la constancia de RUC, y responder las dudas D-F4-1 a D-F4-14 de `docs/research/TRIBUTACION_FASE4.md`. Probar el archivo de Marangatu con uno o dos comprobantes antes de un mes entero.
- Abierto: sábados como inhábiles (D-F4-11); redondeo del IVA por comprobante (D-F4-7); casillas 33/36/39 y 164 del F120 vacías hasta saber del prorrateo (D-F4-14); la nota de débito electrónica no controla el tipo del CDC (D-107).
- ~~**CI `performance` intermitente**~~ **Resuelto (D-117, 2026-11-25):** el diario en XLSX usa el escritor propio (`accounting/fast_xlsx.py`). En esta PC bajó de 2,2 s a 0,6 s; en el runner tardaba de 3,0 a 3,1 s contra un límite de 3 s.
- Windows no distingue mayúsculas: dos archivos como `VoucherForm.tsx` y `voucherForm.ts` rompen el build del instalador. El job `secrets` del CI ya lo rechaza en Linux.
- Sin E2E (probado solo con pruebas unitarias y del backend): presentar, pagar y reabrir obligaciones; anular y proponer el asiento de un comprobante; descarga del archivo de Marangatu; deprecar reglas; excepciones de vencimiento.

**Lo primero:**
1. El propietario prueba el instalador NSIS (artefacto `contador-ai-windows-instalador` del último CI verde, vence a los 30 días) en su PC con Windows 11: P-8 (usuario con tildes o ñ) y P-12 (descarga de Excel dentro de la app).
2. **Rol del contador → la herramienta (D-118).** El mecanismo ya está hecho (D-120, 2026-11-25): ninguna pantalla pide nombre ni matrícula. Quien verifica es CONTADOR AI, contra la fuente oficial, y tu clic queda en la auditoría. En Impuestos → Reglas y feriados, «Verificar las N con fuente oficial» verifica de una vez las reglas con la fuente oficial leída (37 de 39) y lista las otras 2 con el motivo. **Falta el contenido:** la herramienta verifica contra la fuente oficial el plan de cuentas (173 cuentas, `docs/research/PLAN_DE_CUENTAS_PY.md`), las 34 categorías de activo fijo, las dudas D-DEP de `docs/research/DEPRECIACION_PY.md` y, en la fase 4, las reglas, el perfil y las dudas D-F4. Hay que investigar si alguna presentación exige por ley la firma de un contador matriculado (la baja de bienes ya pide el acta de un contador o de un auditor, Decreto 3182, art. 58). **Bloque 1 hecho (D-121, 2026-11-25):** IDU y beneficiarios finales verificables; D-5 resuelta. Quedan sin fuente leída 2 reglas (dígito verificador del RUC y patente municipal) y falta leer la RG 110/2013. **Bloque 2 hecho (D-122):** el IVA del Formulario 120 se calcula con la tasa sobre la suma de las bases; resueltas D-F4-3, 4, 5, 6, 7 y 11. Quedan D-F4-1 (se prueba en Marangatu), 2, 8, 9, 10, 12, 13 y 14. **Bloque 3 hecho en lo que se puede leer (D-123):** las 17 dudas D-DEP quedan clasificadas; 7 solo las resolvería una consulta vinculante a la DNIT. Falta verificar en profundidad el plan de cuentas contra la RG 49/2014.

**Después:**
- **Bot de Marangatu (D-119, nuevo objetivo del propietario):** la herramienta revisa si hay algo para presentar, presenta los registros de comprobantes y los documentos, hace las declaraciones juradas y descarga las constancias, con un bot de navegador (Playwright) que hace los clics. Antes: investigar el portal (captcha, segundo factor, condiciones de uso, servicios web oficiales), las credenciales en el almacén de Windows, un modo de ensayo. Presenta solo, sin pedir aprobación, con las 12 condiciones de la D-119.
- **Fase 4 (tributación)**: cargar el perfil fiscal real del propietario (régimen IRE General o SIMPLE, obligaciones, cierre del ejercicio) y probar con comprobantes reales de un mes. Lo presenta el bot de Marangatu cuando exista (D-119).
- Fase 2: probar el importador con extractos reales anonimizados del propietario y guardar un mapeo por banco.
- CI de Windows: si algo falla, el paso "Lanzador — registros si falló" muestra cada comando (`$ ...`) y su resultado (`→`); la prueba del instalador vuelca `%LOCALAPPDATA%\ContadorAI\logs` y su paso 4b informa si el cierre cayó durante el arranque. `gh run view --log` a veces sale vacío: usar `gh api repos/mandarinagg/Contador/actions/jobs/<id>/logs`.
- Sigue abierto, decisión del propietario: tabla de totales mensuales para el resumen (solo si en la PC real se nota lento).

**Limpieza pendiente:** el worktree `.claude/worktrees/agent-a2d82accdd256c977` (rama `worktree-agent-a2d82accdd256c977`, ya integrada en `main`) se puede borrar.

**Entorno local:** Postgres de desarrollo en el proyecto docker `contador` (127.0.0.1:55433). Para probar el lanzador sin `sudo` se usan los binarios de PostgreSQL 18 de Ubuntu (`apt download` + `dpkg-deb -x`, con `LD_LIBRARY_PATH`) y las variables `CONTADOR_TEST_PGSQL_BIN` y `CONTADOR_TEST_BACKEND_EXE`. E2E en paralelo con otra corrida: `CONTADOR_E2E_DB_NAME`, `CONTADOR_E2E_API_PORT` y `CONTADOR_E2E_WEB_PORT`.

## Próximo objetivo recomendado
Instalar en la PC real del propietario (cierra la fase 1B). En el código: verificar a fondo el contenido contra las fuentes oficiales (reglas, plan, categorías, dudas D-F4 y D-DEP; D-118) y después diseñar el bot de Marangatu (D-119).
