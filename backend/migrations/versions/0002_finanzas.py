"""Finanzas: contextos empresarial y personal, cuentas, categorías, contrapartes,
movimientos e importación de extractos (esquema `finance`).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24

Especificación: docs/specs/FASE2_FINANZAS.md (D-023 a D-027). La separación entre
contextos y la moneda de cada movimiento se imponen con claves foráneas compuestas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copia congelada de lo que agrega esta migración al catálogo (`app/core/permissions.py`).
# Una migración no importa el catálogo vivo: si el catálogo cambia más adelante, esta
# migración debe seguir haciendo exactamente lo mismo. Una prueba verifica catálogo = base.
FINANCE_PERMISSIONS: dict[str, str] = {
    "finance.read": "Ver las finanzas de la empresa (cuentas, movimientos y resúmenes)",
    "finance.manage": "Cargar, editar, anular e importar movimientos de la empresa",
}
FINANCE_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": ("finance.read", "finance.manage"),
    "admin": ("finance.read", "finance.manage"),
    "accountant": ("finance.read", "finance.manage"),
    "viewer": ("finance.read",),
}


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")
    op.create_table(
        "contexts",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'business') = (owner_user_id IS NULL)",
            name=op.f("ck_contexts_owner_matches_kind"),
        ),
        sa.CheckConstraint("kind IN ('business', 'personal')", name=op.f("ck_contexts_kind_valid")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_contexts_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["core.users.id"], name=op.f("fk_contexts_owner_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contexts")),
        schema="finance",
    )
    op.create_index(
        "uq_contexts_business_per_org",
        "contexts",
        ["organization_id"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("kind = 'business'"),
    )
    op.create_index(
        "uq_contexts_personal_per_user",
        "contexts",
        ["organization_id", "owner_user_id"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("kind = 'personal'"),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("context_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("institution", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("number_last4", sa.String(length=4), nullable=True),
        sa.Column(
            "opening_balance", sa.Numeric(precision=18, scale=2), server_default="0", nullable=False
        ),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "currency <> 'PYG' OR opening_balance = trunc(opening_balance)",
            name=op.f("ck_accounts_pyg_integer"),
        ),
        sa.CheckConstraint(
            "currency IN ('PYG', 'USD', 'BRL', 'ARS', 'EUR')",
            name=op.f("ck_accounts_currency_valid"),
        ),
        sa.CheckConstraint(
            "kind IN ('cash', 'checking', 'savings', 'credit_card', 'digital_wallet', 'other')",
            name=op.f("ck_accounts_kind_valid"),
        ),
        sa.CheckConstraint(
            "number_last4 ~ '^[0-9]{4}$'", name=op.f("ck_accounts_number_last4_digits")
        ),
        sa.ForeignKeyConstraint(
            ["context_id"], ["finance.contexts.id"], name=op.f("fk_accounts_context_id_contexts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("context_id", "name", name=op.f("uq_accounts_context_id_name")),
        sa.UniqueConstraint(
            "id", "context_id", "currency", name=op.f("uq_accounts_id_context_id_currency")
        ),
        sa.UniqueConstraint("id", "context_id", name=op.f("uq_accounts_id_context_id")),
        schema="finance",
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("context_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('income', 'expense')", name=op.f("ck_categories_kind_valid")),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_categories_not_own_parent")
        ),
        sa.ForeignKeyConstraint(
            ["context_id"], ["finance.contexts.id"], name=op.f("fk_categories_context_id_contexts")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "context_id"],
            ["finance.categories.id", "finance.categories.context_id"],
            name=op.f("fk_categories_parent_id_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint(
            "context_id",
            "parent_id",
            "name",
            name=op.f("uq_categories_context_id_parent_id_name"),
            postgresql_nulls_not_distinct=True,
        ),
        sa.UniqueConstraint("id", "context_id", name=op.f("uq_categories_id_context_id")),
        schema="finance",
    )
    op.create_table(
        "counterparties",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("context_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("ruc", sa.String(length=8), nullable=True),
        sa.Column("ruc_check_digit", sa.CHAR(length=1), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('customer', 'supplier', 'employee', 'bank', 'government', 'person', 'other')",
            name=op.f("ck_counterparties_kind_valid"),
        ),
        sa.CheckConstraint(
            "ruc IS NULL OR ruc ~ '^[0-9]{1,8}$'", name=op.f("ck_counterparties_ruc_digits")
        ),
        sa.CheckConstraint(
            "ruc_check_digit IS NULL OR ruc_check_digit ~ '^[0-9]$'",
            name=op.f("ck_counterparties_ruc_check_digit_digit"),
        ),
        sa.CheckConstraint(
            "(ruc IS NULL) = (ruc_check_digit IS NULL)", name=op.f("ck_counterparties_ruc_complete")
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["finance.contexts.id"],
            name=op.f("fk_counterparties_context_id_contexts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_counterparties")),
        sa.UniqueConstraint("id", "context_id", name=op.f("uq_counterparties_id_context_id")),
        schema="finance",
    )
    op.create_index(
        "uq_counterparties_ruc_per_context",
        "counterparties",
        ["context_id", "ruc"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("ruc IS NOT NULL"),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("context_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("file_format", sa.String(length=10), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="previewed", nullable=False),
        sa.Column("rows_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_imported", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_duplicate", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_error", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'committed') = (committed_at IS NOT NULL)",
            name=op.f("ck_import_batches_committed"),
        ),
        sa.CheckConstraint(
            "file_format IN ('csv', 'xlsx')", name=op.f("ck_import_batches_file_format_valid")
        ),
        sa.CheckConstraint(
            "status IN ('previewed', 'committed', 'cancelled')",
            name=op.f("ck_import_batches_status_valid"),
        ),
        sa.CheckConstraint(
            "octet_length(file_sha256) = 32", name=op.f("ck_import_batches_file_sha256_length")
        ),
        sa.CheckConstraint(
            "rows_total >= 0 AND rows_imported >= 0 AND rows_duplicate >= 0 AND rows_error >= 0",
            name=op.f("ck_import_batches_counts_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "context_id"],
            ["finance.accounts.id", "finance.accounts.context_id"],
            name=op.f("fk_import_batches_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["finance.contexts.id"],
            name=op.f("fk_import_batches_context_id_contexts"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_import_batches_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
        sa.UniqueConstraint("id", "context_id", name=op.f("uq_import_batches_id_context_id")),
        schema="finance",
    )
    op.create_index(
        "ix_import_batches_account_created",
        "import_batches",
        ["account_id", "created_at"],
        unique=False,
        schema="finance",
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("context_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("booked_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("counterparty_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("import_batch_id", sa.UUID(), nullable=True),
        sa.Column("transfer_group_id", sa.UUID(), nullable=True),
        sa.Column("dedupe_key", sa.LargeBinary(length=32), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.UUID(), nullable=True),
        sa.Column("void_reason", sa.String(length=300), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(source = 'import') = (import_batch_id IS NOT NULL)",
            name=op.f("ck_transactions_import_has_batch"),
        ),
        sa.CheckConstraint(
            "currency <> 'PYG' OR amount = trunc(amount)", name=op.f("ck_transactions_pyg_integer")
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'import')", name=op.f("ck_transactions_source_valid")
        ),
        sa.CheckConstraint(
            "(voided_at IS NULL) = (voided_by IS NULL) AND (voided_at IS NULL) = (void_reason IS NULL)",
            name=op.f("ck_transactions_void_complete"),
        ),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_transactions_amount_not_zero")),
        sa.CheckConstraint(
            "octet_length(dedupe_key) = 32", name=op.f("ck_transactions_dedupe_key_length")
        ),
        sa.CheckConstraint(
            "transfer_group_id IS NULL OR category_id IS NULL",
            name=op.f("ck_transactions_transfer_without_category"),
        ),
        sa.CheckConstraint(
            "void_reason IS NULL OR char_length(btrim(void_reason)) >= 3",
            name=op.f("ck_transactions_void_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "context_id", "currency"],
            ["finance.accounts.id", "finance.accounts.context_id", "finance.accounts.currency"],
            name=op.f("fk_transactions_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "context_id"],
            ["finance.categories.id", "finance.categories.context_id"],
            name=op.f("fk_transactions_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["finance.contexts.id"],
            name=op.f("fk_transactions_context_id_contexts"),
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_id", "context_id"],
            ["finance.counterparties.id", "finance.counterparties.context_id"],
            name=op.f("fk_transactions_counterparty_id_counterparties"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_transactions_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id", "context_id"],
            ["finance.import_batches.id", "finance.import_batches.context_id"],
            name=op.f("fk_transactions_import_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["voided_by"], ["core.users.id"], name=op.f("fk_transactions_voided_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        schema="finance",
    )
    op.create_index(
        "ix_transactions_account_booked",
        "transactions",
        ["account_id", "booked_on"],
        unique=False,
        schema="finance",
    )
    op.create_index(
        "ix_transactions_account_dedupe",
        "transactions",
        ["account_id", "dedupe_key"],
        unique=False,
        schema="finance",
    )
    op.create_index(
        "ix_transactions_context_booked",
        "transactions",
        ["context_id", sa.literal_column("booked_on DESC"), sa.literal_column("id DESC")],
        unique=False,
        schema="finance",
    )
    op.create_index(
        "ix_transactions_import_batch",
        "transactions",
        ["import_batch_id"],
        unique=False,
        schema="finance",
    )
    op.create_index(
        "ix_transactions_transfer_group",
        "transactions",
        ["transfer_group_id"],
        unique=False,
        schema="finance",
        postgresql_where=sa.text("transfer_group_id IS NOT NULL"),
    )
    op.create_table(
        "import_rows",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("booked_on", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("duplicate_of", sa.UUID(), nullable=True),
        sa.Column("duplicate_in_file", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('import', 'skip')", name=op.f("ck_import_rows_decision_valid")
        ),
        sa.CheckConstraint("row_number > 0", name=op.f("ck_import_rows_row_number_positive")),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["finance.import_batches.id"],
            name=op.f("fk_import_rows_batch_id_import_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of"],
            ["finance.transactions.id"],
            name=op.f("fk_import_rows_duplicate_of_transactions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_rows")),
        sa.UniqueConstraint(
            "batch_id", "row_number", name=op.f("uq_import_rows_batch_id_row_number")
        ),
        schema="finance",
    )

    _seed_permissions()
    # Cada organización existente recibe su contexto empresarial (D-023).
    op.execute(
        "INSERT INTO finance.contexts (organization_id, kind, name)"
        " SELECT id, 'business', 'Empresa' FROM core.organizations"
    )


def _seed_permissions() -> None:
    # ON CONFLICT: la 0001 carga el catálogo vivo, así que en una base nueva estos permisos
    # ya pueden existir; en una base creada antes de esta fase, se agregan acá.
    bind = op.get_bind()
    for code, description in FINANCE_PERMISSIONS.items():
        bind.execute(
            sa.text(
                "INSERT INTO core.permissions (code, description) VALUES (:code, :description)"
                " ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "description": description},
        )
    for role, codes in FINANCE_ROLE_PERMISSIONS.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO core.role_permissions (role_code, permission_code)"
                    " VALUES (:role, :code) ON CONFLICT DO NOTHING"
                ),
                {"role": role, "code": code},
            )


def downgrade() -> None:
    # Destructivo: elimina todos los datos financieros. Solo para desarrollo.
    op.drop_table("import_rows", schema="finance")
    op.drop_index(
        "ix_transactions_transfer_group",
        table_name="transactions",
        schema="finance",
        postgresql_where=sa.text("transfer_group_id IS NOT NULL"),
    )
    op.drop_index("ix_transactions_import_batch", table_name="transactions", schema="finance")
    op.drop_index("ix_transactions_context_booked", table_name="transactions", schema="finance")
    op.drop_index("ix_transactions_account_dedupe", table_name="transactions", schema="finance")
    op.drop_index("ix_transactions_account_booked", table_name="transactions", schema="finance")
    op.drop_table("transactions", schema="finance")
    op.drop_index(
        "ix_import_batches_account_created", table_name="import_batches", schema="finance"
    )
    op.drop_table("import_batches", schema="finance")
    op.drop_index(
        "uq_counterparties_ruc_per_context",
        table_name="counterparties",
        schema="finance",
        postgresql_where=sa.text("ruc IS NOT NULL"),
    )
    op.drop_table("counterparties", schema="finance")
    op.drop_table("categories", schema="finance")
    op.drop_table("accounts", schema="finance")
    op.drop_index(
        "uq_contexts_personal_per_user",
        table_name="contexts",
        schema="finance",
        postgresql_where=sa.text("kind = 'personal'"),
    )
    op.drop_index(
        "uq_contexts_business_per_org",
        table_name="contexts",
        schema="finance",
        postgresql_where=sa.text("kind = 'business'"),
    )
    op.drop_table("contexts", schema="finance")
    op.execute("DROP SCHEMA finance")
    op.execute(
        "DELETE FROM core.role_permissions WHERE permission_code IN ('finance.read', 'finance.manage');"
        " DELETE FROM core.permissions WHERE code IN ('finance.read', 'finance.manage');"
    )
