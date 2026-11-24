# Registro de decisiones (ADR)

Formato: contexto → decisión → alternativas → consecuencias. Estado: **Aceptada**, **Propuesta** (requiere confirmación del propietario) o **Reemplazada**.

## D-001 — Repositorio de trabajo
**Aceptada · 2026-11-23.** Se trabaja en `proyectos/Contador/Contador` (clon de `mandarinagg/Contador`). El `.git` de la carpeta superior es un `git init` sin remoto; no se toca.

## D-002 — Estructura por módulos verticales
**Aceptada.** Cada dominio del backend es un paquete con `models`, `schemas`, `service` y `router`. Sin carpeta `database/` (Alembic en `backend/migrations` es la única fuente del esquema). Alternativa descartada: capas horizontales globales (más saltos entre carpetas por cambio). Detalle en `ARCHITECTURE.md`.

## D-003 — PostgreSQL 18
**Aceptada.** Se usa PostgreSQL 18 (`uuidv7()` y `sha256()` nativos). UUIDv7 da PK ordenadas por tiempo (índices más compactos que UUIDv4) sin extensiones. Consecuencia: la distribución debe empaquetar PostgreSQL ≥ 18.

## D-004 — SQLAlchemy y FastAPI en modo síncrono
**Aceptada.** Uso local con pocos usuarios: el modo síncrono simplifica transacciones, triggers, candados y pruebas (rollback por prueba). Lo asíncrono se reserva para trabajos largos en un worker. Alternativa: async con asyncpg (más complejidad sin beneficio medible aquí).

## D-005 — Dinero
**Aceptada (se implementa en fase 2).** `NUMERIC(20,4)` + código de moneda ISO 4217 en cada importe; `Decimal` en Python; en el frontend los importes viajan como **string** decimal, nunca `number`. El redondeo a la unidad mínima (PYG = 0 decimales) se hace al contabilizar, con reglas explícitas. Las tasas de IVA del SIFEN usan 8 decimales en el XML (lo resuelve el servicio SIFEN).

## D-006 — Autenticación con sesiones opacas
**Aceptada.** Token aleatorio de 256 bits; la base guarda solo su SHA-256. Vencimiento absoluto (12 h) e inactividad (60 min), revocables al instante (cerrar sesión, desactivar usuario, cambiar contraseña). Contraseñas con Argon2id. Bloqueo de 15 min tras 5 intentos fallidos. Mismo mensaje para email inexistente y contraseña errónea. Alternativa descartada: JWT (no se revocan sin una lista negra, que es una tabla de sesiones igual).

## D-007 — Facturación: reutilizar el núcleo SIFEN como servicio Node
**Propuesta · requiere confirmación.** El núcleo `sifen/*` del proyecto existente se copia sin cambios a `services/sifen/` y se expone por HTTP local; el backend Python lo usa mediante un adaptador. Alternativas: (a) portar a Python con `lxml`/`signxml`/`cryptography` — descartada por reintroducir riesgos ya resueltos y probados; (b) integrar NestJS completo — descartada, arrastra el CRM. Consecuencia: un segundo runtime en el instalador (ver R-02). Detalle en `INTEGRATIONS.md`.

## D-008 — Auditoría inmutable con cadena de hashes
**Aceptada.** `audit.audit_logs` y `audit.security_events` son de solo inserción (triggers rechazan UPDATE, DELETE y TRUNCATE). Cada fila de `audit_logs` incluye el SHA-256 de la anterior, calculado por la base bajo un candado transaccional; `GET /audit/verify` recalcula la cadena. Protege contra modificaciones ordinarias y hace **evidente** una alteración hecha por alguien con control total de la base (que puede desactivar triggers). Sin FK hacia usuarios/organizaciones: la auditoría sobrevive al borrado.

## D-009 — Configuración inicial en lugar de usuario por defecto
**Aceptada.** Con la base vacía, `POST /system/setup` crea la organización y su propietario; después responde 409. No existe contraseña por defecto. Riesgo aceptado: hasta completar la configuración, cualquier proceso local podría hacerla (la API escucha solo en 127.0.0.1); en fase 8 Tauri hará la configuración inicial en el primer arranque.

