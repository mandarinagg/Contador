"""Asientos recurrentes (D-061): plantillas que generan borradores, nunca contabilizan.

- Una plantilla tiene líneas fijas (cuenta, debe o haber, centro), un día del mes, una
  fecha de inicio y una de fin opcional, y está activa o pausada.
- `generate(period_id)` crea los borradores del período que falten. La fecha es el día de
  la plantilla, o el último día del mes si el mes es más corto (un 31 cae el 30 o el 28);
  tiene que caer dentro del período y de la vigencia (D-079).
- Una generación viva (borrador o contabilizada) por plantilla y período: lo garantiza un
  índice único parcial sobre `entry_status`, que mantienen los triggers. Si el borrador se
  descarta (o el asiento se revierte), se puede regenerar.
- No hay un proceso en segundo plano: la interfaz consulta `due` y lo ofrece.
"""

import calendar
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.modules.accounting import depreciation, entries
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import (
    apply_changes,
    flush_translated,
    jsonable,
    pyg,
    record,
    snapshot,
)
from app.modules.accounting.models import (
    JournalEntry,
    Period,
    RecurringGeneration,
    RecurringTemplate,
    RecurringTemplateLine,
)

HEADER_FIELDS = (
    "description",
    "document_reference",
    "day_of_month",
    "start_date",
    "end_date",
    "status",
)


def template_not_found() -> NotFound:
    return NotFound("RECURRING_TEMPLATE_NOT_FOUND", "La plantilla no existe.")


