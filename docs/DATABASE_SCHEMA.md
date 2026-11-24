# Esquema de base de datos

PostgreSQL 18. Migraciones en `backend/migrations` (Alembic). Convenciones:

- PK `uuid` con `uuidv7()` (ordenadas por tiempo). Excepción: catálogos con código natural (`roles.code`, `permissions.code`).
- `timestamptz` en todas las fechas-hora; `date` para fechas contables y fiscales.
- Importes `NUMERIC(20,4)` + `currency char(3)` (desde fase 2).
- Nombres de restricciones estables (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`).
- Soft delete **no** se usa por defecto: los registros contables no se borran (se revierten) y los maestros se desactivan con `is_active`.
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

## Modelo objetivo (fases 2 a 7)

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
- **Contexto financiero** (`core.financial_contexts`): `kind ∈ {personal, business}`, dueño = persona u organización. Toda cuenta y movimiento pertenece a un contexto; una restricción impide que un asiento empresarial use una cuenta de un contexto personal. Lo consolidado es una **vista**, nunca datos mezclados.
- **Asientos**: `journal_entries.status ∈ {draft, posted, reversed}`. Un trigger rechaza modificar líneas de un asiento `posted` y contabilizar en un período cerrado; otro valida `Σ debe = Σ haber` por moneda al pasar a `posted`. La corrección es un asiento de reversión (`reverses_entry_id`).
- **Reglas tributarias**: `tax_rule_versions` con `valid_from`, `valid_to`, `source_url`, `legal_reference`, `published_at`, `consulted_at`, `validation_status ∈ {pending, verified, deprecated}`, `reviewed_by`. Las obligaciones guardan la versión aplicada. Se cargan como datos, no como código.
- **Facturación**: esquema `billing` propio del servicio SIFEN (fase 5), referenciado desde contabilidad y tributación por `billing_documents.id`.
- **IA**: `ai.ai_interactions`, `ai.ai_tool_executions` (entrada, salida, duración, usuario) y `ai.ai_approvals` (borrador → aprobado/rechazado por un humano).