## D-010 — Roles iniciales
**Aceptada (el propietario puede ajustarla).** Propietario y Administrador: todo; solo un Propietario crea, modifica o asigna Propietarios. Contador: lectura de organización, usuarios y auditoría (ganará permisos contables en fase 3). Consulta: solo lectura de la organización. Siempre queda al menos un propietario activo; nadie cambia su propio rol ni se desactiva.

## D-011 — Gestores de paquetes
**Aceptada.** `npm` (viene con Node, plantilla oficial) y `venv` + `pip` con versiones fijas. pnpm/uv/poetry no aportan lo suficiente para sumar herramientas.

## D-012 — Cliente de pruebas `httpx2`
**Aceptada.** Starlette depreca `httpx` en su `TestClient` en favor de `httpx2`; se usa `httpx2` para no arrastrar advertencias.

## D-013 — Pruebas contra PostgreSQL real
**Aceptada.** Sin SQLite ni mocks de base: triggers, `uuidv7()`, índices parciales y candados solo existen en PostgreSQL. Cada prueba corre en una transacción revertida.

## D-014 — Token en `sessionStorage`
**Aceptada.** Sobrevive a recargas de la ventana pero no a cerrar la app; no se comparte entre ventanas. Ningún dato de negocio se guarda en el navegador. En fase 8 se evaluará pasar el token por el proceso Rust.

## D-015 — Identidad visual
**Aceptada.** Verde de libro mayor como primario, lapacho (árbol nacional) como color de marca usado en un solo lugar, IBM Plex Sans con cifras tabulares, doble raya contable como firma visual. Detalle en `ARCHITECTURE.md § Sistema de diseño`.

## D-016 — Plataforma objetivo: Windows 11, una sola PC
**Aceptada · 2026-11-23 (propietario).** La app se desarrolla en Linux y se usa en **una** PC con Windows 11. Consecuencias: no hace falta servidor ni base compartida en red; la base PostgreSQL vive en esa PC. Linux pasa a ser solo plataforma de desarrollo (los instaladores Linux quedan como opcionales). Los datos cargados en la PC de desarrollo son **solo de prueba**: los datos reales se cargan directamente en la PC de Windows.

## D-017 — Distribución adelantada (antes de la fase 2)
**Aceptada.** El empaquetado estaba en la fase 8. Como el uso real es en otra PC, se adelanta a una **fase 1B**: instalador mínimo para Windows que levanta PostgreSQL portable, el backend y la interfaz. Así se resuelve temprano el riesgo principal (R-01) y cada fase nueva llega a Windows como actualización.

## D-018 — Compilar Windows en GitHub Actions
**Aceptada (requiere autorización para subir el código).** Tauri no genera instaladores de Windows de forma soportada desde Linux. Los instaladores se arman en un runner `windows-latest` de GitHub Actions y se descargan como artefacto. Alternativa descartada: compilar en una PC con Windows (obliga a instalar Rust, Build Tools, Node y Python ahí). **Atención:** el repositorio `mandarinagg/Contador` es **público**; se recomienda hacerlo privado antes del primer push (Actions sigue siendo gratis dentro del cupo mensual).

## D-019 — Backend empaquetado con PyInstaller en modo carpeta
**Aceptada.** `backend/packaging/contador-backend.spec` genera `dist/contador-backend/` (≈ 83 MB en Linux). Modo carpeta en lugar de archivo único: arranca más rápido (no se descomprime en cada inicio) y genera menos falsos positivos de antivirus en Windows. Tauri lo incluye como recurso y lo lanza. El ejecutable aplica las migraciones al arrancar (`python -m app`). Verificado en Linux: migración de base vacía, configuración inicial e ingreso.

## D-020 — PostgreSQL portable de EDB
**Aceptada.** Se empaquetan los binarios oficiales para Windows de EDB (`postgresql-18.7-1-windows-x64-binaries.zip`, la misma versión que en desarrollo), recortados a `bin`, `lib` y `share` (sin pgAdmin, documentación ni StackBuilder). Datos en `%LOCALAPPDATA%\ContadorAI\pgdata`, solo `127.0.0.1`, autenticación `scram-sha-256` con contraseña aleatoria guardada en el Administrador de credenciales de Windows.

