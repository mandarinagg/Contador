# Especificación: Fase 3, Contabilidad (núcleo)

**Estado:** aprobada por el jefe de proyecto (2026-11-24). Es el contrato del backend y de la interfaz de la fase 3.
- **Reglas de negocio:** BR-ACC-01 a BR-ACC-06 (ya existen) y BR-ACC-07 a BR-ACC-12 (nuevas), en `docs/BUSINESS_RULES.md`.
- **Decisiones:** D-035 a D-043.
- **Fuente del plan de cuentas:** `docs/research/PLAN_DE_CUENTAS_PY.md` y `docs/research/plan_de_cuentas_propuesto.yaml`, sin validar.

## 0. Alcance

**Entra en esta tanda:**
- plan de cuentas;
- ejercicios y períodos mensuales, con cierre y reapertura;
- asientos de partida doble (borrador → contabilizado → revertido);
- asiento propuesto desde un movimiento de finanzas de la empresa, con confirmación humana;
- reportes: libro diario, libro mayor, balance de comprobación, balance general y estado de resultados;
- cierre del ejercicio con asiento de refundición de resultados.

**Queda para una tanda siguiente (3B), sin diseñar todavía:**
- activos fijos y depreciaciones;
- centros de costos;
- asientos recurrentes;
- exportación a PDF o XLSX de los libros (para rubricación);
- moneda extranjera con diferencia de cambio automática.

## 1. Decisiones de modelo (no reabrir sin pasar por el jefe de proyecto)

| ID | Decisión | Motivo |
|---|---|---|
| D-035 | **La contabilidad es de la organización**, nunca de una persona: el esquema `accounting` cuelga de `organization_id`. Un movimiento de finanzas **personal** no puede originar un asiento, y lo impide la base: `journal_entries` guarda `source_context_id` + `source_context_kind` con CHECK `= 'business'` y FK compuesta a `finance.contexts (id, kind)`. Para eso se agrega `UNIQUE (id, kind)` en `finance.contexts`. | Separación personal/empresa (BR-FIN-01, D-024) impuesta en la base, con la misma técnica que D-025 |
| D-036 | **Moneda funcional PYG.** El debe y el haber de cada línea están en guaraníes: `NUMERIC(18,2)` con CHECK de entero, `Decimal` en Python y string en JSON. Una línea puede llevar además, como dato informativo, `fx_currency`, `fx_amount` y `fx_rate` (los tres juntos o ninguno). El balance se valida **solo en PYG**. La cotización la escribe la persona: la app no busca cotizaciones y no calcula diferencias de cambio en esta tanda. | NIF 23 y tipo de cambio aplicable: pendientes de validar por el contador. Nunca un número inventado |
| D-037 | **Plan de cuentas** (`accounting.ledger_accounts`): uno por organización, jerárquico por código (`1.01.01.04`). Solo las cuentas **imputables** reciben líneas. Se carga a pedido con el **plan propuesto** (copia empaquetada del YAML de la investigación) y nace con estado `pending`. | RG 49/2014 art. 3: los códigos hasta el 5° nivel no se modifican entre ejercicios; el plan no está validado |
| D-038 | **Validación del plan:** el estado del plan (`chart_status`: `pending` o `validated`) vive en la organización, con `validated_by_name`, `validated_reference` (matrícula) y `validated_at`. Lo marca un usuario con `accounting.post`; la app **no** lo da por validado sola. Mientras esté `pending`, todos los reportes muestran el aviso "Plan de cuentas sin validar por un contador". | El prompt prohíbe presentar como verificado lo que no lo está |
| D-039 | **Ejercicios y períodos:** `fiscal_years` (fechas de inicio y fin; por defecto, el año civil: Decreto 3182 arts. 14-15, duda D-9 abierta) y 12 `periods` mensuales por ejercicio. Estados `open` y `closed`. Cerrar un período bloquea contabilizar y revertir con fecha en él. Se puede **reabrir** con motivo obligatorio y queda auditado. Cerrar el **ejercicio** exige todos sus períodos cerrados, genera el asiento de refundición y deja el ejercicio `closed`, que **no se reabre** en esta tanda. | BR-ACC-03; los errores de cierre mensual pasan, los del anual se corrigen en el ejercicio siguiente |
| D-040 | **Asientos:** `draft` → `posted` → `reversed`, o `draft` → `discarded`. Nada se borra. Un asiento `posted` es **inmutable**, y no solo por el servicio: lo garantizan triggers de la base. La corrección es otro asiento, de reversión (líneas invertidas, `reverses_entry_id`), que se contabiliza en el mismo acto y deja el original `reversed`. El **número** es correlativo por ejercicio, sin huecos, y se asigna **al contabilizar** con un candado sobre la fila del ejercicio. Los borradores no tienen número. | BR-ACC-01/02; el libro diario exige numeración correlativa (Ley 1034/83, Decreto 3182 art. 64) |
| D-041 | **Asiento propuesto desde finanzas:** un movimiento de la cuenta empresarial puede generar un **borrador**, nunca un asiento contabilizado (BR-ACC-06). Usa `finance.accounts.ledger_account_id` (cuenta contable del banco o la caja) y `finance.categories.ledger_account_id` (cuenta de resultado), que se configuran una vez. Un movimiento tiene como máximo **un** asiento vivo (`draft` o `posted`), garantizado por un índice único parcial. Un movimiento con asiento `posted` **no se puede anular** (409, "revertí primero el asiento N° X"). Si el movimiento es en otra moneda, el borrador pide la cotización (D-036). | Trazabilidad finanzas ↔ contabilidad sin contabilizar nada sin una persona |
| D-042 | **Reportes calculados al vuelo** desde las líneas contabilizadas (`posted` y `reversed`; los dos cuentan, porque la reversión es otro asiento que compensa), sin tablas de saldos. Mismo criterio que D-033. El **resultado del ejercicio** del balance general se calcula de las cuentas de ingreso y gasto mientras el ejercicio no esté cerrado. | Sin riesgo de saldos desincronizados |
| D-043 | **Permisos:** `accounting.read` (todos los roles), `accounting.manage` (propietario, administrador y contador: plan de cuentas, borradores, configuración de cuentas contables en finanzas) y `accounting.post` (propietario y contador: contabilizar, revertir, cerrar y reabrir períodos, cerrar el ejercicio, marcar el plan validado). | El administrador gestiona el sistema, no firma la contabilidad |

