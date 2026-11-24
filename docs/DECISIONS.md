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

## D-064 a D-067 — Depreciación: inicio por bien, fiscal y contable en paralelo, valores por ejercicio y cuadro RG 77/2020
**Aceptadas · 2026-11-24**, a partir de `docs/research/DEPRECIACION_PY.md` §8. Detalle en `docs/specs/FASE3B_CONTABILIDAD.md` §6. Todo queda pendiente de validar por el contador (D-DEP-1 a D-DEP-17).


## D-068 a D-081 — Contabilidad 3B: decisiones de implementación
**Aceptadas · 2026-11-24.** Puntos que la especificación 3B no fijaba, o fijaba de forma que admitía dos lecturas. Ante la duda se eligió la opción más conservadora (la que bloquea en vez de suponer). Todo lo que toca parámetros fiscales sigue `pending` de validación (D-DEP-1 a D-DEP-17).

- **D-068 — Categoría completa.** Se usa solo con vida útil, porcentaje de residual y las tres cuentas (bien, acumulada y gasto) válidas; si no, 422 `ASSET_CATEGORY_INCOMPLETE` con lo que falta. "Terrenos" se carga sin vida útil y por eso no se puede usar (no se deprecia). Un cambio de vida útil, residual o cuentas devuelve una categoría validada a `pending`.
- **D-069 — `entry_status` copiado por trigger.** Las corridas y las generaciones guardan el estado de su asiento en `entry_status`, que mantiene la base (`journal_entries_sync_links` y `entry_links_guard`, que además lo relee en cada escritura: no se puede falsear). Así los índices únicos parciales (`uq_depreciation_runs_live_period`, `uq_recurring_generations_live`) imponen "una viva" sin depender del servicio.
- **D-070 — Alta de bienes.** El residual contable por defecto es el fiscal (costo por el porcentaje de la categoría, en guaraníes enteros hacia abajo). El importe depreciable tiene que ser al menos la vida útil en meses (422 `DEPRECIABLE_TOO_SMALL`: si no, la cuota sería de menos de ₲ 1). La depreciación no puede empezar antes del primer ejercicio (422 `DEPRECIATION_START_BEFORE_BOOKS`: esta versión no carga depreciaciones previas a los libros). Un bien que empezaría en o antes de un mes que ya tiene corrida viva da 409 `DEPRECIATION_ALREADY_RUN` (quedaría un mes salteado). Hay una sola corrida viva por **mes** de calendario, aunque un ejercicio irregular lo parta en dos.
- **D-071 — Bienes con depreciaciones vivas.** La spec bloquea cambios con depreciaciones "contabilizadas"; se bloquea también con un **borrador** vivo (409 `ASSET_HAS_DEPRECIATION`, `trg_fixed_assets_depreciated`), porque el detalle del borrador quedaría desfasado del bien. Se corrige descartando el borrador.
- **D-072 — Datos de la baja.** Mientras el asiento de baja es borrador, la fecha, el tipo, el motivo y el documento se guardan en el bien (que sigue `active`, con `disposal_entry_id`); al contabilizar pasa a `disposed`; descartar o revertir los borra. La cuenta de resultado es `settings.asset_disposal_account_id` o, si no está, `17.01` del plan propuesto; si ninguna sirve, 422 `DISPOSAL_ACCOUNT_NOT_SET`. `POST /fixed-assets/{id}/dispose` devuelve el asiento (`EntryOut`), como la corrida.
- **D-073 — El mes de la baja no se deprecia.** La depreciación tiene que estar al día hasta el mes anterior a la baja (409 `DEPRECIATION_NOT_UP_TO_DATE`); la cuota del mes de la baja no se calcula (criterio conservador: no hay norma que fije prorrata, D-DEP-1).
- **D-074 — Reversiones de depreciación y baja.** Se revierten solo dentro del mismo ejercicio (409 `REVERSAL_OTHER_YEAR`); solo la última corrida viva (409 `DEPRECIATION_RUN_NOT_LAST`, para no dejar huecos); no si incluye un bien dado de baja (409 `ASSET_DISPOSED`). Una baja no se revierte si hay corridas vivas desde su mes (409 `DEPRECIATION_AFTER_DISPOSAL`): el bien quedaría sin esas cuotas.
- **D-075 — Balance de comprobación con saldos iniciales (D-062).** Columnas nuevas `opening_*` (saldo hasta el día anterior a `from`, con la refundición, en el sentido deudor o acreedor) y `closing_*` (inicial más el rango). Aparecen las cuentas con movimiento en el rango **o** saldo inicial distinto de cero. `debit_balance`/`credit_balance` siguen siendo el saldo **del rango** (compatibilidad con el núcleo); `balanced` exige que cuadren las tres parejas.
- **D-076 — Formato de los importes en XLSX.** El código de formato es `#,##0` (el de Excel); en una configuración regional de Paraguay se muestra como `#.##0`. Los importes se escriben como enteros, nunca texto ni `float`.
- **D-077 — Cuadro de depreciación.** Vidas en años con dos decimales a partir de los meses; la cuota fiscal del ejercicio es la suma de las cuotas mensuales teóricas del calendario fiscal (D-065); el coeficiente de revalúo es 0 con nota (D-066); un bien dado de baja en el ejercicio muestra su cuota hasta la baja y neto 0; la conciliación compara, por cuenta de bien y de acumulada, el saldo del mayor con el cuadro, y el total con la columna 22.
- **D-078 — Centros de costos en reversiones.** La reversión copia el centro de cada línea (la base lo exige en `trg_journal_entries_reversal_mismatch`) y admite un centro archivado, porque si no archivar un centro impediría revertir. `cost_centers_required` se exige en asientos `manual`, `finance` y `recurring`; los generados (depreciación, baja, refundición, reversión) quedan exentos.
- **D-079 — Fecha y alcance de los recurrentes.** La fecha es el día de la plantilla o el último del mes si es más corto, y tiene que caer dentro de la vigencia (`start_date`, `end_date`). La generación de un período es todo o nada: si una plantilla falla (por ejemplo, una cuenta archivada), 422 con el nombre de la plantilla y no se crea ninguna.
- **D-080 — Bajada de la 0004.** Falla con un mensaje claro (`RuntimeError`) si hay asientos de depreciación, baja o recurrentes, o líneas con centro de costos, aunque estén descartados: la 0003 no los admite y borrarlos violaría D-027. Sin eso, borra las tablas de la 3B y devuelve los triggers exactamente a la versión de la 0003.
- **D-081 — Cuentas de una categoría en uso.** No cambian si algún bien de la categoría tiene depreciaciones vivas (409 `ASSET_CATEGORY_IN_USE`); una cuenta asignada a una categoría no archivada no se archiva (409 `ACCOUNT_IN_ASSET_CATEGORY`), ni la cuenta de resultado por bajas (409 `ACCOUNT_IN_SETTINGS`).

