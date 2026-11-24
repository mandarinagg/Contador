"""Contabilidad, fase 3B: activos fijos y depreciación, centros de costos, asientos
recurrentes (esquema `accounting`).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-24

Especificación: docs/specs/FASE3B_CONTABILIDAD.md (D-056 a D-067; D-068 en adelante en
docs/DECISIONS.md). Escrita a mano sobre un borrador autogenerado. Además de las tablas:
- `journal_entries.kind` pasa a varchar(12) y su CHECK suma `depreciation`, `disposal` y
  `recurring`; `journal_lines.cost_center_id` con FK compuesta; tres columnas en `settings`;
  `UNIQUE (id, organization_id)` en `periods` (destino de las FK compuestas nuevas).
- Triggers (`TRIGGERS_3B_SQL`): las funciones de asientos y de líneas de la 0003 se
  reemplazan con `CREATE OR REPLACE` por una versión ampliada; el downgrade restaura las
  copias congeladas de la 0003 (`JOURNAL_ENTRIES_GUARD_0003`, `JOURNAL_LINES_GUARD_0003`), que
  una prueba compara con el texto de la 0003. Las corridas y generaciones copian el estado
  de su asiento en `entry_status` (lo mantienen los triggers) para su índice único parcial.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_0003 = "kind IN ('manual', 'finance', 'reversal', 'closing')"
KINDS_0004 = (
    "kind IN ('manual', 'finance', 'reversal', 'closing', 'depreciation', 'disposal', 'recurring')"
)


def upgrade() -> None:
    # Destino de las FK compuestas de corridas y generaciones: va antes que sus tablas.
    op.create_unique_constraint(
        op.f("uq_periods_id_organization_id"),
        "periods",
        ["id", "organization_id"],
        schema="accounting",
    )
    op.create_table(
        "cost_centers",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
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
            "code ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'", name=op.f("ck_cost_centers_code_format")
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0", name=op.f("ck_cost_centers_name_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_cost_centers_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_centers")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_cost_centers_id_organization_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "code", name=op.f("uq_cost_centers_organization_id_code")
        ),
        schema="accounting",
    )
    op.create_table(
        "recurring_templates",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("document_reference", sa.String(length=100), nullable=True),
        sa.Column("day_of_month", sa.SmallInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
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
            "status IN ('active', 'paused')", name=op.f("ck_recurring_templates_status_valid")
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) > 0",
            name=op.f("ck_recurring_templates_description_not_blank"),
        ),
        sa.CheckConstraint(
            "day_of_month BETWEEN 1 AND 31", name=op.f("ck_recurring_templates_day_of_month_range")
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name=op.f("ck_recurring_templates_dates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_recurring_templates_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_recurring_templates_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_templates")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_recurring_templates_id_organization_id")
        ),
        schema="accounting",
    )
    op.create_table(
        "asset_categories",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("useful_life_months", sa.Integer(), nullable=True),
        sa.Column("residual_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("asset_account_id", sa.UUID(), nullable=True),
        sa.Column("accumulated_account_id", sa.UUID(), nullable=True),
        sa.Column("expense_account_id", sa.UUID(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("legal_reference", sa.String(length=500), nullable=True),
        sa.Column("citation", sa.String(length=1000), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column(
            "validation_status", sa.String(length=10), server_default="pending", nullable=False
        ),
        sa.Column("validated_by_name", sa.String(length=150), nullable=True),
        sa.Column("validated_reference", sa.String(length=100), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
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
            "(validation_status = 'validated') = (validated_by_name IS NOT NULL) AND (validation_status = 'validated') = (validated_reference IS NOT NULL) AND (validation_status = 'validated') = (validated_at IS NOT NULL)",
            name=op.f("ck_asset_categories_validation_complete"),
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'validated')",
            name=op.f("ck_asset_categories_validation_status_valid"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0", name=op.f("ck_asset_categories_name_not_blank")
        ),
        sa.CheckConstraint(
            "residual_rate IS NULL OR (residual_rate >= 0 AND residual_rate <= 20)",
            name=op.f("ck_asset_categories_residual_rate_range"),
        ),
        sa.CheckConstraint(
            "useful_life_months IS NULL OR useful_life_months > 0",
            name=op.f("ck_asset_categories_useful_life_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["accumulated_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_asset_categories_accumulated_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_asset_categories_asset_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["expense_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_asset_categories_expense_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_asset_categories_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_categories")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_asset_categories_id_organization_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "code", name=op.f("uq_asset_categories_organization_id_code")
        ),
        schema="accounting",
    )
    op.create_table(
        "recurring_template_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("debit", sa.Numeric(precision=18, scale=2), server_default="0", nullable=False),
        sa.Column("credit", sa.Numeric(precision=18, scale=2), server_default="0", nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("fx_currency", sa.CHAR(length=3), nullable=True),
        sa.Column("fx_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("cost_center_id", sa.UUID(), nullable=True),
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
            "fx_currency IS NULL OR fx_currency IN ('USD', 'BRL', 'ARS', 'EUR')",
            name=op.f("ck_recurring_template_lines_fx_currency_valid"),
        ),
        sa.CheckConstraint(
            "(debit > 0) <> (credit > 0)", name=op.f("ck_recurring_template_lines_debit_xor_credit")
        ),
        sa.CheckConstraint(
            "(fx_currency IS NULL) = (fx_amount IS NULL) AND (fx_currency IS NULL) = (fx_rate IS NULL)",
            name=op.f("ck_recurring_template_lines_fx_complete"),
        ),
        sa.CheckConstraint(
            "debit = trunc(debit) AND credit = trunc(credit)",
            name=op.f("ck_recurring_template_lines_pyg_integer"),
        ),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name=op.f("ck_recurring_template_lines_amounts_non_negative"),
        ),
        sa.CheckConstraint(
            "fx_amount IS NULL OR fx_amount > 0",
            name=op.f("ck_recurring_template_lines_fx_amount_positive"),
        ),
        sa.CheckConstraint(
            "fx_rate IS NULL OR fx_rate > 0",
            name=op.f("ck_recurring_template_lines_fx_rate_positive"),
        ),
        sa.CheckConstraint(
            "line_no > 0", name=op.f("ck_recurring_template_lines_line_no_positive")
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_recurring_template_lines_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["cost_center_id", "organization_id"],
            ["accounting.cost_centers.id", "accounting.cost_centers.organization_id"],
            name=op.f("fk_recurring_template_lines_cost_center_id_cost_centers"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_recurring_template_lines_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "organization_id"],
            ["accounting.recurring_templates.id", "accounting.recurring_templates.organization_id"],
            name=op.f("fk_recurring_template_lines_template_id_recurring_templates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_template_lines")),
        sa.UniqueConstraint(
            "template_id", "line_no", name=op.f("uq_recurring_template_lines_template_id_line_no")
        ),
        schema="accounting",
    )
    op.create_table(
        "depreciation_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        # Sin DEFAULT: la escribe el trigger BEFORE INSERT (NOT NULL se verifica después).
        sa.Column("entry_status", sa.String(length=10), nullable=False),
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
            "entry_status IN ('draft', 'posted', 'reversed', 'discarded')",
            name=op.f("ck_depreciation_runs_entry_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_depreciation_runs_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_depreciation_runs_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_depreciation_runs_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["period_id", "organization_id"],
            ["accounting.periods.id", "accounting.periods.organization_id"],
            name=op.f("fk_depreciation_runs_period_id_periods"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_depreciation_runs")),
        sa.UniqueConstraint("entry_id", name=op.f("uq_depreciation_runs_entry_id")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_depreciation_runs_id_organization_id")
        ),
        schema="accounting",
    )
    op.create_index(
        "uq_depreciation_runs_live_period",
        "depreciation_runs",
        ["period_id"],
        unique=True,
        schema="accounting",
        postgresql_where=sa.text("entry_status IN ('draft', 'posted')"),
    )
    op.create_table(
        "fixed_assets",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("serial_or_reference", sa.String(length=100), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("start_rule", sa.String(length=20), nullable=False),
        sa.Column("depreciation_start", sa.Date(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("residual_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("fiscal_useful_life_months", sa.Integer(), nullable=False),
        sa.Column("fiscal_residual_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("fiscal_residual_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("acquisition_entry_id", sa.UUID(), nullable=True),
        sa.Column("source_transaction_id", sa.UUID(), nullable=True),
        sa.Column("source_context_id", sa.UUID(), nullable=True),
        sa.Column("source_context_kind", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("disposed_on", sa.Date(), nullable=True),
        sa.Column("disposal_kind", sa.String(length=10), nullable=True),
        sa.Column("disposal_reason", sa.String(length=300), nullable=True),
        sa.Column("disposal_document_reference", sa.String(length=100), nullable=True),
        sa.Column("disposal_entry_id", sa.UUID(), nullable=True),
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
            "disposal_kind IS NULL OR disposal_kind IN ('sale', 'scrap', 'donation')",
            name=op.f("ck_fixed_assets_disposal_kind_valid"),
        ),
        sa.CheckConstraint(
            "source_context_kind IS NULL OR source_context_kind = 'business'",
            name=op.f("ck_fixed_assets_source_business_only"),
        ),
        sa.CheckConstraint(
            "start_rule IN ('next_month', 'next_fiscal_year')",
            name=op.f("ck_fixed_assets_start_rule_valid"),
        ),
        sa.CheckConstraint(
            "status = 'active' OR disposal_entry_id IS NOT NULL",
            name=op.f("ck_fixed_assets_disposed_has_entry"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disposed')", name=op.f("ck_fixed_assets_status_valid")
        ),
        sa.CheckConstraint(
            "(disposal_entry_id IS NULL) = (disposed_on IS NULL) AND (disposal_entry_id IS NULL) = (disposal_kind IS NULL) AND (disposal_entry_id IS NULL) = (disposal_reason IS NULL) AND (disposal_entry_id IS NULL) = (disposal_document_reference IS NULL)",
            name=op.f("ck_fixed_assets_disposal_complete"),
        ),
        sa.CheckConstraint(
            "(source_transaction_id IS NULL) = (source_context_id IS NULL) AND (source_transaction_id IS NULL) = (source_context_kind IS NULL)",
            name=op.f("ck_fixed_assets_source_complete"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0", name=op.f("ck_fixed_assets_name_not_blank")
        ),
        sa.CheckConstraint(
            "cost > 0 AND cost = trunc(cost)", name=op.f("ck_fixed_assets_cost_positive_integer")
        ),
        sa.CheckConstraint(
            "depreciation_start > acquired_on", name=op.f("ck_fixed_assets_start_after_acquisition")
        ),
        sa.CheckConstraint(
            "disposed_on IS NULL OR disposed_on >= acquired_on",
            name=op.f("ck_fixed_assets_disposed_after_acquired"),
        ),
        sa.CheckConstraint(
            "extract(day FROM depreciation_start) = 1",
            name=op.f("ck_fixed_assets_depreciation_start_first_day"),
        ),
        sa.CheckConstraint(
            "fiscal_residual_rate >= 0 AND fiscal_residual_rate <= 20",
            name=op.f("ck_fixed_assets_fiscal_residual_rate_range"),
        ),
        sa.CheckConstraint(
            "fiscal_residual_value = floor(cost * fiscal_residual_rate / 100)",
            name=op.f("ck_fixed_assets_fiscal_residual_value_exact"),
        ),
        sa.CheckConstraint(
            "residual_value >= 0 AND residual_value = trunc(residual_value) AND residual_value < cost",
            name=op.f("ck_fixed_assets_residual_valid"),
        ),
        sa.CheckConstraint(
            "useful_life_months > 0 AND fiscal_useful_life_months > 0",
            name=op.f("ck_fixed_assets_useful_life_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["acquisition_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_fixed_assets_acquisition_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "organization_id"],
            ["accounting.asset_categories.id", "accounting.asset_categories.organization_id"],
            name=op.f("fk_fixed_assets_category_id_asset_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_fixed_assets_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["disposal_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_fixed_assets_disposal_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_fixed_assets_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["source_context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_fixed_assets_source_context_org_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["source_context_id", "source_context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_fixed_assets_source_context_kind_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["source_transaction_id", "source_context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
            name=op.f("fk_fixed_assets_source_transaction_id_transactions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fixed_assets")),
        sa.UniqueConstraint("disposal_entry_id", name=op.f("uq_fixed_assets_disposal_entry_id")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_fixed_assets_id_organization_id")
        ),
        schema="accounting",
    )
    op.create_index(
        "ix_fixed_assets_org_status",
        "fixed_assets",
        ["organization_id", "status"],
        unique=False,
        schema="accounting",
    )
    op.create_table(
        "recurring_generations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        # Sin DEFAULT: la escribe el trigger BEFORE INSERT (NOT NULL se verifica después).
        sa.Column("entry_status", sa.String(length=10), nullable=False),
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
            "entry_status IN ('draft', 'posted', 'reversed', 'discarded')",
            name=op.f("ck_recurring_generations_entry_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["core.users.id"],
            name=op.f("fk_recurring_generations_created_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_recurring_generations_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_recurring_generations_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["period_id", "organization_id"],
            ["accounting.periods.id", "accounting.periods.organization_id"],
            name=op.f("fk_recurring_generations_period_id_periods"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "organization_id"],
            ["accounting.recurring_templates.id", "accounting.recurring_templates.organization_id"],
            name=op.f("fk_recurring_generations_template_id_recurring_templates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_generations")),
        sa.UniqueConstraint("entry_id", name=op.f("uq_recurring_generations_entry_id")),
        schema="accounting",
    )
    op.create_index(
        "uq_recurring_generations_live",
        "recurring_generations",
        ["template_id", "period_id"],
        unique=True,
        schema="accounting",
        postgresql_where=sa.text("entry_status IN ('draft', 'posted')"),
    )
    op.create_table(
        "asset_year_values",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("fiscal_year_id", sa.UUID(), nullable=False),
        sa.Column("fiscal_net_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("accounting_net_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("fiscal_depreciation", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("accounting_depreciation", sa.Numeric(precision=18, scale=2), nullable=False),
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
            "fiscal_net_value = trunc(fiscal_net_value) AND accounting_net_value = trunc(accounting_net_value) AND fiscal_depreciation = trunc(fiscal_depreciation) AND accounting_depreciation = trunc(accounting_depreciation)",
            name=op.f("ck_asset_year_values_values_pyg_integer"),
        ),
        sa.CheckConstraint(
            "fiscal_net_value >= 0 AND accounting_net_value >= 0 AND fiscal_depreciation >= 0 AND accounting_depreciation >= 0",
            name=op.f("ck_asset_year_values_values_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "organization_id"],
            ["accounting.fixed_assets.id", "accounting.fixed_assets.organization_id"],
            name=op.f("fk_asset_year_values_asset_id_fixed_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_year_id", "organization_id"],
            ["accounting.fiscal_years.id", "accounting.fiscal_years.organization_id"],
            name=op.f("fk_asset_year_values_fiscal_year_id_fiscal_years"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_asset_year_values_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_year_values")),
        sa.UniqueConstraint(
            "asset_id", "fiscal_year_id", name=op.f("uq_asset_year_values_asset_id_fiscal_year_id")
        ),
        schema="accounting",
    )
    op.create_table(
        "depreciation_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("installment", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
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
            "amount > 0 AND amount = trunc(amount)",
            name=op.f("ck_depreciation_items_amount_positive_integer"),
        ),
        sa.CheckConstraint(
            "installment > 0", name=op.f("ck_depreciation_items_installment_positive")
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "organization_id"],
            ["accounting.fixed_assets.id", "accounting.fixed_assets.organization_id"],
            name=op.f("fk_depreciation_items_asset_id_fixed_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_depreciation_items_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "organization_id"],
            ["accounting.depreciation_runs.id", "accounting.depreciation_runs.organization_id"],
            name=op.f("fk_depreciation_items_run_id_depreciation_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_depreciation_items")),
        sa.UniqueConstraint(
            "run_id", "asset_id", name=op.f("uq_depreciation_items_run_id_asset_id")
        ),
        schema="accounting",
    )
    op.create_index(
        "ix_depreciation_items_asset",
        "depreciation_items",
        ["asset_id"],
        unique=False,
        schema="accounting",
    )
    op.alter_column(
        "journal_entries",
        "kind",
        existing_type=sa.VARCHAR(length=10),
        type_=sa.String(length=12),
        existing_nullable=False,
        schema="accounting",
    )
    op.add_column(
        "journal_lines", sa.Column("cost_center_id", sa.UUID(), nullable=True), schema="accounting"
    )
    op.create_foreign_key(
        op.f("fk_journal_lines_cost_center_id_cost_centers"),
        "journal_lines",
        "cost_centers",
        ["cost_center_id", "organization_id"],
        ["id", "organization_id"],
        source_schema="accounting",
        referent_schema="accounting",
    )
    op.add_column(
        "settings",
        sa.Column("asset_disposal_account_id", sa.UUID(), nullable=True),
        schema="accounting",
    )
    op.add_column(
        "settings",
        sa.Column("cost_centers_required", sa.Boolean(), server_default="false", nullable=False),
        schema="accounting",
    )
    op.add_column(
        "settings",
        sa.Column(
            "default_asset_start_rule",
            sa.String(length=20),
            server_default="next_month",
            nullable=False,
        ),
        schema="accounting",
    )
    op.create_foreign_key(
        op.f("fk_settings_asset_disposal_account_id_ledger_accounts"),
        "settings",
        "ledger_accounts",
        ["asset_disposal_account_id", "organization_id"],
        ["id", "organization_id"],
        source_schema="accounting",
        referent_schema="accounting",
    )
    op.drop_constraint(
        op.f("ck_journal_entries_kind_valid"), "journal_entries", schema="accounting", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_journal_entries_kind_valid"), "journal_entries", KINDS_0004, schema="accounting"
    )
    op.create_check_constraint(
        op.f("ck_settings_start_rule_valid"),
        "settings",
        "default_asset_start_rule IN ('next_month', 'next_fiscal_year')",
        schema="accounting",
    )
    op.execute(TRIGGERS_3B_SQL)


TRIGGERS_3B_SQL = r"""
-- Mismas convenciones que la 0003: SQLSTATE 23000 y un nombre estable `trg_*` en CONSTRAINT.

