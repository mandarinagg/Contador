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
from app.modules.organizations.models import Organization, OrganizationMember

INVALID_CREDENTIALS = "Email o contraseña incorrectos."
EMAIL_TAKEN_MESSAGE = (
    "Ya existe un usuario con ese email. Para darle acceso a esta organización, sumalo como "
    "usuario existente."
)


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: UserSession
    member: OrganizationMember


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


@dataclass(frozen=True)
class Membership:
    member: OrganizationMember
    organization: Organization


def active_memberships(db: Session, user_id: uuid.UUID) -> list[Membership]:
    """Membresías activas del usuario, en orden de preferencia para abrir sin elegir (D-138):
    primero la organización usada por última vez (la sesión más reciente, también las de un
    cambio de organización), después la membresía más antigua."""
    last_used = (
        select(
            UserSession.organization_id.label("organization_id"),
            func.max(UserSession.created_at).label("last_used"),
        )
        .where(UserSession.user_id == user_id)
        .group_by(UserSession.organization_id)
        .subquery()
    )
    rows = db.execute(
        select(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .outerjoin(last_used, last_used.c.organization_id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_id, OrganizationMember.is_active.is_(True))
        .order_by(
            last_used.c.last_used.desc().nulls_last(),
            OrganizationMember.created_at,
            OrganizationMember.id,
        )
    ).all()
    return [Membership(member=row[0], organization=row[1]) for row in rows]


def _oldest_organization_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at, OrganizationMember.id)
        .limit(1)
    )


def _find_membership(
    memberships: list[Membership], organization_id: uuid.UUID
) -> OrganizationMember | None:
    return next(
        (m.member for m in memberships if m.member.organization_id == organization_id), None
    )


def organization_not_available() -> Forbidden:
    # Igual si la organización no existe, si no es miembro o si lo desactivaron ahí: no revela
    # qué organizaciones hay en la instalación.
    return Forbidden("ORGANIZATION_NOT_AVAILABLE", "No tenés acceso a esa organización.")


