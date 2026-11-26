import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.core.permissions import Role
from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


def _strong_password(value: str) -> str:
    if value.strip() != value:
        raise ValueError("La contraseña no puede empezar ni terminar con espacios.")
    classes = sum(
        [
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(not c.isalnum() for c in value),
        ]
    )
    if classes < 3:
        raise ValueError("Usá al menos tres de: minúsculas, mayúsculas, números y símbolos.")
    return value


Password = Annotated[
    str,
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
    AfterValidator(_strong_password),
]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    # Opcional: sin ella abre la usada por última vez, si no la membresía más antigua (D-138).
    organization_id: uuid.UUID | None = None


class SwitchOrganizationRequest(BaseModel):
    organization_id: uuid.UUID


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    last_login_at: datetime | None


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    legal_name: str
    trade_name: str | None
    legal_form: str


class MembershipOut(BaseModel):
    """Una organización a la que el usuario tiene acceso, con su rol ahí."""

    id: uuid.UUID
    legal_name: str
    trade_name: str | None
    legal_form: str
    ruc: str | None
    ruc_check_digit: str | None
    role: str
    is_current: bool


class MeResponse(BaseModel):
    user: UserOut
    organization: OrganizationSummary
    role: str
    permissions: list[str]


class LoginResponse(MeResponse):
    token: str
    expires_at: datetime
    # Las organizaciones activas del usuario, para ofrecer elegir otra (D-138).
    organizations: list[MembershipOut]


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: Password


class MemberOut(BaseModel):
    user: UserOut
    role: str
    member_since: datetime


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: FullName
    password: Password
    role: Role


class AddExistingUserRequest(BaseModel):
    email: EmailStr
    role: Role


class UpdateMemberRequest(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class RoleOut(BaseModel):
    code: str
    name: str
    description: str
    permissions: list[str]
