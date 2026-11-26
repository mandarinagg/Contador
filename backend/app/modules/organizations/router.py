import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.api.deps import Auth, AuthContext, DbSession, require
from app.core.errors import Forbidden
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.organizations import service
from app.modules.organizations.ruc import ruc_check_digit

# `/organization`: la de la sesión. `/organizations`: el alta de otra (D-136).
router = APIRouter(prefix="/organization", tags=["organization"])
organizations_router = APIRouter(prefix="/organizations", tags=["organization"])

LegalForm = Literal["EAS", "SA", "SRL", "UNIPERSONAL", "OTRA"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    trade_name: str | None
    legal_form: str
    ruc: str | None
    ruc_check_digit: str | None
    base_currency: str
    created_at: datetime
    updated_at: datetime


Ruc = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,8}$")]
RucCheckDigit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]


def _check_ruc_pair(ruc: str | None, check_digit: str | None) -> None:
    if (ruc is None) != (check_digit is None):
        raise ValueError("El RUC y su dígito verificador van juntos.")
    if ruc is not None and ruc_check_digit(ruc) != int(check_digit or -1):
        raise ValueError("El dígito verificador no corresponde a ese RUC.")


class OrganizationUpdate(BaseModel):
    legal_name: Name | None = None
    trade_name: Name | None = None
    legal_form: LegalForm | None = None
    ruc: Ruc | None = None
    ruc_check_digit: RucCheckDigit | None = None

    @model_validator(mode="after")
    def _ruc_pair(self) -> "OrganizationUpdate":
        _check_ruc_pair(self.ruc, self.ruc_check_digit)
        return self


class OrganizationCreate(BaseModel):
    legal_name: Name
    trade_name: Name | None = None
    legal_form: LegalForm
    ruc: Ruc | None = None
    ruc_check_digit: RucCheckDigit | None = None

    @model_validator(mode="after")
    def _ruc_pair(self) -> "OrganizationCreate":
        _check_ruc_pair(self.ruc, self.ruc_check_digit)
        return self


@router.get("", response_model=OrganizationOut)
def get_organization(
    auth: Annotated[AuthContext, Depends(require(Perm.ORGANIZATION_READ))],
) -> OrganizationOut:
    return OrganizationOut.model_validate(auth.organization)


@router.patch("", response_model=OrganizationOut)
def update_organization(
    body: OrganizationUpdate,
    auth: Annotated[AuthContext, Depends(require(Perm.ORGANIZATION_MANAGE))],
    db: DbSession,
) -> OrganizationOut:
    org = auth.organization
    # Solo se auditan los campos que realmente cambian.
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if getattr(org, k) != v}
    before = {k: getattr(org, k) for k in changes}
    if changes.get("ruc") is not None:
        service.ensure_ruc_available(db, changes["ruc"], exclude_id=org.id)
    for key, value in changes.items():
        setattr(org, key, value)
    service.flush_checking_ruc(db)
    after = {k: getattr(org, k) for k in changes}
    if changes:
        audit.record(
            db,
            action="organization.updated",
            entity_type="organization",
            entity_id=org.id,
            organization_id=org.id,
            actor_user_id=auth.user_id,
            before=before,
            after=after,
        )
    db.commit()
    db.refresh(org)
    return OrganizationOut.model_validate(org)


@organizations_router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(body: OrganizationCreate, auth: Auth, db: DbSession) -> OrganizationOut:
    """Alta de otra organización (respuesta 3 del propietario, D-136): la puede hacer quien sea
    propietario activo de alguna, y queda como su propietario. No cambia la sesión: para
    trabajar en ella, `POST /auth/switch`."""
    if not service.is_active_owner_somewhere(db, auth.user_id):
        raise Forbidden(
            "OWNER_ONLY", "Solo el propietario de una organización puede dar de alta otra."
        )
    org, _ = service.create_organization(
        db,
        owner_user_id=auth.user_id,
        legal_name=body.legal_name,
        trade_name=body.trade_name,
        legal_form=body.legal_form,
        ruc=body.ruc,
        ruc_check_digit=body.ruc_check_digit,
    )
    audit.record(
        db,
        action="organization.created",
        entity_type="organization",
        entity_id=org.id,
        organization_id=org.id,
        actor_user_id=auth.user_id,
        after={
            "legal_name": org.legal_name,
            "trade_name": org.trade_name,
            "legal_form": org.legal_form,
            "ruc": org.ruc,
            "ruc_check_digit": org.ruc_check_digit,
        },
    )
    db.commit()
    db.refresh(org)
    return OrganizationOut.model_validate(org)
