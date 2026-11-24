# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado semántico.

## [Sin publicar]

### Agregado — Fase 4, backend del núcleo tributario (2026-11-24)
- Migración `0005_tributacion` (escrita a mano, esquema `tax`): reglas versionadas, feriados, excepciones de calendario, perfil fiscal versionado, obligaciones, comprobantes y configuración, con triggers que hacen de última defensa y permisos `tax.read`, `tax.manage` y `tax.verify` (el Administrador no verifica). La bajada se niega a perder comprobantes u obligaciones presentadas. Especificación `docs/specs/FASE4_TRIBUTACION.md`; investigación integrada en D-096 a D-099; decisiones de implementación D-100 a D-116.
- **Reglas como datos**: las 39 candidatas de `docs/research/tax_rules_candidatas.yaml` empaquetadas (copia verificada idéntica), carga idempotente, parámetros validados por código, sin vigencias superpuestas; verificar (nombre y matrícula) y deprecar con `tax.verify`. Todo lo que se calcula dice qué regla usó y si está «sin verificar» (D-082).
- **Calendario**: vencimientos por la terminación del RUC (DJ y DJI), corridos al siguiente hábil por sábados, domingos y feriados (Ley 7544/2025, cargados `pending`), excepciones fechadas como la RG DNIT 60/2026, y `remind_by` para avisar por la fecha fija sin correr (D-098).
- **Perfil fiscal** versionado por fecha (declarado o verificado con la constancia de RUC) y **obligaciones** sincronizadas sin duplicar, aun en paralelo, hasta 3 meses adelante: presentar, pagar (con un egreso de la empresa), no corresponde y reabrir con motivo; las presentadas no cambian.
- **Registro de comprobantes** de compras y ventas: timbrado, número, CDC con su DV y coherente con el comprobante, RUC con DV módulo 11 y los demás tipos de identificación oficiales (D-099; RUC antiguo con letra aceptado para revisar), IVA incluido por tasa (±1 ₲ con el impreso), notas de crédito y débito con su original, moneda extranjera con cotización, anti duplicados (también en paralelo), anulación sin borrar, vínculos solo con lo de la empresa. Confirmar el registro del mes bloquea el mes (también por SQL) hasta reabrirlo.
- **Archivo de importación para Marangatu** (`format=marangatu`, borrador): CSV con las columnas oficiales en un ZIP con el nombre que pide la DNIT, lotes de 5.000, sin los electrónicos (la vista previa dice cuáles), separador elegible (D-096).
- **IVA del mes**: estimación por tasa con notas, saldo a favor anterior (declarado antes que estimado), aviso de prorrateo, control contra el mayor y borrador del Formulario 120 v4 con sus casillas oficiales, lo no calculable vacío y con aviso (D-097); se copia a la obligación con `apply`. XLSX con los mismos totales.
- **Asiento desde un comprobante** (borrador, con IVA crédito o débito fiscal y proveedores, clientes o el banco del movimiento); nunca dos asientos vivos para el mismo hecho, ni desde el comprobante ni desde el movimiento (también un trigger en `journal_entries`).
- **Avisos** en el momento: vencidas, vencen pronto, registro sin confirmar, meses con movimientos y sin comprobantes, perfil faltante o sin verificar, reglas en uso sin verificar, RUC antiguos para revisar.
- Libro de compras y ventas XLSX del año con un escritor propio, para cumplir el tiempo con 20.000 comprobantes sin agregar dependencias (D-100).
- Pruebas nuevas en 13 archivos `tests/test_tax_*.py` contra PostgreSQL real: SQL directo contra cada trigger (se verificó que la prueba de cada uno de los 18 falla si se lo quita), calendario contra una referencia en Python para un año entero, concurrencia con conexiones reales (sincronización y duplicados), migración con datos y rendimiento (`slow`). Se adaptaron las pruebas de migración de la contabilidad a la nueva cabeza.