def issue_session(
    db: Session,
    user: User,
    member: OrganizationMember,
    user_agent: str | None,
    *,
    expires_at: datetime | None = None,
) -> IssuedSession:
    """Sesión nueva. `expires_at` la usa el cambio de organización para conservar el
    vencimiento absoluto de la sesión anterior (D-006, D-139)."""
    token = new_session_token()
    now = datetime.now(UTC)
    session = UserSession(
        user_id=user.id,
        organization_id=member.organization_id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=(
            expires_at.astimezone(UTC)
            if expires_at is not None
            else now + timedelta(hours=get_settings().session_ttl_hours)
        ),
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(session)
    return IssuedSession(token=token, session=session, member=member)


def login(
    db: Session,
    email: str,
    password: str,
    *,
    organization_id: uuid.UUID | None = None,
    ip: str | None,
    user_agent: str | None,
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
    memberships = active_memberships(db, user.id) if user is not None else []
    # La de preferencia: con ella se anotan los eventos del usuario (D-134) y se abre la sesión
    # si no pidió ninguna.
    member = memberships[0].member if memberships else None
    # Si lo desactivaron en todas, los eventos van a la más antigua: la que lo desactivó los ve.
    event_org = (
        member.organization_id
        if member is not None
        else _oldest_organization_id(db, user.id)
        if user is not None
        else None
    )

    if user is None or not password_ok or not user.is_active or member is None:
        if user is not None and not password_ok:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                audit.security_event(
                    db,
                    "account_locked",
                    user_id=user.id,
                    organization_id=event_org,
                    email_attempted=email,
                    ip_address=ip,
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
            organization_id=event_org,
            email_attempted=email,
            ip_address=ip,
            details={"reason": reason},
        )
        db.commit()
        # Mismo mensaje en todos los casos: no revela si el email existe.
        raise NotAuthenticated("INVALID_CREDENTIALS", INVALID_CREDENTIALS)

    if organization_id is not None:
        chosen = _find_membership(memberships, organization_id)
        if chosen is None:
            # La contraseña es correcta: no suma intentos fallidos, pero no abre sesión.
            audit.security_event(
                db,
                "login_failed",
                user_id=user.id,
                organization_id=member.organization_id,
                email_attempted=email,
                ip_address=ip,
                details={"reason": "organization_not_available"},
            )
            db.commit()
            raise organization_not_available()
        member = chosen

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


def switch_organization(
    db: Session,
    user: User,
    current: UserSession,
    organization_id: uuid.UUID,
    *,
    ip: str | None,
    user_agent: str | None,
) -> IssuedSession:
    """Cierra la sesión actual y abre otra en la organización pedida, con un token nuevo y el
    mismo vencimiento absoluto (D-139)."""
    # El candado evita que dos cambios simultáneos con el mismo token abran dos sesiones.
    locked = db.scalar(
        select(UserSession)
        .where(UserSession.id == current.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or locked.revoked_at is not None:
        raise NotAuthenticated("SESSION_EXPIRED", "La sesión ya no es válida.")
    if organization_id == locked.organization_id:
        raise Conflict("SAME_ORGANIZATION", "Ya estás trabajando en esa organización.")
    target = _find_membership(active_memberships(db, user.id), organization_id)
    if target is None:
        audit.security_event(
            db,
            "organization_switch_denied",
            user_id=user.id,
            organization_id=locked.organization_id,
            ip_address=ip,
        )
        db.commit()
        raise organization_not_available()

    locked.revoked_at = datetime.now(UTC)
    issued = issue_session(db, user, target, user_agent, expires_at=locked.expires_at)
    # Un evento en cada organización, sin nombrar la otra: ninguna se entera de las demás.
    audit.security_event(
        db,
        "organization_switched",
        user_id=user.id,
        organization_id=locked.organization_id,
        ip_address=ip,
        details={"direction": "out"},
    )
    audit.security_event(
        db,
        "organization_switched",
        user_id=user.id,
        organization_id=target.organization_id,
        ip_address=ip,
        details={"direction": "in"},
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


def _user_snapshot(user: User, member: OrganizationMember) -> dict[str, object]:
    # `is_active`: en esta organización (D-137).
    return {
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active and member.is_active,
        "role": member.role_code,
    }


def _check_owner_grant(role: Role, actor_role: str) -> None:
    if role == Role.OWNER and actor_role != Role.OWNER:
        raise Forbidden("OWNER_ONLY", "Solo un propietario puede crear otro propietario.")


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
    _check_owner_grant(role, actor_role)
    if find_user_by_email(db, email) is not None:
        raise Conflict("EMAIL_TAKEN", EMAIL_TAKEN_MESSAGE)
    user = User(email=email, full_name=full_name, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # carrera con otro alta del mismo email
        db.rollback()
        raise Conflict("EMAIL_TAKEN", EMAIL_TAKEN_MESSAGE) from exc
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
        after=_user_snapshot(user, member),
    )
    db.commit()
    return user, member


def add_existing_member(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    email: str,
    role: Role,
) -> tuple[User, OrganizationMember]:
    """Suma a esta organización a un usuario que ya existe en la instalación (D-136).

    No toca su contraseña, su nombre ni sus membresías en otras organizaciones, y la respuesta
    no dice en cuáles está: solo lo que esta organización necesita para administrarlo."""
    _check_owner_grant(role, actor_role)
    user = find_user_by_email(db, email)
    if user is None:
        raise NotFound(
            "USER_NOT_FOUND", "No hay ningún usuario con ese email. Crealo con sus datos."
        )
    already = db.scalar(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if already is not None:
        raise Conflict("ALREADY_MEMBER", "Ese usuario ya es parte de esta organización.")
    member = OrganizationMember(organization_id=organization_id, user_id=user.id, role_code=role)
    db.add(member)
    try:
        db.flush()
    except IntegrityError as exc:  # carrera con otro alta del mismo usuario
        db.rollback()
        raise Conflict("ALREADY_MEMBER", "Ese usuario ya es parte de esta organización.") from exc
    audit.record(
        db,
        action="user.added",
        entity_type="user",
        entity_id=user.id,
        organization_id=organization_id,
        actor_user_id=actor_id,
        after=_user_snapshot(user, member),
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
                OrganizationMember.is_active.is_(True),
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
    before = _user_snapshot(user, member)

    touches_owner = member.role_code == Role.OWNER or role == Role.OWNER
    if touches_owner and actor_role != Role.OWNER:
        raise Forbidden("OWNER_ONLY", "Solo un propietario puede modificar propietarios.")
    if user_id == actor_id and (is_active is False or (role is not None and role != actor_role)):
        raise AppError("SELF_CHANGE_FORBIDDEN", "No podés desactivarte ni cambiar tu propio rol.")

    if role is not None:
        member.role_code = role
    if is_active is not None:
        # Solo en esta organización: en las demás sigue igual (D-137).
        member.is_active = is_active
    db.flush()

    # Siempre debe quedar al menos un propietario activo.
    if _active_owner_count(db, organization_id) == 0:
        db.rollback()
        raise Conflict("LAST_OWNER", "La organización tiene que conservar un propietario activo.")

    if is_active is False:
        db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.organization_id == organization_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    after = _user_snapshot(user, member)
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