## 2. Esquema `accounting` (migración `0003_contabilidad`, `down_revision = "0002"`: verificar el id real)

Todas las tablas: `id uuid PK DEFAULT uuidv7()`, `created_at` y `updated_at` (`TimestampMixin`), `organization_id` FK `core.organizations` NOT NULL. Las tablas que se referencian llevan `UNIQUE (id, organization_id)` y se referencian con FK compuestas `(x_id, organization_id)`: un asiento no puede usar una cuenta de otra organización. Nombres de restricciones: la convención de `app.core.db.Base`.

### Cambios en tablas existentes
- `core.organizations` (o una tabla `accounting.settings` 1:1, a elección; documentarlo): `chart_status` CHECK ∈ {`none`, `pending`, `validated`} DEFAULT `none`, `chart_validated_by_name` varchar(150) NULL, `chart_validated_reference` varchar(100) NULL, `chart_validated_at` timestamptz NULL. CHECK: los tres `validated_*` presentes si y solo si `chart_status='validated'`. Además, `retained_earnings_account_id` (cuenta de "resultado del ejercicio" para la refundición) NULL.
- `finance.contexts`: `UNIQUE (id, kind)` (D-035).
- `finance.accounts` y `finance.categories`: `ledger_account_id uuid NULL` FK `accounting.ledger_accounts`. Que solo se use en el contexto `business` y que la cuenta contable sea de la misma organización lo valida el servicio, con pruebas. La cuenta de un banco tiene que ser de `kind` activo o pasivo (una tarjeta de crédito es pasivo); la de una categoría, de ingreso o gasto según la categoría.

### `accounting.ledger_accounts`
| Columna | Tipo | Reglas |
|---|---|---|
| code | varchar(30) | NOT NULL, CHECK `^[0-9]+(\.[0-9]+)*$`, `UNIQUE (organization_id, code)` |
| name | varchar(150) | NOT NULL |
| kind | varchar(12) | CHECK ∈ {`asset`, `liability`, `equity`, `income`, `expense`} (el YAML usa activo/pasivo/patrimonio/ingreso/gasto) |
| normal_side | varchar(6) | CHECK ∈ {`debit`, `credit`} (naturaleza deudora o acreedora) |
| is_postable | bool | imputable |
| parent_id | uuid NULL | FK compuesta `(parent_id, organization_id)`; el código del padre es prefijo del hijo (servicio + prueba) |
| origin | varchar(12) | CHECK ∈ {`rg49_2014`, `proposed`, `user`} |
| note | varchar(500) NULL | |
| archived_at | timestamptz NULL | |

