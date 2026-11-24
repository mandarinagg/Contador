"""Feriados y excepciones de calendario (D-086, D-098, BR-TAX-05).

Feriados:
- `candidate_days()` convierte la copia empaquetada de `docs/research/feriados_py.yaml` en
  fechas: los fijos y móviles de la Ley 7544/2025 (art. 1° y 2°) desde su publicación, con
  los traslados por decreto que trae el YAML, Jueves y Viernes Santo de los años que trae
  calculados, y los feriados adicionales (art. 4°). Los años son los que nombra el YAML.
  Todo se carga `pending` (los traslados y adicionales son de fuente secundaria, D-098): un
  feriado sin verificar igual corre el vencimiento, y el aviso usa `remind_by` (la fecha sin
  correr), así nunca se avisa tarde.
- La carga es idempotente: un día que ya existe no se pisa (pudo editarlo el usuario); si
  difiere del YAML se informa en `differing`.
- Un feriado no se borra ni cambia de día si corrió el vencimiento de una obligación ya
  presentada (409 `HOLIDAY_IN_USE`; también lo impide el trigger `holidays_guard`).
- Solo `tax.verify` cambia `validation_status` (lo controla el router).

Excepciones (`due_date_exceptions`): las carga el usuario con su norma, o vienen de una regla
`CAL-EXCEPCION-*` (origen `candidate`, de esas solo cambian `is_active` y las notas). No se
borran (trigger): se desactivan. No se superponen dos activas para el mismo objetivo, mes y
terminación. Si una obligación presentada la usó, no cambia (409 `EXCEPTION_IN_USE`): las
presentadas guardan lo que se aplicó.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.tax import candidate_holidays, rule_params
from app.modules.tax.common import apply_changes, flush_translated, record, snapshot
from app.modules.tax.models import DueDateException, Holiday, Obligation

HOLIDAY_FIELDS = ("day", "name", "source_url", "legal_reference", "validation_status", "notes")
EXCEPTION_FIELDS = (
    "obligation_code",
    "obligation_group",
    "due_month",
    "ruc_digits",
    "new_due_date",
    "legal_reference",
    "source_url",
    "is_active",
    "notes",
)
NOTES_MAX = 500
LAW = "Ley N° 7544/2025"


@dataclass(frozen=True)
class CandidateHoliday:
    day: date
    name: str
    source_url: str | None
    legal_reference: str
    notes: str


def _notes(confidence: str, note: str | None) -> str:
    text_ = f"Confianza: {confidence}." + (f" {' '.join(note.split())}" if note else "")
    return text_ if len(text_) <= NOTES_MAX else text_[: NOTES_MAX - 1] + "…"


def _day(year: int, month_day: str) -> date:
    month, day = month_day.split("-")
    return date(year, int(month), int(day))


def candidate_days(data: dict[str, Any] | None = None) -> list[CandidateHoliday]:
    """Los feriados que se desprenden del YAML de la investigación, ordenados por fecha."""
    data = candidate_holidays.DATA if data is None else data
    law = data["ley_vigente"]
    law_from = date.fromisoformat(law["publicada"])
    law_url = law["source_url"]
    by_year = data.get("por_anio") or {}
    easter = (data.get("semana_santa") or {}).get("fechas") or {}
    years = sorted({int(y) for y in by_year} | {int(y) for y in easter})
    result: dict[date, CandidateHoliday] = {}

    def add(item: CandidateHoliday) -> None:
        if item.day >= law_from:
            result.setdefault(item.day, item)

    for year in years:
        info = by_year.get(str(year)) or {}
        moved = {date.fromisoformat(t["original"]): t for t in info.get("traslados") or []}
        for row in data.get("fijos") or []:
            add(
                CandidateHoliday(
                    _day(year, row["fecha"]),
                    row["nombre"],
                    law_url,
                    f"{LAW}, art. 1°",
                    _notes(row["confidence"], "Feriado fijo: no se traslada."),
                )
            )
        for row in data.get("moviles") or []:
            original = _day(year, row["fecha"])
            move = moved.get(original)
            if move is None:
                add(
                    CandidateHoliday(
                        original,
                        row["nombre"],
                        law_url,
                        f"{LAW}, arts. 1° y 2°",
                        _notes(
                            row["confidence"],
                            "Feriado móvil en su fecha de ley: la investigación no encontró un "
                            "decreto que lo traslade este año (el Poder Ejecutivo puede pasarlo "
                            "al lunes anterior o siguiente, art. 3°).",
                        ),
                    )
                )
                continue
            add(
                CandidateHoliday(
                    date.fromisoformat(move["trasladado_a"]),
                    move.get("nombre") or row["nombre"],
                    move.get("source_url"),
                    move.get("decreto")
                    or f"{LAW}, art. 3° (traslado por decreto, número no visto)",
                    _notes(
                        move["confidence"],
                        f"Trasladado desde el {original:%d/%m/%Y}. {move.get('note') or ''}",
                    ),
                )
            )
        days = easter.get(str(year))
        if days:
            for key, label in (("jueves", "Jueves Santo"), ("viernes", "Viernes Santo")):
                add(
                    CandidateHoliday(
                        date.fromisoformat(days[key]),
                        label,
                        law_url,
                        f"{LAW}, art. 1° (fecha calculada con el cómputo de Pascua)",
                        _notes(days["confidence"], days.get("note")),
                    )
                )
        for row in info.get("adicionales") or []:
            add(
                CandidateHoliday(
                    date.fromisoformat(row["fecha"]),
                    f"Feriado adicional: {row['motivo']}",
                    row.get("source_url"),
                    row.get("decreto") or f"{LAW}, art. 4° (decreto no visto)",
                    _notes(row["confidence"], row.get("note")),
                )
            )
    return [result[day] for day in sorted(result)]


def holiday_not_found() -> NotFound:
    return NotFound("HOLIDAY_NOT_FOUND", "El feriado no existe.")


def list_holidays(db: Session, start: date | None, end: date | None) -> list[Holiday]:
    query = select(Holiday).order_by(Holiday.day)
    if start is not None:
        query = query.where(Holiday.day >= start)
    if end is not None:
        query = query.where(Holiday.day <= end)
    return list(db.scalars(query))


def get_holiday(db: Session, holiday_id: uuid.UUID, *, lock: bool = False) -> Holiday:
    query = select(Holiday).where(Holiday.id == holiday_id)
    if lock:
        query = query.with_for_update()
    holiday = db.scalar(query)
    if holiday is None:
        raise holiday_not_found()
    return holiday


@dataclass
class HolidayLoad:
    created: int = 0
    unchanged: int = 0
    differing: list[dict[str, Any]] | None = None


def load_candidates(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    data: dict[str, Any] | None = None,
) -> HolidayLoad:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('tax.holidays.load', 0))"))
    existing = {h.day: h for h in db.scalars(select(Holiday))}
    result = HolidayLoad(differing=[])
    assert result.differing is not None
    for item in candidate_days(data):
        current = existing.get(item.day)
        if current is not None:
            if current.name == item.name and current.legal_reference == item.legal_reference:
                result.unchanged += 1
            else:
                result.differing.append(
                    {"day": item.day.isoformat(), "loaded": current.name, "candidate": item.name}
                )
            continue
        holiday = Holiday(
            day=item.day,
            name=item.name,
            source_url=item.source_url,
            legal_reference=item.legal_reference,
            notes=item.notes,
            validation_status="pending",
            origin="candidate",
            created_by=actor_id,
        )
        db.add(holiday)
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "holiday",
            "created",
            holiday.id,
            after=snapshot(holiday, (*HOLIDAY_FIELDS, "origin")),
        )
        result.created += 1
    return result


def _shifted_filed(db: Session, day: date) -> bool:
    """¿El feriado corrió el vencimiento de alguna obligación ya presentada?"""
    return (
        db.scalar(
            select(Obligation.id)
            .where(
                Obligation.status.in_(("filed", "paid")),
                Obligation.exception_id.is_(None),
                Obligation.nominal_due_date <= day,
                Obligation.due_date > day,
            )
            .limit(1)
        )
        is not None
    )


def _check_not_in_use(db: Session, day: date) -> None:
    if _shifted_filed(db, day):
        raise Conflict(
            "HOLIDAY_IN_USE",
            f"El feriado del {day:%d/%m/%Y} corrió el vencimiento de una obligación ya "
            "presentada: no se borra ni cambia de día. Si estaba mal, cargá la corrección "
            "como feriado nuevo o reabrí la obligación.",
        )


def _check_free_day(db: Session, day: date, own_id: uuid.UUID | None = None) -> None:
    query = select(Holiday.id).where(Holiday.day == day)
    if own_id is not None:
        query = query.where(Holiday.id != own_id)
    if db.scalar(query) is not None:
        raise Conflict("HOLIDAY_EXISTS", f"Ya hay un feriado el {day:%d/%m/%Y}.")


def create_holiday(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> Holiday:
    _check_free_day(db, data["day"])
    holiday = Holiday(
        **{k: data.get(k) for k in HOLIDAY_FIELDS if k != "validation_status"},
        validation_status="pending",
        origin="user",
        created_by=actor_id,
    )
    db.add(holiday)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "holiday",
        "created",
        holiday.id,
        after=snapshot(holiday, (*HOLIDAY_FIELDS, "origin")),
    )
    return holiday


def update_holiday(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    holiday_id: uuid.UUID,
    changes: dict[str, Any],
) -> Holiday:
    holiday = get_holiday(db, holiday_id, lock=True)
    if "day" in changes and changes["day"] != holiday.day:
        _check_not_in_use(db, holiday.day)
        _check_free_day(db, changes["day"], holiday.id)
    merged_source = changes.get("source_url", holiday.source_url)
    merged_reference = changes.get("legal_reference", holiday.legal_reference)
    if not merged_source and not merged_reference:
        raise AppError(
            "HOLIDAY_SOURCE_REQUIRED",
            "Un feriado lleva su fuente: la norma o la URL donde se publicó.",
            status_code=422,
        )
    before, after = apply_changes(holiday, changes)
    if after:
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "holiday",
            "updated",
            holiday.id,
            before=before,
            after=after,
        )
    return holiday


def delete_holiday(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, holiday_id: uuid.UUID
) -> date:
    holiday = get_holiday(db, holiday_id, lock=True)
    _check_not_in_use(db, holiday.day)
    before = snapshot(holiday, (*HOLIDAY_FIELDS, "origin"))
    day = holiday.day
    db.delete(holiday)
    flush_translated(db)
    record(db, organization_id, actor_id, "holiday", "deleted", holiday_id, before=before)
    return day


# ------------------------------------------------------------------ excepciones


def exception_not_found() -> NotFound:
    return NotFound("EXCEPTION_NOT_FOUND", "La excepción de calendario no existe.")


def list_exceptions(
    db: Session, start: date | None, end: date | None, active: bool | None
) -> list[DueDateException]:
    query = select(DueDateException).order_by(
        DueDateException.due_month, DueDateException.new_due_date, DueDateException.id
    )
    if start is not None:
        query = query.where(DueDateException.due_month >= start.replace(day=1))
    if end is not None:
        query = query.where(DueDateException.due_month <= end)
    if active is not None:
        query = query.where(DueDateException.is_active.is_(active))
    return list(db.scalars(query))


def get_exception(db: Session, exception_id: uuid.UUID, *, lock: bool = False) -> DueDateException:
    query = select(DueDateException).where(DueDateException.id == exception_id)
    if lock:
        query = query.with_for_update()
    exception = db.scalar(query)
    if exception is None:
        raise exception_not_found()
    return exception


def _check_target(data: dict[str, Any]) -> None:
    code, group = data.get("obligation_code"), data.get("obligation_group")
    if (code is None) == (group is None):
        raise AppError(
            "EXCEPTION_TARGET_INVALID",
            "Indicá la obligación (`obligation_code`) o el grupo (`obligation_group`), uno solo.",
            status_code=422,
        )
    if code is not None and code not in rule_params.OBLIGATION_RULES:
        raise AppError(
            "EXCEPTION_TARGET_INVALID",
            f"La obligación {code} no es una de las que calcula el calendario: "
            + ", ".join(sorted(rule_params.OBLIGATION_RULES))
            + ".",
            status_code=422,
        )
    if data["due_month"].day != 1:
        data["due_month"] = data["due_month"].replace(day=1)
    data["ruc_digits"] = sorted(set(data.get("ruc_digits") or []))


def _check_overlap(db: Session, data: dict[str, Any], own_id: uuid.UUID | None) -> None:
    if not data.get("is_active", True):
        return
    query = select(DueDateException).where(
        DueDateException.is_active.is_(True),
        DueDateException.due_month == data["due_month"],
        and_(
            DueDateException.obligation_code.is_not_distinct_from(data.get("obligation_code")),
            DueDateException.obligation_group.is_not_distinct_from(data.get("obligation_group")),
        ),
    )
    if own_id is not None:
        query = query.where(DueDateException.id != own_id)
    digits = set(data["ruc_digits"])
    for other in db.scalars(query):
        other_digits = set(other.ruc_digits)
        if not digits or not other_digits or digits & other_digits:
            raise Conflict(
                "EXCEPTION_OVERLAP",
                "Ya hay una excepción activa para la misma obligación, mes y terminación del "
                f"RUC ({other.legal_reference}). Desactivala o ajustá las terminaciones.",
                details={"exception_id": str(other.id)},
            )


def _used_by_filed(db: Session, exception_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Obligation.id)
            .where(
                Obligation.exception_id == exception_id,
                Obligation.status.in_(("filed", "paid")),
            )
            .limit(1)
        )
        is not None
    )


def create_exception(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> DueDateException:
    data = dict(data)
    data.setdefault("is_active", True)
    _check_target(data)
    _check_overlap(db, data, None)
    exception = DueDateException(
        **{k: data.get(k) for k in EXCEPTION_FIELDS},
        origin="user",
        created_by=actor_id,
    )
    db.add(exception)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "due_date_exception",
        "created",
        exception.id,
        after=snapshot(exception, (*EXCEPTION_FIELDS, "origin")),
    )
    return exception


def update_exception(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    exception_id: uuid.UUID,
    changes: dict[str, Any],
) -> DueDateException:
    exception = get_exception(db, exception_id, lock=True)
    real = {k: v for k, v in changes.items() if getattr(exception, k) != v}
    if exception.origin == "candidate" and set(real) - {"is_active", "notes"}:
        raise Conflict(
            "EXCEPTION_FROM_RULE",
            "Esta excepción viene de una regla de la investigación: solo se puede activar, "
            "desactivar o anotar. Si la fecha es otra, cargá una excepción propia.",
        )
    if set(real) - {"notes"} and _used_by_filed(db, exception.id):
        raise Conflict(
            "EXCEPTION_IN_USE",
            "Una obligación ya presentada usó esta excepción: no cambia. Si hace falta otra "
            "fecha, cargá una excepción nueva (y desactivá esta solo si nada presentado la usa).",
        )
    merged = {k: getattr(exception, k) for k in EXCEPTION_FIELDS} | real
    _check_target(merged)
    _check_overlap(db, merged, exception.id)
    values = {k: merged[k] for k in real}
    before, after = apply_changes(exception, values)
    if after:
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "due_date_exception",
            "updated",
            exception.id,
            before=before,
            after=after,
        )
    return exception