## Fase 4 — Tributación (núcleo), 2026-11-24
Detalle en `docs/specs/FASE4_TRIBUTACION.md`.
- **D-082 — Reglas `pending` utilizables con aviso.** Reformula BR-TAX-01: una regla sin verificar alimenta calendario, avisos y estimaciones, siempre marcada «sin verificar»; nada se presenta como oficial; una `deprecated` no se usa.
- **D-083 — Perfil fiscal versionado**, declarado por el propietario o verificado por el contador con la constancia de RUC.
- **D-084 — Reglas como datos** globales y versionadas; solo cambia el estado; carga idempotente desde el YAML empaquetado.
- **D-085 — Códigos usados en la fase 4**: calendario DJ/DJI, excepciones, IVA (tasas y liquidación), registro mensual, IRE (vencimientos) y estados financieros.
- **D-086 — Días inhábiles**: fines de semana, feriados cargados y excepciones fechadas que reemplazan la fecha.
- **D-087 — Obligaciones** por código y período, sincronizadas de forma idempotente; las presentadas no se recalculan; ninguna se borra.
- **D-088 — Comprobantes** con importes con IVA incluido, IVA calculado (±1 ₲ aceptado), anti duplicado y vínculos con FK compuestas.
- **D-089 — Registro confirmado bloquea el mes** (trigger); se corrige reabriendo con motivo.
- **D-090 — Estimación del IVA y borrador del Formulario 120**, con control contra el mayor y aviso de prorrateo sin calcularlo.
- **D-091 — Asiento desde un comprobante**, nunca dos asientos vivos para el mismo hecho.
- **D-092 — Avisos** calculados en el momento, sin procesos en segundo plano.
- **D-093 — Exportación XLSX**; formato de Marangatu solo con fuente identificada.
- **D-094 — Permisos `tax.read`, `tax.manage`, `tax.verify`** (Administrador sin `verify`).
- **D-095 — Auditoría de todo cambio tributario**; importes nunca `float`.