Reglas del servicio:
- Una cuenta **con líneas** no cambia `code`, `kind`, `normal_side` ni `is_postable`; solo `name` y `note`, y se puede archivar.
- No se archiva una cuenta con saldo distinto de cero ni con hijos sin archivar.
- Una cuenta agrupadora (`is_postable=false`) no recibe líneas: lo valida el trigger de líneas, no solo el servicio.

### `accounting.fiscal_years`
`start_date`, `end_date` (CHECK `end_date > start_date`, a lo sumo 12 meses), `status` CHECK `open`/`closed`, `closed_at`, `closed_by`, `closing_entry_id` NULL, `last_entry_number int DEFAULT 0` (numeración correlativa, D-040). Exclusión de solapamiento: `EXCLUDE USING gist (organization_id WITH =, daterange(start_date, end_date, '[]') WITH &&)` (requiere `btree_gist`; si no está disponible en el PostgreSQL portable de Windows, validarlo en el servicio con un candado y documentarlo).

### `accounting.periods`
`fiscal_year_id` (FK compuesta con la organización), `start_date`, `end_date`, `status` CHECK `open`/`closed`, `closed_at`, `closed_by`, `reopen_reason` NULL. `UNIQUE (fiscal_year_id, start_date)`. Al crear el ejercicio se crean sus 12 períodos.

### `accounting.journal_entries`
| Columna | Tipo | Reglas |
|---|---|---|
| fiscal_year_id | uuid | FK compuesta |
| entry_date | date | NOT NULL; dentro del ejercicio (trigger) |
| number | int NULL | NULL si y solo si `status IN ('draft','discarded')`; `UNIQUE (fiscal_year_id, number)` |
| status | varchar(10) | CHECK ∈ {`draft`, `posted`, `reversed`, `discarded`} |
| kind | varchar(10) | CHECK ∈ {`manual`, `finance`, `reversal`, `closing`} |
| description | varchar(500) | NOT NULL |
| document_reference | varchar(100) NULL | comprobante respaldatorio (BR-ACC-04): nro. de factura, recibo u operación |
| reverses_entry_id | uuid NULL | FK al asiento revertido; UNIQUE (un asiento se revierte una sola vez); CHECK `(kind='reversal') = (reverses_entry_id IS NOT NULL)` |
| source_transaction_id | uuid NULL | FK `finance.transactions` |
| source_context_id, source_context_kind | | D-035: los tres NULL o los tres presentes; `source_context_kind = 'business'`; FK compuesta `(source_transaction_id, source_context_id) → finance.transactions (id, context_id)` y `(source_context_id, source_context_kind) → finance.contexts (id, kind)` |
| created_by, posted_by, posted_at | | `posted_*` presentes si y solo si `status IN ('posted','reversed')` |
| discarded_at, discarded_by, discard_reason | | juntos, si y solo si `status='discarded'` |

Índices: único parcial `(source_transaction_id) WHERE status IN ('draft','posted')` (D-041), `(organization_id, entry_date, number)`, `(fiscal_year_id, status)`.

### `accounting.journal_lines`
`entry_id` FK, `line_no` smallint (`UNIQUE (entry_id, line_no)`), `account_id` (FK compuesta con la organización), `debit` y `credit` numeric(18,2) DEFAULT 0 con CHECK `>= 0`, CHECK exactamente uno `> 0`, CHECK enteros (PYG), `description` varchar(300) NULL, `fx_currency` char(3) NULL, `fx_amount` numeric(18,2) NULL, `fx_rate` numeric(18,6) NULL (los tres juntos, `fx_currency <> 'PYG'`). Índice `(account_id, entry_id)`.

