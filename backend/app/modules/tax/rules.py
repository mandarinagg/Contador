"""Motor de reglas versionado (D-082, D-084, BR-TAX-01/02).

- Las reglas son datos globales (`tax.rule_versions`), cargados desde la copia empaquetada
  del YAML de la investigación. La carga es idempotente: una versión que ya está igual no se
  toca, una que cambió en el YAML no se pisa (se informa en `differing`) y una cuyos
  `parameters` no cumplen el esquema de su código no se carga (`rejected`).
- Una versión no se edita: solo cambia su estado (`pending → verified`, `cualquiera →
  deprecated` con motivo). Lo impone también el trigger.
- Verifica la herramienta (D-118, D-120): solo una regla con la fuente oficial leída
  (`confidence = oficial_leida`, URL, referencia legal y fecha de consulta). La que no cumple
  sigue `pending`.
- Regla vigente a una fecha: la versión no deprecada con `valid_from ≤ fecha ≤ valid_to`.
  Una regla sin `valid_from` (fecha desconocida) nunca está vigente: «sin regla».
- D-082: una regla `pending` sí se usa, y todo lo que depende de ella informa
  `rule_status: "pending"` («sin verificar contra la fuente oficial»).
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.core.verification import TOOL_VERIFIER, source_reference
from app.modules.tax import candidate_rules, rule_params
from app.modules.tax.common import flush_translated, jsonable, now, record, snapshot
from app.modules.tax.models import DueDateException, RuleVersion

CONTENT_FIELDS = (
    "description",
    "parameters",
    "valid_from",
    "valid_to",
    "published_at",
    "source_url",
    "legal_reference",
    "consulted_at",
    "confidence",
    "notes",
)
STATE_FIELDS = (
    "validation_status",
    "reviewed_by_name",
    "reviewed_reference",
    "reviewed_at",
    "review_note",
    "deprecation_reason",
    "deprecated_at",
)
_DATE_FIELDS = ("valid_from", "valid_to", "published_at", "consulted_at")


@dataclass
class LoadResult:
    created: list[RuleVersion] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    differing: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    exceptions_created: int = 0


def rule_not_found() -> NotFound:
    return NotFound("RULE_NOT_FOUND", "La regla no existe.")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _content(row: dict[str, Any]) -> dict[str, Any]:
    """Campos de una regla del YAML, en los tipos de la base."""
    content: dict[str, Any] = {
        "description": _text(row.get("description")) or "",
        "parameters": row.get("parameters"),
        "source_url": _text(row.get("source_url")),
        "legal_reference": _text(row.get("legal_reference")),
        "confidence": row.get("confidence"),
        "notes": _text(row.get("notes")),
    }
    for name in _DATE_FIELDS:
        value = row.get(name)
        content[name] = date.fromisoformat(value) if isinstance(value, str) else value
    return content


def _same(rule: RuleVersion, content: dict[str, Any]) -> bool:
    return all(getattr(rule, name) == content[name] for name in CONTENT_FIELDS)


def _lock_loading(db: Session) -> None:
    # Dos cargas simultáneas se serializan (la segunda ve lo que dejó la primera).
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('tax.rules.load', 0))"))


def load_candidates(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    rows: Sequence[dict[str, Any]] | None = None,
) -> LoadResult:
    """Carga las reglas candidatas empaquetadas (idempotente)."""
    rows = candidate_rules.RULES if rows is None else rows
    _lock_loading(db)
    result = LoadResult()
    for row in rows:
        code = str(row.get("code", ""))
        version = int(row.get("version", 1))
        if row.get("validation_status", "pending") != "pending":
            result.rejected.append(
                {"code": code, "errors": ["La carga solo acepta reglas pendientes."]}
            )
            continue
        content = _content(row)
        problems = rule_params.errors(code, content["parameters"])
        if not content["description"]:
            problems.append("description: falta la descripción.")
        if problems:
            result.rejected.append({"code": code, "errors": problems})
            continue
        existing = db.scalar(
            select(RuleVersion).where(RuleVersion.code == code, RuleVersion.version == version)
        )
        if existing is not None:
            if _same(existing, content):
                result.unchanged.append(code)
                result.exceptions_created += _ensure_exceptions(
                    db, organization_id, actor_id, existing
                )
            else:
                result.differing.append(code)
            continue
        rule = RuleVersion(code=code, version=version, validation_status="pending", **content)
        db.add(rule)
        try:
            flush_translated(db)
        except Conflict as exc:
            if rule in db:
                db.expunge(rule)
            result.rejected.append({"code": code, "errors": [exc.message]})
            continue
        record(
            db,
            organization_id,
            actor_id,
            "rule_version",
            "created",
            rule.id,
            after={"code": code, "version": version}
            | rule_params.as_text(snapshot(rule, CONTENT_FIELDS)),
        )
        result.created.append(rule)
        result.exceptions_created += _ensure_exceptions(db, organization_id, actor_id, rule)
    record(
        db,
        organization_id,
        actor_id,
        "rules",
        "loaded",
        organization_id,
        after={
            "source": "candidates",
            "generated_at": candidate_rules.META.get("generated_at"),
            "created": [r.code for r in result.created],
            "unchanged": len(result.unchanged),
            "differing": result.differing,
            "rejected": [r["code"] for r in result.rejected],
        },
    )
    db.commit()
    return result


def _ensure_exceptions(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, rule: RuleVersion
) -> int:
    """Una regla `CAL-EXCEPCION-*` se materializa como excepciones fechadas (D-086): una
    por cada fecha nueva, con las terminaciones que van a esa fecha."""
    if not rule.code.startswith(rule_params.EXCEPTION_PREFIX):
        return 0
    params = rule_params.parse(rule.code, rule.parameters)
    assert isinstance(params, rule_params.ExceptionParams)
    by_date: dict[date, list[int]] = {}
    for digit, new_date in params.new_date_by_digit.items():
        by_date.setdefault(new_date, []).append(int(digit))
    existing = set(
        db.scalars(
            select(DueDateException.new_due_date).where(DueDateException.rule_version_id == rule.id)
        )
    )
    created = 0
    for new_date, digits in sorted(by_date.items()):
        if new_date in existing:
            continue
        exception = DueDateException(
            obligation_group="determinative",
            due_month=params.due_month,
            ruc_digits=sorted(digits),
            new_due_date=new_date,
            legal_reference=rule.legal_reference or rule.code,
            source_url=rule.source_url,
            rule_version_id=rule.id,
            origin="candidate",
            notes=("No incluye: " + ", ".join(params.excludes) + "." if params.excludes else None),
            created_by=actor_id,
        )
        db.add(exception)
        db.flush()
        record(
            db,
            organization_id,
            actor_id,
            "due_date_exception",
            "created",
            exception.id,
            after=snapshot(
                exception,
                (
                    "obligation_group",
                    "due_month",
                    "ruc_digits",
                    "new_due_date",
                    "legal_reference",
                    "rule_version_id",
                ),
            ),
        )
        created += 1
    return created


def list_rules(
    db: Session, *, code: str | None, status: str | None, at: date | None
) -> list[RuleVersion]:
    query = select(RuleVersion)
    if code:
        query = query.where(RuleVersion.code == code)
    if status:
        query = query.where(RuleVersion.validation_status == status)
    if at is not None:
        query = query.where(*_valid_at(at))
    return list(db.scalars(query.order_by(RuleVersion.code, RuleVersion.version)))


def get_rule(db: Session, rule_id: uuid.UUID, *, lock: bool = False) -> RuleVersion:
    query = select(RuleVersion).where(RuleVersion.id == rule_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    rule = db.scalar(query)
    if rule is None:
        raise rule_not_found()
    return rule


def _valid_at(day: date) -> tuple[Any, ...]:
    return (
        RuleVersion.validation_status != "deprecated",
        RuleVersion.valid_from.is_not(None),
        RuleVersion.valid_from <= day,
        or_(RuleVersion.valid_to.is_(None), RuleVersion.valid_to >= day),
    )


def rule_for(db: Session, code: str, day: date) -> RuleVersion | None:
    """Versión vigente de `code` a `day`, o `None` («sin regla»)."""
    return db.scalar(select(RuleVersion).where(RuleVersion.code == code, *_valid_at(day)))


class RuleCache:
    """Reglas vigentes de un cálculo largo (sincronizar el calendario de muchos períodos)."""

    def __init__(self, db: Session, codes: Iterable[str]):
        self._rules: dict[str, list[RuleVersion]] = {}
        rows = db.scalars(
            select(RuleVersion).where(
                RuleVersion.code.in_(list(codes)),
                RuleVersion.validation_status != "deprecated",
                RuleVersion.valid_from.is_not(None),
            )
        )
        for rule in rows:
            self._rules.setdefault(rule.code, []).append(rule)

    def at(self, code: str, day: date) -> RuleVersion | None:
        for rule in self._rules.get(code, []):
            assert rule.valid_from is not None
            if rule.valid_from <= day and (rule.valid_to is None or rule.valid_to >= day):
                return rule
        return None


def applied(rule: RuleVersion) -> dict[str, Any]:
    """Elemento de `rules_applied` (BR-TAX-02)."""
    return {
        "id": rule.id,
        "code": rule.code,
        "version": rule.version,
        "validation_status": rule.validation_status,
        "legal_reference": rule.legal_reference,
    }


def worst_status(rules: Iterable[RuleVersion]) -> str | None:
    """`verified` solo si todas lo están (D-082); `None` si no se aplicó ninguna."""
    statuses = {r.validation_status for r in rules}
    if not statuses:
        return None
    return "verified" if statuses == {"verified"} else "pending"


def unverifiable_reason(rule: RuleVersion) -> str | None:
    """Por qué la herramienta no puede verificar la regla (`None` si puede, D-120)."""
    if rule.confidence != "oficial_leida":
        return (
            "La fuente oficial no se leyó (confianza "
            f"«{rule.confidence or 'sin indicar'}»): no se verifica de memoria ni por terceros."
        )
    missing = [
        label
        for label, value in (
            ("la URL de la fuente", rule.source_url),
            ("la referencia legal", rule.legal_reference),
            ("la fecha de consulta", rule.consulted_at),
        )
        if not value
    ]
    if missing:
        return "Le falta " + " y ".join(missing) + "."
    return None


def _mark_verified(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    rule: RuleVersion,
    review_note: str | None,
) -> None:
    before = snapshot(rule, STATE_FIELDS)
    rule.validation_status = "verified"
    rule.reviewed_by_name = TOOL_VERIFIER
    rule.reviewed_reference = source_reference(rule.legal_reference or "")
    rule.reviewed_at = now()
    rule.review_note = review_note
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "rule_version",
        "verified",
        rule.id,
        before=before,
        after=snapshot(rule, STATE_FIELDS),
    )


def verify(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    rule_id: uuid.UUID,
    *,
    review_note: str | None,
) -> RuleVersion:
    rule = get_rule(db, rule_id, lock=True)
    if rule.validation_status != "pending":
        raise Conflict(
            "RULE_NOT_PENDING",
            f"La regla {rule.code} (versión {rule.version}) está {rule.validation_status}: solo "
            "se verifica una pendiente.",
        )
    reason = unverifiable_reason(rule)
    if reason is not None:
        raise AppError(
            "RULE_NOT_VERIFIABLE",
            f"CONTADOR AI no puede verificar la regla {rule.code}: {reason}",
            {"code": rule.code, "version": rule.version, "reason": reason},
            status_code=422,
        )
    _mark_verified(db, organization_id, actor_id, rule, review_note)
    db.commit()
    return rule


@dataclass
class BulkVerifyResult:
    verified: list[RuleVersion] = field(default_factory=list)
    left_pending: list[tuple[RuleVersion, str]] = field(default_factory=list)


def verify_verifiable(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID
) -> BulkVerifyResult:
    """Verifica de una vez las pendientes con fuente oficial leída; informa las demás."""
    result = BulkVerifyResult()
    pending = db.scalars(
        select(RuleVersion)
        .where(RuleVersion.validation_status == "pending")
        .order_by(RuleVersion.code, RuleVersion.version)
        .with_for_update()
    ).all()
    for rule in pending:
        reason = unverifiable_reason(rule)
        if reason is None:
            _mark_verified(db, organization_id, actor_id, rule, None)
            result.verified.append(rule)
        else:
            result.left_pending.append((rule, reason))
    db.commit()
    return result


def deprecate(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, rule_id: uuid.UUID, reason: str
) -> RuleVersion:
    rule = get_rule(db, rule_id, lock=True)
    if rule.validation_status == "deprecated":
        raise Conflict("RULE_DEPRECATED", "La regla ya está deprecada.")
    before = snapshot(rule, STATE_FIELDS)
    rule.validation_status = "deprecated"
    rule.deprecation_reason = reason
    rule.deprecated_at = now()
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "rule_version",
        "deprecated",
        rule.id,
        before=before,
        after=snapshot(rule, STATE_FIELDS),
    )
    db.commit()
    return rule


def require_rule(db: Session, code: str, day: date) -> RuleVersion:
    rule = rule_for(db, code, day)
    if rule is None:
        raise AppError(
            "RULE_MISSING",
            f"No hay una versión vigente de la regla {code} al {day:%d/%m/%Y}. Cargá las reglas "
            "candidatas (Impuestos → Reglas) o revisá su vigencia.",
            details={"code": code, "date": jsonable(day)},
            status_code=422,
        )
    return rule
