# Esquema de base de datos

PostgreSQL 18. Migraciones en `backend/migrations` (Alembic). Convenciones:

- PK `uuid` con `uuidv7()` (ordenadas por tiempo). Excepción: catálogos con código natural (`roles.code`, `permissions.code`).
- `timestamptz` en todas las fechas-hora; `date` para fechas contables y fiscales.
- Importes `NUMERIC(18,2)` + `currency char(3)` (D-026; desde la fase 2). Nunca `float`.
- Nombres de restricciones estables (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`).
- Soft delete **no** se usa por defecto: los registros contables no se borran (se revierten), los movimientos financieros se anulan (`voided_at`) y los maestros se desactivan o archivan (`is_active`, `archived_at`).
- Todo dato de negocio lleva `organization_id`.

## Implementado (migración `0001`)

```mermaid
erDiagram
    core_users ||--o{ core_organization_members : "pertenece"
    core_organizations ||--o{ core_organization_members : "tiene"
    core_roles ||--o{ core_organization_members : "rol"
    core_roles ||--o{ core_role_permissions : ""
    core_permissions ||--o{ core_role_permissions : ""
    core_users ||--o{ core_user_sessions : "abre"
    core_organizations ||--o{ core_user_sessions : "contexto"

    core_users {
        uuid id PK
        varchar email "único sin mayúsculas"
        varchar full_name
        text password_hash "argon2id"
        bool is_active
        int failed_login_count
        timestamptz locked_until
        timestamptz last_login_at
        timestamptz password_changed_at
    }
    core_organizations {
        uuid id PK
        varchar legal_name
        varchar trade_name
        varchar legal_form "EAS|SA|SRL|UNIPERSONAL|OTRA"
        varchar ruc "1-8 dígitos, opcional"
        varchar ruc_check_digit "junto con ruc"
        char base_currency "PYG"
    }
    core_organization_members {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        varchar role_code FK
    }
    core_roles {
        varchar code PK
        varchar name
    }
    core_permissions {
        varchar code PK
        text description
    }
    core_role_permissions {
        varchar role_code PK
        varchar permission_code PK
    }
    core_user_sessions {
        uuid id PK
        uuid user_id FK
        uuid organization_id FK
        bytea token_hash "sha256, único"
        timestamptz expires_at
        timestamptz last_seen_at
        timestamptz revoked_at
    }
    audit_audit_logs {
        uuid id PK
        bigint seq "único, lo asigna el trigger"
        uuid organization_id "sin FK"
        uuid actor_user_id "sin FK"
        varchar action
        varchar entity_type
        varchar entity_id
        jsonb before
        jsonb after
        bytea prev_hash
        bytea row_hash
    }
    audit_security_events {
        uuid id PK
        varchar event_type
        uuid user_id
        varchar email_attempted
        inet ip_address
        jsonb details
    }
```

### Restricciones e invariantes en la base
| Objeto | Regla |
|---|---|
| `uq_users_email_lower` | Email único sin distinguir mayúsculas |
| `ck_organizations_ruc_*` | RUC 1-8 dígitos, DV 1 dígito, ambos o ninguno |
| `uq_organization_members_organization_id_user_id` | Una membresía por usuario y organización |
| `ck_user_sessions_expires_after_creation` | Vencimiento posterior a la creación |
| `audit.chain_audit_log()` (trigger) | Asigna `seq` y la cadena de hashes bajo candado |
| `audit.reject_change()` (triggers) | `audit_logs` y `security_events`: sin UPDATE, DELETE ni TRUNCATE |
| `audit.log_row_hash()` | Hash canónico (lo usan el trigger y la verificación) |

### Datos iniciales (en la misma migración)
Permisos `organization.read`, `organization.manage`, `users.read`, `users.manage`, `audit.read`; roles `owner`, `admin`, `accountant`, `viewer` y sus vínculos. Una prueba verifica que coincidan con `app/core/permissions.py`.

## Implementado (migración `0002` — finanzas)

Esquema `finance`. Especificación: `docs/specs/FASE2_FINANZAS.md` (D-023 a D-027). Todas las tablas llevan `id uuid` (`uuidv7()`), `created_at` y `updated_at`.

```mermaid
erDiagram
    core_organizations ||--|| finance_contexts : "un business"
    core_users ||--o| finance_contexts : "un personal por usuario"
    finance_contexts ||--o{ finance_accounts : ""
    finance_contexts ||--o{ finance_categories : ""
    finance_contexts ||--o{ finance_counterparties : ""
    finance_contexts ||--o{ finance_import_batches : ""
    finance_categories ||--o{ finance_categories : "padre (un nivel)"
    finance_accounts ||--o{ finance_transactions : "(account_id, context_id, currency)"
    finance_categories ||--o{ finance_transactions : "(category_id, context_id)"
    finance_counterparties ||--o{ finance_transactions : "(counterparty_id, context_id)"
    finance_accounts ||--o{ finance_import_batches : "(account_id, context_id)"
    finance_import_batches ||--o{ finance_import_rows : "ON DELETE CASCADE"
    finance_import_batches ||--o{ finance_transactions : "(import_batch_id, context_id)"
    finance_transactions ||--o{ finance_import_rows : "duplicate_of"

    finance_contexts {
        uuid id PK
        uuid organization_id FK
        varchar kind "business|personal"
        varchar name
        uuid owner_user_id FK "NULL si business"
        bool is_active
    }
    finance_accounts {
        uuid id PK
        uuid context_id FK
        varchar name "único por contexto"
        varchar kind "cash|checking|savings|credit_card|digital_wallet|other"
        varchar institution
        char currency "PYG|USD|BRL|ARS|EUR"
        varchar number_last4 "solo 4 dígitos"
        numeric opening_balance "18,2"
        date opening_date
        timestamptz archived_at
    }
    finance_categories {
        uuid id PK
        uuid context_id FK
        varchar name
        varchar kind "income|expense"
        uuid parent_id "FK compuesta"
        timestamptz archived_at
    }
    finance_counterparties {
        uuid id PK
        uuid context_id FK
        varchar name
        varchar ruc "1-8 dígitos"
        char ruc_check_digit
        varchar kind "customer|supplier|employee|bank|government|person|other"
        varchar notes
        timestamptz archived_at
    }
    finance_transactions {
        uuid id PK
        uuid context_id FK
        uuid account_id "FK compuesta con moneda"
        char currency
        date booked_on
        numeric amount "18,2; + entra, - sale"
        varchar description
        varchar reference
        uuid category_id "FK compuesta"
        uuid counterparty_id "FK compuesta"
        varchar source "manual|import"
        uuid import_batch_id "FK compuesta"
        uuid transfer_group_id
        bytea dedupe_key "sha256"
        timestamptz reviewed_at
        timestamptz voided_at
        uuid voided_by FK
        varchar void_reason
        uuid created_by FK
    }
    finance_import_batches {
        uuid id PK
        uuid context_id FK
        uuid account_id "FK compuesta"
        varchar filename
        bytea file_sha256
        varchar file_format "csv|xlsx"
        jsonb mapping
        varchar status "previewed|committed|cancelled"
        int rows_total
        int rows_imported
        int rows_duplicate
        int rows_error
        uuid created_by FK
        timestamptz committed_at
    }
    finance_import_rows {
        uuid id PK
        uuid batch_id FK
        int row_number "fila del archivo"
        jsonb raw
        date booked_on
        numeric amount
        varchar description
        varchar reference
        varchar error
        uuid duplicate_of FK
        int duplicate_in_file
        varchar decision "import|skip"
    }
```

### Restricciones e invariantes en la base (finanzas)
| Objeto | Regla |
|---|---|
| `uq_contexts_business_per_org` (parcial) | Exactamente un contexto `business` por organización |
| `uq_contexts_personal_per_user` (parcial) | Como máximo un contexto `personal` por usuario y organización |
| `ck_contexts_owner_matches_kind` | `owner_user_id` NULL si `business`, obligatorio si `personal` |
| `uq_{accounts,categories,counterparties,import_batches}_id_context_id` | Destino de las claves foráneas compuestas (D-025) |
| `uq_accounts_id_context_id_currency` | Destino de la FK que fija la moneda del movimiento |
| `fk_transactions_account_id_accounts` | `(account_id, context_id, currency)`: la cuenta es del mismo contexto y de la misma moneda; además impide cambiar la moneda de una cuenta con movimientos |
| `fk_transactions_{category,counterparty,import_batch}_id_*` | `(x_id, context_id)`: del mismo contexto |
| `fk_categories_parent_id_categories` | `(parent_id, context_id)`: el padre es del mismo contexto (el nivel único se valida en el servicio) |
| `fk_import_batches_account_id_accounts` | `(account_id, context_id)` |
| `uq_accounts_context_id_name` | Nombre de cuenta único por contexto |
| `uq_categories_context_id_parent_id_name` | `NULLS NOT DISTINCT`: nombre único por nivel |
| `uq_counterparties_ruc_per_context` (parcial) | Un RUC por contexto |
| `ck_counterparties_ruc_*` | Mismas reglas de RUC y DV que `core.organizations` |
| `ck_accounts_currency_valid` | Catálogo de monedas de `finance/money.py` |
| `ck_accounts_number_last4_digits` | Solo los últimos 4 dígitos, nunca el número completo |
| `ck_accounts_pyg_integer`, `ck_transactions_pyg_integer` | PYG sin decimales |
| `ck_transactions_amount_not_zero` | Importe distinto de cero |
| `ck_transactions_import_has_batch` | `source = 'import'` si y solo si hay lote |
| `ck_transactions_void_complete`, `ck_transactions_void_reason_length` | Anulación: fecha, usuario y motivo juntos; motivo de 3 caracteres o más |
| `ck_transactions_transfer_without_category` | Una transferencia no lleva categoría |
| `ck_import_batches_committed` | `committed_at` si y solo si `status = 'committed'` |
| `uq_import_rows_batch_id_row_number` | Una fila por número dentro del lote |
| `ix_transactions_context_booked` | `(context_id, booked_on DESC, id DESC)`: listado paginado |
| `ix_transactions_account_dedupe` | `(account_id, dedupe_key)` **no único**: el duplicado se señala, no se prohíbe |

### Datos iniciales (migración `0002`)
Permisos `finance.read` (owner, admin, accountant, viewer) y `finance.manage` (owner, admin, accountant), y el contexto `business` ("Empresa") de cada organización existente. Los permisos se insertan con `ON CONFLICT DO NOTHING` porque la `0001` carga el catálogo vivo de `app/core/permissions.py` (en una base nueva ya los trae).

## Modelo objetivo (fases 3 a 7)

Se implementa por fases; cada tabla nace con su migración, su prueba y su pantalla. Lo que sigue es el diseño de referencia y **se revisará** en cada fase.

```mermaid
erDiagram
    organizations ||--o{ financial_contexts : ""
    persons ||--o{ financial_contexts : "personal"
    financial_contexts ||--o{ financial_accounts : ""
    financial_accounts ||--o{ bank_transactions : ""
    bank_transactions }o--o| transaction_categories : ""
    bank_transactions }o--o| journal_entries : "conciliado con"
    organizations ||--o{ chart_of_accounts : ""
    organizations ||--o{ fiscal_periods : ""
    fiscal_periods ||--o{ journal_entries : ""
    journal_entries ||--|{ journal_lines : "partida doble"
    chart_of_accounts ||--o{ journal_lines : ""
    journal_entries }o--o| journal_entries : "revierte a"
    organizations ||--o| tax_profiles : ""
    tax_rules ||--|{ tax_rule_versions : "versionado"
    tax_rule_versions ||--o{ tax_obligations : "regla aplicada"
    tax_obligations ||--o{ tax_payments : ""
    billing_documents ||--o{ journal_entries : "origen"
    billing_documents ||--o{ tax_obligations : "base imponible"
    documents ||--o{ document_versions : ""
    documents ||--o{ document_relations : "transacción / asiento / obligación"
```

### Decisiones de modelado clave
- **Contexto financiero**: implementado en la fase 2 como `finance.contexts` (ver arriba). En la fase 3, los asientos referenciarán el contexto `business` con la misma técnica de claves foráneas compuestas. Lo consolidado es una **vista**, nunca datos mezclados.
- **Asientos**: `journal_entries.status ∈ {draft, posted, reversed}`. Un trigger rechaza modificar líneas de un asiento `posted` y contabilizar en un período cerrado; otro valida `Σ debe = Σ haber` por moneda al pasar a `posted`. La corrección es un asiento de reversión (`reverses_entry_id`).
- **Reglas tributarias**: `tax_rule_versions` con `valid_from`, `valid_to`, `source_url`, `legal_reference`, `published_at`, `consulted_at`, `validation_status ∈ {pending, verified, deprecated}`, `reviewed_by`. Las obligaciones guardan la versión aplicada. Se cargan como datos, no como código.
- **Facturación**: esquema `billing` propio del servicio SIFEN (fase 5), referenciado desde contabilidad y tributación por `billing_documents.id`.
- **IA**: `ai.ai_interactions`, `ai.ai_tool_executions` (entrada, salida, duración, usuario) y `ai.ai_approvals` (borrador → aprobado/rechazado por un humano).
