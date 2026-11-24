"""Contabilidad (núcleo): plan de cuentas, ejercicios y períodos, asientos de partida doble
y su protección en la base (esquema `accounting`).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24

Especificación: docs/specs/FASE3_CONTABILIDAD.md (D-035 a D-043). Además de las tablas:
- `btree_gist` para impedir ejercicios superpuestos (`EXCLUDE USING gist`). Viene con
  PostgreSQL (`contrib`) en la imagen de Docker de desarrollo y en el zip oficial de
  binarios para Windows; es una extensión *trusted*, así que la puede crear el dueño de la
  base sin ser superusuario.
- Triggers en PL/pgSQL (`ACCOUNTING_TRIGGERS_SQL`): la base es la última defensa de
  BR-ACC-01/02/03 (inmutabilidad de lo contabilizado, balance, períodos cerrados) y de la
  numeración correlativa sin huecos (D-040), que asigna el propio trigger.
- En `finance`: `UNIQUE (id, kind)` y `UNIQUE (id, organization_id)` en contextos,
  `UNIQUE (id, context_id)` en movimientos (destinos de las claves foráneas compuestas de
  los asientos, D-035, D-044) y `ledger_account_id` en cuentas y categorías (D-041).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copia congelada de lo que agrega esta migración al catálogo (`app/core/permissions.py`,
# D-031): una migración no importa el catálogo vivo. Una prueba verifica catálogo = base.
ACCOUNTING_PERMISSIONS: dict[str, str] = {
    "accounting.read": "Ver la contabilidad: plan de cuentas, asientos y reportes",
    "accounting.manage": "Editar el plan de cuentas, preparar borradores de asientos y "
    "asignar cuentas contables en finanzas",
    "accounting.post": "Contabilizar y revertir asientos, cerrar y reabrir períodos, cerrar el "
    "ejercicio y validar el plan de cuentas",
}
# D-043: el administrador gestiona pero no contabiliza ni cierra.
ACCOUNTING_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": ("accounting.read", "accounting.manage", "accounting.post"),
    "admin": ("accounting.read", "accounting.manage"),
    "accountant": ("accounting.read", "accounting.manage", "accounting.post"),
    "viewer": ("accounting.read",),
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE SCHEMA IF NOT EXISTS accounting")

    # Destinos de las claves foráneas compuestas de los asientos (D-035, D-044). Van antes
    # que las tablas que los referencian.
    op.create_unique_constraint(
        op.f("uq_contexts_id_kind"), "contexts", ["id", "kind"], schema="finance"
    )
    op.create_unique_constraint(
        op.f("uq_contexts_id_organization_id"),
        "contexts",
        ["id", "organization_id"],
        schema="finance",
    )
    op.create_unique_constraint(
        op.f("uq_transactions_id_context_id"),
        "transactions",
        ["id", "context_id"],
        schema="finance",
    )

    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("normal_side", sa.String(length=6), nullable=False),
        sa.Column("is_postable", sa.Boolean(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("origin", sa.String(length=12), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
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
            "code ~ '^[0-9]+(\\.[0-9]+)*$'", name=op.f("ck_ledger_accounts_code_format")
        ),
        sa.CheckConstraint(
            "kind IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name=op.f("ck_ledger_accounts_kind_valid"),
        ),
        sa.CheckConstraint(
            "normal_side IN ('debit', 'credit')", name=op.f("ck_ledger_accounts_normal_side_valid")
        ),
        sa.CheckConstraint(
            "origin IN ('rg49_2014', 'proposed', 'user')",
            name=op.f("ck_ledger_accounts_origin_valid"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0", name=op.f("ck_ledger_accounts_name_not_blank")
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_ledger_accounts_not_own_parent")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_ledger_accounts_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_ledger_accounts_parent_id_ledger_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_accounts")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_ledger_accounts_id_organization_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "code", name=op.f("uq_ledger_accounts_organization_id_code")
        ),
        schema="accounting",
    )
    op.create_index(
        "ix_ledger_accounts_parent",
        "ledger_accounts",
        ["parent_id"],
        unique=False,
        schema="accounting",
    )
    op.create_table(
        "settings",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("chart_status", sa.String(length=10), server_default="none", nullable=False),
        sa.Column("chart_validated_by_name", sa.String(length=150), nullable=True),
        sa.Column("chart_validated_reference", sa.String(length=100), nullable=True),
        sa.Column("chart_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retained_earnings_account_id", sa.UUID(), nullable=True),
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
            "(chart_status = 'validated') = (chart_validated_by_name IS NOT NULL) AND (chart_status = 'validated') = (chart_validated_reference IS NOT NULL) AND (chart_status = 'validated') = (chart_validated_at IS NOT NULL)",
            name=op.f("ck_settings_chart_validation_complete"),
        ),
        sa.CheckConstraint(
            "chart_status IN ('none', 'pending', 'validated')",
            name=op.f("ck_settings_chart_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_settings_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["retained_earnings_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_retained_earnings_account_id_ledger_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_settings_organization_id")),
        schema="accounting",
    )
    op.create_table(
        "fiscal_years",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.UUID(), nullable=True),
        sa.Column("closing_entry_id", sa.UUID(), nullable=True),
        sa.Column("last_entry_number", sa.Integer(), server_default="0", nullable=False),
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
        postgresql.ExcludeConstraint(
            (sa.column("organization_id"), "="),
            (sa.text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            name="ex_fiscal_years_no_overlap",
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL) AND (status = 'closed') = (closed_by IS NOT NULL)",
            name=op.f("ck_fiscal_years_closed_complete"),
        ),
        sa.CheckConstraint(
            "closing_entry_id IS NULL OR status = 'closed'",
            name=op.f("ck_fiscal_years_closing_entry_when_closed"),
        ),
        sa.CheckConstraint(
            "end_date < (start_date + interval '1 year')::date",
            name=op.f("ck_fiscal_years_at_most_one_year"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed')", name=op.f("ck_fiscal_years_status_valid")
        ),
        sa.CheckConstraint("end_date > start_date", name=op.f("ck_fiscal_years_dates_ordered")),
        sa.CheckConstraint(
            "last_entry_number >= 0", name=op.f("ck_fiscal_years_last_entry_number_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"], ["core.users.id"], name=op.f("fk_fiscal_years_closed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_fiscal_years_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fiscal_years")),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_fiscal_years_id_organization_id")
        ),
        schema="accounting",
    )
    op.create_table(
        "periods",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("fiscal_year_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.UUID(), nullable=True),
        sa.Column("reopen_reason", sa.String(length=300), nullable=True),
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
            "(status = 'closed') = (closed_at IS NOT NULL) AND (status = 'closed') = (closed_by IS NOT NULL)",
            name=op.f("ck_periods_closed_complete"),
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_periods_status_valid")),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_periods_dates_ordered")),
        sa.CheckConstraint(
            "reopen_reason IS NULL OR char_length(btrim(reopen_reason)) >= 3",
            name=op.f("ck_periods_reopen_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"], ["core.users.id"], name=op.f("fk_periods_closed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_year_id", "organization_id"],
            ["accounting.fiscal_years.id", "accounting.fiscal_years.organization_id"],
            name=op.f("fk_periods_fiscal_year_id_fiscal_years"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_periods_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_periods")),
        sa.UniqueConstraint(
            "fiscal_year_id", "start_date", name=op.f("uq_periods_fiscal_year_id_start_date")
        ),
        schema="accounting",
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("fiscal_year_id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="draft", nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("document_reference", sa.String(length=100), nullable=True),
        sa.Column("reverses_entry_id", sa.UUID(), nullable=True),
        sa.Column("source_transaction_id", sa.UUID(), nullable=True),
        sa.Column("source_context_id", sa.UUID(), nullable=True),
        sa.Column("source_context_kind", sa.String(length=10), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("posted_by", sa.UUID(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_by", sa.UUID(), nullable=True),
        sa.Column("discard_reason", sa.String(length=300), nullable=True),
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
            "(kind = 'finance') = (source_transaction_id IS NOT NULL)",
            name=op.f("ck_journal_entries_finance_has_source"),
        ),
        sa.CheckConstraint(
            "(kind = 'reversal') = (reverses_entry_id IS NOT NULL)",
            name=op.f("ck_journal_entries_reversal_has_original"),
        ),
        sa.CheckConstraint(
            "(number IS NULL) = (status IN ('draft', 'discarded'))",
            name=op.f("ck_journal_entries_number_when_posted"),
        ),
        sa.CheckConstraint(
            "(status = 'discarded') = (discarded_at IS NOT NULL) AND (status = 'discarded') = (discarded_by IS NOT NULL) AND (status = 'discarded') = (discard_reason IS NOT NULL)",
            name=op.f("ck_journal_entries_discarded_complete"),
        ),
        sa.CheckConstraint(
            "(status IN ('posted', 'reversed')) = (posted_at IS NOT NULL) AND (status IN ('posted', 'reversed')) = (posted_by IS NOT NULL)",
            name=op.f("ck_journal_entries_posted_complete"),
        ),
        sa.CheckConstraint(
            "kind IN ('manual', 'finance', 'reversal', 'closing')",
            name=op.f("ck_journal_entries_kind_valid"),
        ),
        sa.CheckConstraint(
            "source_context_kind IS NULL OR source_context_kind = 'business'",
            name=op.f("ck_journal_entries_source_business_only"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'posted', 'reversed', 'discarded')",
            name=op.f("ck_journal_entries_status_valid"),
        ),
        sa.CheckConstraint(
            "(source_transaction_id IS NULL) = (source_context_id IS NULL) AND (source_transaction_id IS NULL) = (source_context_kind IS NULL)",
            name=op.f("ck_journal_entries_source_complete"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) > 0",
            name=op.f("ck_journal_entries_description_not_blank"),
        ),
        sa.CheckConstraint(
            "discard_reason IS NULL OR char_length(btrim(discard_reason)) >= 3",
            name=op.f("ck_journal_entries_discard_reason_length"),
        ),
        sa.CheckConstraint(
            "number IS NULL OR number > 0", name=op.f("ck_journal_entries_number_positive")
        ),
        sa.CheckConstraint(
            "reverses_entry_id IS NULL OR reverses_entry_id <> id",
            name=op.f("ck_journal_entries_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_journal_entries_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["discarded_by"], ["core.users.id"], name=op.f("fk_journal_entries_discarded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["fiscal_year_id", "organization_id"],
            ["accounting.fiscal_years.id", "accounting.fiscal_years.organization_id"],
            name=op.f("fk_journal_entries_fiscal_year_id_fiscal_years"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_journal_entries_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["posted_by"], ["core.users.id"], name=op.f("fk_journal_entries_posted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["reverses_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_journal_entries_reverses_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["source_context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_journal_entries_source_context_org_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["source_context_id", "source_context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_journal_entries_source_context_kind_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["source_transaction_id", "source_context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
            name=op.f("fk_journal_entries_source_transaction_id_transactions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.UniqueConstraint(
            "fiscal_year_id", "number", name=op.f("uq_journal_entries_fiscal_year_id_number")
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name=op.f("uq_journal_entries_id_organization_id")
        ),
        sa.UniqueConstraint("reverses_entry_id", name=op.f("uq_journal_entries_reverses_entry_id")),
        schema="accounting",
    )
    op.create_index(
        "ix_journal_entries_org_date_number",
        "journal_entries",
        ["organization_id", "entry_date", "number"],
        unique=False,
        schema="accounting",
    )
    op.create_index(
        "ix_journal_entries_year_status",
        "journal_entries",
        ["fiscal_year_id", "status"],
        unique=False,
        schema="accounting",
    )
    op.create_index(
        "uq_journal_entries_closing_per_year",
        "journal_entries",
        ["fiscal_year_id"],
        unique=True,
        schema="accounting",
        postgresql_where=sa.text("kind = 'closing' AND status IN ('draft', 'posted')"),
    )
    op.create_index(
        "uq_journal_entries_live_source",
        "journal_entries",
        ["source_transaction_id"],
        unique=True,
        schema="accounting",
        postgresql_where=sa.text("status IN ('draft', 'posted')"),
    )
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("debit", sa.Numeric(precision=18, scale=2), server_default="0", nullable=False),
        sa.Column("credit", sa.Numeric(precision=18, scale=2), server_default="0", nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("fx_currency", sa.CHAR(length=3), nullable=True),
        sa.Column("fx_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=True),
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
            name=op.f("ck_journal_lines_fx_currency_valid"),
        ),
        sa.CheckConstraint(
            "(debit > 0) <> (credit > 0)", name=op.f("ck_journal_lines_debit_xor_credit")
        ),
        sa.CheckConstraint(
            "(fx_currency IS NULL) = (fx_amount IS NULL) AND (fx_currency IS NULL) = (fx_rate IS NULL)",
            name=op.f("ck_journal_lines_fx_complete"),
        ),
        sa.CheckConstraint(
            "debit = trunc(debit) AND credit = trunc(credit)",
            name=op.f("ck_journal_lines_pyg_integer"),
        ),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0", name=op.f("ck_journal_lines_amounts_non_negative")
        ),
        sa.CheckConstraint(
            "fx_amount IS NULL OR fx_amount > 0", name=op.f("ck_journal_lines_fx_amount_positive")
        ),
        sa.CheckConstraint(
            "fx_rate IS NULL OR fx_rate > 0", name=op.f("ck_journal_lines_fx_rate_positive")
        ),
        sa.CheckConstraint("line_no > 0", name=op.f("ck_journal_lines_line_no_positive")),
        sa.ForeignKeyConstraint(
            ["account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_journal_lines_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_journal_lines_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_journal_lines_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_lines")),
        sa.UniqueConstraint("entry_id", "line_no", name=op.f("uq_journal_lines_entry_id_line_no")),
        schema="accounting",
    )
    op.create_index(
        "ix_journal_lines_account_entry",
        "journal_lines",
        ["account_id", "entry_id"],
        unique=False,
        schema="accounting",
    )
    # Referencia circular ejercicio ↔ asiento de refundición: se agrega al final.
    op.create_foreign_key(
        "fk_fiscal_years_closing_entry_id_journal_entries",
        "fiscal_years",
        "journal_entries",
        ["closing_entry_id", "organization_id"],
        ["id", "organization_id"],
        source_schema="accounting",
        referent_schema="accounting",
    )

    # D-041: cuenta contable del banco o la caja, y de cada categoría.
    for table in ("accounts", "categories"):
        op.add_column(
            table, sa.Column("ledger_account_id", sa.UUID(), nullable=True), schema="finance"
        )
        op.create_foreign_key(
            op.f(f"fk_{table}_ledger_account_id_ledger_accounts"),
            table,
            "ledger_accounts",
            ["ledger_account_id"],
            ["id"],
            source_schema="finance",
            referent_schema="accounting",
        )

    op.execute(ACCOUNTING_TRIGGERS_SQL)
    _seed_permissions()


ACCOUNTING_TRIGGERS_SQL = r"""
-- Todas las violaciones usan SQLSTATE 23000 (integrity_constraint_violation) y un nombre
-- estable en CONSTRAINT (`trg_*`): el servicio y las pruebas las reconocen por ese nombre.

