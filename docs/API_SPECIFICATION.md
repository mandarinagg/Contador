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

## Acciones auditadas
`system.setup`, `organization.updated`, `user.created`, `user.updated`.

Finanzas (`entity_type` = `finance.<entidad>`; en un contexto personal, `finance.personal.<entidad>`, visible solo para su dueño): `finance.context.created` (personal), `finance.account.{created,updated,archived,unarchived}`, `finance.category.{created,updated}`, `finance.counterparty.{created,updated}`, `finance.transaction.{created,updated,voided}`, `finance.import.{previewed,committed,cancelled}` (un evento por lote, no por fila). Los cambios registran solo los campos que cambian.