## D-096 a D-099 — Fase 4: integración de la investigación (`docs/research/TRIBUTACION_FASE4.md`)
**Aceptadas · 2026-11-24**, por indicación del coordinador al llegar la investigación a `main`. Todo sigue `pending` hasta que lo revise el contador (dudas D-F4-1 a D-F4-14).

- **D-096 — Archivo de importación de Marangatu (`format=marangatu`).** CSV UTF-8 sin BOM y sin encabezado, con el orden oficial de columnas de VENTAS (19) y COMPRAS (20) de la Especificación Técnica de la RG 90/2021, dentro de un ZIP del mismo nombre `<RUC sin DV>_REG_<MMAAAA>_<XXXXX>`. Un ZIP por lote de hasta 5.000 filas; con más de un lote, un ZIP que los contiene (`..._lotes.zip`). Importes enteros con IVA incluido. Los comprobantes electrónicos **no** van (se imputan en «Obtener Comprobantes Electrónicos y Virtuales»): `GET /tax/vouchers/export/marangatu-preview` dice cuántos y cuáles quedan fuera. Separador `?separator=semicolon|comma`, por defecto punto y coma, el del ejemplo oficial (D-F4-1). La API dice que el archivo es un **borrador** y recomienda probar antes con uno o dos comprobantes (`limit`). Notas de crédito: la emitida en COMPRAS y la recibida en VENTAS, como dice la guía de registro manual de 2022 (D-F4-4, anotada como duda).
- **D-097 — Borrador del Formulario 120 v4.** Mapa de casillas de la investigación §2, **sin IVA y sin céntimos** (base = importe menos su IVA, §3.7). Se precalculan solo las casillas que la investigación marca como calculables; las de exportadores, las retenciones (52, 169; D-F4-6) y el prorrateo (164) quedan vacías con aviso, sin cálculo. Cada casilla lleva su número oficial, su estado (`calculated`, `from_previous`, `not_calculated`) y las dudas que la afectan. Solo se arma si rige la regla `IVA-F120-ESTRUCTURA`.
- **D-098 — Días inhábiles y avisos.** `due_date` sigue la D-086 (sábado, domingo y feriados cargados son inhábiles; RG DNIT 60/2026). Se agrega `remind_by` = la fecha fija del calendario **sin correr** si es anterior (`LEAST(nominal_due_date, due_date)`, columna generada). El aviso «vence pronto» usa `remind_by`; si difiere del vencimiento, la obligación trae `shift_explanation`: «si el día es inhábil, el vencimiento pasa al …, sin verificar». Los feriados de fuente secundaria se cargan `pending`.
- **D-099 — Identificación de la contraparte.** Tipos oficiales de la Tabla 3 (RUC 11, cédula 12, pasaporte 13, cédula extranjera 14, sin nombre 15, diplomático 16, identificación tributaria 17). El DV módulo 11 se valida solo en un RUC numérico. Un RUC antiguo terminado en letra (D-F4-10) se acepta solo como identificación sin DV, marcado para revisar (`counterparty_review_required`, aviso `COUNTERPARTY_RUC_UNCHECKED`); no se rechaza. El redondeo del IVA sigue por comprobante (D-F4-7 abierta).

## D-100 a D-116 — Fase 4: decisiones de implementación
**Aceptadas · 2026-11-24.** Puntos que la spec de la fase 4 no fijaba o admitían dos lecturas. Ante la duda, la opción más conservadora.