-- Asientos (versión 0004 de la función de la 0003). Cambios, todos al contabilizar:
-- * D-058/D-059/D-061: los asientos de depreciación, baja y recurrentes también se revierten;
-- * D-060: la reversión copia también el centro de costos de cada línea;
-- * D-060: con `settings.cost_centers_required`, las líneas de resultado de un asiento manual,
--   de finanzas o recurrente llevan centro (la refundición, la depreciación, la baja y las
--   reversiones quedan exceptuadas: las genera el sistema o copian el original);
-- * D-058: una corrida suma exactamente lo que dice su detalle por bien;
-- * D-059: un asiento de baja tiene su bien.
CREATE OR REPLACE FUNCTION accounting.journal_entries_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_year accounting.fiscal_years%ROWTYPE;
  v_period_status text;
  v_lines integer;
  v_debit numeric;
  v_credit numeric;
  v_postable boolean;
  v_original accounting.journal_entries%ROWTYPE;
  v_voided timestamptz;
  v_items numeric;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un asiento no se borra: se descarta (borrador) o se revierte'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_no_delete';
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' OR NEW.number IS NOT NULL THEN
      RAISE EXCEPTION 'Un asiento nace como borrador y sin número'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_insert_draft';
    END IF;
  ELSE
    IF OLD.status IN ('reversed', 'discarded') THEN
      RAISE EXCEPTION 'El asiento % está %: es definitivo',
        coalesce(OLD.number::text, OLD.id::text), OLD.status
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_final';
    END IF;
    IF OLD.status = 'posted' THEN
      IF NEW.status <> 'reversed'
         OR (to_jsonb(NEW) - 'status' - 'updated_at') <> (to_jsonb(OLD) - 'status' - 'updated_at')
      THEN
        RAISE EXCEPTION 'El asiento N° % está contabilizado: no se modifica, se revierte',
          OLD.number
          USING ERRCODE = 'integrity_constraint_violation',
                CONSTRAINT = 'trg_journal_entries_posted_immutable';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM accounting.journal_entries
                     WHERE reverses_entry_id = OLD.id AND status = 'posted') THEN
        RAISE EXCEPTION 'El asiento N° % solo pasa a revertido con su reversión contabilizada',
          OLD.number
          USING ERRCODE = 'integrity_constraint_violation',
                CONSTRAINT = 'trg_journal_entries_reversal_missing';
      END IF;
      RETURN NEW;
    END IF;
    -- OLD.status = 'draft'
    IF NEW.status = 'reversed' THEN
      RAISE EXCEPTION 'Un borrador no se revierte: se descarta'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_final';
    END IF;
  END IF;

  -- Alta o cambio de un borrador, descarte o contabilización: la fecha cae en el ejercicio.
  SELECT * INTO v_year FROM accounting.fiscal_years WHERE id = NEW.fiscal_year_id;
  IF NEW.entry_date < v_year.start_date OR NEW.entry_date > v_year.end_date THEN
    RAISE EXCEPTION 'La fecha % está fuera del ejercicio % - %',
      NEW.entry_date, v_year.start_date, v_year.end_date
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_date_outside_year';
  END IF;
  IF NEW.status <> 'posted' THEN
    RETURN NEW;
  END IF;

  -- draft → posted.
  IF NEW.number IS NOT NULL THEN
    RAISE EXCEPTION 'El número del asiento lo asigna la base al contabilizar'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_number_assigned';
  END IF;
  IF v_year.status <> 'open' THEN
    RAISE EXCEPTION 'El ejercicio % - % está cerrado', v_year.start_date, v_year.end_date
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_year_closed';
  END IF;

  SELECT count(*), coalesce(sum(l.debit), 0), coalesce(sum(l.credit), 0),
         coalesce(bool_and(a.is_postable AND a.archived_at IS NULL), true)
    INTO v_lines, v_debit, v_credit, v_postable
    FROM accounting.journal_lines l
    JOIN accounting.ledger_accounts a ON a.id = l.account_id
   WHERE l.entry_id = NEW.id;
  IF v_lines < 2 THEN
    RAISE EXCEPTION 'Un asiento se contabiliza con al menos dos líneas (tiene %)', v_lines
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_min_lines';
  END IF;
  IF v_debit <> v_credit OR v_debit = 0 THEN
    RAISE EXCEPTION 'El asiento no balancea: debe % y haber %', v_debit, v_credit
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_unbalanced';
  END IF;
  IF NOT v_postable THEN
    RAISE EXCEPTION 'El asiento usa una cuenta agrupadora o archivada'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_account_not_postable';
  END IF;

  IF NEW.kind = 'closing' THEN
    -- La refundición la genera el cierre del ejercicio antes de marcarlo cerrado: va al
    -- último día y con todos los períodos ya cerrados. Es la única excepción a la regla
    -- del período abierto.
    IF NEW.entry_date <> v_year.end_date OR EXISTS (
         SELECT 1 FROM accounting.periods
          WHERE fiscal_year_id = NEW.fiscal_year_id AND status = 'open') THEN
      RAISE EXCEPTION 'La refundición va al último día del ejercicio, con sus períodos cerrados'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_closing_invalid';
    END IF;
  ELSE
    SELECT status INTO v_period_status FROM accounting.periods
     WHERE fiscal_year_id = NEW.fiscal_year_id
       AND NEW.entry_date BETWEEN start_date AND end_date
     FOR SHARE;
    IF v_period_status IS DISTINCT FROM 'open' THEN
      RAISE EXCEPTION 'El período de la fecha % está cerrado', NEW.entry_date
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_period_closed';
    END IF;
  END IF;

  IF NEW.kind = 'reversal' THEN
    SELECT * INTO v_original FROM accounting.journal_entries
     WHERE id = NEW.reverses_entry_id FOR UPDATE;
    IF v_original.status <> 'posted'
       OR v_original.kind NOT IN ('manual', 'finance', 'depreciation', 'disposal', 'recurring')
    THEN
      RAISE EXCEPTION 'Solo se revierte un asiento contabilizado que no sea una reversión ni una '
        'refundición'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_reversal_invalid';
    END IF;
    -- Las líneas de la reversión son exactamente las del original con el debe y el haber
    -- intercambiados y el mismo centro de costos (multiconjuntos en los dos sentidos; en las
    -- operaciones de conjuntos, dos NULL cuentan como iguales).
    IF EXISTS (
         (SELECT account_id, credit AS debit, debit AS credit, cost_center_id
            FROM accounting.journal_lines WHERE entry_id = NEW.reverses_entry_id
          EXCEPT ALL
          SELECT account_id, debit, credit, cost_center_id
            FROM accounting.journal_lines WHERE entry_id = NEW.id)
         UNION ALL
         (SELECT account_id, debit, credit, cost_center_id
            FROM accounting.journal_lines WHERE entry_id = NEW.id
          EXCEPT ALL
          SELECT account_id, credit, debit, cost_center_id
            FROM accounting.journal_lines WHERE entry_id = NEW.reverses_entry_id)) THEN
      RAISE EXCEPTION 'Las líneas de la reversión no son las del asiento original invertidas'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_reversal_mismatch';
    END IF;
  END IF;

  IF NEW.kind IN ('manual', 'finance', 'recurring')
     AND EXISTS (SELECT 1 FROM accounting.settings
                  WHERE organization_id = NEW.organization_id AND cost_centers_required)
     AND EXISTS (SELECT 1 FROM accounting.journal_lines l
                   JOIN accounting.ledger_accounts a ON a.id = l.account_id
                  WHERE l.entry_id = NEW.id AND a.kind IN ('income', 'expense')
                    AND l.cost_center_id IS NULL) THEN
    RAISE EXCEPTION 'Las líneas de ingreso y gasto llevan centro de costos (es obligatorio)'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_cost_center_required';
  END IF;

  IF NEW.kind = 'depreciation' THEN
    SELECT sum(i.amount) INTO v_items
      FROM accounting.depreciation_runs r
      JOIN accounting.depreciation_items i ON i.run_id = r.id
     WHERE r.entry_id = NEW.id;
    IF v_items IS DISTINCT FROM v_debit THEN
      RAISE EXCEPTION 'La corrida de depreciación no coincide con su detalle por bien '
        '(asiento %, detalle %)', v_debit, coalesce(v_items, 0)
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_depreciation_mismatch';
    END IF;
  END IF;

  IF NEW.kind = 'disposal'
     AND NOT EXISTS (SELECT 1 FROM accounting.fixed_assets WHERE disposal_entry_id = NEW.id) THEN
    RAISE EXCEPTION 'El asiento de baja no corresponde a ningún bien'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_disposal_orphan';
  END IF;

  IF NEW.source_transaction_id IS NOT NULL THEN
    SELECT voided_at INTO v_voided FROM finance.transactions
     WHERE id = NEW.source_transaction_id FOR SHARE;
    IF v_voided IS NOT NULL THEN
      RAISE EXCEPTION 'El movimiento de finanzas de origen está anulado'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_source_voided';
    END IF;
  END IF;

  UPDATE accounting.fiscal_years SET last_entry_number = last_entry_number + 1
   WHERE id = NEW.fiscal_year_id
  RETURNING last_entry_number INTO NEW.number;
  RETURN NEW;