-- Plan de cuentas: el código del hijo extiende el del padre, el padre es agrupador y una
-- cuenta con líneas no cambia de código, tipo, naturaleza ni imputabilidad (BR-ACC-09).
CREATE FUNCTION accounting.ledger_accounts_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_parent accounting.ledger_accounts%ROWTYPE;
BEGIN
  IF NEW.parent_id IS NOT NULL AND (TG_OP = 'INSERT'
      OR NEW.parent_id IS DISTINCT FROM OLD.parent_id OR NEW.code <> OLD.code) THEN
    SELECT * INTO v_parent FROM accounting.ledger_accounts WHERE id = NEW.parent_id;
    IF left(NEW.code, length(v_parent.code) + 1) <> v_parent.code || '.' THEN
      RAISE EXCEPTION 'El código % no es hijo del código % de su cuenta padre',
        NEW.code, v_parent.code
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_ledger_accounts_parent_prefix';
    END IF;
    IF v_parent.is_postable THEN
      RAISE EXCEPTION 'La cuenta padre % es imputable: solo una agrupadora tiene hijas',
        v_parent.code
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_ledger_accounts_parent_postable';
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF (NEW.code, NEW.kind, NEW.normal_side, NEW.is_postable)
         IS DISTINCT FROM (OLD.code, OLD.kind, OLD.normal_side, OLD.is_postable)
       AND EXISTS (SELECT 1 FROM accounting.journal_lines WHERE account_id = OLD.id) THEN
      RAISE EXCEPTION 'La cuenta % tiene líneas de asiento: no cambia de código, tipo, '
        'naturaleza ni imputabilidad', OLD.code
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_ledger_accounts_in_use';
    END IF;
    IF NEW.code <> OLD.code
       AND EXISTS (SELECT 1 FROM accounting.ledger_accounts WHERE parent_id = OLD.id) THEN
      RAISE EXCEPTION 'La cuenta % tiene cuentas hijas: no cambia de código', OLD.code
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_ledger_accounts_has_children';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER ledger_accounts_guard BEFORE INSERT OR UPDATE ON accounting.ledger_accounts
  FOR EACH ROW EXECUTE FUNCTION accounting.ledger_accounts_guard();