## D-021 — Datos fuera de la carpeta del identificador
**Aceptada.** La base vive en `%LOCALAPPDATA%\ContadorAI` y no en `%LOCALAPPDATA%\py.contadorai.desktop`: el desinstalador de Tauri ofrece "borrar datos de la aplicación" sobre la carpeta del identificador, y la contabilidad no debe poder borrarse con un clic al desinstalar. El CI verifica que desinstalar deja los datos.

## D-022 — Lanzador en Rust (`desktop/src-tauri/src/stack.rs`)
**Aceptada.** Sin dependencias de red extra (HTTP mínimo sobre `TcpStream` para el chequeo de salud). Reglas: nunca borra una carpeta de datos existente (la creación inicial ocurre en `pgdata.init` y se renombra al terminar); contraseña aleatoria de 256 bits en el Administrador de credenciales (`ContadorAI` / `postgresql`), que se reutiliza si se crea una base nueva (nunca se pisa: una base movida a un costado debe poder abrirse); PostgreSQL solo TCP en `127.0.0.1:55440`, sin sockets Unix, `scram-sha-256`, ICU `es-PY` para ordenar en español; backend atado a la app con un *job object* de Windows (muere con ella aunque la app falle); si PostgreSQL quedó en marcha tras un cierre brusco, se reutiliza; una sola instancia de la app. Fuera de Windows (solo desarrollo) la contraseña va a un archivo `0600`.

## D-023 a D-027 — Modelo de finanzas (fase 2)
**Aceptadas · 2026-11-24.** Detalle y motivos en [`specs/FASE2_FINANZAS.md`](specs/FASE2_FINANZAS.md) §1: contextos `business` (uno por organización) y `personal` (uno por usuario) (D-023); finanzas personales privadas de su dueño sin importar el rol (D-024); separación impuesta en la base con claves foráneas compuestas, incluida la moneda (D-025); importes `NUMERIC(18,2)`/`Decimal`/string, sin mezclar monedas (D-026); nada se borra, se anula o archiva con auditoría (D-027).

## D-028 — Equipo de agentes
**Aceptada · 2026-11-24 (autorizada por el propietario).** El trabajo se reparte entre agentes especializados, cada uno en su propio *worktree* de git y con su propia base de pruebas (`contador_test_<agente>`), bajo una especificación escrita por el jefe de proyecto. El jefe revisa, corre todas las pruebas e integra en `main`; ningún agente decide el modelo de datos ni sube código por su cuenta.

## D-029 — Copia de seguridad diaria automática con `pg_dump` y restauración en base nueva
**Aceptada.** `desktop/src-tauri/src/backup.rs`. Con los servicios en marcha, un hilo aparte (no demora la apertura) hace `pg_dump -Fc` de la base `contador` a `%LOCALAPPDATA%\ContadorAI\backups\auto\contador-AAAAMMDD-HHMMSS.dump` si todavía no hay una copia automática de **hoy** (fecha local); si la app queda abierta varios días, revisa cada 30 minutos. Se escribe a `*.partial` y se renombra solo si `pg_dump` terminó bien **y** `pg_restore --list` lee el archivo; si falla, se borra solo el `.partial`, se registra en `logs/backup.log` y la app sigue. Retención: las últimas 14; solo se borran archivos regulares que coinciden exactamente con `contador-AAAAMMDD-HHMMSS.dump` dentro de `backups/auto/` (nunca otros nombres, carpetas ni otras rutas); con 14 o menos no se borra nada. La contraseña de la base queda solo en memoria en el `Stack` y se pasa a `pg_dump` por `PGPASSWORD`, nunca por argumento. La restauración (`restore_dump`) solo carga en una base **nueva**: `createdb` falla si existe y no se toca; si la carga falla se descarta la base recién creada. Restaurar sobre datos vivos queda **fuera de alcance**; el procedimiento manual (`docs/RESTAURACION.md`) intercambia nombres de bases y no borra nada. Se agrega `chrono` (solo reloj local) para la fecha. **Pendiente:** copias cifradas, destino externo elegido por el propietario (hoy están en el mismo disco que la base), restauración desde la interfaz y un rol de base de datos de mínimo privilegio para `pg_dump`.