END $$;

-- Líneas (versión 0004): además de lo de la 0003, el centro de costos (D-060) va solo en
-- cuentas de ingreso o gasto y no puede estar archivado (salvo en una reversión, que copia
-- las líneas del original tal cual: si no, archivar un centro impediría revertir).
CREATE OR REPLACE FUNCTION accounting.journal_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
  v_postable boolean;
  v_kind text;
  v_center_archived timestamptz;
  v_entry_kind text;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT status INTO v_status FROM accounting.journal_entries
     WHERE id = OLD.entry_id FOR SHARE;
    IF v_status <> 'draft' THEN
      RAISE EXCEPTION 'Las líneas de un asiento % no se modifican', v_status
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_lines_entry_not_draft';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  SELECT status, kind INTO v_status, v_entry_kind FROM accounting.journal_entries
   WHERE id = NEW.entry_id FOR SHARE;
  IF v_status <> 'draft' THEN
    RAISE EXCEPTION 'Las líneas de un asiento % no se modifican', v_status
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_lines_entry_not_draft';
  END IF;
  SELECT is_postable AND archived_at IS NULL, kind INTO v_postable, v_kind
    FROM accounting.ledger_accounts WHERE id = NEW.account_id;
  IF NOT coalesce(v_postable, true) THEN
    RAISE EXCEPTION 'La cuenta de la línea % es agrupadora o está archivada', NEW.line_no
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_lines_account_not_postable';
  END IF;
  IF NEW.cost_center_id IS NOT NULL THEN
    IF v_kind NOT IN ('income', 'expense') THEN
      RAISE EXCEPTION 'La línea % lleva centro de costos con una cuenta que no es de ingreso '
        'ni de gasto', NEW.line_no
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_lines_cost_center_account';
    END IF;
    SELECT archived_at INTO v_center_archived FROM accounting.cost_centers
     WHERE id = NEW.cost_center_id;
    IF v_center_archived IS NOT NULL AND v_entry_kind <> 'reversal' THEN
      RAISE EXCEPTION 'El centro de costos de la línea % está archivado', NEW.line_no
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_lines_cost_center_archived';
    END IF;
  END IF;
  RETURN NEW;
