"""Dependencias de FastAPI: sesión de base, usuario autenticado y permisos."""

import ipaddress
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import Forbidden, NotAuthenticated
from app.core.permissions import Perm
from app.core.security import hash_token
from app.modules.identity.models import RolePermission, User, UserSession
from app.modules.organizations.models import Organization, OrganizationMember

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)

# No se actualiza last_seen_at en cada pedido: una escritura por minuto basta para el
# vencimiento por inactividad.
_TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession
    organization: Organization
    role_code: str
    permissions: frozenset[str]

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id


def client_ip(request: Request) -> str | None:
    """IP del cliente si es una dirección válida (no se confía en cabeceras de proxy)."""
    host = request.client.host if request.client else None
    if host is None:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def load_permissions(db: Session, role_code: str) -> frozenset[str]:
    return frozenset(
        db.scalars(
            select(RolePermission.permission_code).where(RolePermission.role_code == role_code)
        )
    )


def get_auth(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise NotAuthenticated("NOT_AUTHENTICATED", "Iniciá sesión para continuar.")
    now = datetime.now(UTC)
    settings = get_settings()
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_token(credentials.credentials))
    )
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at + timedelta(minutes=settings.session_idle_minutes) <= now
    ):
        raise NotAuthenticated("SESSION_EXPIRED", "La sesión venció. Iniciá sesión de nuevo.")

    user = db.get(User, session.user_id)
    member = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == session.user_id,
            OrganizationMember.organization_id == session.organization_id,
        )
    )
    organization = db.get(Organization, session.organization_id)
    if (
        user is None
        or not user.is_active
        or member is None
        or not member.is_active
        or organization is None
    ):
        raise NotAuthenticated("SESSION_EXPIRED", "La sesión ya no es válida.")

    if now - session.last_seen_at >= _TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()

    return AuthContext(
        user=user,
        session=session,
        organization=organization,
        role_code=member.role_code,
        permissions=load_permissions(db, member.role_code),
    )


Auth = Annotated[AuthContext, Depends(get_auth)]


def require(*perms: Perm) -> Callable[[AuthContext], AuthContext]:
    """Dependencia que exige todos los permisos indicados en la organización activa."""

    def checker(auth: Auth) -> AuthContext:
        missing = [p.value for p in perms if p.value not in auth.permissions]
        if missing:
            raise Forbidden(
                "FORBIDDEN", "No tenés permiso para esta acción.", details={"missing": missing}
            )
        return auth

    return checker