## D-030 — La auditoría de finanzas personales es privada
**Aceptada · 2026-11-24.** Las acciones sobre un contexto personal se auditan como `finance.personal.*` y `GET /audit/logs` solo se las muestra a su autor (el dueño del contexto, único que puede operarlo). Sin esto, quien tiene `audit.read` (administrador, contador) vería las finanzas personales del propietario, contra D-024. La cadena de hashes no se altera: la verificación sigue cubriendo todas las entradas. Prueba: `test_personal_audit_is_private_to_its_owner`.

## D-031 — Las migraciones no importan catálogos vivos
**Aceptada · 2026-11-24.** Cada migración lleva una copia congelada de los permisos y roles que carga (la 0001 se congeló con su catálogo original). Así una base nueva queda idéntica a una actualizada desde versiones anteriores. Las migraciones existentes no se modifican salvo para congelarlas sin cambiar su resultado.

## D-032 — `defusedxml` para leer XLSX
**Aceptada · 2026-11-24.** `openpyxl` lo usa automáticamente si está instalado: el XML interno de un XLSX se lee sin expansión de entidades (defensa ante archivos armados para agotar memoria). Los extractos vienen de afuera, así que se tratan como no confiables.

## D-033 — Resumen financiero en una sola pasada, sin índices nuevos
**Aceptada · 2026-11-24.** `summary.summarize` y `summary.context_totals` leían los movimientos tres veces (saldos, flujo mensual con `to_char`, gasto por categoría). Ahora hacen **una sola consulta** agrupada por (cuenta, mes, categoría, signo) con una única suma: las filas que solo cuentan para el saldo (anteriores al período o transferencias) llevan mes, categoría y signo `NULL`, y el resto se reparte en Python. La moneda se toma de la cuenta (la clave foránea compuesta de D-025 garantiza que es la del movimiento) y el mes se calcula con `date_trunc` sobre `timestamp` (sin zona horaria: el resultado no depende de la configuración del servidor). Un solo `SELECT` además da una lectura consistente: saldos y flujos salen de la misma instantánea.

*Medido* con 100.000 movimientos (PostgreSQL 18.7; tablas y planes en `docs/DATABASE_SCHEMA.md` § Rendimiento del resumen): el resumen baja de ~82 a ~47 ms con la máquina libre y de 222-294 a 153-158 ms con la máquina cargada (≈ 40 % menos CPU). **No se agregan índices**: se probaron un índice parcial cubriente `(context_id, booked_on) INCLUDE (...) WHERE voided_at IS NULL`, otro `(context_id, account_id, booked_on) INCLUDE (...)` y uno angosto solo para saldos. Con la tabla en `VACUUM` el escaneo solo-índice ganó a lo sumo ~15 % en una medición por reloj y empató en CPU de PostgreSQL con filas anchas (≈ 116 contra ≈ 118 ms), porque el costo está en agregar 100.000 filas, no en leerlas; sin `VACUUM` (el estado de la prueba) el planificador no los usa. Costarían ~9 MB y escrituras extra por cada 100.000 movimientos. Por eso la fase 2 no agregó una migración de índices (la `0003` es la de contabilidad).

*Descartado por regla:* cachés de resultados en memoria y tablas de saldos materializados (riesgo de inconsistencia en datos contables). *Si hiciera falta más margen* (cientos de miles de movimientos por contexto, o el resumen bajo carga en la PC final), la opción sería una tabla de totales mensuales por (cuenta, mes, categoría, signo) mantenida **en la misma transacción** que cada alta, edición o anulación y verificada contra el cálculo directo: queda propuesta, no implementada. Prueba de equivalencia: `tests/test_finance_summary_reference.py` (cálculo de referencia en Python sobre ~600 movimientos con varias monedas, anulados, transferencias, categorías y subcategorías, bordes de período, cuenta archivada y cuenta sin movimientos; pasa idéntica con la implementación anterior y con la nueva).