END $$;

-- Corridas y generaciones (D-058, D-061): `entry_status` copia el estado de su asiento.
-- Al cambiar el estado de un asiento de depreciación o recurrente se copia acá; y cada
-- escritura de la corrida o la generación la recalcula, así que no se puede falsear.
CREATE FUNCTION accounting.journal_entries_sync_links() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.kind = 'depreciation' THEN
    UPDATE accounting.depreciation_runs SET entry_status = NEW.status WHERE entry_id = NEW.id;
  ELSE
    UPDATE accounting.recurring_generations SET entry_status = NEW.status
     WHERE entry_id = NEW.id;
  END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER journal_entries_sync_links AFTER UPDATE OF status ON accounting.journal_entries
  FOR EACH ROW
  WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.kind IN ('depreciation', 'recurring'))
  EXECUTE FUNCTION accounting.journal_entries_sync_links();

-- Una corrida o generación nace con su asiento en borrador, del tipo que corresponde y con
-- la fecha dentro de su período; después solo cambia `entry_status`, que siempre se relee
-- del asiento.
CREATE FUNCTION accounting.entry_links_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_entry accounting.journal_entries%ROWTYPE;
  v_kind text := CASE TG_TABLE_NAME WHEN 'depreciation_runs' THEN 'depreciation'
                                    ELSE 'recurring' END;
