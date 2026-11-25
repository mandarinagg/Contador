"""Modelos del esquema `tax` (migración 0005). Especificación: FASE4_TRIBUTACION.md §2.

- Las reglas, los feriados y las excepciones de calendario son **globales** (normas del
  país, D-084, D-086); el resto es de una organización y usa claves foráneas compuestas
  `(x_id, organization_id)`, como `accounting`.
- Lo que no cabe en una restricción declarativa (transiciones de estado, inmutabilidad de
  las reglas, bloqueo del período confirmado, nada se borra) lo imponen los triggers de la
  migración 0005 (`TAX_TRIGGERS_SQL`): la base es la última defensa.
- Importes: guaraníes enteros, `NUMERIC(18,0)` (D-088, D-095). Nunca `float`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.modules.finance.money import CURRENCIES

SCHEMA = "tax"
RULE_STATUSES = ("pending", "verified", "deprecated")
CONFIDENCES = ("oficial_leida", "oficial_citada_por_terceros", "secundaria", "no_encontrada")
HOLIDAY_STATUSES = ("pending", "verified")
ORIGINS = ("candidate", "user")
EXCEPTION_GROUPS = ("determinative",)
IRE_REGIMES = ("ire_general", "ire_simple", "unknown")
PROFILE_ORIGINS = ("declared", "verified")
OBLIGATION_STATUSES = ("pending", "filed", "paid", "not_applicable")
DIRECTIONS = ("purchase", "sale")
VOUCHER_TYPES = ("invoice", "credit_note", "debit_note")
NOTE_TYPES = ("credit_note", "debit_note")
# Tipos de identificación de la contraparte: los de la Tabla 3 del formato oficial de
# importación del registro de comprobantes (11 a 17, D-099). El código oficial está en
# `marangatu.IDENTIFICATION_CODES`.
DOC_TYPES = (
    "ruc",
    "identity_card",
    "passport",
    "foreign_id",
    "unnamed",
    "diplomatic",
    "tax_id",
)
DOCUMENT_TYPES = ("identity_card", "passport", "foreign_id", "diplomatic", "tax_id")
CONDITIONS = ("cash", "credit")

# Importes en guaraníes enteros.
Pyg = Numeric(18, 0)


def _in(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))


def _organization() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("core.organizations.id"), nullable=False)


def _ledger_fk(column_name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        [column_name, "organization_id"],
        ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
    )


class RuleVersion(TimestampMixin, Base):
    """Versión de una regla tributaria (D-084). Global: es una norma del país.

    La versión no se edita: un cambio de ley es una versión nueva con su `valid_from`. Solo
    cambia el estado (`pending → verified`, `cualquiera → deprecated` con motivo), y lo
    restringe el trigger `rule_versions_guard`.
    """

    __tablename__ = "rule_versions"
    __table_args__ = (
        CheckConstraint(r"code ~ '^[A-Z0-9]+(-[A-Z0-9]+)*$'", name="code_format"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(_in("validation_status", RULE_STATUSES), name="status_valid"),
        CheckConstraint(
            "confidence IS NULL OR " + _in("confidence", CONFIDENCES), name="confidence_valid"
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_ordered",
        ),
        CheckConstraint("jsonb_typeof(parameters) = 'object'", name="parameters_object"),
        # Verificada: revisor, matrícula y fecha completos (y se conservan si se depreca).
        CheckConstraint(
            "(reviewed_by_name IS NULL) = (reviewed_reference IS NULL)"
            " AND (reviewed_by_name IS NULL) = (reviewed_at IS NULL)"
            " AND (validation_status <> 'verified' OR reviewed_by_name IS NOT NULL)",
            name="review_complete",
        ),
        CheckConstraint(
            "(validation_status = 'deprecated') = (deprecation_reason IS NOT NULL)"
            " AND (validation_status = 'deprecated') = (deprecated_at IS NOT NULL)",
            name="deprecation_complete",
        ),
        UniqueConstraint("code", "version"),
        # Dos versiones vivas del mismo código no tienen vigencias que se pisen.
        ExcludeConstraint(
            (column("code"), "="),
            (func.daterange(column("valid_from"), column("valid_to"), "[]"), "&&"),
            using="gist",
            name="ex_rule_versions_no_overlap",
            where=text("validation_status <> 'deprecated'"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    legal_reference: Mapped[str | None] = mapped_column(String(500))
    consulted_at: Mapped[date | None] = mapped_column(Date)
    confidence: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="pending"
    )
    reviewed_by_name: Mapped[str | None] = mapped_column(String(150))
    reviewed_reference: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(500))
    deprecation_reason: Mapped[str | None] = mapped_column(String(300))
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Holiday(TimestampMixin, Base):
    """Feriado nacional (D-086). Global; editable con auditoría."""

    __tablename__ = "holidays"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(_in("validation_status", HOLIDAY_STATUSES), name="status_valid"),
        CheckConstraint(_in("origin", ORIGINS), name="origin_valid"),
        CheckConstraint(
            "source_url IS NOT NULL OR legal_reference IS NOT NULL", name="source_present"
        ),
        UniqueConstraint("day"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    day: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    legal_reference: Mapped[str | None] = mapped_column(String(300))
    validation_status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="pending"
    )
    origin: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)


class DueDateException(TimestampMixin, Base):
    """Traslado excepcional de vencimientos (D-086): reemplaza la fecha calculada.

    Apunta a una obligación (`obligation_code`, el código de la regla) o a un grupo
    (`determinative`: todas las declaraciones determinativas). `due_month` es el mes del
    vencimiento calculado que se traslada (primer día del mes). `ruc_digits` vacío = todas
    las terminaciones del RUC.
    """

    __tablename__ = "due_date_exceptions"
    __table_args__ = (
        CheckConstraint(
            "(obligation_code IS NULL) <> (obligation_group IS NULL)", name="target_one"
        ),
        CheckConstraint(
            "obligation_group IS NULL OR " + _in("obligation_group", EXCEPTION_GROUPS),
            name="group_valid",
        ),
        CheckConstraint("extract(day FROM due_month) = 1", name="due_month_first_day"),
        CheckConstraint(
            "ruc_digits <@ ARRAY[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]::smallint[]",
            name="ruc_digits_valid",
        ),
        CheckConstraint("char_length(btrim(legal_reference)) > 0", name="legal_reference_present"),
        CheckConstraint(_in("origin", ORIGINS), name="origin_valid"),
        CheckConstraint(
            "(origin = 'candidate') = (rule_version_id IS NOT NULL)", name="candidate_has_rule"
        ),
        Index(
            "uq_due_date_exceptions_rule_date",
            "rule_version_id",
            "new_due_date",
            unique=True,
            postgresql_where=text("rule_version_id IS NOT NULL"),
        ),
        Index("ix_due_date_exceptions_due_month", "due_month"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    obligation_code: Mapped[str | None] = mapped_column(String(60))
    obligation_group: Mapped[str | None] = mapped_column(String(20))
    due_month: Mapped[date] = mapped_column(Date, nullable=False)
    ruc_digits: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), nullable=False, server_default=text("'{}'::smallint[]")
    )
    new_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    legal_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tax.rule_versions.id"))
    origin: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)


class Profile(TimestampMixin, Base):
    """Perfil fiscal versionado de la organización (D-083)."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(_in("ire_regime", IRE_REGIMES), name="ire_regime_valid"),
        CheckConstraint("fiscal_close_month BETWEEN 1 AND 12", name="close_month_range"),
        CheckConstraint(_in("origin", PROFILE_ORIGINS), name="origin_valid"),
        # Verificado: nombre, matrícula, referencia de la constancia, fecha y usuario.
        CheckConstraint(
            "(origin = 'verified') = (verified_by_name IS NOT NULL)"
            " AND (origin = 'verified') = (verified_license IS NOT NULL)"
            " AND (origin = 'verified') = (verified_document_reference IS NOT NULL)"
            " AND (origin = 'verified') = (verified_at IS NOT NULL)"
            " AND (origin = 'verified') = (verified_by IS NOT NULL)",
            name="verification_complete",
        ),
        UniqueConstraint("organization_id", "valid_from"),
        UniqueConstraint("id", "organization_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    ire_regime: Mapped[str] = mapped_column(String(12), nullable=False)
    fiscal_close_month: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="12"
    )
    vat_taxpayer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    origin: Mapped[str] = mapped_column(String(10), nullable=False, server_default="declared")
    verified_by_name: Mapped[str | None] = mapped_column(String(150))
    verified_license: Mapped[str | None] = mapped_column(String(100))
    verified_document_reference: Mapped[str | None] = mapped_column(String(150))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)