-- Rechazo genérico del borrado (por fila) y del TRUNCATE de las tablas contables.
CREATE FUNCTION accounting.reject_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'En %.% no se borra nada (operación %)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'integrity_constraint_violation',
          CONSTRAINT = 'trg_' || TG_TABLE_NAME || '_no_delete';
END $$;

-- Ejercicios: las fechas no cambian, la numeración no retrocede y un ejercicio cerrado es
-- definitivo (D-039).
CREATE FUNCTION accounting.fiscal_years_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'closed' THEN
    RAISE EXCEPTION 'El ejercicio % - % está cerrado y no se modifica',
      OLD.start_date, OLD.end_date
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_fiscal_years_closed_final';
  END IF;
  IF (NEW.start_date, NEW.end_date, NEW.organization_id)
       IS DISTINCT FROM (OLD.start_date, OLD.end_date, OLD.organization_id) THEN
    RAISE EXCEPTION 'Las fechas de un ejercicio no cambian'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_fiscal_years_dates_fixed';
  END IF;
  IF NEW.last_entry_number < OLD.last_entry_number THEN
    RAISE EXCEPTION 'La numeración de asientos no retrocede'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_fiscal_years_numbering';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER fiscal_years_guard BEFORE UPDATE ON accounting.fiscal_years
  FOR EACH ROW EXECUTE FUNCTION accounting.fiscal_years_guard();

