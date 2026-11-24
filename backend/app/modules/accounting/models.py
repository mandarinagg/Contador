"""Modelos del esquema `accounting` (migración 0003). Especificación: FASE3_CONTABILIDAD.md §2.

La contabilidad es de la organización (D-035): toda tabla lleva `organization_id`, las que
se referencian tienen `UNIQUE (id, organization_id)` y se referencian con claves foráneas
compuestas, así un asiento no puede usar una cuenta ni un ejercicio de otra organización.

Lo que no cabe en una restricción declarativa (inmutabilidad de lo contabilizado,
numeración correlativa, balance, períodos cerrados) lo imponen los triggers de la
migración 0003 (`ACCOUNTING_TRIGGERS_SQL`): la base es la última defensa (BR-ACC-01/02/03).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.modules.finance.money import CURRENCIES

SCHEMA = "accounting"
ACCOUNT_KINDS = ("asset", "liability", "equity", "income", "expense")
NORMAL_SIDES = ("debit", "credit")
ACCOUNT_ORIGINS = ("rg49_2014", "proposed", "user")
CHART_STATUSES = ("none", "pending", "validated")
YEAR_STATUSES = ("open", "closed")
ENTRY_STATUSES = ("draft", "posted", "reversed", "discarded")
# 3B (D-058, D-059, D-061): depreciación, baja de un bien y asiento recurrente.
ENTRY_KINDS = (
    "manual",
    "finance",
    "reversal",
    "closing",
    "depreciation",
    "disposal",
    "recurring",
)
START_RULES = ("next_month", "next_fiscal_year")
VALIDATION_STATUSES = ("pending", "validated")
ASSET_STATUSES = ("active", "disposed")
DISPOSAL_KINDS = ("sale", "scrap", "donation")
TEMPLATE_STATUSES = ("active", "paused")
# Estado de un asiento vivo: el que ocupa el lugar de una corrida o de una generación.
LIVE_ENTRY = "entry_status IN ('draft', 'posted')"
FX_CURRENCIES = tuple(c for c in CURRENCIES if c != "PYG")


def _in(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))


def _organization() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("core.organizations.id"), nullable=False)


# Importes en guaraníes (moneda funcional, D-036): NUMERIC(18,2) con CHECK de entero.
Money = Numeric(18, 2)


class LedgerAccount(TimestampMixin, Base):
    """Cuenta del plan de cuentas (D-037). Solo las imputables reciben líneas."""

    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint(r"code ~ '^[0-9]+(\.[0-9]+)*$'", name="code_format"),
        CheckConstraint(_in("kind", ACCOUNT_KINDS), name="kind_valid"),
        CheckConstraint(_in("normal_side", NORMAL_SIDES), name="normal_side_valid"),
        CheckConstraint(_in("origin", ACCOUNT_ORIGINS), name="origin_valid"),
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("id", "organization_id"),
        # El padre es de la misma organización.
        ForeignKeyConstraint(
            ["parent_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
        ),
        Index("ix_ledger_accounts_parent", "parent_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    normal_side: Mapped[str] = mapped_column(String(6), nullable=False)
    is_postable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    origin: Mapped[str] = mapped_column(String(12), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountingSettings(TimestampMixin, Base):
    """Configuración contable 1:1 con la organización (estado del plan, D-038).

    Va en una tabla propia del esquema `accounting` y no en `core.organizations` para que
    la cuenta de resultados se referencie con una clave foránea compuesta de la misma
    organización, sin que `core` dependa de `accounting`.
    """

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint(_in("chart_status", CHART_STATUSES), name="chart_status_valid"),
        # Los tres datos de la validación, si y solo si el plan está validado.
        CheckConstraint(
            "(chart_status = 'validated') = (chart_validated_by_name IS NOT NULL)"
            " AND (chart_status = 'validated') = (chart_validated_reference IS NOT NULL)"
            " AND (chart_status = 'validated') = (chart_validated_at IS NOT NULL)",
            name="chart_validation_complete",
        ),
        CheckConstraint(_in("default_asset_start_rule", START_RULES), name="start_rule_valid"),
        UniqueConstraint("organization_id"),
        ForeignKeyConstraint(
            ["retained_earnings_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
        ),
        # 3B (D-059): cuenta de resultado de la baja de bienes (por defecto, 17.01).
        ForeignKeyConstraint(
            ["asset_disposal_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    chart_status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="none")
    chart_validated_by_name: Mapped[str | None] = mapped_column(String(150))
    chart_validated_reference: Mapped[str | None] = mapped_column(String(100))
    chart_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retained_earnings_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # 3B: baja de bienes (D-059), centros obligatorios (D-060) e inicio por defecto (D-064).
    asset_disposal_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cost_centers_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    default_asset_start_rule: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="next_month"
    )


class FiscalYear(TimestampMixin, Base):
    """Ejercicio (D-039). `last_entry_number` lleva la numeración correlativa (D-040)."""

    __tablename__ = "fiscal_years"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="dates_ordered"),
        CheckConstraint(
            "end_date < (start_date + interval '1 year')::date", name="at_most_one_year"
        ),
        CheckConstraint(_in("status", YEAR_STATUSES), name="status_valid"),
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)"
            " AND (status = 'closed') = (closed_by IS NOT NULL)",
            name="closed_complete",
        ),
        CheckConstraint(
            "closing_entry_id IS NULL OR status = 'closed'", name="closing_entry_when_closed"
        ),
        CheckConstraint("last_entry_number >= 0", name="last_entry_number_non_negative"),
        UniqueConstraint("id", "organization_id"),
        # Dos ejercicios de la misma organización no se superponen (requiere btree_gist).
        ExcludeConstraint(
            (column("organization_id"), "="),
            (func.daterange(column("start_date"), column("end_date"), "[]"), "&&"),
            using="gist",
            name="ex_fiscal_years_no_overlap",
        ),
        ForeignKeyConstraint(
            ["closing_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            use_alter=True,
            name="fk_fiscal_years_closing_entry_id_journal_entries",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    closing_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # La incrementa el trigger al contabilizar: el ORM la relee, nunca la escribe.
    last_entry_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", server_onupdate=FetchedValue()
    )


class Period(TimestampMixin, Base):
    """Período mensual de un ejercicio. Cerrado = no se contabiliza ni revierte en él."""

    __tablename__ = "periods"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
        CheckConstraint(_in("status", YEAR_STATUSES), name="status_valid"),
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)"
            " AND (status = 'closed') = (closed_by IS NOT NULL)",
            name="closed_complete",
        ),
        CheckConstraint(
            "reopen_reason IS NULL OR char_length(btrim(reopen_reason)) >= 3",
            name="reopen_reason_length",
        ),
        UniqueConstraint("fiscal_year_id", "start_date"),
        # Destino de las claves foráneas compuestas de las corridas y generaciones (0004).
        UniqueConstraint("id", "organization_id"),
        ForeignKeyConstraint(
            ["fiscal_year_id", "organization_id"],
            ["accounting.fiscal_years.id", "accounting.fiscal_years.organization_id"],
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    reopen_reason: Mapped[str | None] = mapped_column(String(300))


class JournalEntry(TimestampMixin, Base):
    """Asiento (D-040): `draft` → `posted` → `reversed`, o `draft` → `discarded`."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(_in("status", ENTRY_STATUSES), name="status_valid"),
        CheckConstraint(_in("kind", ENTRY_KINDS), name="kind_valid"),
        CheckConstraint("char_length(btrim(description)) > 0", name="description_not_blank"),
        # Número, si y solo si está (o estuvo) contabilizado.
        CheckConstraint(
            "(number IS NULL) = (status IN ('draft', 'discarded'))", name="number_when_posted"
        ),
        CheckConstraint("number IS NULL OR number > 0", name="number_positive"),
        CheckConstraint(
            "(status IN ('posted', 'reversed')) = (posted_at IS NOT NULL)"
            " AND (status IN ('posted', 'reversed')) = (posted_by IS NOT NULL)",
            name="posted_complete",
        ),
        CheckConstraint(
            "(status = 'discarded') = (discarded_at IS NOT NULL)"
            " AND (status = 'discarded') = (discarded_by IS NOT NULL)"
            " AND (status = 'discarded') = (discard_reason IS NOT NULL)",
            name="discarded_complete",
        ),
        CheckConstraint(
            "discard_reason IS NULL OR char_length(btrim(discard_reason)) >= 3",
            name="discard_reason_length",
        ),
        CheckConstraint(
            "(kind = 'reversal') = (reverses_entry_id IS NOT NULL)", name="reversal_has_original"
        ),
        CheckConstraint("reverses_entry_id IS NULL OR reverses_entry_id <> id", name="not_self"),
        # D-035: el origen en finanzas va completo o no va, y solo puede ser empresarial.
        CheckConstraint(
            "(source_transaction_id IS NULL) = (source_context_id IS NULL)"
            " AND (source_transaction_id IS NULL) = (source_context_kind IS NULL)",
            name="source_complete",
        ),
        CheckConstraint(
            "source_context_kind IS NULL OR source_context_kind = 'business'",
            name="source_business_only",
        ),
        CheckConstraint(
            "(kind = 'finance') = (source_transaction_id IS NOT NULL)",
            name="finance_has_source",
        ),
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("fiscal_year_id", "number"),
        # Un asiento se revierte una sola vez.
        UniqueConstraint("reverses_entry_id"),
        ForeignKeyConstraint(
            ["fiscal_year_id", "organization_id"],
            ["accounting.fiscal_years.id", "accounting.fiscal_years.organization_id"],
        ),
        ForeignKeyConstraint(
            ["reverses_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
        ),
        # D-035: el movimiento es del contexto indicado, el contexto es de esa clase (que
        # solo puede ser 'business') y de la misma organización que el asiento.
        ForeignKeyConstraint(
            ["source_transaction_id", "source_context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
        ),
        ForeignKeyConstraint(
            ["source_context_id", "source_context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_journal_entries_source_context_kind_contexts",
        ),
        ForeignKeyConstraint(
            ["source_context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_journal_entries_source_context_org_contexts",
        ),
        # D-041: como máximo un asiento vivo por movimiento.
        Index(
            "uq_journal_entries_live_source",
            "source_transaction_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'posted')"),
        ),
        # Una sola refundición viva por ejercicio.
        Index(
            "uq_journal_entries_closing_per_year",
            "fiscal_year_id",
            unique=True,
            postgresql_where=text("kind = 'closing' AND status IN ('draft', 'posted')"),
        ),
        Index("ix_journal_entries_org_date_number", "organization_id", "entry_date", "number"),
        Index("ix_journal_entries_year_status", "fiscal_year_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Lo asigna el trigger al contabilizar (D-040): el ORM lo relee, nunca lo escribe.
    number: Mapped[int | None] = mapped_column(Integer, server_onupdate=FetchedValue())
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="draft")
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    document_reference: Mapped[str | None] = mapped_column(String(100))
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_context_kind: Mapped[str | None] = mapped_column(String(10))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)
    posted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discarded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    discard_reason: Mapped[str | None] = mapped_column(String(300))


class JournalLine(TimestampMixin, Base):
    """Línea de asiento: debe o haber en guaraníes; la moneda extranjera es informativa."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("line_no > 0", name="line_no_positive"),
        CheckConstraint("debit >= 0 AND credit >= 0", name="amounts_non_negative"),
        CheckConstraint("(debit > 0) <> (credit > 0)", name="debit_xor_credit"),
        CheckConstraint("debit = trunc(debit) AND credit = trunc(credit)", name="pyg_integer"),
        CheckConstraint(
            "(fx_currency IS NULL) = (fx_amount IS NULL)"
            " AND (fx_currency IS NULL) = (fx_rate IS NULL)",
            name="fx_complete",
        ),
        CheckConstraint(
            f"fx_currency IS NULL OR fx_currency IN ({', '.join(repr(c) for c in FX_CURRENCIES)})",
            name="fx_currency_valid",
        ),
        CheckConstraint("fx_amount IS NULL OR fx_amount > 0", name="fx_amount_positive"),
        CheckConstraint("fx_rate IS NULL OR fx_rate > 0", name="fx_rate_positive"),
        UniqueConstraint("entry_id", "line_no"),
        ForeignKeyConstraint(
            ["entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
        ),
        ForeignKeyConstraint(
            ["account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
        ),
        # D-060: el centro de costos es de la misma organización (y solo en cuentas de
        # resultado: lo impone el trigger de líneas).
        ForeignKeyConstraint(
            ["cost_center_id", "organization_id"],
            ["accounting.cost_centers.id", "accounting.cost_centers.organization_id"],
        ),
        Index("ix_journal_lines_account_entry", "account_id", "entry_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    credit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    description: Mapped[str | None] = mapped_column(String(300))
    fx_currency: Mapped[str | None] = mapped_column(CHAR(3))
    fx_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


# --- Fase 3B (migración 0004). Especificación: FASE3B_CONTABILIDAD.md §2 y §6 -------------


def _org_fk(columns: list[str], table: str, name: str | None = None) -> ForeignKeyConstraint:
    """Clave foránea compuesta `(x_id, organization_id)`: la fila es de la misma organización."""
    return ForeignKeyConstraint(
        [*columns, "organization_id"],
        [f"accounting.{table}.id", f"accounting.{table}.organization_id"],
        name=name,
    )


class AssetCategory(TimestampMixin, Base):
    """Categoría de activo fijo (D-056): vida útil, residual fiscal y las tres cuentas.

    Se carga a pedido desde las candidatas de la investigación (sin validar). Mientras le
    falte la vida útil, el porcentaje de residual o alguna cuenta, no se usa (el servicio
    responde 422 diciendo qué falta).
    """

    __tablename__ = "asset_categories"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "useful_life_months IS NULL OR useful_life_months > 0", name="useful_life_positive"
        ),
        # Ley 6380, art. 11: el residual fiscal no supera el 20 % del costo.
        CheckConstraint(
            "residual_rate IS NULL OR (residual_rate >= 0 AND residual_rate <= 20)",
            name="residual_rate_range",
        ),
        CheckConstraint(
            _in("validation_status", VALIDATION_STATUSES), name="validation_status_valid"
        ),
        CheckConstraint(
            "(validation_status = 'validated') = (validated_by_name IS NOT NULL)"
            " AND (validation_status = 'validated') = (validated_reference IS NOT NULL)"
            " AND (validation_status = 'validated') = (validated_at IS NOT NULL)",
            name="validation_complete",
        ),
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("organization_id", "code"),
        _org_fk(["asset_account_id"], "ledger_accounts"),
        _org_fk(["accumulated_account_id"], "ledger_accounts"),
        _org_fk(["expense_account_id"], "ledger_accounts"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    # Identificador de la candidata (`codigo` del YAML); NULL en las que crea la persona.
    code: Mapped[str | None] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    useful_life_months: Mapped[int | None] = mapped_column(Integer)
    residual_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    asset_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    accumulated_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expense_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_url: Mapped[str | None] = mapped_column(String(500))
    legal_reference: Mapped[str | None] = mapped_column(String(500))
    citation: Mapped[str | None] = mapped_column(String(1000))
    note: Mapped[str | None] = mapped_column(String(1000))
    validation_status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="pending"
    )
    validated_by_name: Mapped[str | None] = mapped_column(String(150))
    validated_reference: Mapped[str | None] = mapped_column(String(100))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FixedAsset(TimestampMixin, Base):
    """Bien del activo fijo (D-057, D-064, D-065).

    Parámetros **contables** (vida útil, residual, inicio): los que generan asientos.
    Parámetros **fiscales** (vida útil y porcentaje de residual, copiados de la categoría al
    alta): solo se usan en el cuadro de depreciación. Importes en guaraníes enteros.

    La baja (D-059) se prepara como borrador: mientras el borrador vive, el bien sigue
    `active` con los datos de la baja cargados; al contabilizarlo pasa a `disposed`, y al
    revertirlo vuelve a `active` sin datos de baja.
    """

    __tablename__ = "fixed_assets"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("cost > 0 AND cost = trunc(cost)", name="cost_positive_integer"),
        CheckConstraint(
            "residual_value >= 0 AND residual_value = trunc(residual_value)"
            " AND residual_value < cost",
            name="residual_valid",
        ),
        CheckConstraint(
            "useful_life_months > 0 AND fiscal_useful_life_months > 0",
            name="useful_life_positive",
        ),
        CheckConstraint(
            "fiscal_residual_rate >= 0 AND fiscal_residual_rate <= 20",
            name="fiscal_residual_rate_range",
        ),
        # RG 77/2020, col. 6: costo por porcentaje, en guaraníes enteros hacia abajo.
        CheckConstraint(
            "fiscal_residual_value = floor(cost * fiscal_residual_rate / 100)",
            name="fiscal_residual_value_exact",
        ),
        CheckConstraint(_in("start_rule", START_RULES), name="start_rule_valid"),
        CheckConstraint(
            "extract(day FROM depreciation_start) = 1", name="depreciation_start_first_day"
        ),
        CheckConstraint("depreciation_start > acquired_on", name="start_after_acquisition"),
        CheckConstraint(_in("status", ASSET_STATUSES), name="status_valid"),
        CheckConstraint(
            "disposal_kind IS NULL OR " + _in("disposal_kind", DISPOSAL_KINDS),
            name="disposal_kind_valid",
        ),
        CheckConstraint(
            "(disposal_entry_id IS NULL) = (disposed_on IS NULL)"
            " AND (disposal_entry_id IS NULL) = (disposal_kind IS NULL)"
            " AND (disposal_entry_id IS NULL) = (disposal_reason IS NULL)"
            " AND (disposal_entry_id IS NULL) = (disposal_document_reference IS NULL)",
            name="disposal_complete",
        ),
        CheckConstraint(
            "status = 'active' OR disposal_entry_id IS NOT NULL", name="disposed_has_entry"
        ),
        CheckConstraint(
            "disposed_on IS NULL OR disposed_on >= acquired_on", name="disposed_after_acquired"
        ),
        # Movimiento de finanzas de origen: las mismas claves que los asientos (D-035).
        CheckConstraint(
            "(source_transaction_id IS NULL) = (source_context_id IS NULL)"
            " AND (source_transaction_id IS NULL) = (source_context_kind IS NULL)",
            name="source_complete",
        ),
        CheckConstraint(
            "source_context_kind IS NULL OR source_context_kind = 'business'",
            name="source_business_only",
        ),
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("disposal_entry_id"),
        _org_fk(["category_id"], "asset_categories"),
        _org_fk(["acquisition_entry_id"], "journal_entries"),
        _org_fk(["disposal_entry_id"], "journal_entries"),
        ForeignKeyConstraint(
            ["source_transaction_id", "source_context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
        ),
        ForeignKeyConstraint(
            ["source_context_id", "source_context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_fixed_assets_source_context_kind_contexts",
        ),
        ForeignKeyConstraint(
            ["source_context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_fixed_assets_source_context_org_contexts",
        ),
        Index("ix_fixed_assets_org_status", "organization_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    serial_or_reference: Mapped[str | None] = mapped_column(String(100))
    acquired_on: Mapped[date] = mapped_column(Date, nullable=False)
    start_rule: Mapped[str] = mapped_column(String(20), nullable=False)
    depreciation_start: Mapped[date] = mapped_column(Date, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    residual_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_residual_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    fiscal_residual_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    acquisition_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_context_kind: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    disposed_on: Mapped[date | None] = mapped_column(Date)
    disposal_kind: Mapped[str | None] = mapped_column(String(10))
    disposal_reason: Mapped[str | None] = mapped_column(String(300))
    disposal_document_reference: Mapped[str | None] = mapped_column(String(100))
    disposal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)


class DepreciationRun(TimestampMixin, Base):
    """Corrida de depreciación de un período (D-058): un borrador con su detalle por bien.

    `entry_status` copia el estado del asiento y la mantienen los triggers de la 0004 (se
    sincroniza al cambiar el asiento y se recalcula en cada escritura de la corrida): así
    el índice único parcial garantiza una sola corrida viva por período, y descartar o
    revertir el asiento la libera.
    """

    __tablename__ = "depreciation_runs"
    __table_args__ = (
        CheckConstraint(_in("entry_status", ENTRY_STATUSES), name="entry_status_valid"),
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("entry_id"),
        _org_fk(["period_id"], "periods"),
        _org_fk(["entry_id"], "journal_entries"),
        Index(
            "uq_depreciation_runs_live_period",
            "period_id",
            unique=True,
            postgresql_where=text(LIVE_ENTRY),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # La escriben los triggers: el ORM la relee, nunca la escribe.
    entry_status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=FetchedValue(), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)


class DepreciationItem(TimestampMixin, Base):
    """Cuota de un bien en una corrida. Inmutable: solo se inserta con el asiento en borrador."""

    __tablename__ = "depreciation_items"
    __table_args__ = (
        CheckConstraint("amount > 0 AND amount = trunc(amount)", name="amount_positive_integer"),
        CheckConstraint("installment > 0", name="installment_positive"),
        UniqueConstraint("run_id", "asset_id"),
        _org_fk(["run_id"], "depreciation_runs"),
        _org_fk(["asset_id"], "fixed_assets"),
        Index("ix_depreciation_items_asset", "asset_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    installment: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class AssetYearValue(TimestampMixin, Base):
    """Valores de un bien al cierre de un ejercicio (D-066). Se escribe al cerrar el ejercicio,
    en la misma transacción, y no cambia más (prepara un revalúo futuro, que no se implementa).
    """

    __tablename__ = "asset_year_values"
    __table_args__ = (
        CheckConstraint(
            "fiscal_net_value >= 0 AND accounting_net_value >= 0"
            " AND fiscal_depreciation >= 0 AND accounting_depreciation >= 0",
            name="values_non_negative",
        ),
        CheckConstraint(
            "fiscal_net_value = trunc(fiscal_net_value)"
            " AND accounting_net_value = trunc(accounting_net_value)"
            " AND fiscal_depreciation = trunc(fiscal_depreciation)"
            " AND accounting_depreciation = trunc(accounting_depreciation)",
            name="values_pyg_integer",
        ),
        UniqueConstraint("asset_id", "fiscal_year_id"),
        _org_fk(["asset_id"], "fixed_assets"),
        _org_fk(["fiscal_year_id"], "fiscal_years"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fiscal_net_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    accounting_net_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    fiscal_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False)
    accounting_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False)


class CostCenter(TimestampMixin, Base):
    """Centro de costos (D-060): dimensión de gestión de las líneas de resultado, un nivel."""

    __tablename__ = "cost_centers"
    __table_args__ = (
        CheckConstraint(r"code ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'", name="code_format"),
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("id", "organization_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecurringTemplate(TimestampMixin, Base):
    """Plantilla de asiento recurrente (D-061): genera borradores, nunca contabiliza."""

    __tablename__ = "recurring_templates"
    __table_args__ = (
        CheckConstraint("char_length(btrim(description)) > 0", name="description_not_blank"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month_range"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="dates_ordered"),
        CheckConstraint(_in("status", TEMPLATE_STATUSES), name="status_valid"),
        UniqueConstraint("id", "organization_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    document_reference: Mapped[str | None] = mapped_column(String(100))
    day_of_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)


class RecurringTemplateLine(TimestampMixin, Base):
    """Línea fija de una plantilla: las mismas columnas que una línea de asiento."""

    __tablename__ = "recurring_template_lines"
    __table_args__ = (
        CheckConstraint("line_no > 0", name="line_no_positive"),
        CheckConstraint("debit >= 0 AND credit >= 0", name="amounts_non_negative"),
        CheckConstraint("(debit > 0) <> (credit > 0)", name="debit_xor_credit"),
        CheckConstraint("debit = trunc(debit) AND credit = trunc(credit)", name="pyg_integer"),
        CheckConstraint(
            "(fx_currency IS NULL) = (fx_amount IS NULL)"
            " AND (fx_currency IS NULL) = (fx_rate IS NULL)",
            name="fx_complete",
        ),
        CheckConstraint(
            f"fx_currency IS NULL OR fx_currency IN ({', '.join(repr(c) for c in FX_CURRENCIES)})",
            name="fx_currency_valid",
        ),
        CheckConstraint("fx_amount IS NULL OR fx_amount > 0", name="fx_amount_positive"),
        CheckConstraint("fx_rate IS NULL OR fx_rate > 0", name="fx_rate_positive"),
        UniqueConstraint("template_id", "line_no"),
        _org_fk(["template_id"], "recurring_templates"),
        _org_fk(["account_id"], "ledger_accounts"),
        _org_fk(["cost_center_id"], "cost_centers"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    credit: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    description: Mapped[str | None] = mapped_column(String(300))
    fx_currency: Mapped[str | None] = mapped_column(CHAR(3))
    fx_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class RecurringGeneration(TimestampMixin, Base):
    """Borrador generado por una plantilla en un período (D-061).

    Como en las corridas, `entry_status` la mantienen los triggers: el índice único parcial
    impide dos generaciones vivas de la misma plantilla en el mismo período, y descartar o
    revertir el asiento permite regenerarlo.
    """

    __tablename__ = "recurring_generations"
    __table_args__ = (
        CheckConstraint(_in("entry_status", ENTRY_STATUSES), name="entry_status_valid"),
        UniqueConstraint("entry_id"),
        _org_fk(["template_id"], "recurring_templates"),
        _org_fk(["period_id"], "periods"),
        _org_fk(["entry_id"], "journal_entries"),
        Index(
            "uq_recurring_generations_live",
            "template_id",
            "period_id",
            unique=True,
            postgresql_where=text(LIVE_ENTRY),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entry_status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=FetchedValue(), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)