## D-034 — Confirmar importaciones: orden de candados y prueba con conexiones reales
**Aceptada · 2026-11-24.** `imports.commit` toma los candados **siempre en este orden**: fila del lote (`FOR UPDATE`) y luego fila de la cuenta (`FOR UPDATE`); ninguna otra operación toma el de la cuenta después de un lote, así que no hay interbloqueo. El del lote hace idempotente confirmar dos veces el mismo lote (el segundo espera, relee el estado ya confirmado y recibe 409 `IMPORT_ALREADY_COMMITTED`); el de la cuenta serializa lotes distintos de la misma cuenta, de modo que la búsqueda de duplicados (`READ COMMITTED`: instantánea por sentencia) ve lo que el otro ya confirmó y responde 409 `IMPORT_NEW_DUPLICATES` en vez de duplicar. Verificado en `tests/test_finance_import_concurrency.py`: hilos, un pedido HTTP y una conexión por hilo, contra una base propia confirmada (`<base de pruebas>_conc`, que el fixture crea y borra). La prueba **retiene el candado de la cuenta desde otra conexión** hasta que los dos pedidos están bloqueados y recién entonces lo suelta, para que la carrera sea determinista; además repite seis veces la carrera libre. Se comprobó que las pruebas fallan si se quita cualquiera de los dos candados. No se encontró una carrera real en el servicio. Límite conocido: las altas manuales no toman el candado de la cuenta, pero tampoco prohíben duplicados (solo se señalan, BR-FIN-03).

## D-035 a D-043 — Modelo de la contabilidad (fase 3)
**Aceptadas · 2026-11-24.** Detalle y motivos en `docs/specs/FASE3_CONTABILIDAD.md` §1:
- **D-035:** la contabilidad es de la organización. La base impide que un movimiento personal origine un asiento (FK a `finance.contexts (id, kind)` con `kind = 'business'`).
- **D-036:** moneda funcional PYG; la moneda extranjera es informativa y la cotización la escribe la persona.
- **D-037:** plan de cuentas jerárquico por organización. Se carga el propuesto (RG 49/2014) y solo las cuentas imputables reciben líneas.
- **D-038:** el plan nace `pending` y lo valida explícitamente un contador (nombre y matrícula).
- **D-039:** ejercicio por defecto = año civil (duda D-9 abierta), 12 períodos que se cierran y reabren con motivo. El ejercicio cerrado no se reabre.
- **D-040:** borrador → contabilizado → revertido. Inmutabilidad por triggers y numeración correlativa al contabilizar.
- **D-041:** desde finanzas solo se proponen borradores; el movimiento no se anula si tiene un asiento contabilizado.
- **D-042:** reportes calculados al vuelo, sin tablas de saldos.
- **D-043:** permisos `accounting.read`, `accounting.manage` y `accounting.post`; el administrador no contabiliza.


## D-044 — Claves de destino para el origen de los asientos
**Aceptada · 2026-11-24.** La FK `(source_transaction_id, source_context_id) → finance.transactions (id, context_id)` que pide la spec necesita un `UNIQUE (id, context_id)` en `finance.transactions`, que no existía: la 0003 lo agrega. Además, `finance.contexts` recibe `UNIQUE (id, organization_id)` y el asiento lleva la FK `(source_context_id, organization_id) → finance.contexts`: sin ella, un asiento de una organización podría citar un movimiento empresarial de otra. Las dos restricciones son de solo índice (no cambian datos). Pruebas: `test_entry_from_personal_context_is_rejected_by_database`, `test_source_context_must_belong_to_the_same_organization`.

## D-045 — Configuración contable en `accounting.settings`
**Aceptada · 2026-11-24.** La spec dejaba elegir entre columnas en `core.organizations` o una tabla 1:1. Se eligió la tabla `accounting.settings` (`UNIQUE (organization_id)`): el núcleo no depende de la contabilidad y la bajada de la 0003 no toca `core`. La fila se crea al primer uso (`INSERT … ON CONFLICT DO NOTHING` y luego `FOR UPDATE`); sin fila, el estado es `none`. El CHECK `ck_settings_chart_validation_complete` exige nombre, matrícula y fecha si y solo si el estado es `validated`.

## D-046 — Un cambio estructural del plan vuelve a `pending`
**Aceptada · 2026-11-24.** La validación del contador (D-038) se refiere a un plan concreto. Dar de alta una cuenta, cambiar código, tipo, naturaleza o imputabilidad, y archivar o desarchivar vuelven el estado a `pending` y borran nombre, matrícula y fecha (queda auditado como `accounting.chart.pending`). Cambiar nombre o nota no. Es la opción conservadora: un reporte nunca dice "validado" sobre un plan que el contador no vio. Prueba: `test_validation_requires_accountant_and_any_structural_change_resets_it`.