### Triggers (la base es la última defensa, BR-ACC-01/02/03)
1. **`journal_lines`:** INSERT, UPDATE o DELETE solo si el asiento está en `draft`; la cuenta tiene que ser `is_postable` y no archivada.
2. **`journal_entries` UPDATE:**
   - Desde `draft` se puede cambiar todo y pasar a `posted` o `discarded`.
   - Desde `posted` solo se permite `status → reversed`, sin tocar ninguna otra columna.
   - `reversed` y `discarded` son finales.
   - **DELETE prohibido siempre.**
3. **Al pasar a `posted`** (trigger de restricción `DEFERRABLE INITIALLY DEFERRED`, o validación en el mismo trigger):
   - al menos 2 líneas y `Σ debit = Σ credit > 0`;
   - `entry_date` dentro de un período `open` del ejercicio;
   - ejercicio `open`, salvo el asiento `closing`, que lo genera el propio cierre antes de marcar el ejercicio.
4. **`periods` y `fiscal_years`:** no se cierra un período con borradores. Esto lo decide el servicio: se informan los borradores y se pide descartarlos o moverlos. El trigger solo protege que un período `closed` no reciba asientos.

Probar cada trigger con SQL directo, como en D-025: un `UPDATE` sobre un asiento `posted` falla **en la base**.

## 3. Permisos
`accounting.read`, `accounting.manage` y `accounting.post` (D-043): en `app/core/permissions.py` y cargados por la migración 0003 con su propia copia congelada del catálogo (D-031: las migraciones no importan catálogos vivos). Actualizar `ROLE_PERMISSIONS`.

## 4. API (`/api/v1/accounting`)