class ProfileObligation(TimestampMixin, Base):
    """Obligación inscripta en el RUC, con su código DNIT y su fecha de alta."""

    __tablename__ = "profile_obligations"
    __table_args__ = (
        CheckConstraint("code ~ '^[0-9]{1,4}$'", name="code_digits"),
        UniqueConstraint("profile_id", "code"),
        ForeignKeyConstraint(
            ["profile_id", "organization_id"],
            ["tax.profiles.id", "tax.profiles.organization_id"],
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(4), nullable=False)
    registered_on: Mapped[date] = mapped_column(Date, nullable=False)


class Obligation(TimestampMixin, Base):
    """Obligación de un período (D-087): una fila por (organización, código, período).

    `code` es el código de la regla que la genera (p. ej. `IVA-GENERAL-LIQUIDACION`) y
    `dnit_code` el de la obligación en el RUC (`211`). `nominal_due_date` es el día del
    calendario antes de correr los inhábiles y de las excepciones; `remind_by`, el menor de
    los dos (D-098).
    """

    __tablename__ = "obligations"
    __table_args__ = (
        CheckConstraint(_in("status", OBLIGATION_STATUSES), name="status_valid"),
        CheckConstraint("period_end >= period_start", name="period_ordered"),
        CheckConstraint(
            "(status IN ('filed', 'paid')) = (filed_on IS NOT NULL)"
            " AND (status IN ('filed', 'paid')) = (filing_reference IS NOT NULL)",
            name="filing_complete",
        ),
        CheckConstraint(
            "(status = 'paid') = (paid_on IS NOT NULL)"
            " AND (status = 'paid') = (paid_amount IS NOT NULL)",
            name="payment_complete",
        ),
        CheckConstraint(
            "(status = 'not_applicable') = (not_applicable_reason IS NOT NULL)",
            name="not_applicable_has_reason",
        ),
        CheckConstraint(
            "NOT not_applicable_auto OR status = 'not_applicable'", name="auto_when_not_applicable"
        ),
        CheckConstraint(
            "declared_amount IS NULL OR status IN ('filed', 'paid')", name="declared_when_filed"
        ),
        CheckConstraint(
            "declared_credit_balance IS NULL OR status IN ('filed', 'paid')",
            name="declared_balance_when_filed",
        ),
        CheckConstraint(
            "payment_transaction_id IS NULL OR status = 'paid'", name="payment_tx_when_paid"
        ),
        CheckConstraint(
            "(payment_transaction_id IS NULL) = (payment_context_id IS NULL)"
            " AND (payment_transaction_id IS NULL) = (payment_context_kind IS NULL)",
            name="payment_source_complete",
        ),
        CheckConstraint(
            "payment_context_kind IS NULL OR payment_context_kind = 'business'",
            name="payment_business_only",
        ),
        CheckConstraint(
            "(calculated_amount IS NULL OR calculated_amount >= 0)"
            " AND (calculated_credit_balance IS NULL OR calculated_credit_balance >= 0)"
            " AND (declared_amount IS NULL OR declared_amount >= 0)"
            " AND (declared_credit_balance IS NULL OR declared_credit_balance >= 0)"
            " AND (paid_amount IS NULL OR paid_amount >= 0)",
            name="amounts_non_negative",
        ),
        CheckConstraint(
            "reopen_reason IS NULL OR char_length(btrim(reopen_reason)) >= 3",
            name="reopen_reason_length",
        ),
        UniqueConstraint("organization_id", "code", "period_start"),
        ForeignKeyConstraint(
            ["payment_transaction_id", "payment_context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
        ),
        ForeignKeyConstraint(
            ["payment_context_id", "payment_context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_obligations_payment_context_kind_contexts",
        ),
        ForeignKeyConstraint(
            ["payment_context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_obligations_payment_context_org_contexts",
        ),
        Index("ix_obligations_org_due", "organization_id", "due_date"),
        Index("ix_obligations_org_remind", "organization_id", "remind_by"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    dnit_code: Mapped[str] = mapped_column(String(4), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    nominal_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    # D-098: el aviso usa la fecha fija del calendario sin correr si es anterior, porque no
    # está verificado que los feriados corran los vencimientos (D-F4-12; los sábados sí, D-122):
    # así nunca se avisa más tarde que el vencimiento real.
    remind_by: Mapped[date] = mapped_column(
        Date, Computed("LEAST(nominal_due_date, due_date)", persisted=True)
    )
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax.rule_versions.id"), nullable=False
    )
    calendar_rule_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax.rule_versions.id"), nullable=False
    )
    exception_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tax.due_date_exceptions.id"))
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default="pending")
    calculated_amount: Mapped[Decimal | None] = mapped_column(Pyg)
    calculated_credit_balance: Mapped[Decimal | None] = mapped_column(Pyg)
    filed_on: Mapped[date | None] = mapped_column(Date)
    filing_reference: Mapped[str | None] = mapped_column(String(60))
    declared_amount: Mapped[Decimal | None] = mapped_column(Pyg)
    declared_credit_balance: Mapped[Decimal | None] = mapped_column(Pyg)
    paid_on: Mapped[date | None] = mapped_column(Date)
    paid_amount: Mapped[Decimal | None] = mapped_column(Pyg)
    payment_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payment_context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payment_context_kind: Mapped[str | None] = mapped_column(String(10))
    not_applicable_reason: Mapped[str | None] = mapped_column(String(300))
    not_applicable_auto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reopen_reason: Mapped[str | None] = mapped_column(String(300))


class Voucher(TimestampMixin, Base):
    """Comprobante de compra o de venta (D-088). Se anula, nunca se borra."""

    __tablename__ = "vouchers"
    __table_args__ = (
        CheckConstraint(_in("direction", DIRECTIONS), name="direction_valid"),
        CheckConstraint(_in("voucher_type", VOUCHER_TYPES), name="type_valid"),
        CheckConstraint(_in("counterparty_doc_type", DOC_TYPES), name="doc_type_valid"),
        CheckConstraint(_in("condition", CONDITIONS), name="condition_valid"),
        CheckConstraint("timbrado ~ '^[0-9]{8}$'", name="timbrado_format"),
        CheckConstraint("number ~ '^[0-9]{3}-[0-9]{3}-[0-9]{7}$'", name="number_format"),
        # CDC: 44 dígitos, solo en los electrónicos, con su dígito verificador módulo 11.
        CheckConstraint("is_electronic = (cdc IS NOT NULL)", name="cdc_when_electronic"),
        CheckConstraint(
            "cdc IS NULL OR (cdc ~ '^[0-9]{44}$'"
            " AND tax.ruc_check_digit(left(cdc, 43)) = right(cdc, 1)::integer)",
            name="cdc_format",
        ),
        # Contraparte: RUC con DV válido, documento o «sin nombre».
        # El RUC numérico lleva su DV módulo 11; un RUC antiguo terminado en letra (D-F4-10)
        # se acepta sin DV, como identificación a revisar (D-099).
        CheckConstraint(
            "(counterparty_doc_type = 'ruc') = (counterparty_ruc IS NOT NULL)",
            name="ruc_when_ruc",
        ),
        CheckConstraint(
            "counterparty_ruc IS NULL"
            " OR (counterparty_ruc ~ '^[0-9]{1,8}$' AND counterparty_ruc_dv ~ '^[0-9]$'"
            " AND tax.ruc_check_digit(counterparty_ruc) = counterparty_ruc_dv::integer)"
            " OR (counterparty_ruc ~ '^[0-9]{1,8}[A-Z]$' AND counterparty_ruc_dv IS NULL)",
            name="ruc_check_digit",
        ),
        CheckConstraint(
            "counterparty_ruc IS NOT NULL OR counterparty_ruc_dv IS NULL", name="dv_with_ruc"
        ),
        CheckConstraint(
            f"({_in('counterparty_doc_type', DOCUMENT_TYPES)})"
            " = (counterparty_document IS NOT NULL)",
            name="document_when_document",
        ),
        CheckConstraint("char_length(btrim(counterparty_name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "direction <> 'purchase' OR counterparty_doc_type = 'ruc'", name="purchase_has_ruc"
        ),
        # Moneda (D-041): en guaraníes, sin cotización; en otra, cotización y total original.
        CheckConstraint(
            "(currency = 'PYG') = (fx_rate IS NULL)"
            " AND (currency = 'PYG') = (foreign_total IS NULL)",
            name="fx_complete",
        ),
        CheckConstraint(
            f"currency IN ({', '.join(repr(c) for c in CURRENCIES)})", name="currency_valid"
        ),
        CheckConstraint(
            "(fx_rate IS NULL OR fx_rate > 0) AND (foreign_total IS NULL OR foreign_total > 0)",
            name="fx_positive",
        ),
        # Importes con IVA incluido, como en la factura; el IVA no supera su base gravada.
        CheckConstraint(
            "taxed_10 >= 0 AND taxed_5 >= 0 AND exempt >= 0 AND vat_10 >= 0 AND vat_5 >= 0",
            name="amounts_non_negative",
        ),
        CheckConstraint("taxed_10 + taxed_5 + exempt > 0", name="total_positive"),
        CheckConstraint(
            "vat_10 <= taxed_10 AND vat_5 <= taxed_5"
            " AND (taxed_10 > 0 OR vat_10 = 0) AND (taxed_5 > 0 OR vat_5 = 0)",
            name="vat_consistent",
        ),
        CheckConstraint(
            "(voucher_type IN ('credit_note', 'debit_note')) = (related_voucher_id IS NOT NULL)",
            name="note_has_original",
        ),
        CheckConstraint("related_voucher_id IS NULL OR related_voucher_id <> id", name="not_self"),
        CheckConstraint(
            "(voided_at IS NULL) = (voided_by IS NULL)"
            " AND (voided_at IS NULL) = (void_reason IS NULL)",
            name="void_complete",
        ),
        CheckConstraint(
            "void_reason IS NULL OR char_length(btrim(void_reason)) >= 3",
            name="void_reason_length",
        ),
        CheckConstraint("context_kind = 'business'", name="business_only"),
        UniqueConstraint("id", "organization_id"),
        UniqueConstraint("id", "organization_id", "direction"),
        # La nota referencia un comprobante de la misma organización y dirección.
        ForeignKeyConstraint(
            ["related_voucher_id", "organization_id", "direction"],
            ["tax.vouchers.id", "tax.vouchers.organization_id", "tax.vouchers.direction"],
        ),
        # Contexto empresarial de la misma organización; contraparte y movimiento de ese
        # contexto (nunca del personal, D-024).
        ForeignKeyConstraint(
            ["context_id", "context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_vouchers_context_kind_contexts",
        ),
        ForeignKeyConstraint(
            ["context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_vouchers_context_org_contexts",
        ),
        ForeignKeyConstraint(
            ["finance_counterparty_id", "context_id"],
            ["finance.counterparties.id", "finance.counterparties.context_id"],
        ),
        ForeignKeyConstraint(
            ["transaction_id", "context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
        ),
        ForeignKeyConstraint(
            ["journal_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
        ),
        # BR-TAX-07: sin duplicados entre los vivos. En compras, por proveedor; en ventas, el
        # emisor es la propia empresa.
        Index(
            "uq_vouchers_purchase_live",
            "organization_id",
            "voucher_type",
            "counterparty_ruc",
            "timbrado",
            "number",
            unique=True,
            postgresql_where=text("direction = 'purchase' AND voided_at IS NULL"),
        ),
        Index(
            "uq_vouchers_sale_live",
            "organization_id",
            "voucher_type",
            "timbrado",
            "number",
            unique=True,
            postgresql_where=text("direction = 'sale' AND voided_at IS NULL"),
        ),
        Index("ix_vouchers_org_issued", "organization_id", "issued_on"),
        Index("ix_vouchers_transaction", "transaction_id"),
        Index("ix_vouchers_journal_entry", "journal_entry_id"),
        Index("ix_vouchers_related", "related_voucher_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    context_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    context_kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="business")
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(12), nullable=False)
    is_electronic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cdc: Mapped[str | None] = mapped_column(CHAR(44))
    timbrado: Mapped[str] = mapped_column(CHAR(8), nullable=False)
    number: Mapped[str] = mapped_column(String(15), nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty_doc_type: Mapped[str] = mapped_column(String(15), nullable=False)
    counterparty_ruc: Mapped[str | None] = mapped_column(String(8))
    counterparty_ruc_dv: Mapped[str | None] = mapped_column(CHAR(1))
    counterparty_document: Mapped[str | None] = mapped_column(String(20))
    counterparty_name: Mapped[str] = mapped_column(String(200), nullable=False)
    condition: Mapped[str] = mapped_column(String(6), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="PYG")
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    foreign_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    taxed_10: Mapped[Decimal] = mapped_column(Pyg, nullable=False, server_default="0")
    taxed_5: Mapped[Decimal] = mapped_column(Pyg, nullable=False, server_default="0")
    exempt: Mapped[Decimal] = mapped_column(Pyg, nullable=False, server_default="0")
    vat_10: Mapped[Decimal] = mapped_column(Pyg, nullable=False, server_default="0")
    vat_5: Mapped[Decimal] = mapped_column(Pyg, nullable=False, server_default="0")
    imputes_vat: Mapped[bool] = mapped_column(Boolean, nullable=False)
    imputes_ire: Mapped[bool] = mapped_column(Boolean, nullable=False)
    imputes_irp: Mapped[bool] = mapped_column(Boolean, nullable=False)
    vat_rule_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax.rule_versions.id"), nullable=False
    )
    related_voucher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    finance_counterparty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("core.users.id"))
    void_reason: Mapped[str | None] = mapped_column(String(300))


class TaxSettings(TimestampMixin, Base):
    """Configuración tributaria 1:1 con la organización.

    Cuentas de IVA (D-091) y, además (D-096), las de proveedores y clientes para el haber o
    el debe de los comprobantes a crédito. Si una cuenta es `null` se usa la del plan
    propuesto por su código, si existe. Días de anticipación de los avisos (D-092).
    """

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("alert_days BETWEEN 1 AND 60", name="alert_days_range"),
        UniqueConstraint("organization_id"),
        _ledger_fk("vat_credit_10_account_id"),
        _ledger_fk("vat_credit_5_account_id"),
        _ledger_fk("vat_debit_10_account_id"),
        _ledger_fk("vat_debit_5_account_id"),
        _ledger_fk("suppliers_account_id"),
        _ledger_fk("customers_account_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    vat_credit_10_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vat_credit_5_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vat_debit_10_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vat_debit_5_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    suppliers_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    customers_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    alert_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="10")
