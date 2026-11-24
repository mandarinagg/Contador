# Especificación — Fase 2: Finanzas (backend)

**Estado:** aprobada por el jefe de proyecto (2026-11-24). Es el contrato para el backend y la interfaz de la fase 2.
Reglas de negocio: BR-FIN-01 a BR-FIN-09 (`docs/BUSINESS_RULES.md`). Decisiones: D-023 a D-027 (`docs/DECISIONS.md`).

## 1. Decisiones de modelo (no reabrir sin pasar por el jefe de proyecto)

| ID | Decisión | Motivo |
|---|---|---|
| D-023 | **Contexto financiero** (`finance.contexts`): `kind ∈ {business, personal}`. Cada organización tiene **exactamente un** contexto `business`. Un contexto `personal` pertenece a **un usuario** (`owner_user_id`) y hay como máximo uno por usuario y organización | BR-FIN-01: la separación es estructural, no una etiqueta |
| D-024 | **Las finanzas personales son privadas de su dueño.** Un contexto `personal` solo lo ve y lo opera su `owner_user_id`, **sin importar el rol** (un administrador o el contador no ven las finanzas personales del propietario). Los permisos `finance.*` aplican al contexto `business` | Privacidad: son datos personales, no de la empresa |
| D-025 | La separación se **impone en la base**: cuentas, categorías y contrapartes tienen `UNIQUE (id, context_id)`, y los movimientos las referencian con **claves foráneas compuestas** `(x_id, context_id)`. Es imposible, aun con un error de código, que un movimiento personal use una cuenta o categoría empresarial. Igual con la moneda: el movimiento referencia `(account_id, context_id, currency)` | Defensa en profundidad de BR-FIN-01 |
| D-026 | **Importes:** `NUMERIC(18,2)` en la base, `Decimal` en Python y **string** en JSON (nunca `float`). Monedas permitidas por catálogo en código: `PYG` (0 decimales), `USD`, `BRL`, `ARS`, `EUR` (2 decimales). Un importe con más decimales que su moneda se rechaza (no se redondea). Signo: positivo = entra dinero, negativo = sale. **No se suman monedas distintas** ni se convierten (no hay fuente de cotizaciones todavía) | BR-ACC-05; evitar totales engañosos |
| D-027 | **Nada se borra:** un movimiento se **anula** (`voided_at`, `voided_by`, `void_reason` obligatorio) y deja de contar en saldos; cuentas, categorías y contrapartes se **archivan**. Todo alta, cambio, anulación y archivo se audita (`audit.record`, solo campos que cambian). La importación se audita **por lote** (no por fila) | "No eliminar información sin autorización"; trazabilidad |

## 2. Esquema `finance` (migración `0002_finanzas`, `down_revision = "0001"` — verificar el id real de la 0001)

Todas las tablas: `id uuid PK DEFAULT uuidv7()`, `created_at`, `updated_at` (mismo `TimestampMixin` que `core`), y `organization_id` donde se indica. Convención de nombres de restricciones: la de `app.core.db.Base`.

### `finance.contexts`
| Columna | Tipo | Reglas |
|---|---|---|
| organization_id | uuid FK core.organizations | NOT NULL |
| kind | varchar(10) | CHECK `business`/`personal` |
| name | varchar(100) | NOT NULL ("Empresa", "Personal — {nombre}") |
| owner_user_id | uuid FK core.users | NULL si `business`; NOT NULL si `personal` (CHECK) |
| is_active | bool | DEFAULT true |

Índices únicos parciales: `(organization_id) WHERE kind='business'`; `(organization_id, owner_user_id) WHERE kind='personal'`.
La migración crea el contexto `business` de cada organización existente. `POST /system/setup` lo crea junto con la organización (misma transacción).

### `finance.accounts`
`context_id` FK, `name` varchar(100), `kind` CHECK ∈ {`cash`, `checking`, `savings`, `credit_card`, `digital_wallet`, `other`}, `institution` varchar(100) NULL, `currency` char(3) CHECK catálogo, `number_last4` varchar(4) NULL CHECK `^[0-9]{4}$` (**solo los últimos 4 dígitos**, nunca el número completo), `opening_balance` numeric(18,2) DEFAULT 0, `opening_date` date NOT NULL, `archived_at` timestamptz NULL.
`UNIQUE (id, context_id)`, `UNIQUE (id, context_id, currency)`, `UNIQUE (context_id, name)`.

### `finance.categories`
`context_id` FK, `name` varchar(80), `kind` CHECK ∈ {`income`, `expense`}, `parent_id` NULL (un solo nivel: el padre no puede tener padre — validar en servicio), `archived_at`.
`UNIQUE (id, context_id)`, `UNIQUE (context_id, parent_id, name)` con `NULLS NOT DISTINCT`.
FK compuesta `(parent_id, context_id) → (id, context_id)`.

