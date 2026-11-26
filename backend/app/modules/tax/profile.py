"""Perfil fiscal versionado (D-083, BR-TAX-04).

- Lo declara el propietario (`origin = declared`) y lo verifica CONTADOR AI contra la
  constancia de RUC (`verified`, D-094, D-120): quién verificó, la fuente y la referencia de
  la constancia; el usuario que aprobó queda en `verified_by`.
- Cada versión rige desde su `valid_from`. Una versión nueva con la misma fecha que una
  declarada la **corrige** (queda auditado el antes y el después); si esa versión ya está
  verificada, no cambia (409): se carga otra con otra fecha.
- El RUC y el DV salen de `core.organizations` y son obligatorios (también lo exige el
  trigger `profiles_guard`). Sin perfil no hay obligaciones.
- Coherencia mínima, para no generar obligaciones contradictorias (`_check_consistency`):
  211 (IVA) solo si es contribuyente del IVA; cada obligación del IRE (700, 701, 702) con su
  régimen y nunca dos juntas; el IRP (715, 716) y la 956 solo para una persona física, con
  el cierre en diciembre; el RESIMPLE sin IVA; la 956 sin la 211 (D-142). El backend no
  exige contabilidad a nadie: eso es un aviso del frontend.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.core.verification import PROFILE_SOURCE, TOOL_VERIFIER
from app.modules.organizations.models import Organization
from app.modules.tax.common import flush_translated, jsonable, now, record, snapshot
from app.modules.tax.models import Profile, ProfileObligation

PROFILE_FIELDS = ("valid_from", "ire_regime", "fiscal_close_month", "vat_taxpayer", "notes")
VERIFICATION_FIELDS = (
    "origin",
    "verified_by_name",
    "verified_license",
    "verified_document_reference",
    "verified_at",
)


@dataclass(frozen=True)
class ProfileVersion:
    profile: Profile
    obligations: list[ProfileObligation]


def profile_not_found() -> NotFound:
    return NotFound("PROFILE_NOT_FOUND", "El perfil fiscal no existe.")


def _obligations_of(db: Session, profile_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Any]]:
    result: dict[uuid.UUID, list[Any]] = {pid: [] for pid in profile_ids}
    if profile_ids:
        rows = db.scalars(
            select(ProfileObligation)
            .where(ProfileObligation.profile_id.in_(profile_ids))
            .order_by(ProfileObligation.code)
        )
        for row in rows:
            result[row.profile_id].append(row)
    return result


def versions(db: Session, organization_id: uuid.UUID) -> list[ProfileVersion]:
    """Todas las versiones, de la más antigua a la más nueva."""
    profiles = list(
        db.scalars(
            select(Profile)
            .where(Profile.organization_id == organization_id)
            .order_by(Profile.valid_from)
        )
    )
    obligations = _obligations_of(db, [p.id for p in profiles])
    return [ProfileVersion(p, obligations[p.id]) for p in profiles]


def vigente(history: list[ProfileVersion], day: date) -> ProfileVersion | None:
    """La versión que rige en `day` (la última con `valid_from ≤ day`)."""
    current = None
    for version in history:
        if version.profile.valid_from <= day:
            current = version
    return current


def _obligations_snapshot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"code": r["code"], "registered_on": jsonable(r["registered_on"])} for r in rows]


_IRE_OBLIGATIONS = {"700": "ire_general", "701": "ire_simple", "702": "resimple"}
_IRE_NAMES = {
    "700": "IRE General",
    "701": "IRE SIMPLE",
    "702": "IRE RESIMPLE",
}
_REGIME_NAMES = {
    "ire_general": "el IRE General",
    "ire_simple": "el IRE SIMPLE",
    "resimple": "el RESIMPLE",
    "none": "«sin IRE»",
}
_IRP_OBLIGATIONS = {"715": "IRP-RSP", "716": "IRP-RGC"}
# Formas jurídicas que son contribuyentes del IRE por sí mismas (Ley 6380/2019, art. 2°).
_COMPANY_FORMS = frozenset({"EAS", "SA", "SRL", "UNIPERSONAL"})
_RESIMPLE_FORMS = frozenset({"PERSONA_FISICA", "UNIPERSONAL"})


def _check_consistency(data: dict[str, Any], legal_form: str) -> None:
    codes = [o["code"] for o in data["obligations"]]
    if len(codes) != len(set(codes)):
        raise AppError(
            "PROFILE_DUPLICATE_OBLIGATION",
            "Una obligación figura dos veces: cada código va una sola vez.",
            status_code=422,
        )
    regime = data["ire_regime"]
    person = legal_form == "PERSONA_FISICA"
    problems: list[str] = []
    if "211" in codes and not data["vat_taxpayer"]:
        problems.append("La obligación 211 (IVA General) es de contribuyentes del IVA.")
    ire = [c for c in _IRE_OBLIGATIONS if c in codes]
    if len(ire) > 1:
        names = " y ".join(f"{_IRE_NAMES[c]} ({c})" for c in ire)
        problems.append(f"No se puede estar en más de un régimen del IRE a la vez: {names}.")
    for code in ire:
        expected = _IRE_OBLIGATIONS[code]
        if code == "702" and regime != expected:
            problems.append(
                "La obligación 702 es del IRE RESIMPLE: elegí el régimen RESIMPLE para cargarla."
            )
        elif code != "702" and regime in _REGIME_NAMES and regime != expected:
            problems.append(
                f"La obligación {code} es del {_IRE_NAMES[code]}, pero el régimen es "
                f"{_REGIME_NAMES[regime]}."
            )
    if regime == "resimple" and legal_form not in _RESIMPLE_FORMS:
        problems.append(
            "El RESIMPLE es solo para empresas unipersonales de una persona física "
            "(Ley 6380/2019, art. 27)."
        )
    if regime == "none" and legal_form in _COMPANY_FORMS:
        problems.append(
            "Una empresa es contribuyente del IRE (Ley 6380/2019, art. 2°): elegí su régimen "
            "o «Todavía no lo sé»."
        )
    if regime == "resimple" and "211" in codes:
        problems.append(
            "Quien liquida por el RESIMPLE no es contribuyente del IVA (Ley 6380/2019, art. 27, "
            "último párrafo): no puede tener la obligación 211."
        )
    irp = [c for c in _IRP_OBLIGATIONS if c in codes]
    for code in irp:
        if not person:
            problems.append(
                f"La obligación {code} ({_IRP_OBLIGATIONS[code]}) es del impuesto a la renta "
                "personal: solo la tiene una persona física, no una empresa."
            )
    if irp and person and data["fiscal_close_month"] != 12:
        problems.append(
            "El ejercicio del IRP es el año civil (Ley 6380/2019, art. 52): con la obligación "
            f"{' o '.join(irp)} el cierre del ejercicio es en diciembre."
        )
    if "956" in codes:
        if "211" in codes:
            problems.append(
                "Con la 211 (IVA) el registro de comprobantes es el mensual, 955, no el anual 956 "
                "(RG 90/2021, art. 7°, texto de la RG DNIT 12/2024)."
            )
        if "715" not in codes:
            problems.append(
                "El registro anual de comprobantes (956) va con la obligación 715 (IRP-RSP) "
                "(RG 90/2021, art. 7°, texto de la RG DNIT 12/2024)."
            )
    if problems:
        raise AppError(
            "PROFILE_INCONSISTENT",
            " ".join(problems),
            details={"problems": problems},
            status_code=422,
        )


def put_version(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> ProfileVersion:
    """Alta de una versión (o corrección de la declarada con la misma fecha)."""
    org = db.get(Organization, organization_id)
    if org is None or org.ruc is None or org.ruc_check_digit is None:
        raise AppError(
            "PROFILE_REQUIRES_RUC",
            "Cargá el RUC y su dígito verificador en los datos de la organización antes del "
            "perfil fiscal: los vencimientos dependen de la terminación del RUC.",
            status_code=422,
        )
    _check_consistency(data, org.legal_form)
    existing = db.scalar(
        select(Profile)
        .where(Profile.organization_id == organization_id, Profile.valid_from == data["valid_from"])
        .with_for_update()
    )
    fields = {k: data.get(k) for k in PROFILE_FIELDS}
    new_obligations = _obligations_snapshot(data["obligations"])
    if existing is not None:
        if existing.origin == "verified":
            raise Conflict(
                "PROFILE_VERIFIED",
                f"La versión del perfil desde el {existing.valid_from:%d/%m/%Y} está verificada: "
                "no cambia. Cargá una versión nueva con otra fecha.",
            )
        old_obligations = [
            {"code": o.code, "registered_on": jsonable(o.registered_on)}
            for o in _obligations_of(db, [existing.id])[existing.id]
        ]
        before = snapshot(existing, PROFILE_FIELDS) | {"obligations": old_obligations}
        for key, value in fields.items():
            setattr(existing, key, value)
        db.execute(delete(ProfileObligation).where(ProfileObligation.profile_id == existing.id))
        profile = existing
        verb = "replaced"
    else:
        profile = Profile(
            organization_id=organization_id, origin="declared", created_by=actor_id, **fields
        )
        db.add(profile)
        before = None
        verb = "created"
    flush_translated(db)
    for row in data["obligations"]:
        db.add(
            ProfileObligation(
                organization_id=organization_id,
                profile_id=profile.id,
                code=row["code"],
                registered_on=row["registered_on"],
            )
        )
    flush_translated(db)
    after = snapshot(profile, PROFILE_FIELDS) | {"obligations": new_obligations}
    record(db, organization_id, actor_id, "profile", verb, profile.id, before=before, after=after)
    return ProfileVersion(profile, _obligations_of(db, [profile.id])[profile.id])


def verify(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    profile_id: uuid.UUID,
    *,
    verified_document_reference: str,
) -> ProfileVersion:
    profile = db.scalar(
        select(Profile)
        .where(Profile.id == profile_id, Profile.organization_id == organization_id)
        .with_for_update()
    )
    if profile is None:
        raise profile_not_found()
    if profile.origin == "verified":
        raise Conflict("PROFILE_VERIFIED", "Esta versión del perfil ya está verificada.")
    before = snapshot(profile, VERIFICATION_FIELDS)
    profile.origin = "verified"
    profile.verified_by_name = TOOL_VERIFIER
    profile.verified_license = PROFILE_SOURCE
    profile.verified_document_reference = verified_document_reference
    profile.verified_at = now()
    profile.verified_by = actor_id
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "profile",
        "verified",
        profile.id,
        before=before,
        after=snapshot(profile, VERIFICATION_FIELDS),
    )
    db.commit()
    return ProfileVersion(profile, _obligations_of(db, [profile.id])[profile.id])