- **D-100 — XLSX del registro de comprobantes con un escritor propio.** Con 20.000 comprobantes por 24 columnas, `openpyxl` sin `lxml` tardaba 5,5 s y la spec pide menos de 3 s (§5.12). `tax/fast_xlsx.py` escribe el mismo libro (encabezado, negritas, `#,##0`, enteros) como XML de texto (~1,3 s). No agrega dependencias. El resto de los XLSX sigue con `openpyxl`.
- **D-101 — Cuentas de proveedores y clientes en la configuración tributaria.** Además de las cuatro de IVA, `tax.settings` guarda las cuentas de proveedores (`2.01.01.01`) y clientes (`1.01.03.01`) para el asiento de un comprobante a crédito; por defecto, las del plan propuesto.
- **D-102 — Excepciones de calendario.** `due_month` es el mes del vencimiento nominal. Una excepción que nombra la obligación gana sobre una del grupo `determinative`; solo se superponen (409 `EXCEPTION_OVERLAP`) dos activas con el mismo destino, mes y alguna terminación en común.
- **D-103 — `not_applicable` automático y reversible.** Lo marca el sistema cuando el perfil deja de incluir la obligación (`not_applicable_auto`); si el perfil la vuelve a incluir, vuelve a `pending`. La base solo permite `not_applicable → pending` cuando la marcó el sistema; una manual es final.
- **D-104 — Clave anti duplicado.** Incluye el tipo de comprobante (una factura y una nota pueden compartir número). Compras: RUC del proveedor, timbrado, número y tipo; ventas: timbrado, número y tipo (el talonario es propio).
- **D-105 — Saldo a favor declarado.** La obligación IVA guarda `declared_credit_balance` al presentarla (y `calculated_credit_balance` al aplicar la estimación); el mes siguiente usa el declarado antes que el estimado.
- **D-106 — Asiento desde un comprobante.** Con movimiento vinculado es de tipo `finance` con el movimiento como origen (lo cubre el índice único de la 3); sin movimiento, `manual`. Pide `tax.manage` y `accounting.manage`. Una compra que no imputa IVA suma el IVA al costo; una venta siempre lleva débito fiscal. El bloqueo del período confirmado deja cambiar solo `journal_entry_id` (no altera lo registrado).
- **D-107 — CDC coherente con el comprobante.** Además de su DV: RUC del emisor (en una compra, la contraparte; en una venta, la organización), establecimiento, punto, número, fecha y tipo (01 factura y 05 nota de crédito, los del proyecto de facturación; el de la nota de débito no se controla porque la investigación no lo trae). Si no coincide, 422 `CDC_MISMATCH` que dice qué campo.
- **D-108 — Carga de reglas.** Solo se cargan filas `pending` del YAML; una versión ya cargada con contenido distinto se informa (`differing`), no se pisa. Las reglas son globales y su auditoría queda en la organización de quien las carga. Los parámetros con decimales van como texto en la API (D-095).
- **D-109 — Una compra lleva el RUC del proveedor** (tipo `ruc`; 422 `COUNTERPARTY_RUC_REQUIRED`): sin RUC no hay crédito fiscal. Las autofacturas y los despachos de importación quedan fuera de esta fase.
- **D-110 — El libro XLSX no incluye los anulados**, igual que la estimación y el archivo de Marangatu.
- **D-111 — Sin regla de tasas vigente, 422 `RULE_MISSING`.** Un comprobante anterior a la vigencia de `IVA-GENERAL-TASAS` (2020-01-01) no se carga: no hay regla con qué calcularlo (D-082).
- **D-112 — Estimación del IVA.** El débito cuenta solo ventas que imputan IVA (D-090 literal), con aviso `SALES_NOT_IMPUTED` si hay otras; el crédito, solo compras que imputan IVA (aviso `PURCHASES_NOT_IMPUTED`). En el F120, el 5 % va en 151/157; todas las compras se toman como de afectación directa a operaciones gravadas (32/35/38; 33/36/39 vacías, ligadas al prorrateo); el Rubro 2 suma los últimos 6 meses; del Rubro 5 solo se calcula 55; la 46 se precarga con el saldo anterior (declarado o estimado). El control contra el mayor compara el movimiento neto del mes de las cuentas de IVA.
- **D-113 — Detalles del archivo de Marangatu.** `NO_IMPUTA` siempre `N`; los comprobantes que no imputan a nada quedan fuera (Marangatu exige imputar cada uno), con su lista; filas con CRLF; venta «sin nombre» sin número de identificación, con aviso; `limit` y `first_id` (hasta 5 posiciones) para probar y para nombres distintos; requiere la regla `REG-COMPROB-IMPORTACION` vigente. Nombres y documentos sin el separador, comillas ni saltos de línea (aviso).
- **D-114 — Feriados.** La carga de candidatos nunca pisa uno existente (informa los distintos). Un feriado que corrió el vencimiento de una obligación ya presentada (de cualquier organización) no se borra ni cambia de día (409 `HOLIDAY_IN_USE`, trigger `trg_holidays_in_use`), con un mensaje que no revela de quién.
- **D-115 — Excepciones que vienen de una regla** (`origin = candidate`, como la RG 60/2026): solo cambian `is_active` y las notas (409 `EXCEPTION_FROM_RULE`). Una excepción usada por una obligación presentada no cambia de fecha ni de alcance (409 `EXCEPTION_IN_USE`).
- **D-116 — Sincronizar escribe: pide `tax.manage`.** Las lecturas no sincronizan; la sincronización corre después de cargar reglas, feriados, excepciones o el perfil, y a pedido.