Listados paginados por cursor, igual que en finanzas. Errores con el formato existente. Importes como string. Todo alta, cambio, contabilización, reversión, descarte, cierre y reapertura se audita (`audit.record`, solo campos que cambian).

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/chart` | read | Árbol o lista plana (`?flat=true`) con estado del plan, y saldo opcional `?balance_at=` |
| POST | `/chart/load-proposed` | manage | Carga el plan propuesto si la organización no tiene cuentas (409 si tiene). `chart_status → pending` |
| POST / PATCH | `/chart/accounts[/{id}]` | manage | Alta (bajo un padre, código hijo del padre) / edición / archivo, con las reglas de §2 |
| POST | `/chart/validate` | post | `{validated_by_name, validated_reference}` → `validated`. `POST /chart/invalidate` lo vuelve a `pending` (por ejemplo, si se cambió el plan) |
| PUT | `/settings` | post | `retained_earnings_account_id` (cuenta de patrimonio, imputable) |
| GET / POST | `/fiscal-years` | read / post | Crear ejercicio (por defecto, el año civil indicado) con sus 12 períodos |
| POST | `/periods/{id}/close` · `/periods/{id}/reopen` | post | Cerrar (409 con la lista si hay borradores) / reabrir con `{reason}` (ejercicio abierto) |
| POST | `/fiscal-years/{id}/close` | post | Exige los 12 períodos cerrados y la cuenta de resultados configurada. Genera y contabiliza la refundición (cada cuenta de ingreso y gasto con saldo, contra `retained_earnings_account_id`) y cierra el ejercicio |
| GET | `/entries` | read | Filtros: `fiscal_year_id`, `status`, `from`, `to`, `account_id`, `q`, `kind` |
| POST | `/entries` | manage | Borrador con líneas (puede estar desbalanceado mientras sea borrador) |
| GET / PATCH | `/entries/{id}` | read / manage | El PATCH reemplaza cabecera y líneas **solo en borrador** (409 si no) |
| POST | `/entries/{id}/post` | post | Valida y contabiliza; asigna número. Errores legibles: `ENTRY_UNBALANCED` (con la diferencia), `PERIOD_CLOSED`, `ACCOUNT_NOT_POSTABLE` |
| POST | `/entries/{id}/reverse` | post | `{date?, reason}`: reversión contabilizada (por defecto, misma fecha; si su período está cerrado, se pide una fecha en un período abierto) |
| POST | `/entries/{id}/discard` | manage | `{reason}`, solo borradores |
| POST | `/entries/from-transaction/{tid}` | manage | Borrador propuesto desde un movimiento de la empresa (D-041). 409 si ya tiene asiento vivo; 422 si falta la cuenta contable del banco o de la categoría (decir cuál), y si el movimiento es en otra moneda sin `fx_rate` |
| GET | `/reports/journal` | read | Libro diario: asientos contabilizados por fecha y número, con sus líneas, en un rango |
| GET | `/reports/ledger/{account_id}` | read | Libro mayor: saldo anterior al rango, movimientos con saldo acumulado, saldo final |
| GET | `/reports/trial-balance` | read | `?from&to`: por cuenta imputable con movimiento, sumas (debe/haber) y saldos (deudor/acreedor); totales, que tienen que coincidir |
| GET | `/reports/balance-sheet` | read | `?at=`: activo, pasivo y patrimonio agrupados por la jerarquía del plan (subtotales por cuenta agrupadora), más el resultado del ejercicio en curso. Verifica `activo = pasivo + patrimonio` y lo informa |
| GET | `/reports/income-statement` | read | `?from&to`: ingresos y gastos agrupados por la jerarquía (RG 49/2014 Anexo 2) y el resultado |

Todos los reportes devuelven `chart_status`. Si no es `validated`, la interfaz muestra el aviso.

`finance`: `PATCH /finance/contexts/{cid}/accounts/{id}` y `/categories/{id}` aceptan `ledger_account_id`, solo en el contexto `business`: 422 en el personal. `POST .../transactions/{id}/void` devuelve 409 `TRANSACTION_HAS_POSTED_ENTRY` si tiene asiento contabilizado. Los movimientos devuelven `journal_entry` (`{id, number, status}` o null), pero solo en el contexto `business`.

## 5. Pruebas mínimas (pytest, PostgreSQL real)
1. **Triggers por SQL directo:**
   - `UPDATE` y `DELETE` de un asiento `posted` fallan;
   - insertar una línea en un asiento `posted` falla;
   - contabilizar desbalanceado, con una sola línea o en un período cerrado falla;
   - una línea con cuenta agrupadora falla;
   - una línea con cuenta de otra organización falla (FK compuesta).
2. **D-035:** un asiento con `source_context_kind='personal'` o un movimiento personal falla en la base; `from-transaction` sobre un movimiento personal da 404 (el contexto es privado).
3. **Numeración:** correlativa sin huecos aunque se descarten borradores; dos contabilizaciones concurrentes en el mismo ejercicio, con conexiones reales como en D-034, no repiten ni saltean números.
4. **Reversión:** líneas invertidas, original `reversed`, el saldo neto del mayor vuelve a cero, no se revierte dos veces, y revertir en un período cerrado pide otra fecha.
5. **Períodos:** cerrar con borradores da 409 con la lista; reabrir exige motivo y queda auditado; el ejercicio cerrado no se reabre.
6. **Cierre del ejercicio:** la refundición deja en cero todas las cuentas de ingreso y gasto, lleva el resultado a la cuenta configurada, y el balance general cuadra antes y después.
7. **Plan propuesto:**
   - carga las 159 cuentas con jerarquía y tipos correctos;
   - la copia empaquetada es **idéntica** al YAML de `docs/research/` (prueba que lee los dos; `PyYAML` solo como dependencia de desarrollo si hace falta);
   - no se carga dos veces;
   - una cuenta usada no cambia de código.
8. **Reportes:** balance de comprobación con debe = haber; balance general con activo = pasivo + patrimonio; resultados = ingresos − gastos. Todo contra un **cálculo de referencia en Python** sobre un conjunto variado (como `test_finance_summary_reference.py`). El mayor tiene saldo anterior y acumulado correctos en los bordes del rango.
9. **Desde finanzas:**
   - el borrador propuesto tiene banco contra categoría con el signo correcto (un ingreso debita el banco y acredita la cuenta de ingreso);
   - 409 si ya hay asiento vivo;
   - no se anula un movimiento con asiento contabilizado;
   - USD sin cotización da 422, y con cotización hace la conversión exacta (`Decimal`, sin redondeo silencioso: si el producto tiene decimales en PYG, error pidiendo redondear explícitamente).
10. **Permisos:** viewer solo lee; admin no contabiliza ni cierra (403); contador sí.
11. **Migración:** `alembic check` sin diferencias; `downgrade 0002` → `upgrade head` OK; el catálogo de permisos coincide con la base.
12. **Rendimiento** (`@pytest.mark.slow`): con 100.000 líneas contabilizadas, el balance de comprobación anual, el mayor de una cuenta con 20.000 líneas (primera página) y el balance general responden en < 300 ms.