-- Períodos: fechas fijas; los de un ejercicio cerrado no se reabren ni se tocan.
CREATE FUNCTION accounting.periods_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.start_date, NEW.end_date, NEW.fiscal_year_id, NEW.organization_id)
       IS DISTINCT FROM (OLD.start_date, OLD.end_date, OLD.fiscal_year_id, OLD.organization_id)
  THEN
    RAISE EXCEPTION 'Las fechas de un período no cambian'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_periods_dates_fixed';
  END IF;
  IF EXISTS (SELECT 1 FROM accounting.fiscal_years
             WHERE id = OLD.fiscal_year_id AND status = 'closed') THEN
    RAISE EXCEPTION 'El período % - % es de un ejercicio cerrado', OLD.start_date, OLD.end_date
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_periods_year_closed';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER periods_guard BEFORE UPDATE ON accounting.periods
  FOR EACH ROW EXECUTE FUNCTION accounting.periods_guard();

-- Asientos (D-040, BR-ACC-01/02/03):
-- * nacen como borrador y sin número;
-- * un borrador cambia libremente y pasa a `posted` o `discarded`;
-- * al contabilizar se valida todo y el número lo asigna este trigger, incrementando
--   `fiscal_years.last_entry_number` (la fila del ejercicio queda bloqueada hasta el COMMIT:
--   dos contabilizaciones del mismo ejercicio se serializan y no hay huecos ni repetidos);
-- * de `posted` solo se pasa a `reversed`, sin tocar otra columna, y solo si existe la
--   reversión contabilizada; `reversed` y `discarded` son finales;
-- * nunca se borra.
CREATE FUNCTION accounting.journal_entries_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER journal_entries_guard BEFORE INSERT OR UPDATE OR DELETE
  ON accounting.journal_entries
  FOR EACH ROW EXECUTE FUNCTION accounting.journal_entries_guard();