## D-047 — Ejercicios: año civil o fechas, períodos por mes calendario
**Aceptada · 2026-11-24.** `POST /fiscal-years` acepta `{year}` (año civil, D-039) o `{start_date, end_date}` para un primer ejercicio irregular (una empresa que empezó a mitad de año). Duración a lo sumo 12 meses calendario (CHECK `end_date < start_date + 1 año`). Los períodos son meses calendario: el primero y el último pueden ser parciales, y un ejercicio corto tiene menos de 12. El cierre exige **todos** los períodos del ejercicio cerrados. Crear un ejercicio exige `accounting.post` (como dice la spec). Prueba: `test_fiscal_year_creation_rules`.

## D-048 — Un movimiento con asiento contabilizado tampoco cambia importe, fecha ni cuenta
**Aceptada · 2026-11-24.** La spec exige 409 `TRANSACTION_HAS_POSTED_ENTRY` al anular. Por la misma razón (el asiento quedaría distinto del movimiento), también se rechaza cambiar `amount`, `booked_on` o `account_id` de un movimiento con asiento contabilizado; descripción, referencia, contraparte, categoría y revisado se pueden corregir (son datos de gestión; el asiento ya contabilizado es el registro contable y no cambia). Para corregir la contabilidad: revertir el asiento y volver a proponerlo. Prueba: `test_transaction_with_posted_entry_cannot_be_voided_or_changed`.

## D-049 — El número lo asigna la base, al contabilizar
**Aceptada · 2026-11-24.** El trigger de `journal_entries`, al pasar de `draft` a `posted`, hace `UPDATE accounting.fiscal_years SET last_entry_number = last_entry_number + 1 … RETURNING` y lo pone en `number`: el candado de fila del ejercicio serializa la numeración y, como el número se toma en la misma transacción que contabiliza, un fallo posterior lo devuelve (sin huecos, BR-ACC-08). Un número puesto a mano se rechaza (`trg_journal_entries_number_assigned`), y `last_entry_number` no retrocede (`trg_fiscal_years_numbering`). Orden de candados en el servicio: ejercicio (`FOR UPDATE`) → asiento (`FOR UPDATE`) → período y movimiento de origen (`FOR SHARE`, en el trigger). Cerrar un período toma el ejercicio y luego el período, así que una contabilización y un cierre del mismo mes no se cruzan. Pruebas: `test_numbering_is_correlative_without_gaps_despite_discards` y `tests/test_accounting_numbering_concurrency.py` (con conexiones reales, como D-034: la prueba retiene la fila del ejercicio hasta que los pedidos se bloquean).

## D-050 — La refundición
**Aceptada · 2026-11-24.** "Ejercicio `open`, salvo el asiento `closing`" (spec §2) se interpretó así: el ejercicio tiene que seguir abierto también para la refundición (se contabiliza **antes** de marcarlo cerrado), y lo que se exceptúa es la regla del período abierto: la refundición va fechada el último día y exige todos los períodos cerrados (`trg_journal_entries_closing_invalid`). Lleva cada cuenta de ingreso y gasto con saldo a cero contra la cuenta de resultados configurada; si el ejercicio no tuvo resultados, se cierra sin asiento (`closing_entry_id` nulo). Una refundición no se revierte, y el estado de resultados no la cuenta (si no, el resultado del ejercicio cerrado daría cero). Un ejercicio cerrado es definitivo: un trigger impide reabrirlo y reabrir sus períodos.

## D-051 — Reversiones
**Aceptada · 2026-11-24.** Por defecto, en la fecha del original; si su período está cerrado, 409 `PERIOD_CLOSED` con `details.date` para que la persona elija una fecha (`date`) en un período abierto, nunca anterior al original (422 `REVERSAL_DATE_INVALID`); puede caer en el ejercicio siguiente si está abierto. Una reversión o una refundición no se revierten (409 `ENTRY_NOT_REVERSIBLE`). La base exige que las líneas de la reversión sean exactamente las del original con debe y haber invertidos (`trg_journal_entries_reversal_mismatch`) y que el original pase a `reversed` solo con su reversión contabilizada.