BEGIN
  IF TG_OP = 'UPDATE'
     AND (to_jsonb(NEW) - 'entry_status' - 'updated_at')
         <> (to_jsonb(OLD) - 'entry_status' - 'updated_at') THEN
    RAISE EXCEPTION 'En %.% solo cambia el estado del asiento', TG_TABLE_SCHEMA, TG_TABLE_NAME
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_' || TG_TABLE_NAME || '_immutable';
  END IF;
  SELECT * INTO v_entry FROM accounting.journal_entries WHERE id = NEW.entry_id;
  IF TG_OP = 'INSERT' THEN
    IF v_entry.status IS DISTINCT FROM 'draft' OR v_entry.kind IS DISTINCT FROM v_kind THEN
      RAISE EXCEPTION 'El asiento de %.% tiene que ser un borrador de tipo %',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, v_kind
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_' || TG_TABLE_NAME || '_entry_invalid';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM accounting.periods
                    WHERE id = NEW.period_id AND fiscal_year_id = v_entry.fiscal_year_id
                      AND v_entry.entry_date BETWEEN start_date AND end_date) THEN
      RAISE EXCEPTION 'La fecha del asiento no cae en el período de %.%',
        TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_' || TG_TABLE_NAME || '_period_mismatch';
    END IF;
  END IF;
  NEW.entry_status := v_entry.status;
  RETURN NEW;