-- Líneas: solo se agregan, cambian o quitan mientras el asiento es borrador, y solo con
-- cuentas imputables y no archivadas. FOR SHARE espera a una contabilización en curso del
-- mismo asiento y relee su estado.
CREATE FUNCTION accounting.journal_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER journal_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting.journal_lines
  FOR EACH ROW EXECUTE FUNCTION accounting.journal_lines_guard();

-- Ejercicios y períodos no se borran; ninguna tabla contable se vacía con TRUNCATE.
CREATE TRIGGER fiscal_years_no_delete BEFORE DELETE ON accounting.fiscal_years
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER periods_no_delete BEFORE DELETE ON accounting.periods
  FOR EACH ROW EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER journal_entries_no_truncate BEFORE TRUNCATE ON accounting.journal_entries
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER journal_lines_no_truncate BEFORE TRUNCATE ON accounting.journal_lines
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER fiscal_years_no_truncate BEFORE TRUNCATE ON accounting.fiscal_years
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
CREATE TRIGGER periods_no_truncate BEFORE TRUNCATE ON accounting.periods
  FOR EACH STATEMENT EXECUTE FUNCTION accounting.reject_delete();
"""


def _seed_permissions() -> None:
    bind = op.get_bind()
    for code, description in ACCOUNTING_PERMISSIONS.items():
        bind.execute(
            sa.text(
                "INSERT INTO core.permissions (code, description) VALUES (:code, :description)"
            ),
            {"code": code, "description": description},
        )
    for role, codes in ACCOUNTING_ROLE_PERMISSIONS.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO core.role_permissions (role_code, permission_code)"
                    " VALUES (:role, :code)"
                ),
                {"role": role, "code": code},
            )


def downgrade() -> None:
    # Destructivo: elimina toda la contabilidad. Solo para desarrollo. La extensión
    # btree_gist se deja instalada: pudo existir antes de esta migración.
    op.execute(
        "DELETE FROM core.role_permissions WHERE permission_code LIKE 'accounting.%';"
        " DELETE FROM core.permissions WHERE code LIKE 'accounting.%';"
    )
    for table in ("categories", "accounts"):
        op.drop_constraint(
            op.f(f"fk_{table}_ledger_account_id_ledger_accounts"),
            table,
            schema="finance",
            type_="foreignkey",
        )
        op.drop_column(table, "ledger_account_id", schema="finance")
    op.drop_constraint(
        "fk_fiscal_years_closing_entry_id_journal_entries",
        "fiscal_years",
        schema="accounting",
        type_="foreignkey",
    )
    # DROP TABLE no dispara los triggers de borrado: caen con sus tablas.
    op.drop_index("ix_journal_lines_account_entry", table_name="journal_lines", schema="accounting")
    op.drop_table("journal_lines", schema="accounting")
    op.drop_index(
        "uq_journal_entries_live_source",
        table_name="journal_entries",
        schema="accounting",
        postgresql_where=sa.text("status IN ('draft', 'posted')"),
    )
    op.drop_index(
        "uq_journal_entries_closing_per_year",
        table_name="journal_entries",
        schema="accounting",
        postgresql_where=sa.text("kind = 'closing' AND status IN ('draft', 'posted')"),
    )
    op.drop_index(
        "ix_journal_entries_year_status", table_name="journal_entries", schema="accounting"
    )
    op.drop_index(
        "ix_journal_entries_org_date_number", table_name="journal_entries", schema="accounting"
    )
    op.drop_table("journal_entries", schema="accounting")
    op.drop_table("periods", schema="accounting")
    op.drop_table("fiscal_years", schema="accounting")
    op.drop_table("settings", schema="accounting")
    op.drop_index("ix_ledger_accounts_parent", table_name="ledger_accounts", schema="accounting")
    op.drop_table("ledger_accounts", schema="accounting")
    op.execute(
        "DROP FUNCTION accounting.journal_lines_guard();"
        " DROP FUNCTION accounting.journal_entries_guard();"
        " DROP FUNCTION accounting.periods_guard();"
        " DROP FUNCTION accounting.fiscal_years_guard();"
        " DROP FUNCTION accounting.reject_delete();"
        " DROP FUNCTION accounting.ledger_accounts_guard();"
        " DROP SCHEMA accounting;"
    )
    op.drop_constraint(
        op.f("uq_transactions_id_context_id"), "transactions", schema="finance", type_="unique"
    )
    op.drop_constraint(
        op.f("uq_contexts_id_organization_id"), "contexts", schema="finance", type_="unique"
    )
    op.drop_constraint(op.f("uq_contexts_id_kind"), "contexts", schema="finance", type_="unique")