### Corregido — Exportaciones (2026-11-24)
- CORS expone `Content-Disposition`: en el navegador la interfaz usa el nombre de archivo que da la API.
- El Excel del cuadro de depreciación lleva las fechas del ejercicio en el nombre (`cuadro-de-depreciacion-AAAA-MM-DD-AAAA-MM-DD.xlsx`), así dos ejercicios no se pisan.
- La documentación nombraba `disposal_account_id`; el campo real es `asset_disposal_account_id`.

### Agregado — Fase 3B, interfaz de contabilidad: activos fijos, centros de costos, recurrentes y exportación (2026-11-24)
- Menú **Contabilidad** con tres entradas nuevas: Asientos recurrentes, Activos fijos y Centros de costos.
- **Activos fijos → Categorías**: sin categorías, invita a «Cargar las 34 categorías propuestas» (Decreto 3182/2019, art. 31, redacción del Decreto 6105/2021), que quedan **sin validar**. Cada una muestra la fuente, la referencia legal y la cita; las incompletas dicen qué les falta y se completan desde ahí. Validar (nombre y matrícula, solo `accounting.post`; una incompleta no se valida) y archivar. Configuración del inicio de la depreciación por defecto y de la cuenta de resultado por bajas. Una franja en todas las pantallas de activos dice cuántas categorías faltan validar.
- **Activos fijos → Bienes**: lista con filtros en la URL (categoría, estado, texto) y totales. Alta y edición con categoría, costo, fecha, inicio (por defecto el de la configuración), asiento de compra por número, y parámetros fiscales y contables (iguales por defecto; si difieren, explica la cuota no deducible con el importe del primer año). Avisa si el bien se compró antes del 14-10-2021 y aclara que el costo no incluye intereses de la financiación ni diferencias de cambio. Panel «Así se deprecia» con el mes de inicio, la cuota y el total depreciable. Detalle con el plan de cuotas por año (contabilizada, en borrador, pendiente, con enlace a cada asiento), valor neto y **baja** con fecha, tipo, motivo y acta obligatoria, que abre el borrador generado.
- **Activos fijos → Depreciación del mes**: los meses del ejercicio con su estado y total; «Calcular» abre el borrador para contabilizar. Los 409 y 422 se explican con su salida: mes anterior sin calcular (botón «Ir a {mes}»), corrida ya viva (enlace), categoría incompleta (enlace a completarla), período cerrado.
- **Activos fijos → Cuadro de depreciación** (RG 77/2020): columnas 1 a 13 (fiscal) o 14 a 22 (contable), grupos por categoría con subtotales, avisos «Antes de presentarlo» y conciliación por cuenta con el balance.
- **Centros de costos**: alta, edición y archivo; casilla «Exigir centro de costos en ingresos y gastos» (`settings.cost_centers_required`). En el editor de asientos la columna Centro aparece solo en las líneas de ingreso o gasto y, si se exige, marca las que faltan y no deja contabilizar. **Estado de resultados por centro** (una columna por centro, «Sin centro» y total).
- **Asientos recurrentes**: plantillas con el mismo editor de líneas (con centro), día del mes, vigencia, pausar y activar. «Generar los del período» muestra lo creado y lo que ya existía (no duplica). Aviso en Inicio y en Asientos cuando `GET /recurring/due` informa pendientes del mes, con botón para generarlos.
- **Balance de comprobación** con saldo inicial y final (deudor/acreedor) además de los movimientos del rango, y opción de ver también el saldo del rango (D-075).
- **Exportar**: «Descargar Excel» en cada reporte y en el cuadro (`?format=xlsx`; nombre del archivo de la API, o el mismo armado en la interfaz si CORS no expone la cabecera) e «Imprimir / PDF» con estilos de impresión: solo el reporte, encabezado con razón social y RUC, sin menú ni botones, A4 (apaisado en el cuadro y en resultados por centro), filas que no se parten entre páginas y doble raya bajo los totales.
- **Pendientes del núcleo**: el detalle de un movimiento de finanzas se lee por id (`GET /finance/contexts/{cid}/transactions/{id}`, P-9), así se abre aunque los filtros de la lista lo excluyan; asientos y libro diario muestran quién cargó y quién contabilizó (`created_by_name`, `posted_by_name`, P-10); la Auditoría nombra en castellano las acciones `accounting.*`.
- Pruebas nuevas: Vitest 34 (fechas de inicio y cuotas de un bien, residual fiscal, cuota no deducible, plan de cuotas por año, errores de la baja, centros en las líneas, plantillas, nombres de archivo XLSX, acciones de auditoría; total 124) y E2E `e2e/contabilidad-3b.spec.ts` (9 flujos) más 2 en `contabilidad.spec.ts` (subcuenta y archivo; cierre del ejercicio 2025 con refundición).

