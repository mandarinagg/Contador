"""Autenticación, sesiones y gestión de usuarios de una organización."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotAuthenticated, NotFound
from app.core.permissions import Role
from app.core.security import (
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from app.modules.audit import service as audit
from app.modules.identity.models import User, UserSession
from app.modules.organizations.models import OrganizationMember

INVALID_CREDENTIALS = "Email o contraseña incorrectos."


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: UserSession
    member: OrganizationMember


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def _primary_membership(db: Session, user_id: uuid.UUID) -> OrganizationMember | None:
    # Una sola organización por ahora; con varias, el login elegirá cuál abrir.
    return db.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at)
        .limit(1)
    )


def issue_session(
    db: Session, user: User, member: OrganizationMember, user_agent: str | None
) -> IssuedSession:
    token = new_session_token()
    now = datetime.now(UTC)
    session = UserSession(
        user_id=user.id,
        organization_id=member.organization_id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(session)
    return IssuedSession(token=token, session=session, member=member)


def login(
    db: Session, email: str, password: str, *, ip: str | None, user_agent: str | None
) -> IssuedSession:
    settings = get_settings()
    now = datetime.now(UTC)
    user = find_user_by_email(db, email)

    if user is not None and user.locked_until is not None and user.locked_until > now:
        audit.security_event(
            db, "login_blocked", user_id=user.id, email_attempted=email, ip_address=ip
        )
        db.commit()
        raise AppError(
            "ACCOUNT_LOCKED",
            "Demasiados intentos fallidos. Probá de nuevo más tarde.",
            status_code=423,
            details={"locked_until": user.locked_until.isoformat()},
        )

    password_ok = verify_password(user.password_hash if user else None, password)
    member = _primary_membership(db, user.id) if user is not None else None

    if user is None or not password_ok or not user.is_active or member is None:
        if user is not None and not password_ok:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                audit.security_event(
                    db, "account_locked", user_id=user.id, email_attempted=email, ip_address=ip
                )
        reason = (
            "unknown_email"
            if user is None
            else "bad_password"
            if not password_ok
            else "inactive"
            if not user.is_active
            else "no_membership"
        )
        audit.security_event(
            db,
            "login_failed",
            user_id=user.id if user else None,
            organization_id=member.organization_id if member else None,
            email_attempted=email,
            ip_address=ip,
            details={"reason": reason},
        )
        db.commit()
        # Mismo mensaje en todos los casos: no revela si el email existe.
        raise NotAuthenticated("INVALID_CREDENTIALS", INVALID_CREDENTIALS)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    issued = issue_session(db, user, member, user_agent)
    audit.security_event(
        db, "login_success", user_id=user.id, organization_id=member.organization_id, ip_address=ip
    )
    db.commit()
    return issued


def logout(db: Session, session: UserSession, *, ip: str | None) -> None:
    session.revoked_at = datetime.now(UTC)
    audit.security_event(
        db,
        "logout",
        user_id=session.user_id,
        organization_id=session.organization_id,
        ip_address=ip,
    )
    db.commit()


def change_password(
    db: Session, user: User, current_session: UserSession, current: str, new: str, *, ip: str | None
) -> None:
    if not verify_password(user.password_hash, current):
        raise AppError("INVALID_CURRENT_PASSWORD", "La contraseña actual no es correcta.")
    if verify_password(user.password_hash, new):
        raise AppError("PASSWORD_REUSED", "La contraseña nueva tiene que ser distinta.")
    now = datetime.now(UTC)
    user.password_hash = hash_password(new)
    user.password_changed_at = now
    # Cierra las demás sesiones abiertas del usuario.
    db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.id != current_session.id,
        )
        .values(revoked_at=now)
    )
    audit.security_event(
        db,
        "password_changed",
        user_id=user.id,
        organization_id=current_session.organization_id,
        ip_address=ip,
    )
    db.commit()


# --- Gestión de usuarios de la organización -------------------------------------------


def list_members(db: Session, organization_id: uuid.UUID) -> list[tuple[User, OrganizationMember]]:
    rows = db.execute(
        select(User, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(User.full_name)
    ).all()
    return [(row[0], row[1]) for row in rows]


def _user_snapshot(user: User, role: str) -> dict[str, object]:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "role": role,
    }


def create_member(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    email: str,
    full_name: str,
    password: str,
    role: Role,
) -> tuple[User, OrganizationMember]:
    if role == Role.OWNER and actor_role != Role.OWNER:
        raise Forbidden("OWNER_ONLY", "Solo un propietario puede crear otro propietario.")
    if find_user_by_email(db, email) is not None:
        raise Conflict("EMAIL_TAKEN", "Ya existe un usuario con ese email.")
    user = User(email=email, full_name=full_name, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # carrera con otro alta del mismo email
        db.rollback()
        raise Conflict("EMAIL_TAKEN", "Ya existe un usuario con ese email.") from exc
    member = OrganizationMember(organization_id=organization_id, user_id=user.id, role_code=role)
    db.add(member)
    db.flush()
    audit.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        organization_id=organization_id,
        actor_user_id=actor_id,
        after=_user_snapshot(user, role),
    )
    db.commit()
    return user, member


def _active_owner_count(db: Session, organization_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role_code == Role.OWNER,
                User.is_active.is_(True),
            )
        )
        or 0
    )


def update_member(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    user_id: uuid.UUID,
    role: Role | None,
    is_active: bool | None,
) -> tuple[User, OrganizationMember]:
    row = db.execute(
        select(User, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == organization_id, User.id == user_id)
        .with_for_update()
    ).first()
    if row is None:
        raise NotFound("USER_NOT_FOUND", "El usuario no existe en esta organización.")
    user, member = row[0], row[1]
    before = _user_snapshot(user, member.role_code)

    touches_owner = member.role_code == Role.OWNER or role == Role.OWNER
    if touches_owner and actor_role != Role.OWNER:
        raise Forbidden("OWNER_ONLY", "Solo un propietario puede modificar propietarios.")
    if user_id == actor_id and (is_active is False or (role is not None and role != actor_role)):
        raise AppError("SELF_CHANGE_FORBIDDEN", "No podés desactivarte ni cambiar tu propio rol.")

    if role is not None:
        member.role_code = role
    if is_active is not None:
        user.is_active = is_active
    db.flush()

    # Siempre debe quedar al menos un propietario activo.
    if _active_owner_count(db, organization_id) == 0:
        db.rollback()
        raise Conflict("LAST_OWNER", "La organización tiene que conservar un propietario activo.")

    if is_active is False:
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    after = _user_snapshot(user, member.role_code)
    if after != before:
        audit.record(
            db,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            organization_id=organization_id,
            actor_user_id=actor_id,
            before=before,
            after=after,
        )
    db.commit()
    return user, member