END $$;

CREATE TRIGGER depreciation_runs_guard BEFORE INSERT OR UPDATE ON accounting.depreciation_runs
  FOR EACH ROW EXECUTE FUNCTION accounting.entry_links_guard();
CREATE TRIGGER recurring_generations_guard BEFORE INSERT OR UPDATE
  ON accounting.recurring_generations
  FOR EACH ROW EXECUTE FUNCTION accounting.entry_links_guard();

-- Detalle de una corrida: solo se agrega mientras su asiento es borrador; no cambia ni se
-- borra (si la corrida se descarta, el detalle queda como registro de lo que se propuso).
CREATE FUNCTION accounting.depreciation_items_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'El detalle de una corrida de depreciación no se modifica'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_depreciation_items_immutable';
  END IF;
  SELECT e.status INTO v_status
    FROM accounting.depreciation_runs r
    JOIN accounting.journal_entries e ON e.id = r.entry_id
   WHERE r.id = NEW.run_id;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'El detalle se agrega solo con la corrida en borrador'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_depreciation_items_entry_not_draft';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER depreciation_items_guard BEFORE INSERT OR UPDATE OR DELETE
  ON accounting.depreciation_items
  FOR EACH ROW EXECUTE FUNCTION accounting.depreciation_items_guard();

-- Un bien con depreciaciones vivas (borrador o contabilizadas) no cambia su categoría ni sus
-- parámetros de depreciación (D-057): cambiarlos dejaría el detalle desfasado.
CREATE FUNCTION accounting.fixed_assets_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.organization_id, NEW.category_id, NEW.acquired_on, NEW.start_rule,
      NEW.depreciation_start, NEW.cost, NEW.residual_value, NEW.useful_life_months,
      NEW.fiscal_useful_life_months, NEW.fiscal_residual_rate, NEW.fiscal_residual_value)
       IS DISTINCT FROM
     (OLD.organization_id, OLD.category_id, OLD.acquired_on, OLD.start_rule,
      OLD.depreciation_start, OLD.cost, OLD.residual_value, OLD.useful_life_months,
      OLD.fiscal_useful_life_months, OLD.fiscal_residual_rate, OLD.fiscal_residual_value)
     AND EXISTS (SELECT 1 FROM accounting.depreciation_items i
                   JOIN accounting.depreciation_runs r ON r.id = i.run_id
                  WHERE i.asset_id = OLD.id AND r.entry_status IN ('draft', 'posted')) THEN
    RAISE EXCEPTION 'El bien tiene depreciaciones: no cambian su costo, residual, vida útil, '
      'inicio ni categoría'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_fixed_assets_depreciated';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER fixed_assets_guard BEFORE UPDATE ON accounting.fixed_assets
  FOR EACH ROW EXECUTE FUNCTION accounting.fixed_assets_guard();

-- Valores por ejercicio (D-066): se escriben al cerrar y no cambian más.
CREATE FUNCTION accounting.reject_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'En %.% no se modifica nada', TG_TABLE_SCHEMA, TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation',
          CONSTRAINT = 'trg_' || TG_TABLE_NAME || '_immutable';
END $$;

CREATE TRIGGER asset_year_values_immutable BEFORE UPDATE ON accounting.asset_year_values
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_update();