### Agregado — Fase 3B, backend de contabilidad: activos fijos, centros de costos, recurrentes, saldos iniciales y XLSX (2026-11-24)
- Migración `0004_contabilidad_3b` (escrita a mano): nueve tablas, centro de costos en las líneas, tres campos de configuración y los triggers del núcleo extendidos con `CREATE OR REPLACE`; la bajada restaura exactamente las funciones de la 0003 y se niega a perder asientos de la 3B (D-080). Especificación: `docs/specs/FASE3B_CONTABILIDAD.md`; decisiones de implementación D-068 a D-081.
- **Categorías de activo**: las 34 candidatas de `docs/research/` empaquetadas (copia verificada idéntica al YAML), `pending` hasta que las valida un contador; una incompleta no se usa (422 que dice qué falta).
- **Bienes del activo fijo** con parámetros contables y fiscales (D-065), inicio `next_month` o `next_fiscal_year` por bien (D-064), residual fiscal ≤ 20 %, cuotas exactas en guaraníes (la última absorbe la diferencia) y aviso para bienes anteriores al 14/10/2021.
- **Depreciación**: corrida mensual como borrador, una viva por período y sin saltear meses (lo impone la base), detalle por bien que tiene que coincidir con el asiento, reversión solo de la última. **Baja** con documento obligatorio: deja en cero costo y acumulada y registra el resultado; descartarla o revertirla devuelve el bien. El cierre del ejercicio exige la depreciación de todos sus meses y guarda los valores netos fiscal y contable de cada bien.
- **Cuadro de depreciación** con las columnas de la RG 77/2020 (revalúo en cero con nota, avisos de IRE SIMPLE), conciliado con las cuentas del balance.
- **Centros de costos** solo en líneas de ingreso o gasto (trigger), obligatorios si se configura; la reversión los copia; estado de resultados por centro.
- **Asientos recurrentes**: plantillas que generan borradores una vez por período (día 31 en meses cortos: el último día), todo o nada.
- **Balance de comprobación** con saldo inicial y final (D-062, D-075).
- **XLSX** (`?format=xlsx`) del diario y el mayor completos, comprobación, balance general, estado de resultados (también por centro) y cuadro de depreciación, con encabezado, aviso de plan sin validar e importes numéricos.
- **Plan propuesto**: 173 cuentas (MAQUINARIAS `1.02.04.04`, verificada en el XLS oficial de la RG 49/2014; terreno y construcciones separados; depreciación acumulada por clase de bien).
- **API (pedidos de la interfaz)**: `GET /finance/contexts/{cid}/transactions/{id}` con las reglas de acceso del listado (P-9) y `created_by_name`/`posted_by_name` en asientos y libro diario (P-10).
- Pruebas nuevas (84 en 12 archivos; total 239 con 4 `slow`; además se adaptaron la referencia de reportes y la migración del núcleo): SQL directo para cada regla nueva de la base (`test_accounting_db_triggers_3b.py`; se verificó que las 22 fallan si se quita su regla), depreciación contra un cálculo de referencia, corridas, bajas, cuadro y cierre, centros, recurrentes, XLSX contra el JSON, saldos iniciales en la referencia de reportes, concurrencia con conexiones reales (una corrida y una generación por período), migración con datos y rendimiento (corrida de 2.000 bienes ~0,4 s; XLSX del diario con 20.000 líneas ~2,1 s).

