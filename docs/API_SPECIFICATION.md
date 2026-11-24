# Especificación de la API local

Base: `http://127.0.0.1:8765/api/v1`. JSON. Autenticación: `Authorization: Bearer <token>`.
La especificación OpenAPI completa y navegable está en `http://127.0.0.1:8765/docs` (solo fuera de producción).

## Convenciones

- **Errores:** `{"error": {"code": "CODIGO", "message": "texto para la persona", "details": ...}}`.
- **Validación (422):** `code = VALIDATION_ERROR`, `details = [{"field": "owner.password", "message": "..."}]`.
- **Trazabilidad:** toda respuesta trae `X-Request-Id`; se puede enviar uno propio (8-64 caracteres ASCII).
- **Fechas:** ISO 8601 con zona horaria; fechas contables `YYYY-MM-DD`. **Importes (desde fase 2):** string decimal + `currency`, en la entrada y en la salida. La entrada rechaza números JSON (`0.1` → 422): siempre `"0.10"`. La salida usa los decimales de la moneda (`PYG` → `"150000"`, `USD` → `"0.30"`).

| HTTP | Códigos |
|---|---|
| 400 | `INVALID_CURRENT_PASSWORD`, `PASSWORD_REUSED`, `SELF_CHANGE_FORBIDDEN`, `INVALID_CURSOR` |
| 401 | `NOT_AUTHENTICATED`, `SESSION_EXPIRED`, `INVALID_CREDENTIALS` |
| 403 | `FORBIDDEN` (`details.missing` = permisos faltantes), `OWNER_ONLY` |
| 404 | `USER_NOT_FOUND`, `NOT_FOUND`, `CONTEXT_NOT_FOUND`, `ACCOUNT_NOT_FOUND`, `CATEGORY_NOT_FOUND`, `COUNTERPARTY_NOT_FOUND`, `TRANSACTION_NOT_FOUND`, `IMPORT_NOT_FOUND`, `IMPORT_ROW_NOT_FOUND` |
| 409 | `ALREADY_SET_UP`, `EMAIL_TAKEN`, `LAST_OWNER`, `PERSONAL_CONTEXT_EXISTS`, `CONTEXT_INACTIVE`, `ACCOUNT_NAME_TAKEN`, `ACCOUNT_HAS_TRANSACTIONS`, `ACCOUNT_ARCHIVED`, `CATEGORY_NAME_TAKEN`, `CATEGORY_ARCHIVED`, `CATEGORIES_EXIST`, `COUNTERPARTY_RUC_TAKEN`, `COUNTERPARTY_ARCHIVED`, `TRANSACTION_VOIDED`, `TRANSACTION_NOT_EDITABLE`, `TRANSFER_HAS_NO_CATEGORY`, `ALREADY_VOIDED`, `IMPORT_ALREADY_COMMITTED`, `IMPORT_CANCELLED`, `IMPORT_ROW_HAS_ERROR`, `IMPORT_NEW_DUPLICATES` (`details.rows`), `IMPORT_STALE` |
| 413 | `IMPORT_FILE_TOO_LARGE` |
| 422 | `VALIDATION_ERROR`, `INVALID_AMOUNT`, `INVALID_RANGE`, `CATEGORY_TOO_DEEP`, `CATEGORY_KIND_MISMATCH`, `TRANSFER_SAME_ACCOUNT`, `TRANSFER_AMOUNTS_DIFFER`, `IMPORT_UNSUPPORTED_FORMAT`, `IMPORT_UNREADABLE`, `IMPORT_EMPTY`, `IMPORT_TOO_MANY_ROWS`, `IMPORT_COLUMN_NOT_FOUND` (`details.missing`, `details.available`) |
| 423 | `ACCOUNT_LOCKED` (`details.locked_until`) |
| 500 | `INTERNAL_ERROR` |

