"""Organizaciones (empresas) y su membresía (esquema `core`).

Multi-organización desde el inicio: todo dato de negocio cuelga de una organización,
aunque al principio exista una sola EAS.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

LEGAL_FORMS = ("EAS", "SA", "SRL", "UNIPERSONAL", "PERSONA_FISICA", "OTRA")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "legal_form IN ('EAS','SA','SRL','UNIPERSONAL','PERSONA_FISICA','OTRA')",
            name="legal_form_valid",
        ),
        # Persona física: nombres y apellidos; cualquier otra forma: ninguno (D-141).
        CheckConstraint(
            "(legal_form = 'PERSONA_FISICA' AND first_names IS NOT NULL AND last_names IS NOT NULL)"
            " OR (legal_form <> 'PERSONA_FISICA' AND first_names IS NULL AND last_names IS NULL)",
            name="person_names",
        ),
        # RUC paraguayo: hasta 8 dígitos + DV. Opcional hasta verificarlo documentalmente.
        CheckConstraint("ruc IS NULL OR ruc ~ '^[0-9]{1,8}$'", name="ruc_digits"),
        CheckConstraint(
            "ruc_check_digit IS NULL OR ruc_check_digit ~ '^[0-9]$'", name="ruc_check_digit_digit"
        ),
        CheckConstraint("(ruc IS NULL) = (ruc_check_digit IS NULL)", name="ruc_complete"),
        CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="base_currency_iso"),
        # Una sola organización por RUC en la instalación (la clave de Marangatu es por RUC,
        # D-128; respuesta 1 del propietario). Migración 0008.
        Index("uq_organizations_ruc", "ruc", unique=True, postgresql_where=text("ruc IS NOT NULL")),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(200))
    legal_form: Mapped[str] = mapped_column(String(20), nullable=False)
    first_names: Mapped[str | None] = mapped_column(String(100))
    last_names: Mapped[str | None] = mapped_column(String(100))
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
    # Activo en esta organización. Desactivar a alguien en una no lo toca en las demás
    # (migración 0009, D-137). `users.is_active` queda como interruptor de toda la cuenta.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
