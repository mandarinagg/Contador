import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.api.deps import AuthContext, DbSession, require
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.organizations.ruc import ruc_check_digit

router = APIRouter(prefix="/organization", tags=["organization"])

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


class OrganizationUpdate(BaseModel):
    legal_name: Name | None = None
    trade_name: Name | None = None
    legal_form: LegalForm | None = None
    ruc: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,8}$")] | None = None
    ruc_check_digit: Annotated[str, StringConstraints(pattern=r"^[0-9]$")] | None = None

    @model_validator(mode="after")
    def _ruc_pair(self) -> "OrganizationUpdate":
        if (self.ruc is None) != (self.ruc_check_digit is None):
            raise ValueError("El RUC y su dígito verificador van juntos.")
        if self.ruc is not None and ruc_check_digit(self.ruc) != int(self.ruc_check_digit or -1):
            raise ValueError("El dígito verificador no corresponde a ese RUC.")
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
    for key, value in changes.items():
        setattr(org, key, value)
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
