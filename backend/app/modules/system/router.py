"""Salud del servicio y configuración inicial (primer arranque)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import func, select, text

from app.api.deps import DbSession, client_ip
from app.core.errors import Conflict
from app.core.security import hash_password
from app.modules.audit import service as audit
from app.modules.identity import router as identity_router
from app.modules.identity import service as identity
from app.modules.identity.models import User
from app.modules.identity.schemas import FullName, LoginResponse, Password
from app.modules.organizations import service as organizations

router = APIRouter(prefix="/system", tags=["system"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class HealthOut(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    version: str


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupOrganization(BaseModel):
    legal_name: Name
    trade_name: Name | None = None
    legal_form: Literal["EAS", "SA", "SRL", "UNIPERSONAL", "OTRA"] = "EAS"


class SetupOwner(BaseModel):
    full_name: FullName
    email: EmailStr
    password: Password


class SetupRequest(BaseModel):
    organization: SetupOrganization
    owner: SetupOwner


@router.get("/health", response_model=HealthOut)
def health(db: DbSession) -> HealthOut:
    db.execute(text("SELECT 1"))
    return HealthOut(status="ok", database="ok", version="0.1.0")


def _has_users(db: DbSession) -> bool:
    return (db.scalar(select(func.count()).select_from(User)) or 0) > 0


@router.get("/setup", response_model=SetupStatus)
def setup_status(db: DbSession) -> SetupStatus:
    return SetupStatus(needs_setup=not _has_users(db))


@router.post("/setup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def run_setup(body: SetupRequest, request: Request, db: DbSession) -> LoginResponse:
    """Crea la organización y su propietario. Solo funciona con la base vacía.

    El candado serializa dos configuraciones simultáneas; la segunda ve el usuario
    creado por la primera y recibe 409.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('contador.setup'))"))
    if _has_users(db):
        raise Conflict("ALREADY_SET_UP", "El sistema ya fue configurado.")

    user = User(
        email=str(body.owner.email),
        full_name=body.owner.full_name,
        password_hash=hash_password(body.owner.password),
    )
    db.add(user)
    db.flush()
    # Mismo alta que `POST /organizations` (con su contexto empresarial, D-023), sin RUC.
    org, member = organizations.create_organization(
        db,
        owner_user_id=user.id,
        legal_name=body.organization.legal_name,
        trade_name=body.organization.trade_name,
        legal_form=body.organization.legal_form,
    )
    audit.record(
        db,
        action="system.setup",
        entity_type="organization",
        entity_id=org.id,
        organization_id=org.id,
        actor_user_id=user.id,
        after={
            "legal_name": org.legal_name,
            "legal_form": org.legal_form,
            "owner_email": user.email,
        },
    )
    audit.security_event(
        db,
        "setup_completed",
        user_id=user.id,
        organization_id=org.id,
        ip_address=client_ip(request),
    )
    issued = identity.issue_session(db, user, member, request.headers.get("user-agent"))
    db.commit()
    return identity_router.session_response(db, issued)
