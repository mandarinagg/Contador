import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, AuthContext, DbSession, client_ip, load_permissions, require
from app.core.permissions import Perm
from app.modules.identity import service
from app.modules.identity.models import PermissionRow, RolePermission, RoleRow, User
from app.modules.identity.schemas import (
    AddExistingUserRequest,
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    MemberOut,
    MembershipOut,
    MeResponse,
    OrganizationSummary,
    RoleOut,
    SwitchOrganizationRequest,
    UpdateMemberRequest,
    UserOut,
)
from app.modules.organizations.models import Organization, OrganizationMember

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


def _org_summary(org: Organization) -> OrganizationSummary:
    return OrganizationSummary(
        id=org.id, legal_name=org.legal_name, trade_name=org.trade_name, legal_form=org.legal_form
    )


def organizations_of(
    db: Session, user_id: uuid.UUID, current_id: uuid.UUID | None
) -> list[MembershipOut]:
    """Las organizaciones activas del usuario, por nombre."""
    rows = [
        MembershipOut(
            id=m.organization.id,
            legal_name=m.organization.legal_name,
            trade_name=m.organization.trade_name,
            legal_form=m.organization.legal_form,
            ruc=m.organization.ruc,
            ruc_check_digit=m.organization.ruc_check_digit,
            role=m.member.role_code,
            is_current=m.organization.id == current_id,
        )
        for m in service.active_memberships(db, user_id)
    ]
    return sorted(rows, key=lambda r: (r.legal_name.casefold(), str(r.id)))


def session_response(db: Session, issued: service.IssuedSession) -> LoginResponse:
    """Respuesta de toda sesión nueva: ingreso, cambio de organización y setup."""
    user = db.get_one(User, issued.session.user_id)
    org = db.get_one(Organization, issued.member.organization_id)
    return LoginResponse(
        token=issued.token,
        expires_at=issued.session.expires_at,
        user=UserOut.model_validate(user),
        organization=_org_summary(org),
        role=issued.member.role_code,
        permissions=sorted(load_permissions(db, issued.member.role_code)),
        organizations=organizations_of(db, user.id, org.id),
    )


@auth_router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    issued = service.login(
        db,
        body.email,
        body.password,
        organization_id=body.organization_id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return session_response(db, issued)


@auth_router.get("/organizations", response_model=list[MembershipOut])
def list_my_organizations(auth: Auth, db: DbSession) -> list[MembershipOut]:
    return organizations_of(db, auth.user_id, auth.organization_id)


@auth_router.post("/switch", response_model=LoginResponse)
def switch_organization(
    body: SwitchOrganizationRequest, auth: Auth, request: Request, db: DbSession
) -> LoginResponse:
    """Cambia de organización: el token actual deja de valer y se entrega uno nuevo."""
    issued = service.switch_organization(
        db,
        auth.user,
        auth.session,
        body.organization_id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return session_response(db, issued)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(auth: Auth, request: Request, db: DbSession) -> Response:
    service.logout(db, auth.session, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_router.get("/me", response_model=MeResponse)
def me(auth: Auth) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(auth.user),
        organization=_org_summary(auth.organization),
        role=auth.role_code,
        permissions=sorted(auth.permissions),
    )


@auth_router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest, auth: Auth, request: Request, db: DbSession
) -> Response:
    service.change_password(
        db,
        auth.user,
        auth.session,
        body.current_password,
        body.new_password,
        ip=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _member_out(user: User, member: OrganizationMember) -> MemberOut:
    # `user.is_active` dice si está activo en ESTA organización (D-137).
    out = UserOut.model_validate(user).model_copy(
        update={"is_active": user.is_active and member.is_active}
    )
    return MemberOut(user=out, role=member.role_code, member_since=member.created_at)


@users_router.get("", response_model=list[MemberOut])
def list_users(
    auth: Annotated[AuthContext, Depends(require(Perm.USERS_READ))], db: DbSession
) -> list[MemberOut]:
    return [_member_out(u, m) for u, m in service.list_members(db, auth.organization_id)]


@users_router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    auth: Annotated[AuthContext, Depends(require(Perm.USERS_MANAGE))],
    db: DbSession,
) -> MemberOut:
    user, member = service.create_member(
        db,
        organization_id=auth.organization_id,
        actor_id=auth.user_id,
        actor_role=auth.role_code,
        email=str(body.email),
        full_name=body.full_name,
        password=body.password,
        role=body.role,
    )
    return _member_out(user, member)


@users_router.post("/existing", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_existing_user(
    body: AddExistingUserRequest,
    auth: Annotated[AuthContext, Depends(require(Perm.USERS_MANAGE))],
    db: DbSession,
) -> MemberOut:
    """Suma a un usuario que ya existe (con su contraseña de siempre) a esta organización."""
    user, member = service.add_existing_member(
        db,
        organization_id=auth.organization_id,
        actor_id=auth.user_id,
        actor_role=auth.role_code,
        email=str(body.email),
        role=body.role,
    )
    return _member_out(user, member)


@users_router.patch("/{user_id}", response_model=MemberOut)
def update_user(
    user_id: uuid.UUID,
    body: UpdateMemberRequest,
    auth: Annotated[AuthContext, Depends(require(Perm.USERS_MANAGE))],
    db: DbSession,
) -> MemberOut:
    user, member = service.update_member(
        db,
        organization_id=auth.organization_id,
        actor_id=auth.user_id,
        actor_role=auth.role_code,
        user_id=user_id,
        role=body.role,
        is_active=body.is_active,
    )
    return _member_out(user, member)


@users_router.get("/roles", response_model=list[RoleOut])
def list_roles(
    _: Annotated[AuthContext, Depends(require(Perm.USERS_READ))], db: DbSession
) -> list[RoleOut]:
    roles = db.scalars(select(RoleRow)).all()
    links = db.execute(select(RolePermission.role_code, RolePermission.permission_code)).all()
    by_role: dict[str, list[str]] = {}
    for role_code, perm in links:
        by_role.setdefault(role_code, []).append(perm)
    order = {"owner": 0, "admin": 1, "accountant": 2, "viewer": 3}
    return [
        RoleOut(
            code=r.code,
            name=r.name,
            description=r.description,
            permissions=sorted(by_role.get(r.code, [])),
        )
        for r in sorted(roles, key=lambda r: order.get(r.code, 99))
    ]


@users_router.get("/permissions", response_model=dict[str, str])
def list_permissions(
    _: Annotated[AuthContext, Depends(require(Perm.USERS_READ))], db: DbSession
) -> dict[str, str]:
    return {
        p.code: p.description
        for p in db.scalars(select(PermissionRow).order_by(PermissionRow.code))
    }