Los códigos de contabilidad (fase 3) están en su propia tabla, al final de [Contabilidad](#contabilidad-accounting).

## Sistema

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/system/health` | — | `{status, database, version}` |
| GET | `/system/setup` | — | `{needs_setup: bool}` |
| POST | `/system/setup` | — (solo con la base vacía) | Crea organización + propietario + contexto financiero `business` ("Empresa"), en una transacción. Cuerpo: `{organization: {legal_name, trade_name?, legal_form}, owner: {full_name, email, password}}`. Responde como `/auth/login` (201) |

## Autenticación

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| POST | `/auth/login` | — | `{email, password}` → `{token, expires_at, user, organization, role, permissions[]}` |
| POST | `/auth/logout` | sesión | Revoca la sesión actual (204) |
| GET | `/auth/me` | sesión | `{user, organization, role, permissions[]}` |
| POST | `/auth/change-password` | sesión | `{current_password, new_password}` (204). Cierra las demás sesiones |

## Usuarios

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/users` | `users.read` | Miembros de la organización: `[{user, role, member_since}]` |
| POST | `/users` | `users.manage` | `{email, full_name, password, role}` → 201. Crear `owner` exige ser `owner` |
| PATCH | `/users/{id}` | `users.manage` | `{role?, is_active?}`. Reglas BR-ID-08/09 |
| GET | `/users/roles` | `users.read` | Roles con sus permisos |
| GET | `/users/permissions` | `users.read` | Catálogo `{codigo: descripcion}` |

## Organización

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/organization` | `organization.read` | Datos de la organización activa |
| PATCH | `/organization` | `organization.manage` | `{legal_name?, trade_name?, legal_form?, ruc?, ruc_check_digit?}`; RUC y DV van juntos y se valida el DV |

## Auditoría

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/audit/logs` | `audit.read` | `?limit=1..200&before_seq=&entity_type=&action=`; orden descendente por `seq` (paginación por cursor) |
| GET | `/audit/security-events` | `audit.read` | `?limit=1..200` |
| GET | `/audit/verify` | `audit.read` | `{valid, checked, first_broken_seq}` |

## Finanzas (`/finance`)

Especificación: `docs/specs/FASE2_FINANZAS.md`. **Acceso:** el contexto `business` exige `finance.read` para leer y `finance.manage` para escribir (403 `FORBIDDEN`). Un contexto `personal` solo existe para su dueño, sin importar el rol: para cualquier otro usuario responde 404 `CONTEXT_NOT_FOUND` (no 403, para no revelar que existe). Un id de cuenta, categoría o contraparte de otro contexto responde 404.

**Listados:** paginados por cursor, `?limit=1..200` (50 por defecto) `&before=<id del último recibido>`, más nuevos primero. Movimientos: por `booked_on` y luego `id`, descendente. Cuentas, categorías, contrapartes y lotes: por `id` (uuidv7 = orden de creación), descendente; `include_archived=false` por defecto.

**PATCH:** solo se modifican los campos enviados; `null` explícito borra un campo opcional. `archived: true|false` archiva o desarchiva.

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/finance/contexts` | sesión | Contextos visibles: el de la empresa (con `finance.read`) y el personal propio si existe. `[{id, kind, name, owner_user_id, is_active, created_at}]` |
| POST | `/finance/contexts/personal` | sesión | Crea el contexto personal del usuario ("Personal — {nombre}"). 201; 409 `PERSONAL_CONTEXT_EXISTS` |
| GET | `/finance/contexts/{cid}/accounts` | leer | Cuentas con `balance` actual (saldo inicial + movimientos no anulados) |
| POST | `/finance/contexts/{cid}/accounts` | escribir | `{name, kind, institution?, currency, number_last4?, opening_balance?, opening_date}` → 201 |
| PATCH | `/finance/contexts/{cid}/accounts/{id}` | escribir | `{name?, kind?, institution?, number_last4?, archived?, opening_date?, currency?, opening_balance?}`. Moneda y saldo inicial: 409 `ACCOUNT_HAS_TRANSACTIONS` si ya tiene movimientos (incluso anulados) |
| GET | `/finance/contexts/{cid}/categories` | leer | Categorías `{id, name, kind, parent_id, archived_at}` |
| POST | `/finance/contexts/{cid}/categories` | escribir | `{name, kind: income\|expense, parent_id?}`. Un solo nivel (422 `CATEGORY_TOO_DEEP`); el hijo es del mismo tipo que el padre |
| PATCH | `/finance/contexts/{cid}/categories/{id}` | escribir | `{name?, parent_id?, archived?}` (el tipo no cambia) |
| POST | `/finance/contexts/{cid}/categories/suggested` | escribir | Crea el conjunto sugerido (`finance/suggested.py`, distinto para empresa y personal) solo si no hay categorías; si no, 409 `CATEGORIES_EXIST` |
| GET | `/finance/contexts/{cid}/counterparties` | leer | `?q=` busca por nombre (contiene) o RUC (empieza con) |
| POST | `/finance/contexts/{cid}/counterparties` | escribir | `{name, kind, ruc?, ruc_check_digit?, notes?}`; RUC y DV juntos y DV válido; RUC único por contexto |
| PATCH | `/finance/contexts/{cid}/counterparties/{id}` | escribir | `{name?, kind?, ruc?, ruc_check_digit?, notes?, archived?}` |
| GET | `/finance/contexts/{cid}/transactions` | leer | Filtros: `account_id`, `category_id`, `counterparty_id`, `from`, `to`, `q` (descripción o referencia), `unreviewed=true`, `include_voided=false` |
| GET | `/finance/contexts/{cid}/transactions/{id}` | leer | Un movimiento, con el mismo esquema que un ítem del listado (en el contexto `business`, con `journal_entry`). Mismas reglas de acceso que el listado: un contexto personal solo lo ve su dueño (404 `CONTEXT_NOT_FOUND` para el resto); la empresa pide `finance.read` (403). Devuelve también los anulados. 404 `TRANSACTION_NOT_FOUND` si no es de ese contexto (P-9) |
| POST | `/finance/contexts/{cid}/transactions` | escribir | Alta manual `{account_id, booked_on, amount, description, reference?, category_id?, counterparty_id?}`. Positivo = entra, negativo = sale. Nace revisado |
| PATCH | `/finance/contexts/{cid}/transactions/{id}` | escribir | `{category_id?, counterparty_id?, description?, reference?, reviewed?}`; `booked_on`, `amount`, `account_id` solo si es manual, no anulado y no es transferencia (409 `TRANSACTION_NOT_EDITABLE`). Un anulado no se edita (409 `TRANSACTION_VOIDED`) |
| POST | `/finance/contexts/{cid}/transactions/{id}/void` | escribir | `{reason}` (3 a 300 caracteres). Devuelve la lista de anulados: si es una transferencia, se anulan las dos patas |
| POST | `/finance/contexts/{cid}/transfers` | escribir | `{from_account_id, to_account_id, booked_on, amount_out, amount_in, description, reference?}` (importes positivos). Crea los dos movimientos con el mismo `transfer_group_id`. Misma moneda: `amount_out = amount_in` (las comisiones van aparte). → `{transfer_group_id, outgoing, incoming}` |
| POST | `/finance/contexts/{cid}/imports` | escribir | `multipart/form-data`: `file` (CSV o XLSX, hasta 10 MB y 20.000 filas), `account_id`, `mapping` (JSON, ver abajo); `?rows_limit=200`. Analiza y devuelve el lote con sus filas, errores y duplicados. **No crea movimientos.** 201 |
| GET | `/finance/contexts/{cid}/imports` | leer | Lotes sin filas; `?account_id=&limit=1` da el último lote de una cuenta (para reutilizar su `mapping`) |
| GET | `/finance/contexts/{cid}/imports/{bid}` | leer | Lote con filas en orden de archivo: `?rows_limit=1..1000&rows_after=<último row_number>` |
| PATCH | `/finance/contexts/{cid}/imports/{bid}/rows/{n}` | escribir | `{decision: import\|skip}`. Una fila con error no se puede importar (409 `IMPORT_ROW_HAS_ERROR`) |
| POST | `/finance/contexts/{cid}/imports/{bid}/commit` | escribir | Crea en una transacción los movimientos de las filas `import` sin error (nacen sin revisar). Un lote confirmado o cancelado → 409. Si desde el análisis aparecieron movimientos iguales, los marca como duplicados y responde 409 `IMPORT_NEW_DUPLICATES` para revisar |
| POST | `/finance/contexts/{cid}/imports/{bid}/cancel` | escribir | Cancela un lote analizado |
| GET | `/finance/contexts/{cid}/summary` | leer | `?from&to` (por defecto, los últimos 12 meses calendario). `{balances: [saldo por cuenta al "to"], totals: [por moneda], by_month: [por moneda y mes "YYYY-MM"], expenses_by_category: [por moneda]}`; cada total `{currency, income, expense, net}` con `expense` en positivo. Excluye anulados y transferencias |
| GET | `/finance/summary/consolidated` | sesión | `?from&to`. `{contexts: [{context: {id, kind, name, …}, totals: [{currency, income, expense, net, balance}]}]}`: por cada contexto visible, identificado. No hay total entre contextos ni entre monedas |

### Mapeo de importación (`mapping`)
```json
{
  "has_header": true, "delimiter": ";", "encoding": "auto",
  "date_column": "Fecha", "date_format": "%d/%m/%Y",
  "description_column": "Concepto", "reference_column": "Nro. Operación",
  "amount": {"mode": "single", "column": "Importe"},
  "decimal_separator": ",", "thousands_separator": ".",
  "skip_rows": 0
}
```
- `amount` también puede ser `{"mode": "split", "debit_column": "Débito", "credit_column": "Crédito"}`: débito = sale (negativo), crédito = entra; una fila con los dos o con ninguno es error.
- `delimiter` ∈ `;` `,` tabulador `|`; `encoding` ∈ `auto`, `utf-8`, `cp1252` (`auto` prueba UTF-8 y luego Windows-1252); `thousands_separator` ∈ `.` `,` espacio o vacío, distinto del decimal. Valores por defecto: los del ejemplo (las columnas de fecha, descripción e importe son obligatorias; `reference_column` es opcional).
- Sin encabezado (`has_header: false`), las columnas se indican por posición: `"1"`, `"2"`…
- `skip_rows`: filas a saltear al principio (títulos del banco antes del encabezado). Las filas vacías se ignoran.
- Importes: `1.234.567`, `1.234,50`, `-1.000`, `1.000-`, `(1.000)`. La moneda puede venir escrita junto al número (`Gs. 1.500.000`, `1.500.000 Gs`, `₲`, `US$`, `U$S`, `R$`, `€` o el código ISO). Se acepta solo si es la moneda de la cuenta; si no, la fila da error (`El importe está en USD y la cuenta en PYG: …`) y nunca se convierte.
- Fechas: si traen la hora de la operación (`15/01/2026 10:23`, `2026-01-15T10:23:05`, `10:23 p. m.`) y `date_format` no la pide, la hora se ignora.
- XLSX: las fórmulas **no** se evalúan, se usa el valor guardado en el archivo. Los números se leen como los muestra Excel (15 dígitos significativos): una celda calculada que vale `1234.5600000000001` es `1234,56`. Una fecha guardada como número, en una celda sin formato de fecha, se lee como número de serie de Excel (1960 a 2099). `.xls` se rechaza con un mensaje que pide CSV o XLSX.
- Las filas de totales o saldo final al pie de un extracto quedan como filas con error (sin fecha o sin importe) y no se importan.
- Cada fila trae `row_number` (fila del archivo), `raw` (la fila original como texto), los valores interpretados, `error` (en español, p. ej. `"Fecha inválida: 31/02/2026"`), `duplicate_of` (movimiento existente no anulado de la misma cuenta con la misma clave) y `duplicate_in_file` (fila anterior igual). Duplicados y filas con error nacen con `decision = "skip"`.

## Contabilidad (`/accounting`)

Especificación: `docs/specs/FASE3_CONTABILIDAD.md` (D-035 a D-043; implementación D-044 a D-055) y `docs/specs/FASE3B_CONTABILIDAD.md` (D-056 a D-067; implementación D-068 a D-081). Contabilidad de la organización: no hay contextos personales. **Permisos:** `accounting.read` para leer (todos los roles), `accounting.manage` para el plan y los borradores (propietario, administrador, contador) y `accounting.post` para contabilizar, revertir, validar el plan, configurar, crear ejercicios y cerrar (propietario y contador; el administrador recibe 403 con `details.missing = ["accounting.post"]`).

**Importes:** debe y haber en guaraníes enteros, como string (`"150000"`); un número JSON da 422. La cotización (`fx_rate`) admite hasta 6 decimales (`"7300.25"`). Las columnas `fx_*` de una línea son informativas: el asiento balancea en guaraníes (D-036).

**Estados del asiento:** `draft` → `posted` (número correlativo por ejercicio, lo asigna la base) → `reversed` (con su reversión contabilizada); `draft` → `discarded`. Lo contabilizado no cambia ni se borra: lo impiden triggers (ver `docs/DATABASE_SCHEMA.md`). Todos los reportes devuelven `chart_status` (`none`, `pending`, `validated`): si no es `validated`, la interfaz avisa que el plan no lo validó un contador.

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/accounting/chart` | read | `{chart_status, chart_validated_*, retained_earnings_account_id, balance_at, accounts}`. Árbol por código (`children`) o lista plana con `?flat=true`. Con `?balance_at=YYYY-MM-DD`, `balance` de cada cuenta a esa fecha en el sentido de su tipo (las agrupadoras suman su subárbol). Cada cuenta: `{id, code, name, kind, normal_side, is_postable, parent_id, origin, note, archived_at, in_use}`. Sin paginación |
| POST | `/accounting/chart/load-proposed` | manage | Carga las 173 cuentas del plan propuesto (RG 49/2014, `docs/research/plan_de_cuentas_propuesto.yaml`) y deja el plan `pending`. 201 con la lista; 409 `CHART_NOT_EMPTY` si ya hay cuentas |
| POST | `/accounting/chart/accounts` | manage | `{parent_id?, code, name, is_postable, kind?, normal_side?, note?}`. El código es el del padre más un segmento (sin padre, un solo segmento); el padre es agrupador; el tipo, por defecto el del padre, es del mismo estado (patrimonial o de resultados); la naturaleza, por defecto la del tipo. Vuelve el plan a `pending` (D-046). 201 |
| PATCH | `/accounting/chart/accounts/{id}` | manage | `{name?, note?, code?, kind?, normal_side?, is_postable?, archived?}`. Con líneas, solo `name`, `note` y `archived` (409 `ACCOUNT_IN_USE`). No se archiva con saldo, con hijas sin archivar, usada en borradores, en la configuración o en finanzas. Un cambio estructural vuelve el plan a `pending` |
| POST | `/accounting/chart/validate` | post | `{validated_by_name, validated_reference}` (nombre y matrícula del contador) → `validated`. 409 `CHART_EMPTY` sin cuentas |
| POST | `/accounting/chart/invalidate` | post | Vuelve a `pending`. 409 `CHART_NOT_VALIDATED` si no estaba validado |
| GET | `/accounting/settings` | read | `{chart_status, chart_validated_by_name, chart_validated_reference, chart_validated_at, retained_earnings_account_id, disposal_account_id, cost_centers_required, default_asset_start_rule}` |
| PUT | `/accounting/settings` | post | Campos opcionales (solo cambian los enviados): `retained_earnings_account_id` (cuenta de patrimonio imputable y no archivada, o `null`; 422 `INVALID_RETAINED_EARNINGS_ACCOUNT`), `disposal_account_id` (resultado por bajas: ingreso o gasto imputable, o `null` para usar `17.01`; 422 `INVALID_DISPOSAL_ACCOUNT`), `cost_centers_required` (bool), `default_asset_start_rule` (`next_month` o `next_fiscal_year`, D-064). `null` en un campo obligatorio: 422 `FIELD_REQUIRED` |
| GET | `/accounting/fiscal-years` | read | Todos, más nuevos primero, con `periods` |
| POST | `/accounting/fiscal-years` | post | `{year}` (año civil) o `{start_date, end_date}` (a lo sumo 12 meses calendario, D-047). Crea un período por mes calendario. 201; 422 `FISCAL_YEAR_INVALID`; 409 `FISCAL_YEAR_OVERLAP` |
| GET | `/accounting/fiscal-years/{id}` | read | `{id, start_date, end_date, status, closed_at, closed_by, closing_entry_id, last_entry_number, periods}` |
| POST | `/accounting/fiscal-years/{id}/close` | post | Exige todos los períodos cerrados (409 `PERIODS_OPEN`, `details.periods`), ningún borrador (409 `FISCAL_YEAR_HAS_DRAFTS`) y la cuenta de resultados configurada (409 `RETAINED_EARNINGS_NOT_SET`). Contabiliza la refundición (cada cuenta de ingreso y gasto con saldo, contra esa cuenta, fechada el último día; sin resultados no hay asiento) y cierra el ejercicio para siempre (D-050) |
| POST | `/accounting/periods/{id}/close` | post | 409 `PERIOD_HAS_DRAFTS` con `details.drafts = [{id, entry_date, description}]`; 409 `PERIOD_ALREADY_CLOSED`; 409 `FISCAL_YEAR_CLOSED` |
| POST | `/accounting/periods/{id}/reopen` | post | `{reason}` (3 a 300 caracteres). 409 `PERIOD_NOT_CLOSED`, `FISCAL_YEAR_CLOSED`. Queda auditado con el motivo |
| GET | `/accounting/entries` | read | Más recientes primero (fecha, id), sin líneas (`lines: null`). Filtros: `fiscal_year_id`, `status`, `kind`, `from`, `to`, `account_id`, `q` (descripción, referencia o número). Cursor `?limit=1..200` (50) `&before=<id>` |
| POST | `/accounting/entries` | manage | Borrador `{entry_date, description, document_reference?, lines: [{account_id, debit?, credit?, description?, fx_currency?, fx_amount?, fx_rate?, cost_center_id?}]}` (1 a 500 líneas; puede estar desbalanceado). El centro de costos va solo en cuentas de ingreso o gasto (422 `COST_CENTER_NOT_ALLOWED`), existe (422 `COST_CENTER_NOT_FOUND`) y no está archivado (422 `COST_CENTER_ARCHIVED`). El ejercicio sale de la fecha (422 `FISCAL_YEAR_NOT_FOUND`, 409 `FISCAL_YEAR_CLOSED`). 201 |
| GET | `/accounting/entries/{id}` | read | `{id, fiscal_year_id, number, status, kind, entry_date, description, document_reference, reverses_entry_id, reversed_by_entry_id, source_transaction_id, source_context_id, created_by, created_by_name, posted_by, posted_by_name, posted_at, discarded_*, total_debit, total_credit, balanced, lines: [{id, line_no, account_id, account_code, account_name, debit, credit, description, fx_*, cost_center_id, cost_center_code}]}`. `created_by_name` y `posted_by_name` son el nombre visible del usuario (o `null`), sin ningún otro dato suyo: así el rol Consulta, que no lee `/users`, ve quién hizo cada cosa (P-10). `kind`: `manual`, `finance`, `closing`, `reversal`, `depreciation`, `disposal`, `recurring` |
| PATCH | `/accounting/entries/{id}` | manage | Mismo cuerpo que el alta: reemplaza cabecera y líneas, solo en borrador (409 `ENTRY_NOT_DRAFT`). Los borradores generados (`closing`, `depreciation`, `disposal`) no se editan: se descartan y se vuelven a generar (409 `ENTRY_NOT_EDITABLE`) |
| POST | `/accounting/entries/{id}/post` | post | Contabiliza y numera. 422 `ENTRY_UNBALANCED` (`details: {debit, credit, difference}`), `ENTRY_TOO_FEW_LINES`, `ACCOUNT_NOT_POSTABLE` (`details.lines`), `COST_CENTER_REQUIRED` (con `cost_centers_required`, en `manual`, `finance` y `recurring`; `details.lines`), `COST_CENTER_ARCHIVED`; 409 `PERIOD_CLOSED`, `FISCAL_YEAR_CLOSED`, `SOURCE_TRANSACTION_VOIDED`, `ENTRY_NOT_DRAFT`, y para depreciaciones y bajas `DEPRECIATION_OUT_OF_SEQUENCE`, `ASSET_DISPOSED`, `DEPRECIATION_AFTER_DISPOSAL`, `ASSET_ALREADY_DISPOSED` |
| POST | `/accounting/entries/{id}/reverse` | post | `{reason, date?}` → la reversión contabilizada (líneas invertidas); el original queda `reversed`. Por defecto en la fecha del original; si su período está cerrado, 409 `PERIOD_CLOSED` con `details.date` para elegir otra (no anterior: 422 `REVERSAL_DATE_INVALID`). 409 `ENTRY_NOT_POSTED`, `ENTRY_NOT_REVERSIBLE` (reversiones y refundiciones). La reversión copia el centro de costos de cada línea. Depreciaciones y bajas (D-074): en el mismo ejercicio (409 `REVERSAL_OTHER_YEAR`), solo la última corrida viva (409 `DEPRECIATION_RUN_NOT_LAST`), no si incluye un bien dado de baja (409 `ASSET_DISPOSED`); una baja no se revierte con corridas vivas desde su mes (409 `DEPRECIATION_AFTER_DISPOSAL`). Revertir una baja devuelve el bien a `active` |
| POST | `/accounting/entries/{id}/discard` | manage | `{reason}`, solo borradores |
| POST | `/accounting/entries/from-transaction/{tid}` | manage | Borrador propuesto desde un movimiento **de la empresa** (D-041, D-052): ingreso = debe banco / haber categoría; gasto al revés. Cuerpo opcional `{fx_rate?, amount_pyg?}` para movimientos en otra moneda. 404 `TRANSACTION_NOT_FOUND` (también si es personal); 409 `TRANSACTION_HAS_ENTRY` (`details.entry_id`), `TRANSACTION_VOIDED`; 422 `LEDGER_ACCOUNT_MISSING` (`details.missing` dice cuál), `CATEGORY_REQUIRED`, `TRANSFER_NOT_SUPPORTED`, `FX_RATE_REQUIRED`, `FX_NOT_APPLICABLE`, `FX_ROUNDING_REQUIRED` (`details: {exact, floor, ceil}`), `FX_ROUNDING_INVALID`. 201 |
| GET | `/accounting/reports/journal` | read | Libro diario `?from&to` (obligatorios): asientos contabilizados y revertidos por fecha y número, con líneas, `created_by_name` y `posted_by_name`; `total_debit`, `total_credit`. Cursor `?limit=1..1000` (200) `&after=<id del último asiento>`; `next_cursor`. Con `?format=xlsx`, el diario completo sin paginar |
| GET | `/accounting/reports/ledger/{account_id}` | read | Libro mayor de una cuenta imputable `?from&to`: `opening_balance` (antes del rango), `movements` con `balance` acumulado (según la naturaleza de la cuenta), `total_debit`, `total_credit`, `closing_balance`. Cursor `?limit=1..1000` (200) `&after=<line_id>`; el acumulado sigue entre páginas. Con `?format=xlsx`, el mayor completo |
| GET | `/accounting/reports/trial-balance` | read | `?from&to`: por cuenta con movimiento en el rango **o** saldo inicial distinto de cero (D-062, D-075): saldo inicial (`opening_debit`, `opening_credit`: todo lo contabilizado antes de `from`, con la refundición), sumas del rango (`debit`, `credit`), saldo del rango (`debit_balance`, `credit_balance`) y saldo final (`closing_debit`, `closing_credit`); totales de cada columna (`total_opening_*`, `total_*`, `total_closing_*`) y `balanced` (cuadran las tres parejas). `?format=xlsx` |
| GET | `/accounting/reports/balance-sheet` | read | `?at=`: `assets`, `liabilities`, `equity` por la jerarquía del plan (cada nodo con `amount` de su subárbol; las regularizadoras restan), totales, `result` (resultado no refundido), `total_liabilities_and_equity` y `balanced`. `?format=xlsx` |
| GET | `/accounting/reports/income-statement` | read | `?from&to`: `accounts` (ingresos y gastos por la jerarquía, RG 49/2014 Anexo 2), `total_income`, `total_expense`, `result`. No cuenta la refundición. Con `?by_cost_center=true`, `cost_center_columns` (`[{cost_center_id, code, name, total_income, total_expense, result}]`, una por centro con movimiento en el rango, por código, y una última "Sin centro" con `cost_center_id` y `code` `null`) y en cada nodo `column_amounts` en ese orden; las columnas suman el total. Sin el parámetro, `cost_center_columns` es `null`. `?format=xlsx` |

### Fase 3B: activos fijos, centros de costos y recurrentes

Especificación: `docs/specs/FASE3B_CONTABILIDAD.md`. Las vidas útiles, los residuales y el cuadro fiscal son **candidatos sin validar** (D-056, D-064 a D-067): se muestran como `pending` hasta que un contador los valida. Importes como string en guaraníes enteros; porcentajes como string con hasta dos decimales.

| Método | Ruta | Permiso | Notas |
|---|---|---|---|
| GET | `/accounting/asset-categories` | read | Todas (`?include_archived=true` por defecto). Cada una: `{id, code, name, useful_life_months, residual_rate, asset_account_id, accumulated_account_id, expense_account_id, source_url, legal_reference, citation, note, validation_status, validated_by_name, validated_reference, validated_at, archived_at, complete, missing}`; `missing` dice qué le falta para usarse (D-068) |
| POST | `/accounting/asset-categories` | manage | `{name, code?, useful_life_months?, residual_rate?, asset_account_id?, accumulated_account_id?, expense_account_id?, source_url?, legal_reference?, citation?, note?}`. Cuentas imputables del tipo correcto (bien: activo deudor; acumulada: activo acreedor; gasto: gasto; 422 `INVALID_CATEGORY_ACCOUNT`); residual de 0 a 20 % (422 `RESIDUAL_RATE_INVALID`); 409 `ASSET_CATEGORY_CODE_TAKEN`. 201 |
| POST | `/accounting/asset-categories/load-proposed` | manage | Carga las 34 candidatas (`docs/research/categorias_activo_fijo_candidatas.yaml`, copia empaquetada idéntica), `pending`, con las cuentas del plan propuesto si existen. 201; 409 `ASSET_CATEGORIES_NOT_EMPTY` |
| GET | `/accounting/asset-categories/{id}` | read | 404 `ASSET_CATEGORY_NOT_FOUND` |
| PATCH | `/accounting/asset-categories/{id}` | manage | Campos del alta (menos `code`) más `archived`. Un cambio de vida útil, residual o cuentas vuelve a `pending`. Las cuentas no cambian si hay bienes con depreciaciones vivas (409 `ASSET_CATEGORY_IN_USE`, D-081) |
| POST | `/accounting/asset-categories/{id}/validate` | post | `{validated_by_name, validated_reference}` → `validated`. 422 `ASSET_CATEGORY_INCOMPLETE` |
| GET | `/accounting/fixed-assets` | read | Filtros `category_id`, `status` (`active`, `disposed`), `q` (nombre, descripción o referencia). Sin cuotas (`installments: null`) |
| POST | `/accounting/fixed-assets` | manage | `{category_id, name, acquired_on, cost, description?, serial_or_reference?, residual_value?, useful_life_months?, fiscal_useful_life_months?, fiscal_residual_rate?, start_rule?, acquisition_entry_id?, source_transaction_id?}`. Por defecto, la vida útil (contable y fiscal) y el residual fiscal de la categoría, el residual contable igual al fiscal y `start_rule` de la configuración (D-064, D-065, D-070). `depreciation_start` sale de `acquired_on` y `start_rule`. 422 `ASSET_CATEGORY_INCOMPLETE` (dice qué falta), `ASSET_CATEGORY_ARCHIVED`, `RESIDUAL_INVALID` (residual ≥ costo), `RESIDUAL_RATE_INVALID` (fiscal > 20 %), `DEPRECIABLE_TOO_SMALL`, `DEPRECIATION_START_BEFORE_BOOKS`; 409 `DEPRECIATION_ALREADY_RUN`. 201 con `installments` |
| GET | `/accounting/fixed-assets/{id}` | read | `{..., status, disposed_on, disposal_*, disposal_entry_id, accumulated_depreciation, net_book_value, warnings, installments: [{installment, month, amount, status, entry_id}]}`. `status` de la cuota: `pending`, `draft` o `posted`. `warnings` avisa si el bien se adquirió antes del 14/10/2021 (otra versión de la norma). 404 `FIXED_ASSET_NOT_FOUND` |
| PATCH | `/accounting/fixed-assets/{id}` | manage | Campos del alta. Con depreciaciones vivas (borrador o contabilizadas) solo cambian nombre, descripción, referencia y asiento de compra (409 `ASSET_HAS_DEPRECIATION`, D-071); dado de baja, nada (409 `ASSET_DISPOSED`) |
| POST | `/accounting/fixed-assets/{id}/dispose` | manage | `{date, kind, reason, document_reference}` (`kind`: `sale` venta, `scrap` destrucción o desuso, `donation` donación; el documento es obligatorio, D-059 y §6). Crea el borrador de baja (`EntryOut`, `kind = disposal`): debe la acumulada, debe la cuenta de resultado por el neto, haber el costo. El bien pasa a `disposed` al contabilizarlo; descartar o revertir lo devuelve a `active`. 409 `DEPRECIATION_NOT_UP_TO_DATE` (`details.month`), `DEPRECIATION_AFTER_DISPOSAL`, `ASSET_ALREADY_DISPOSED`, `ASSET_DISPOSAL_PENDING`, `PERIOD_CLOSED`, `FISCAL_YEAR_CLOSED`; 422 `DISPOSAL_DATE_INVALID` (antes del inicio de la depreciación), `DISPOSAL_ACCOUNT_NOT_SET`. 201 |
| POST | `/accounting/depreciation/run` | manage | `{period_id}`: borrador de depreciación del período (`kind = depreciation`, fechado el último día), una línea por cuenta y el detalle por bien. 201 `{id, period_id, entry_id, entry_status, total, created_at, entry, items: [{asset_id, asset_name, category_id, installment, amount}]}`. 409 `DEPRECIATION_RUN_EXISTS` (`details.run_id`), `DEPRECIATION_MONTH_MISSING` (`details.month`: el primer mes sin correr), `PERIOD_CLOSED`; 422 `NOTHING_TO_DEPRECIATE`, `ASSET_CATEGORY_INCOMPLETE` |
| GET | `/accounting/depreciation/runs` | read | Más recientes primero; `?fiscal_year_id`. Sin asiento ni detalle |
| GET | `/accounting/depreciation/runs/{id}` | read | Con `entry` e `items`. 404 `DEPRECIATION_RUN_NOT_FOUND` |
| GET | `/accounting/reports/depreciation-schedule` | read | `?fiscal_year_id` (obligatorio). Cuadro con las columnas del Anexo de la RG 77/2020 (D-067, D-077), por categoría: `{chart_status, fiscal_year_id, date_from, date_to, warnings, categories: [{category_id, name, validation_status, assets: [fila], totals}], totals, reconciliation: {lines: [{account_id, code, name, ledger_balance, schedule_amount, difference}], schedule_total, ledger_total, reconciled}}`. Fila: `asset_id, description, acquired_on, disposed_on, cost, revaluation_coefficient` (0), `fiscal_residual_rate, fiscal_residual_value, fiscal_useful_life_{months,years}, fiscal_remaining_{months,years}, fiscal_net_previous, fiscal_depreciable, fiscal_depreciation, fiscal_accumulated, fiscal_net_value, residual_value, useful_life_{months,years}, remaining_{months,years}, accounting_net_previous, accounting_depreciable, accounting_depreciation, non_deductible, accounting_accumulated, accounting_net_value`. `warnings` incluye IRE SIMPLE y revalúo. `reconciled` dice si el total de la columna 22 cuadra con las cuentas del balance. `?format=xlsx` |
| GET | `/accounting/cost-centers` | read | `?include_archived=false`. `{id, code, name, archived_at}` |
| POST | `/accounting/cost-centers` | manage | `{code, name}` (código: letras, números, `-`, `_`, `.`). 409 `COST_CENTER_CODE_TAKEN`. 201 |
| GET | `/accounting/cost-centers/{id}` | read | 404 `COST_CENTER_NOT_FOUND` |
| PATCH | `/accounting/cost-centers/{id}` | manage | `{code?, name?, archived?}` |
| GET | `/accounting/recurring` | read | Plantillas `{id, description, document_reference, day_of_month, start_date, end_date, status, total, lines: [{line_no, account_id, account_code, account_name, debit, credit, description, cost_center_id}], created_at}` |
| POST | `/accounting/recurring` | manage | `{description, day_of_month (1 a 31), start_date, end_date?, document_reference?, status?, lines}` (como las de un asiento; al menos dos y balanceadas: 422 `ENTRY_UNBALANCED`, `ENTRY_TOO_FEW_LINES`). 201 |
| GET | `/accounting/recurring/due` | read | `?period_id`: qué se generaría `[{template_id, description, entry_date, total}]` (activas, en vigencia y sin generación viva) |
| POST | `/accounting/recurring/generate` | manage | `{period_id}` → `{created, existing}` (asientos `recurring` en borrador). Un día 31 cae el último día de un mes corto. Generar dos veces no duplica (lo existente va en `existing`). Todo o nada: 422 con el nombre de la plantilla que falla (D-079). 409 `PERIOD_CLOSED` |
| GET | `/accounting/recurring/{id}` | read | 404 `RECURRING_TEMPLATE_NOT_FOUND` |
| PATCH | `/accounting/recurring/{id}` | manage | Campos del alta más `status` (`active` o `paused`); `lines` reemplaza todas. El fin de vigencia es `end_date` |

El cierre del ejercicio exige además la depreciación de todos sus meses (409 `DEPRECIATION_MISSING`, `details.month`) y guarda los valores netos fiscal y contable de cada bien (`asset_year_values`, D-066).

**Exportación XLSX (D-063, D-076):** `?format=xlsx` en el diario, el mayor, el balance de comprobación, el balance general, el estado de resultados (también por centro) y el cuadro de depreciación. Devuelve `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` como adjunto. Encabezado con razón social, RUC, título, rango o fecha y emisión; si el plan no está validado, el aviso "Plan de cuentas sin validar por un contador". Importes como números enteros con formato `#,##0`; totales iguales a los del JSON.

**Finanzas ↔ contabilidad:** `PATCH /finance/contexts/{cid}/accounts/{id}` y `/categories/{id}` aceptan `ledger_account_id` (o `null`) solo en el contexto `business` (422 `LEDGER_ACCOUNT_BUSINESS_ONLY` en el personal) y con `accounting.manage`; la cuenta contable es imputable (422 `ACCOUNT_NOT_POSTABLE`) y del tipo correcto (422 `LEDGER_ACCOUNT_KIND_MISMATCH`: activo o pasivo para un banco, el de la categoría para una categoría). Los movimientos del contexto `business` traen `journal_entry` (`{id, number, status}` del asiento vivo o del último revertido; `null` si no hay); en el personal siempre `null`. Con asiento contabilizado, anular o cambiar importe, fecha o cuenta da 409 `TRANSACTION_HAS_POSTED_ENTRY` (BR-ACC-11, D-048).

**Errores de contabilidad:**

| HTTP | Códigos |
|---|---|
| 400 | `INVALID_CURSOR` |
| 404 | `LEDGER_ACCOUNT_NOT_FOUND`, `FISCAL_YEAR_NOT_FOUND`, `PERIOD_NOT_FOUND`, `ENTRY_NOT_FOUND`, `TRANSACTION_NOT_FOUND`, `ASSET_CATEGORY_NOT_FOUND`, `FIXED_ASSET_NOT_FOUND`, `DEPRECIATION_RUN_NOT_FOUND`, `COST_CENTER_NOT_FOUND`, `RECURRING_TEMPLATE_NOT_FOUND` |
| 409 | `CHART_NOT_EMPTY`, `CHART_EMPTY`, `CHART_NOT_VALIDATED`, `ACCOUNT_CODE_TAKEN`, `ACCOUNT_IN_USE`, `ACCOUNT_HAS_BALANCE`, `ACCOUNT_HAS_CHILDREN`, `ACCOUNT_IN_DRAFTS`, `ACCOUNT_IN_SETTINGS`, `ACCOUNT_MAPPED_IN_FINANCE`, `FISCAL_YEAR_OVERLAP`, `FISCAL_YEAR_CLOSED`, `FISCAL_YEAR_HAS_DRAFTS`, `PERIODS_OPEN`, `RETAINED_EARNINGS_NOT_SET`, `PERIOD_CLOSED`, `PERIOD_ALREADY_CLOSED`, `PERIOD_NOT_CLOSED`, `PERIOD_HAS_DRAFTS`, `ENTRY_NOT_DRAFT`, `ENTRY_NOT_POSTED`, `ENTRY_NOT_REVERSIBLE`, `ENTRY_CHANGED`, `SOURCE_TRANSACTION_VOIDED`, `TRANSACTION_HAS_ENTRY`, `TRANSACTION_HAS_POSTED_ENTRY`, `TRANSACTION_VOIDED`; 3B: `ENTRY_NOT_EDITABLE`, `ACCOUNT_IN_ASSET_CATEGORY`, `ASSET_CATEGORIES_NOT_EMPTY`, `ASSET_CATEGORY_CODE_TAKEN`, `ASSET_CATEGORY_IN_USE`, `ASSET_HAS_DEPRECIATION`, `ASSET_DISPOSED`, `ASSET_ALREADY_DISPOSED`, `ASSET_DISPOSAL_PENDING`, `DEPRECIATION_ALREADY_RUN`, `DEPRECIATION_RUN_EXISTS`, `DEPRECIATION_RUN_MISMATCH`, `DEPRECIATION_MONTH_MISSING`, `DEPRECIATION_OUT_OF_SEQUENCE`, `DEPRECIATION_RUN_NOT_LAST`, `DEPRECIATION_NOT_UP_TO_DATE`, `DEPRECIATION_AFTER_DISPOSAL`, `DEPRECIATION_MISSING`, `DISPOSAL_WITHOUT_ASSET`, `REVERSAL_OTHER_YEAR`, `COST_CENTER_CODE_TAKEN`, `RECURRING_ALREADY_GENERATED` |
| 422 | `ACCOUNT_CODE_INVALID`, `ACCOUNT_KIND_MISMATCH`, `ACCOUNT_KIND_REQUIRED`, `PARENT_IS_POSTABLE`, `INVALID_RETAINED_EARNINGS_ACCOUNT`, `FISCAL_YEAR_INVALID`, `FISCAL_YEAR_NOT_FOUND` (fecha sin ejercicio), `LEDGER_ACCOUNT_NOT_FOUND` (en una línea), `ACCOUNT_NOT_POSTABLE`, `LINE_DEBIT_XOR_CREDIT`, `FX_INCOMPLETE`, `INVALID_AMOUNT`, `ENTRY_UNBALANCED`, `ENTRY_TOO_FEW_LINES`, `REVERSAL_DATE_INVALID`, `INVALID_RANGE`, `LEDGER_ACCOUNT_BUSINESS_ONLY`, `LEDGER_ACCOUNT_KIND_MISMATCH`, `LEDGER_ACCOUNT_MISSING`, `CATEGORY_REQUIRED`, `TRANSFER_NOT_SUPPORTED`, `FX_RATE_REQUIRED`, `FX_NOT_APPLICABLE`, `FX_ROUNDING_REQUIRED`, `FX_ROUNDING_INVALID`; 3B: `INVALID_DISPOSAL_ACCOUNT`, `FIELD_REQUIRED`, `NAME_REQUIRED`, `INVALID_CATEGORY_ACCOUNT`, `RESIDUAL_RATE_INVALID`, `RESIDUAL_INVALID`, `ASSET_CATEGORY_INCOMPLETE`, `ASSET_CATEGORY_ARCHIVED`, `DEPRECIABLE_TOO_SMALL`, `DEPRECIATION_START_BEFORE_BOOKS`, `NOTHING_TO_DEPRECIATE`, `DISPOSAL_DATE_INVALID`, `DISPOSAL_ACCOUNT_NOT_SET`, `COST_CENTER_NOT_FOUND` (en una línea), `COST_CENTER_ARCHIVED`, `COST_CENTER_NOT_ALLOWED`, `COST_CENTER_REQUIRED` |

## Acciones auditadas
`system.setup`, `organization.updated`, `user.created`, `user.updated`.

Finanzas (`entity_type` = `finance.<entidad>`; en un contexto personal, `finance.personal.<entidad>`, visible solo para su dueño): `finance.context.created` (personal), `finance.account.{created,updated,archived,unarchived}`, `finance.category.{created,updated}`, `finance.counterparty.{created,updated}`, `finance.transaction.{created,updated,voided}`, `finance.import.{previewed,committed,cancelled}` (un evento por lote, no por fila). Los cambios registran solo los campos que cambian.

Contabilidad (`entity_type` = `accounting.<entidad>`): `accounting.chart.{loaded,pending,validated,invalidated}`, `accounting.ledger_account.{created,updated,archived,unarchived}` (la carga del plan propuesto audita cada cuenta), `accounting.settings.updated`, `accounting.fiscal_year.{created,closed}` (el cierre registra el resultado y la refundición), `accounting.period.{closed,reopened}` (con el motivo), `accounting.journal_entry.{created,updated,posted,reversed,discarded}` (las líneas van en el registro del alta y de la edición; la reversión registra el asiento que revierte y el motivo). 3B: `accounting.asset_categories.loaded`, `accounting.asset_category.{created,updated,validated}`, `accounting.fixed_asset.{created,updated,disposal_drafted,disposed,disposal_discarded,disposal_reversed}`, `accounting.depreciation_run.created`, `accounting.cost_center.{created,updated}`, `accounting.recurring_template.{created,updated}`, `accounting.recurring_generation.created`.