## D-052 — Borrador desde finanzas: alcance
**Aceptada · 2026-11-24.** Un ingreso debita la cuenta contable del banco y acredita la de la categoría; un gasto al revés. Una subcategoría sin cuenta contable usa la de su categoría padre. Sin categoría: 422 `CATEGORY_REQUIRED`. **Las transferencias no se proponen** en esta fase (422 `TRANSFER_NOT_SUPPORTED`): cada pata es un movimiento y proponer una sola daría un asiento incompleto. Moneda extranjera: el importe en guaraníes es `importe × fx_rate` exacto con `Decimal`; si no es entero, 422 `FX_ROUNDING_REQUIRED` con `exact`, `floor` y `ceil`, y la persona elige uno en `amount_pyg` (otro valor: `FX_ROUNDING_INVALID`). Asignar `ledger_account_id` en finanzas exige además `accounting.manage`.

## D-053 — Convenciones de los reportes
**Aceptada · 2026-11-24.** Cuentan los asientos `posted` y `reversed` (la reversión es otro asiento que compensa). Los reportes jerárquicos y los saldos del plan usan el signo del **tipo** de la cuenta (activo y gasto: debe − haber; el resto: haber − debe), así que una regularizadora como "(-) DEPRECIACIÓN ACUMULADA" da negativo y resta en su grupo; el libro mayor usa la **naturaleza** de la cuenta. El balance general suma todo lo contabilizado hasta `at` y muestra aparte el resultado no refundido (ingresos − gastos de los ejercicios sin cerrar). El balance de comprobación es de sumas y saldos **del rango**: no hay asiento de apertura en esta fase, así que para ver saldos acumulados se pide desde el inicio del primer ejercicio. El plan y los ejercicios no se paginan (son listas acotadas); `/entries` pagina por cursor (≤ 200) y el diario y el mayor por cursor `after` (≤ 1000, 200 por defecto).

## D-054 — `btree_gist` para la exclusión de solapamiento
**Aceptada · 2026-11-24.** La 0003 hace `CREATE EXTENSION IF NOT EXISTS btree_gist` (extensión de confianza, está en el PostgreSQL 18 de Docker y en la distribución binaria de Windows, que trae `lib/` y `share/extension/` completos) y la bajada **no** la elimina: es inocua y podría usarla otra cosa. Si una instalación no la tuviera, la migración fallaría de forma explícita; la alternativa documentada en la spec (validar en el servicio con candado) no se implementó porque no hizo falta.

## D-055 — Siembra de la prueba de rendimiento contable
**Aceptada · 2026-11-24.** `tests/test_accounting_performance.py` escribe las 100.000 líneas con SQL directo y los triggers de usuario desactivados **dentro de la transacción de la prueba** (se revierte). Contabilizar 50.000 asientos uno por uno en una sola transacción actualizaría 50.000 veces la misma fila del ejercicio (la numeración) y mediría la siembra, no los reportes. Los números se ponen correlativos por ejercicio, como los asignaría el trigger. Medido (PostgreSQL 18.7, Docker): balance de comprobación anual ~32 ms, mayor de una cuenta con 20.000 líneas (primera página) ~40 ms, balance general ~44 ms (mediana de 9).

## D-056 a D-063 — Contabilidad 3B: activos fijos, centros de costos, recurrentes y libros exportables
**Aceptadas · 2026-11-24.** Detalle y motivos en `docs/specs/FASE3B_CONTABILIDAD.md` §1:
- **D-056:** categorías de activo con vida útil y cuentas, cargadas desde candidatas sin validar.
- **D-057:** depreciación lineal mensual exacta en guaraníes; la última cuota absorbe la diferencia.
- **D-058:** una corrida por período como borrador, sin saltear meses.
- **D-059:** la baja genera un borrador que deja en cero el costo y la acumulada.
- **D-060:** centros de costos solo en cuentas de resultado, impuesto por trigger.
- **D-061:** plantillas recurrentes que generan borradores, una vez por período y sin procesos ocultos.
- **D-062:** saldos iniciales en el balance de comprobación, sin asientos de apertura.
- **D-063:** XLSX desde el backend y PDF por impresión de la interfaz.