### Agregado — Fase 3, interfaz de contabilidad (núcleo) (2026-11-24)
- Menú **Contabilidad** (permiso `accounting.read`): Plan de cuentas, Ejercicios y períodos, Asientos, Libros y balances. Una franja en todas sus pantallas (y un aviso en cada reporte) dice «Plan de cuentas sin validar por un contador» mientras no se valide.
- **Plan de cuentas**: árbol con expandir/contraer, búsqueda por código o nombre, tipo y naturaleza, imputable o agrupadora, origen (RG 49/2014, propuesta, agregada) y archivadas atenuadas. Sin plan, invita a «Cargar el plan propuesto» y explica que es una propuesta que valida un contador. Alta de subcuentas (código sugerido), edición (campos fijos si la cuenta tiene movimientos), archivo con el error de la API a la vista, validación con nombre y matrícula (solo `accounting.post`), vuelta a «sin validar» y cuenta de resultados del ejercicio (`/settings`).
- **Ejercicios y períodos**: alta (año civil por defecto u otras fechas), cierre de períodos (con 409 `PERIOD_HAS_DRAFTS`, lista los borradores con enlace), reapertura con motivo obligatorio y cierre del ejercicio con confirmación que explica la refundición y que no se reabre.
- **Asientos**: lista con filtros en la URL (ejercicio, estado, tipo, fechas, cuenta, texto) y paginación por cursor. Editor con selector de cuentas imputables con búsqueda (combobox accesible), debe o haber por línea, detalle, moneda extranjera opcional, totales en vivo y barra de balance que muestra la diferencia y de qué lado falta; teclado: Enter/↓ baja de línea (en la última agrega otra con la diferencia propuesta), ↑ sube, Ctrl+S guarda. Guardar borrador, contabilizar (muestra el número), descartar con motivo, revertir con motivo y fecha (si el período del original está cerrado, pide otra fecha y sugiere la primera abierta). Vista de solo lectura con número, quién y cuándo, enlaces al asiento revertido o que lo revierte y al movimiento de finanzas de origen.
- **Libros y balances**: libro diario, libro mayor (saldo anterior, saldo por naturaleza con D/A), balance de comprobación (sumas y saldos; avisa si no cuadra), balance general en dos columnas con subtotales, resultado del ejercicio en curso y control activo = pasivo + patrimonio + resultado, y estado de resultados. Importes en guaraníes alineados a la derecha, negativos con signo menos (D-053), doble raya bajo los totales.
- **Desde finanzas** (solo la empresa): «Proponer asiento» en la lista y en el nuevo detalle de un movimiento (`?tx=`). Si falta la cuenta contable del banco o de la categoría, se elige ahí mismo y se guarda; en otra moneda pide la cotización y, ante `FX_ROUNDING_REQUIRED`, muestra el producto exacto y deja elegir hacia abajo o hacia arriba. Cada movimiento muestra su asiento (N°, borrador, revertido) con enlace; con asiento contabilizado, anular y cambiar fecha, importe o cuenta quedan bloqueados con «revertí primero el asiento N° X» y enlace (también ante el 409 de la API). Campo «Cuenta contable» en cuentas y categorías de la empresa (subcategoría sin cuenta: usa la de su categoría, D-052).
- Permisos en la interfaz: Consulta solo lee; `accounting.manage` prepara plan y borradores; contabilizar, revertir, cerrar, reabrir y validar requieren `accounting.post` (el Administrador ve por qué no puede, D-043).
- Pruebas nuevas: Vitest 36 (sumas de importes con BigInt, balance del editor en vivo, armado del cuerpo y errores por línea, árbol del plan y búsqueda, cotización y redondeo, reglas para proponer y bloquear movimientos) y E2E `e2e/contabilidad.spec.ts` (9 flujos).

