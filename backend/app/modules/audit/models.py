"""Auditoría (esquema `audit`).

Las dos tablas son de solo inserción: triggers de la migración 0001 rechazan UPDATE,
DELETE y TRUNCATE. `audit_logs` además forma una cadena de hashes (cada fila incluye el
hash de la anterior) calculada por la base, así una alteración por fuera de la
aplicación se detecta con `GET /audit/verify`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, FetchedValue, Index, LargeBinary, String, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_seq", "organization_id", "seq"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        {"schema": "audit"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # La asigna el trigger después de tomar el candado de la cadena: el orden de `seq`
    # coincide con el orden de la cadena de hashes aunque haya transacciones concurrentes.
    seq: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, server_default=FetchedValue()
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Sin FK a propósito: la auditoría sobrevive aunque se borre el usuario u organización.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="user")
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), server_default=FetchedValue())
    row_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, server_default=FetchedValue()
    )


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_occurred", "occurred_at"),
        Index("ix_security_events_user", "user_id"),
        {"schema": "audit"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    email_attempted: Mapped[str | None] = mapped_column(String(254))
    ip_address: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