### `finance.counterparties`
`context_id` FK, `name` varchar(150), `ruc` varchar(8) NULL + `ruc_check_digit` char(1) NULL (mismas CHECK que `core.organizations`; DV validado con `organizations.ruc.ruc_check_digit`), `kind` CHECK ∈ {`customer`, `supplier`, `employee`, `bank`, `government`, `person`, `other`}, `notes` varchar(500) NULL, `archived_at`.
`UNIQUE (id, context_id)`; único parcial `(context_id, ruc) WHERE ruc IS NOT NULL`.

### `finance.import_batches`
`context_id`, `account_id` (FK compuesta con context), `filename` varchar(255), `file_sha256` bytea(32), `file_format` CHECK ∈ {`csv`, `xlsx`}, `mapping` jsonb, `status` CHECK ∈ {`previewed`, `committed`, `cancelled`}, `rows_total`, `rows_imported`, `rows_duplicate`, `rows_error` int, `created_by` FK users, `committed_at` NULL.

### `finance.import_rows`
`batch_id` FK ON DELETE CASCADE, `row_number` int, `raw` jsonb (la fila original), `booked_on` date NULL, `amount` numeric(18,2) NULL, `description` varchar(500) NULL, `reference` varchar(100) NULL, `error` varchar(300) NULL, `duplicate_of` uuid NULL (movimiento existente que coincide), `duplicate_in_file` int NULL (fila anterior del mismo archivo), `decision` CHECK ∈ {`import`, `skip`}. `UNIQUE (batch_id, row_number)`.

### `finance.transactions`
| Columna | Tipo | Reglas |
|---|---|---|
| context_id | uuid | NOT NULL |
| account_id | uuid | FK compuesta `(account_id, context_id, currency)` → accounts |
| currency | char(3) | copia de la moneda de la cuenta (la FK garantiza que coincide) |
| booked_on | date | NOT NULL |
| amount | numeric(18,2) | NOT NULL, CHECK `<> 0` |
| description | varchar(500) | NOT NULL |
| reference | varchar(100) | NULL (número de comprobante/operación) |
| category_id | uuid NULL | FK compuesta `(category_id, context_id)` |
| counterparty_id | uuid NULL | FK compuesta `(counterparty_id, context_id)` |
| source | varchar(10) | CHECK `manual`/`import` |
| import_batch_id | uuid NULL | FK; CHECK `(source='import') = (import_batch_id IS NOT NULL)` |
| dedupe_key | bytea(32) | sha256 de `account_id|booked_on|amount|descripción normalizada|referencia normalizada` |
| reviewed_at | timestamptz NULL | los importados nacen sin revisar; los manuales, revisados |
| voided_at, voided_by, void_reason | | CHECK: los tres juntos o ninguno; `void_reason` ≥ 3 caracteres |
| created_by | uuid FK users | NOT NULL |

Índices: `(context_id, booked_on DESC, id DESC)`, `(account_id, booked_on)`, `(account_id, dedupe_key)` **no único** (dos cafés iguales el mismo día son legítimos: el duplicado se **señala**, no se prohíbe — BR-FIN-03).
Normalización para `dedupe_key`: minúsculas, sin tildes (NFKD), espacios colapsados, sin espacios al borde. Implementarla **una sola vez** en Python y probarla.

**Transferencias entre cuentas propias** del mismo contexto: dos movimientos con el mismo `transfer_group_id uuid NULL` (uno negativo, otro positivo; pueden tener distinta moneda). No llevan categoría y no cuentan como ingreso ni gasto en los reportes. Un movimiento entre contextos (aporte del dueño a la empresa) **no es una transferencia**: son dos movimientos independientes, uno en cada contexto.

## 3. Permisos (catálogo en `app/core/permissions.py` + carga en la migración 0002)

| Permiso | Owner | Admin | Accountant | Viewer |
|---|---|---|---|---|
| `finance.read` — ver finanzas de la empresa | ✓ | ✓ | ✓ | ✓ |
| `finance.manage` — cargar, editar, anular, importar | ✓ | ✓ | ✓ | — |

Contexto personal: cualquier usuario activo puede **crear su propio** contexto personal y operarlo; nadie más lo ve (404, no 403, para no revelar que existe). La prueba que verifica catálogo = base debe seguir pasando.

## 4. API (`/api/v1/finance`)