### Agregado — Fase 3, backend de contabilidad (núcleo) (2026-11-24)
- Módulo `backend/app/modules/accounting/` y migración `0003_contabilidad` (esquema `accounting`, triggers PL/pgSQL, extensión `btree_gist`). Especificación: `docs/specs/FASE3_CONTABILIDAD.md`; decisiones de implementación D-044 a D-055.
- **Plan de cuentas** jerárquico por organización: carga del plan propuesto (159 cuentas, RG 49/2014; copia empaquetada en `proposed_chart.py`, verificada idéntica al YAML de `docs/research/`), altas bajo un padre, edición, archivo y saldos por fecha. El plan nace `pending` y lo valida un contador con nombre y matrícula; un cambio estructural lo vuelve a `pending` (D-046). Configuración de la cuenta de resultados para la refundición (`accounting.settings`, D-045).
- **Ejercicios** (año civil o fechas, a lo sumo 12 meses, sin solapamiento en la base) con un período por mes calendario; cierre y reapertura de períodos con motivo; **cierre del ejercicio** con asiento de refundición, definitivo.
- **Asientos**: borradores (pueden estar desbalanceados), contabilización con número correlativo por ejercicio asignado por la base (sin huecos, también con contabilizaciones concurrentes), reversión con líneas invertidas y descarte con motivo. Lo contabilizado no se modifica ni se borra: lo impiden triggers, probados con SQL directo.
- **Desde finanzas**: borrador propuesto desde un movimiento de la empresa (banco contra categoría, moneda extranjera con cotización explícita y sin redondeo silencioso); `ledger_account_id` en cuentas y categorías del contexto `business`; los movimientos muestran su `journal_entry`; un movimiento con asiento contabilizado no se anula ni cambia importe, fecha o cuenta (409 `TRANSACTION_HAS_POSTED_ENTRY`). Un movimiento personal nunca origina un asiento: lo impide la base (D-035).
- **Reportes** al vuelo: libro diario, libro mayor (saldo anterior y acumulado, paginado), balance de comprobación, balance general (con verificación activo = pasivo + patrimonio) y estado de resultados. Todos informan `chart_status`.
- Permisos `accounting.read`, `accounting.manage` y `accounting.post` (el administrador no contabiliza ni cierra). Todo se audita (`accounting.*`).
- Dependencia de desarrollo `pyyaml==6.0.4` (solo para la prueba que compara el plan empaquetado con el YAML).
- Pruebas nuevas (68): triggers y D-035 por SQL directo (`test_accounting_db_triggers.py`; cada una falla si se quita su trigger o restricción), plan de cuentas, asientos, períodos, cierre y permisos, finanzas ↔ contabilidad, numeración concurrente con conexiones reales (`test_accounting_numbering_concurrency.py`), reportes contra un cálculo de referencia en Python (`test_accounting_reports_reference.py`), migración (`test_accounting_migration.py`) y rendimiento con 100.000 líneas (`slow`: balance de comprobación ~32 ms, mayor ~40 ms, balance general ~44 ms).

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
- Si la ventana se cerraba mientras los servicios arrancaban, PostgreSQL quedaba en marcha: el hilo de arranque iba a detenerlo, pero el proceso terminaba antes. Ahora la salida espera a ese hilo. El CI lo prueba con un paso nuevo (cerrar la app apenas aparece la ventana).
- Con la app instalada, `initdb` no arrancaba porque Tauri entrega la carpeta de recursos como `\\?\C:\...` y `initdb` no encuentra `postgres.exe` con ese prefijo. El lanzador ahora lo quita (`dunce`) para las herramientas de PostgreSQL y el backend. `tests/stack.rs` usa rutas `canonicalize` para cubrir este caso en Windows.

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