def get_template(
    db: Session, organization_id: uuid.UUID, template_id: uuid.UUID, *, lock: bool = False
) -> RecurringTemplate:
    query = select(RecurringTemplate).where(
        RecurringTemplate.id == template_id, RecurringTemplate.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    template = db.scalar(query)
    if template is None:
        raise template_not_found()
    return template


def list_templates(db: Session, organization_id: uuid.UUID) -> list[RecurringTemplate]:
    return list(
        db.scalars(
            select(RecurringTemplate)
            .where(RecurringTemplate.organization_id == organization_id)
            .order_by(RecurringTemplate.day_of_month, RecurringTemplate.description)
        )
    )


def template_lines(
    db: Session, template_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[RecurringTemplateLine]]:
    result: dict[uuid.UUID, list[RecurringTemplateLine]] = {i: [] for i in template_ids}
    if template_ids:
        for line in db.scalars(
            select(RecurringTemplateLine)
            .where(RecurringTemplateLine.template_id.in_(template_ids))
            .order_by(RecurringTemplateLine.template_id, RecurringTemplateLine.line_no)
            .execution_options(populate_existing=True)
        ):
            result[line.template_id].append(line)
    return result


def _validated(
    db: Session, organization_id: uuid.UUID, raw_lines: list[dict[str, Any]]
) -> list[entries.LineData]:
    """Las mismas reglas que un asiento, y además balanceada: se contabiliza sin tocarla."""
    lines = entries.validated_lines(db, organization_id, raw_lines)
    if len(lines) < 2:
        raise AppError(
            "ENTRY_TOO_FEW_LINES", "Una plantilla lleva al menos dos líneas.", status_code=422
        )
    debit = sum((line.debit for line in lines), ZERO)
    credit = sum((line.credit for line in lines), ZERO)
    if debit != credit:
        raise AppError(
            "ENTRY_UNBALANCED",
            f"La plantilla no balancea: debe {pyg(debit)} y haber {pyg(credit)}.",
            status_code=422,
        )
    return lines


def _check_dates(start: date, end: date | None) -> None:
    if end is not None and end < start:
        raise AppError(
            "INVALID_RANGE", "La fecha de fin es anterior a la de inicio.", status_code=422
        )


def _insert_lines(db: Session, template: RecurringTemplate, lines: list[entries.LineData]) -> None:
    for line_no, line in enumerate(lines, start=1):
        db.add(
            RecurringTemplateLine(
                organization_id=template.organization_id,
                template_id=template.id,
                line_no=line_no,
                account_id=line.account_id,
                debit=line.debit,
                credit=line.credit,
                description=line.description,
                fx_currency=line.fx_currency,
                fx_amount=line.fx_amount,
                fx_rate=line.fx_rate,
                cost_center_id=line.cost_center_id,
            )
        )


def _lines_snapshot(lines: list[entries.LineData]) -> list[dict[str, Any]]:
    return [
        {
            "account_id": jsonable(line.account_id),
            "debit": jsonable(line.debit),
            "credit": jsonable(line.credit),
            "description": line.description,
            "cost_center_id": jsonable(line.cost_center_id),
        }
        for line in lines
    ]


def _stored(lines: list[RecurringTemplateLine]) -> list[entries.LineData]:
    return [
        entries.LineData(
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
            description=line.description,
            fx_currency=line.fx_currency,
            fx_amount=line.fx_amount,
            fx_rate=line.fx_rate,
            cost_center_id=line.cost_center_id,
        )
        for line in lines
    ]


def create_template(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> RecurringTemplate:
    _check_dates(data["start_date"], data.get("end_date"))
    lines = _validated(db, organization_id, data["lines"])
    template = RecurringTemplate(
        organization_id=organization_id,
        description=data["description"],
        document_reference=data.get("document_reference"),
        day_of_month=data["day_of_month"],
        start_date=data["start_date"],
        end_date=data.get("end_date"),
        status=data.get("status") or "active",
        created_by=actor_id,
    )
    db.add(template)
    flush_translated(db)
    _insert_lines(db, template, lines)
    flush_translated(db)
    after = snapshot(template, HEADER_FIELDS)
    after["lines"] = _lines_snapshot(lines)
    record(db, organization_id, actor_id, "recurring_template", "created", template.id, after=after)
    db.commit()
    return template


def update_template(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    template_id: uuid.UUID,
    data: dict[str, Any],
) -> RecurringTemplate:
    """Cambia la cabecera y, si vienen, reemplaza las líneas. Los borradores ya generados
    no cambian."""
    template = get_template(db, organization_id, template_id, lock=True)
    for key in ("description", "day_of_month", "start_date", "status"):
        if key in data and data[key] is None:
            raise AppError("FIELD_REQUIRED", f"`{key}` no puede quedar vacío.", status_code=422)
    changes = {k: data[k] for k in HEADER_FIELDS if k in data}
    _check_dates(
        changes.get("start_date", template.start_date), changes.get("end_date", template.end_date)
    )
    before, after = apply_changes(template, changes)
    if data.get("lines") is not None:
        lines = _validated(db, organization_id, data["lines"])
        old = _stored(template_lines(db, [template.id])[template.id])
        if lines != old:
            before["lines"] = _lines_snapshot(old)
            after["lines"] = _lines_snapshot(lines)
            db.execute(
                delete(RecurringTemplateLine).where(
                    RecurringTemplateLine.template_id == template.id
                )
            )
            _insert_lines(db, template, lines)
    flush_translated(db)
    if after:
        record(
            db,
            organization_id,
            actor_id,
            "recurring_template",
            "updated",
            template.id,
            before=before,
            after=after,
        )
    db.commit()
    return template


# --- Generación ---------------------------------------------------------------------------


def occurrence(template: RecurringTemplate, period: Period) -> date | None:
    """Fecha del asiento de la plantilla en el período, o None si no corresponde."""
    month = period.start_date
    last = calendar.monthrange(month.year, month.month)[1]
    day = date(month.year, month.month, min(template.day_of_month, last))
    if not (period.start_date <= day <= period.end_date):
        return None
    if day < template.start_date or (template.end_date is not None and day > template.end_date):
        return None
    return day


@dataclass(frozen=True)
class Due:
    template: RecurringTemplate
    entry_date: date
    total: Decimal


def _live_generations(db: Session, period_id: uuid.UUID) -> dict[uuid.UUID, RecurringGeneration]:
    return {
        g.template_id: g
        for g in db.scalars(
            select(RecurringGeneration).where(
                RecurringGeneration.period_id == period_id,
                RecurringGeneration.entry_status.in_(depreciation.LIVE),
            )
        )
    }


def _period(db: Session, organization_id: uuid.UUID, period_id: uuid.UUID) -> Period:
    period = db.scalar(
        select(Period).where(Period.id == period_id, Period.organization_id == organization_id)
    )
    if period is None:
        raise NotFound("PERIOD_NOT_FOUND", "El período no existe.")
    return period


def due(db: Session, organization_id: uuid.UUID, period_id: uuid.UUID) -> list[Due]:
    """Plantillas activas con asiento en el período que todavía no se generó."""
    period = _period(db, organization_id, period_id)
    live = _live_generations(db, period.id)
    templates = [t for t in list_templates(db, organization_id) if t.status == "active"]
    lines = template_lines(db, [t.id for t in templates])
    result = []
    for template in templates:
        day = occurrence(template, period)
        if day is None or template.id in live:
            continue
        total = sum((line.debit for line in lines[template.id]), ZERO)
        result.append(Due(template, day, total))
    return sorted(result, key=lambda d: (d.entry_date, d.template.description))


@dataclass
class Generated:
    created: list[JournalEntry]
    existing: list[JournalEntry]


def generate(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, period_id: uuid.UUID
) -> Generated:
    """Crea los borradores que falten (todo o nada: si una plantilla tiene una cuenta o un
    centro que ya no sirve, 422 sin generar ninguno)."""
    year, period = depreciation.locked_open_period(db, organization_id, period_id)
    live = _live_generations(db, period.id)
    templates = [t for t in list_templates(db, organization_id) if t.status == "active"]
    lines = template_lines(db, [t.id for t in templates])
    created: list[JournalEntry] = []
    existing_ids: list[uuid.UUID] = []
    for template in templates:
        day = occurrence(template, period)
        if day is None:
            continue
        if template.id in live:
            existing_ids.append(live[template.id].entry_id)
            continue
        try:
            validated = _validated(
                db,
                organization_id,
                [
                    {
                        "account_id": line.account_id,
                        "debit": line.debit,
                        "credit": line.credit,
                        "description": line.description,
                        "fx_currency": line.fx_currency,
                        "fx_amount": line.fx_amount,
                        "fx_rate": line.fx_rate,
                        "cost_center_id": line.cost_center_id,
                    }
                    for line in lines[template.id]
                ],
            )
        except AppError as exc:
            raise AppError(
                exc.code,
                f"Plantilla «{template.description}»: {exc.message}",
                details={"template_id": str(template.id)},
                status_code=exc.status_code,
            ) from exc
        entry = entries.create_draft(
            db,
            organization_id,
            actor_id,
            {
                "entry_date": day,
                "description": template.description,
                "document_reference": template.document_reference,
            },
            kind="recurring",
            lines=validated,
            year=year,
            commit=False,
        )
        db.add(
            RecurringGeneration(
                organization_id=organization_id,
                template_id=template.id,
                period_id=period.id,
                entry_id=entry.id,
                created_by=actor_id,
            )
        )
        flush_translated(db)
        created.append(entry)
    if created:
        record(
            db,
            organization_id,
            actor_id,
            "recurring_generation",
            "created",
            period.id,
            after={"period_id": str(period.id), "entries": [str(e.id) for e in created]},
        )
    db.commit()
    existing = (
        list(
            db.scalars(
                select(JournalEntry)
                .where(JournalEntry.id.in_(existing_ids))
                .order_by(JournalEntry.entry_date, JournalEntry.id)
            )
        )
        if existing_ids
        else []
    )
    return Generated(created, existing)