Todo listado paginado por cursor (`?limit=50&before=<id>`), ordenado por fecha descendente. Errores con el formato existente (`app.core.errors`). Importes como string decimal.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/contexts` | Contextos visibles para el usuario (el de la empresa si tiene `finance.read` + su personal si existe) |
| POST | `/contexts/personal` | Crea el contexto personal del usuario actual (409 si ya existe) |
| GET/POST | `/contexts/{cid}/accounts` | Listar (con saldo actual) / crear |
| PATCH | `/contexts/{cid}/accounts/{id}` | Editar nombre, institución, últimos 4, archivar/desarchivar. **No** se cambia moneda ni saldo inicial si ya tiene movimientos (409) |
| GET/POST/PATCH | `/contexts/{cid}/categories[/{id}]` | Igual, con archivo |
| POST | `/contexts/{cid}/categories/suggested` | Crea un conjunto inicial sugerido **solo si el contexto no tiene categorías** (409 si tiene). Lista distinta para `business` y `personal`, en el código, documentada |
| GET/POST/PATCH | `/contexts/{cid}/counterparties[/{id}]` | Igual; búsqueda `?q=` por nombre o RUC |
| GET | `/contexts/{cid}/transactions` | Filtros: `account_id`, `category_id`, `counterparty_id`, `from`, `to`, `q`, `unreviewed=true`, `include_voided=false` |
| POST | `/contexts/{cid}/transactions` | Alta manual |
| PATCH | `/contexts/{cid}/transactions/{id}` | Editar categoría, contraparte, descripción, referencia, marcar revisado. Fecha/importe/cuenta solo si `source='manual'` y no anulado |
| POST | `/contexts/{cid}/transactions/{id}/void` | `{reason}` |
| POST | `/contexts/{cid}/transfers` | `{from_account_id, to_account_id, booked_on, amount_out, amount_in, description}` → crea los dos movimientos en una transacción |
| POST | `/contexts/{cid}/imports` | multipart: `file`, `account_id`, `mapping` (JSON). Analiza y devuelve el lote con filas, errores y duplicados. **No crea movimientos** |
| GET | `/contexts/{cid}/imports/{bid}` | Lote con filas paginadas |
| PATCH | `/contexts/{cid}/imports/{bid}/rows/{n}` | `{decision}` |
| POST | `/contexts/{cid}/imports/{bid}/commit` | Crea los movimientos de las filas `decision='import'` sin error, en **una** transacción; idempotente (un lote `committed` no se vuelve a importar → 409) |
| POST | `/contexts/{cid}/imports/{bid}/cancel` | |
| GET | `/contexts/{cid}/summary` | `?from&to`: saldo por cuenta; ingresos, gastos y neto **por moneda y por mes**; gastos por categoría por moneda. Excluye anulados y transferencias |
| GET | `/summary/consolidated` | Para el usuario: por cada contexto visible, totales por moneda, **con el contexto identificado** (BR-FIN-02). Nunca un total que mezcle contextos sin etiqueta |

### Importación (`mapping`)
```json
{
  "has_header": true, "delimiter": ";", "encoding": "auto",
  "date_column": "Fecha", "date_format": "%d/%m/%Y",
  "description_column": "Concepto", "reference_column": "Nro. Operación",
  "amount": {"mode": "single", "column": "Importe"}
           | {"mode": "split", "debit_column": "Débito", "credit_column": "Crédito"},
  "decimal_separator": ",", "thousands_separator": ".",
  "skip_rows": 0
}
```
- CSV: detectar codificación `utf-8-sig` → `cp1252` (los bancos paraguayos exportan en ambas). XLSX: `openpyxl` en modo `read_only=True, data_only=True` (no ejecuta fórmulas ni macros). `.xls` antiguo: rechazar con mensaje claro (pedir CSV o XLSX).
- Límites: 10 MB por archivo, 20.000 filas. Rechazar más allá con mensaje claro.
- Paraguay: `1.234.567` (miles con punto) y `1.234,50`. Un importe PYG con decimales distintos de cero es error de fila.
- Cada fila: error legible en español (`"Fecha inválida: 31/02/2026"`), duplicado contra movimientos existentes no anulados de la misma cuenta (`dedupe_key`) y contra filas anteriores del mismo archivo. Duplicados nacen con `decision='skip'`; el resto `import`.
- `GET /finance/import-formats` no hace falta: los mapeos se guardan en el lote; la interfaz puede ofrecer "usar el mapeo de la última importación de esta cuenta" leyendo el último lote (`GET /contexts/{cid}/imports?account_id=&limit=1`).

## 5. Pruebas mínimas (pytest, PostgreSQL real)
1. Un movimiento con cuenta de otro contexto falla **en la base** (insert directo con SQL, no solo por el servicio) — D-025.
2. Un movimiento con moneda distinta a su cuenta falla en la base.
3. Usuario A no ve (404) el contexto personal de B, aun siendo `owner`/`admin`; viewer no puede escribir en el de la empresa (403) pero sí en su personal.
4. Importes: `float` nunca aparece; `"0.1"+"0.2"` da `"0.30"`; PYG con decimales rechazado; JSON devuelve strings.
5. Importación CSV (utf-8 y cp1252, `;` y `,`) y XLSX, single y split, miles con punto; filas con error; duplicados contra base y dentro del archivo; commit idempotente; cancel.
6. Anulación: saldo y resumen la excluyen; requiere motivo; queda auditada.
7. Transferencia: dos movimientos, mismo grupo, no cuentan como ingreso/gasto.
8. Resumen: no mezcla monedas; consolidado identifica el contexto.
9. Auditoría: alta/cambio/anulación de cada entidad registra solo campos cambiados; importación registra un evento por lote.
10. `alembic check` sin diferencias; `downgrade` de la 0002 → `upgrade` OK; catálogo de permisos = base.
11. Rendimiento: con 100.000 movimientos sembrados en la prueba, `GET /transactions` (primera página) y `/summary` de 12 meses responden en < 300 ms (medir en la prueba, marcar `@pytest.mark.slow`).