-- Nada de la 3B se borra (las líneas de una plantilla sí se reemplazan al editarla).
CREATE TRIGGER asset_categories_no_delete BEFORE DELETE ON accounting.asset_categories
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER fixed_assets_no_delete BEFORE DELETE ON accounting.fixed_assets
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER depreciation_runs_no_delete BEFORE DELETE ON accounting.depreciation_runs
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER asset_year_values_no_delete BEFORE DELETE ON accounting.asset_year_values
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER cost_centers_no_delete BEFORE DELETE ON accounting.cost_centers
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER recurring_templates_no_delete BEFORE DELETE ON accounting.recurring_templates
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER recurring_generations_no_delete BEFORE DELETE
  ON accounting.recurring_generations
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER asset_categories_no_truncate BEFORE TRUNCATE ON accounting.asset_categories
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER fixed_assets_no_truncate BEFORE TRUNCATE ON accounting.fixed_assets
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER depreciation_runs_no_truncate BEFORE TRUNCATE ON accounting.depreciation_runs
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER depreciation_items_no_truncate BEFORE TRUNCATE ON accounting.depreciation_items
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER asset_year_values_no_truncate BEFORE TRUNCATE ON accounting.asset_year_values
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER cost_centers_no_truncate BEFORE TRUNCATE ON accounting.cost_centers
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER recurring_templates_no_truncate BEFORE TRUNCATE
  ON accounting.recurring_templates
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER recurring_generations_no_truncate BEFORE TRUNCATE
  ON accounting.recurring_generations
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
"""

# Copias congeladas de las funciones de la 0003 que esta migración reemplaza: el downgrade
# las restaura tal cual (una prueba verifica que coinciden con el texto de la 0003).
JOURNAL_ENTRIES_GUARD_0003 = r"""
CREATE OR REPLACE FUNCTION accounting.journal_entries_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_year accounting.fiscal_years%ROWTYPE;
  v_period_status text;
  v_lines integer;
  v_debit numeric;
  v_credit numeric;
  v_postable boolean;
  v_original accounting.journal_entries%ROWTYPE;
  v_voided timestamptz;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un asiento no se borra: se descarta (borrador) o se revierte'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_no_delete';
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' OR NEW.number IS NOT NULL THEN
      RAISE EXCEPTION 'Un asiento nace como borrador y sin número'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_insert_draft';
    END IF;
  ELSE
    IF OLD.status IN ('reversed', 'discarded') THEN
      RAISE EXCEPTION 'El asiento % está %: es definitivo',
        coalesce(OLD.number::text, OLD.id::text), OLD.status
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_final';
    END IF;
    IF OLD.status = 'posted' THEN
      IF NEW.status <> 'reversed'
         OR (to_jsonb(NEW) - 'status' - 'updated_at') <> (to_jsonb(OLD) - 'status' - 'updated_at')
      THEN
        RAISE EXCEPTION 'El asiento N° % está contabilizado: no se modifica, se revierte',
          OLD.number
          USING ERRCODE = 'integrity_constraint_violation',
                CONSTRAINT = 'trg_journal_entries_posted_immutable';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM accounting.journal_entries
                     WHERE reverses_entry_id = OLD.id AND status = 'posted') THEN
        RAISE EXCEPTION 'El asiento N° % solo pasa a revertido con su reversión contabilizada',
          OLD.number
          USING ERRCODE = 'integrity_constraint_violation',
                CONSTRAINT = 'trg_journal_entries_reversal_missing';
      END IF;
      RETURN NEW;
    END IF;
    -- OLD.status = 'draft'
    IF NEW.status = 'reversed' THEN
      RAISE EXCEPTION 'Un borrador no se revierte: se descarta'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_final';
    END IF;
  END IF;

  -- Alta o cambio de un borrador, descarte o contabilización: la fecha cae en el ejercicio.
  SELECT * INTO v_year FROM accounting.fiscal_years WHERE id = NEW.fiscal_year_id;
  IF NEW.entry_date < v_year.start_date OR NEW.entry_date > v_year.end_date THEN
    RAISE EXCEPTION 'La fecha % está fuera del ejercicio % - %',
      NEW.entry_date, v_year.start_date, v_year.end_date
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_date_outside_year';
  END IF;
  IF NEW.status <> 'posted' THEN
    RETURN NEW;
  END IF;

  -- draft → posted.
  IF NEW.number IS NOT NULL THEN
    RAISE EXCEPTION 'El número del asiento lo asigna la base al contabilizar'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_number_assigned';
  END IF;
  IF v_year.status <> 'open' THEN
    RAISE EXCEPTION 'El ejercicio % - % está cerrado', v_year.start_date, v_year.end_date
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_year_closed';
  END IF;

  SELECT count(*), coalesce(sum(l.debit), 0), coalesce(sum(l.credit), 0),
         coalesce(bool_and(a.is_postable AND a.archived_at IS NULL), true)
    INTO v_lines, v_debit, v_credit, v_postable
    FROM accounting.journal_lines l
    JOIN accounting.ledger_accounts a ON a.id = l.account_id
   WHERE l.entry_id = NEW.id;
  IF v_lines < 2 THEN
    RAISE EXCEPTION 'Un asiento se contabiliza con al menos dos líneas (tiene %)', v_lines
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_min_lines';
  END IF;
  IF v_debit <> v_credit OR v_debit = 0 THEN
    RAISE EXCEPTION 'El asiento no balancea: debe % y haber %', v_debit, v_credit
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_unbalanced';
  END IF;
  IF NOT v_postable THEN
    RAISE EXCEPTION 'El asiento usa una cuenta agrupadora o archivada'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_account_not_postable';
  END IF;

  IF NEW.kind = 'closing' THEN
    -- La refundición la genera el cierre del ejercicio antes de marcarlo cerrado: va al
    -- último día y con todos los períodos ya cerrados. Es la única excepción a la regla
    -- del período abierto.
    IF NEW.entry_date <> v_year.end_date OR EXISTS (
         SELECT 1 FROM accounting.periods
          WHERE fiscal_year_id = NEW.fiscal_year_id AND status = 'open') THEN
      RAISE EXCEPTION 'La refundición va al último día del ejercicio, con sus períodos cerrados'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_closing_invalid';
    END IF;
  ELSE
    SELECT status INTO v_period_status FROM accounting.periods
     WHERE fiscal_year_id = NEW.fiscal_year_id
       AND NEW.entry_date BETWEEN start_date AND end_date
     FOR SHARE;
    IF v_period_status IS DISTINCT FROM 'open' THEN
      RAISE EXCEPTION 'El período de la fecha % está cerrado', NEW.entry_date
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_period_closed';
    END IF;
  END IF;

  IF NEW.kind = 'reversal' THEN
    SELECT * INTO v_original FROM accounting.journal_entries
     WHERE id = NEW.reverses_entry_id FOR UPDATE;
    IF v_original.status <> 'posted' OR v_original.kind NOT IN ('manual', 'finance') THEN
      RAISE EXCEPTION 'Solo se revierte un asiento manual o de finanzas contabilizado'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_reversal_invalid';
    END IF;
    -- Las líneas de la reversión son exactamente las del original con el debe y el haber
    -- intercambiados (comparación de multiconjuntos en los dos sentidos).
    IF EXISTS (
         (SELECT account_id, credit AS debit, debit AS credit FROM accounting.journal_lines
           WHERE entry_id = NEW.reverses_entry_id
          EXCEPT ALL
          SELECT account_id, debit, credit FROM accounting.journal_lines WHERE entry_id = NEW.id)
         UNION ALL
         (SELECT account_id, debit, credit FROM accounting.journal_lines WHERE entry_id = NEW.id
          EXCEPT ALL
          SELECT account_id, credit, debit FROM accounting.journal_lines
           WHERE entry_id = NEW.reverses_entry_id)) THEN
      RAISE EXCEPTION 'Las líneas de la reversión no son las del asiento original invertidas'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_reversal_mismatch';
    END IF;
  END IF;

  IF NEW.source_transaction_id IS NOT NULL THEN
    SELECT voided_at INTO v_voided FROM finance.transactions
     WHERE id = NEW.source_transaction_id FOR SHARE;
    IF v_voided IS NOT NULL THEN
      RAISE EXCEPTION 'El movimiento de finanzas de origen está anulado'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_entries_source_voided';
    END IF;
  END IF;

  UPDATE accounting.fiscal_years SET last_entry_number = last_entry_number + 1
   WHERE id = NEW.fiscal_year_id
  RETURNING last_entry_number INTO NEW.number;
  RETURN NEW;
