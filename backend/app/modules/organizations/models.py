"""Organizaciones (empresas) y su membresía (esquema `core`).

Multi-organización desde el inicio: todo dato de negocio cuelga de una organización,
aunque al principio exista una sola EAS.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

LEGAL_FORMS = ("EAS", "SA", "SRL", "UNIPERSONAL", "OTRA")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "legal_form IN ('EAS','SA','SRL','UNIPERSONAL','OTRA')", name="legal_form_valid"
        ),
        # RUC paraguayo: hasta 8 dígitos + DV. Opcional hasta verificarlo documentalmente.
        CheckConstraint("ruc IS NULL OR ruc ~ '^[0-9]{1,8}$'", name="ruc_digits"),
        CheckConstraint(
            "ruc_check_digit IS NULL OR ruc_check_digit ~ '^[0-9]$'", name="ruc_check_digit_digit"
        ),
        CheckConstraint("(ruc IS NULL) = (ruc_check_digit IS NULL)", name="ruc_complete"),
        CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="base_currency_iso"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(200))
    legal_form: Mapped[str] = mapped_column(String(20), nullable=False)
    ruc: Mapped[str | None] = mapped_column(String(8))
    ruc_check_digit: Mapped[str | None] = mapped_column(String(1))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="PYG")


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_code: Mapped[str] = mapped_column(ForeignKey("core.roles.code"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
