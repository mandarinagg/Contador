"""Modelos del esquema `finance` (migración 0002).

La separación entre contextos se impone en la base (D-025): cuentas, categorías,
contrapartes y lotes tienen `UNIQUE (id, context_id)` y los movimientos los referencian
con claves foráneas compuestas que incluyen `context_id` (y, para la cuenta, también la
moneda). Así, aun con un error de código, un movimiento personal no puede usar una cuenta
empresarial ni una moneda distinta a la de su cuenta.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.modules.finance.money import currency_sql_list

SCHEMA = "finance"
CONTEXT_KINDS = ("business", "personal")
ACCOUNT_KINDS = ("cash", "checking", "savings", "credit_card", "digital_wallet", "other")
CATEGORY_KINDS = ("income", "expense")
COUNTERPARTY_KINDS = (
    "customer",
    "supplier",
    "employee",
    "bank",
    "government",
    "person",
    "other",
)
IMPORT_FORMATS = ("csv", "xlsx")
IMPORT_STATUSES = ("previewed", "committed", "cancelled")
ROW_DECISIONS = ("import", "skip")
TRANSACTION_SOURCES = ("manual", "import")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))


# Montos NUMERIC(18,2) como Decimal (asdecimal=True es el valor por defecto de Numeric).
Money = Numeric(18, 2)

# Los PYG no tienen decimales: defensa en profundidad además de la validación en código.
_PYG_INTEGER = "currency <> 'PYG' OR {col} = trunc({col})"


class FinancialContext(TimestampMixin, Base):
    __tablename__ = "contexts"
    __table_args__ = (
        CheckConstraint(_in("kind", CONTEXT_KINDS), name="kind_valid"),
        CheckConstraint("(kind = 'business') = (owner_user_id IS NULL)", name="owner_matches_kind"),
        # Exactamente un contexto empresarial por organización (el alta lo hace el setup).
        Index(
            "uq_contexts_business_per_org",
            "organization_id",
            unique=True,
            postgresql_where=text("kind = 'business'"),
        ),
        # Como máximo un contexto personal por usuario y organización.
        Index(
            "uq_contexts_personal_per_user",
            "organization_id",
            "owner_user_id",
            unique=True,
            postgresql_where=text("kind = 'personal'"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.organizations.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(_in("kind", ACCOUNT_KINDS), name="kind_valid"),
        CheckConstraint(f"currency IN ({currency_sql_list()})", name="currency_valid"),
        # Solo los últimos 4 dígitos, nunca el número completo.
        CheckConstraint("number_last4 ~ '^[0-9]{4}$'", name="number_last4_digits"),
        CheckConstraint(_PYG_INTEGER.format(col="opening_balance"), name="pyg_integer"),
        UniqueConstraint("id", "context_id"),
        UniqueConstraint("id", "context_id", "currency"),
        UniqueConstraint("context_id", "name"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    context_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance.contexts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    number_last4: Mapped[str | None] = mapped_column(String(4))
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, server_default="0")
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(_in("kind", CATEGORY_KINDS), name="kind_valid"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        UniqueConstraint("id", "context_id"),
        UniqueConstraint("context_id", "parent_id", "name", postgresql_nulls_not_distinct=True),
        # El padre es del mismo contexto.
        ForeignKeyConstraint(
            ["parent_id", "context_id"],
            ["finance.categories.id", "finance.categories.context_id"],
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    context_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance.contexts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Counterparty(TimestampMixin, Base):
    __tablename__ = "counterparties"
    __table_args__ = (
        CheckConstraint(_in("kind", COUNTERPARTY_KINDS), name="kind_valid"),
        # Mismas reglas de RUC que core.organizations.
        CheckConstraint("ruc IS NULL OR ruc ~ '^[0-9]{1,8}$'", name="ruc_digits"),
        CheckConstraint(
            "ruc_check_digit IS NULL OR ruc_check_digit ~ '^[0-9]$'", name="ruc_check_digit_digit"
        ),
        CheckConstraint("(ruc IS NULL) = (ruc_check_digit IS NULL)", name="ruc_complete"),
        UniqueConstraint("id", "context_id"),
        Index(
            "uq_counterparties_ruc_per_context",
            "context_id",
            "ruc",
            unique=True,
            postgresql_where=text("ruc IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    context_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance.contexts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    ruc: Mapped[str | None] = mapped_column(String(8))
    ruc_check_digit: Mapped[str | None] = mapped_column(CHAR(1))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(_in("file_format", IMPORT_FORMATS), name="file_format_valid"),
        CheckConstraint(_in("status", IMPORT_STATUSES), name="status_valid"),
        CheckConstraint("(status = 'committed') = (committed_at IS NOT NULL)", name="committed"),
        CheckConstraint(
            "rows_total >= 0 AND rows_imported >= 0 AND rows_duplicate >= 0 AND rows_error >= 0",
            name="counts_non_negative",
        ),
        CheckConstraint("octet_length(file_sha256) = 32", name="file_sha256_length"),
        UniqueConstraint("id", "context_id"),
        # La cuenta del lote es del mismo contexto.
        ForeignKeyConstraint(
            ["account_id", "context_id"],
            ["finance.accounts.id", "finance.accounts.context_id"],
        ),
        Index("ix_import_batches_account_created", "account_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    context_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance.contexts.id"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="previewed")
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_error: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(TimestampMixin, Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        CheckConstraint(_in("decision", ROW_DECISIONS), name="decision_valid"),
        CheckConstraint("row_number > 0", name="row_number_positive"),
        UniqueConstraint("batch_id", "row_number"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("finance.import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    booked_on: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(String(300))
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("finance.transactions.id"))
    duplicate_in_file: Mapped[int | None] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        CheckConstraint(_PYG_INTEGER.format(col="amount"), name="pyg_integer"),
        CheckConstraint(_in("source", TRANSACTION_SOURCES), name="source_valid"),
        CheckConstraint(
            "(source = 'import') = (import_batch_id IS NOT NULL)", name="import_has_batch"
        ),
        CheckConstraint(
            "(voided_at IS NULL) = (voided_by IS NULL)"
            " AND (voided_at IS NULL) = (void_reason IS NULL)",
            name="void_complete",
        ),
        CheckConstraint(
            "void_reason IS NULL OR char_length(btrim(void_reason)) >= 3",
            name="void_reason_length",
        ),
        # Una transferencia entre cuentas propias no lleva categoría (no es ingreso ni gasto).
        CheckConstraint(
            "transfer_group_id IS NULL OR category_id IS NULL", name="transfer_without_category"
        ),
        CheckConstraint("octet_length(dedupe_key) = 32", name="dedupe_key_length"),
        # D-025: cuenta, categoría, contraparte y lote del mismo contexto; moneda de la cuenta.
        ForeignKeyConstraint(
            ["account_id", "context_id", "currency"],
            [
                "finance.accounts.id",
                "finance.accounts.context_id",
                "finance.accounts.currency",
            ],
        ),
        ForeignKeyConstraint(
            ["category_id", "context_id"],
            ["finance.categories.id", "finance.categories.context_id"],
        ),
        ForeignKeyConstraint(
            ["counterparty_id", "context_id"],
            ["finance.counterparties.id", "finance.counterparties.context_id"],
        ),
        ForeignKeyConstraint(
            ["import_batch_id", "context_id"],
            ["finance.import_batches.id", "finance.import_batches.context_id"],
        ),
        Index(
            "ix_transactions_context_booked",
            "context_id",
            text("booked_on DESC"),
            text("id DESC"),
        ),
        Index("ix_transactions_account_booked", "account_id", "booked_on"),
        # No único: dos movimientos iguales el mismo día son legítimos; se señalan (BR-FIN-03).
        Index("ix_transactions_account_dedupe", "account_id", "dedupe_key"),
        Index(
            "ix_transactions_transfer_group",
            "transfer_group_id",
            postgresql_where=text("transfer_group_id IS NOT NULL"),
        ),
        Index("ix_transactions_import_batch", "import_batch_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    context_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("finance.contexts.id"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    booked_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dedupe_key: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    void_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)