END $$;
"""

JOURNAL_LINES_GUARD_0003 = r"""
CREATE OR REPLACE FUNCTION accounting.journal_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
  v_postable boolean;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT status INTO v_status FROM accounting.journal_entries
     WHERE id = OLD.entry_id FOR SHARE;
    IF v_status <> 'draft' THEN
      RAISE EXCEPTION 'Las líneas de un asiento % no se modifican', v_status
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_journal_lines_entry_not_draft';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  SELECT status INTO v_status FROM accounting.journal_entries WHERE id = NEW.entry_id FOR SHARE;
  IF v_status <> 'draft' THEN
    RAISE EXCEPTION 'Las líneas de un asiento % no se modifican', v_status
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_lines_entry_not_draft';
  END IF;
  SELECT is_postable AND archived_at IS NULL INTO v_postable
    FROM accounting.ledger_accounts WHERE id = NEW.account_id;
  IF NOT coalesce(v_postable, true) THEN
    RAISE EXCEPTION 'La cuenta de la línea % es agrupadora o está archivada', NEW.line_no
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_lines_account_not_postable';
  END IF;
  RETURN NEW;
END $$;
"""

DROP_3B_TRIGGERS_SQL = """
DROP TRIGGER journal_entries_sync_links ON accounting.journal_entries;
DROP FUNCTION accounting.journal_entries_sync_links();
"""


def downgrade() -> None:
    # Lo que la 0003 no puede representar hace fallar el downgrade en lugar de perderse en
    # silencio: asientos de los tipos nuevos y líneas con centro de costos. El resto de la
    # 3B (categorías, bienes sin asientos, centros, plantillas) se borra con sus tablas.
    bind = op.get_bind()
    entries = bind.execute(
        sa.text(
            "SELECT count(*) FROM accounting.journal_entries"
            " WHERE kind IN ('depreciation', 'disposal', 'recurring')"
        )
    ).scalar_one()
    lines = bind.execute(
        sa.text("SELECT count(*) FROM accounting.journal_lines WHERE cost_center_id IS NOT NULL")
    ).scalar_one()
    if entries or lines:
        raise RuntimeError(
            "No se puede volver a la 0003: hay "
            f"{entries} asientos de depreciación, baja o recurrentes y {lines} líneas con"
            " centro de costos, que la 0003 no admite."
        )
    op.execute(DROP_3B_TRIGGERS_SQL)
    op.execute(JOURNAL_ENTRIES_GUARD_0003)
    op.execute(JOURNAL_LINES_GUARD_0003)
    op.drop_constraint(
        op.f("ck_settings_start_rule_valid"), "settings", schema="accounting", type_="check"
    )
    op.drop_constraint(
        op.f("ck_journal_entries_kind_valid"), "journal_entries", schema="accounting", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_journal_entries_kind_valid"), "journal_entries", KINDS_0003, schema="accounting"
    )
    # DROP TABLE no dispara los triggers de borrado: caen con sus tablas (y sus funciones
    # exclusivas, después).
    op.drop_constraint(
        op.f("fk_settings_asset_disposal_account_id_ledger_accounts"),
        "settings",
        schema="accounting",
        type_="foreignkey",
    )
    op.drop_column("settings", "default_asset_start_rule", schema="accounting")
    op.drop_column("settings", "cost_centers_required", schema="accounting")
    op.drop_column("settings", "asset_disposal_account_id", schema="accounting")
    op.drop_constraint(
        op.f("fk_journal_lines_cost_center_id_cost_centers"),
        "journal_lines",
        schema="accounting",
        type_="foreignkey",
    )
    op.drop_column("journal_lines", "cost_center_id", schema="accounting")
    op.alter_column(
        "journal_entries",
        "kind",
        existing_type=sa.String(length=12),
        type_=sa.VARCHAR(length=10),
        existing_nullable=False,
        schema="accounting",
    )
    op.drop_index(
        "ix_depreciation_items_asset", table_name="depreciation_items", schema="accounting"
    )
    op.drop_table("depreciation_items", schema="accounting")
    op.drop_table("asset_year_values", schema="accounting")
    op.drop_index(
        "uq_recurring_generations_live",
        table_name="recurring_generations",
        schema="accounting",
        postgresql_where=sa.text("entry_status IN ('draft', 'posted')"),
    )
    op.drop_table("recurring_generations", schema="accounting")
    op.drop_index("ix_fixed_assets_org_status", table_name="fixed_assets", schema="accounting")
    op.drop_table("fixed_assets", schema="accounting")
    op.drop_index(
        "uq_depreciation_runs_live_period",
        table_name="depreciation_runs",
        schema="accounting",
        postgresql_where=sa.text("entry_status IN ('draft', 'posted')"),
    )
    op.drop_table("depreciation_runs", schema="accounting")
    op.drop_table("recurring_template_lines", schema="accounting")
    op.drop_table("asset_categories", schema="accounting")
    op.drop_table("recurring_templates", schema="accounting")
    op.drop_table("cost_centers", schema="accounting")
    op.drop_constraint(
        op.f("uq_periods_id_organization_id"), "periods", schema="accounting", type_="unique"
    )
    op.execute(
        "DROP FUNCTION accounting.reject_update();"
        " DROP FUNCTION accounting.fixed_assets_guard();"
        " DROP FUNCTION accounting.depreciation_items_guard();"
        " DROP FUNCTION accounting.entry_links_guard();"
    )
