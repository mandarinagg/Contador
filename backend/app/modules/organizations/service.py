"""Alta de organizaciones y RUC único (fase M2 del plan multiempresa).

Lo usan el setup (D-009, solo con la base vacía) y `POST /organizations` (D-136).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.core.permissions import Role
from app.modules.finance import service as finance
from app.modules.identity.models import User
from app.modules.marangatu import credentials
from app.modules.organizations.models import Organization, OrganizationMember

RUC_INDEX = "uq_organizations_ruc"


def ruc_taken() -> Conflict:
    return Conflict("RUC_TAKEN", "Ya hay otra organización con ese RUC en esta instalación.")


def ensure_ruc_available(db: Session, ruc: str | None, *, exclude_id: uuid.UUID | None) -> None:
    """409 `RUC_TAKEN` si otra organización ya tiene ese RUC (D-135). El índice único parcial
    de la 0008 es la garantía; esto da el error claro sin esperar a la base."""
    if ruc is None:
        return
    query = select(Organization.id).where(Organization.ruc == ruc)
    if exclude_id is not None:
        query = query.where(Organization.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise ruc_taken()


def ensure_ruc_changeable(current_ruc: str | None) -> None:
    """409 `MARANGATU_CREDENTIALS_EXIST` si hay una clave de Marangatu guardada para el RUC
    actual (D-140). La clave del almacén es por RUC (D-128): cambiarlo la dejaría huérfana, y
    con ella otra organización que tomara ese RUC después. Primero se borra la clave. Sin RUC
    actual no hay clave posible. Si el almacén no responde no se puede saber (ni nadie puede
    leerla): no se bloquea un cambio de datos por eso."""
    if current_ruc is None:
        return
    try:
        saved = credentials.has_password(current_ruc)
    except credentials.CredentialStoreError:
        return
    if saved:
        raise Conflict(
            "MARANGATU_CREDENTIALS_EXIST",
            "Hay una clave de Marangatu guardada para este RUC: borrá la clave de Marangatu "
            "antes de cambiar el RUC.",
        )


def flush_checking_ruc(db: Session) -> None:
    """`flush` que traduce la violación del índice de RUC (carrera entre dos altas) a 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        if RUC_INDEX not in str(exc.orig):
            raise
        db.rollback()
        raise ruc_taken() from exc


def is_active_owner_somewhere(db: Session, user_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(OrganizationMember.id)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.role_code == Role.OWNER,
                OrganizationMember.is_active.is_(True),
                User.is_active.is_(True),
            )
            .limit(1)
        )
        is not None
    )


def person_legal_name(first_names: str | None, last_names: str | None) -> str:
    """La razón social de una persona física, única fuente: «Apellidos, Nombres» (D-141)."""
    return f"{last_names}, {first_names}"


def check_identity_patch(org: Organization, sent: dict[str, object]) -> None:
    """422 si el cambio mezcla empresa y persona física: la forma jurídica no pasa de una a
    la otra, los nombres son solo de la persona y su razón social se calcula (D-141)."""

    def refuse(message: str) -> AppError:
        return AppError("VALIDATION_ERROR", message, status_code=422)

    is_person = org.legal_form == "PERSONA_FISICA"
    form = sent.get("legal_form", org.legal_form)
    if (form == "PERSONA_FISICA") != is_person:
        raise refuse("La forma jurídica no pasa de empresa a persona física ni al revés.")
    if is_person and "legal_name" in sent:
        raise refuse("La razón social de una persona física se calcula de su nombre.")
    if not is_person and ("first_names" in sent or "last_names" in sent):
        raise refuse("Los nombres y apellidos son solo de una persona física.")


def create_organization(
    db: Session,
    *,
    owner_user_id: uuid.UUID,
    legal_name: str | None,
    trade_name: str | None,
    legal_form: str,
    first_names: str | None = None,
    last_names: str | None = None,
    ruc: str | None = None,
    ruc_check_digit: str | None = None,
) -> tuple[Organization, OrganizationMember]:
    """Organización, su propietario y su contexto financiero empresarial (D-023), en la
    transacción del que llama (no hace `commit` ni audita: cada llamador deja su registro)."""
    ensure_ruc_available(db, ruc, exclude_id=None)
    if legal_form == "PERSONA_FISICA":
        legal_name = person_legal_name(first_names, last_names)
    org = Organization(
        legal_name=legal_name or "",
        trade_name=trade_name,
        legal_form=legal_form,
        first_names=first_names,
        last_names=last_names,
        ruc=ruc,
        ruc_check_digit=ruc_check_digit,
    )
    db.add(org)
    flush_checking_ruc(db)
    member = OrganizationMember(organization_id=org.id, user_id=owner_user_id, role_code=Role.OWNER)
    db.add(member)
    finance.create_business_context(db, org.id)
    db.flush()
    return org, member
