"""Registro y consulta de auditoría."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.modules.audit.models import AuditLog, SecurityEvent


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_kind: str = "user",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Agrega una entrada en la misma transacción que el cambio auditado.

    Si la transacción se revierte, la entrada también: nunca queda auditado un
    cambio que no ocurrió ni un cambio sin auditar.
    """
    db.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind,
            before=before,
            after=after,
            request_id=request_id_var.get(),
        )
    )


def security_event(
    db: Session,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    email_attempted: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        SecurityEvent(
            event_type=event_type,
            user_id=user_id,
            organization_id=organization_id,
            email_attempted=email_attempted,
            ip_address=ip_address,
            details=details,
        )
    )


# Auditoría de finanzas personales (D-024): solo la ve su dueño, que es el único que puede
# operar ese contexto y por lo tanto el único actor de esas entradas.
PRIVATE_ENTITY_PREFIX = "finance.personal."


def list_logs(
    db: Session,
    organization_id: uuid.UUID,
    *,
    viewer_user_id: uuid.UUID,
    limit: int,
    before_seq: int | None,
    entity_type: str | None,
    action: str | None,
) -> list[AuditLog]:
    query = select(AuditLog).where(
        AuditLog.organization_id == organization_id,
        or_(
            ~AuditLog.entity_type.startswith(PRIVATE_ENTITY_PREFIX, autoescape=True),
            AuditLog.actor_user_id == viewer_user_id,
        ),
    )
    if before_seq is not None:
        query = query.where(AuditLog.seq < before_seq)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if action:
        query = query.where(AuditLog.action == action)
    return list(db.scalars(query.order_by(AuditLog.seq.desc()).limit(limit)))


def list_security_events(
    db: Session, organization_id: uuid.UUID, *, limit: int
) -> list[SecurityEvent]:
    # Los intentos fallidos con un email desconocido no tienen organización: también se muestran
    # (la app de escritorio tiene una sola instalación por máquina).
    query = (
        select(SecurityEvent)
        .where(
            (SecurityEvent.organization_id == organization_id)
            | SecurityEvent.organization_id.is_(None)
        )
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    checked: int
    first_broken_seq: int | None


def verify_chain(db: Session) -> ChainVerification:
    """Recalcula toda la cadena de hashes y devuelve la primera fila alterada."""
    rows = db.execute(
        text(
            """
            SELECT seq,
                   prev_hash IS NOT DISTINCT FROM lag(row_hash) OVER (ORDER BY seq) AS link_ok,
                   row_hash = audit.log_row_hash(prev_hash, seq, id, occurred_at, organization_id,
                       actor_user_id, actor_kind, action, entity_type, entity_id, before, after,
                       request_id) AS hash_ok
            FROM audit.audit_logs
            ORDER BY seq
            """
        )
    ).all()
    for row in rows:
        if not (row.link_ok and row.hash_ok):
            return ChainVerification(valid=False, checked=len(rows), first_broken_seq=row.seq)
    return ChainVerification(valid=True, checked=len(rows), first_broken_seq=None)


def count_logs(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AuditLog)) or 0
