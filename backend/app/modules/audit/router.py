import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.deps import AuthContext, DbSession, require
from app.core.permissions import Perm
from app.modules.audit import service

router = APIRouter(prefix="/audit", tags=["audit"])
AuditReader = Annotated[AuthContext, Depends(require(Perm.AUDIT_READ))]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_kind: str
    action: str
    entity_type: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None


class SecurityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    event_type: str
    user_id: uuid.UUID | None
    email_attempted: str | None
    ip_address: Any
    details: dict[str, Any] | None


class VerifyOut(BaseModel):
    valid: bool
    checked: int
    first_broken_seq: int | None


@router.get("/logs", response_model=list[AuditLogOut])
def list_logs(
    auth: AuditReader,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    entity_type: Annotated[str | None, Query(max_length=100)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AuditLogOut]:
    rows = service.list_logs(
        db,
        auth.organization_id,
        viewer_user_id=auth.user_id,
        limit=limit,
        before_seq=before_seq,
        entity_type=entity_type,
        action=action,
    )
    return [AuditLogOut.model_validate(r) for r in rows]


@router.get("/security-events", response_model=list[SecurityEventOut])
def list_security_events(
    auth: AuditReader, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[SecurityEventOut]:
    return [
        SecurityEventOut.model_validate(e)
        for e in service.list_security_events(db, auth.organization_id, limit=limit)
    ]


@router.get("/verify", response_model=VerifyOut)
def verify(_: AuditReader, db: DbSession) -> VerifyOut:
    result = service.verify_chain(db)
    return VerifyOut(
        valid=result.valid, checked=result.checked, first_broken_seq=result.first_broken_seq
    )
