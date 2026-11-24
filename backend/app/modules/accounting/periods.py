"""Ejercicios y períodos (D-039).

- Un ejercicio es, por defecto, el año civil (Decreto 3182 arts. 14-15; la duda D-9 sigue
  abierta). Se puede indicar otro rango de a lo sumo 12 meses calendario (por ejemplo, el
  primer ejercicio de una empresa que empezó a mitad de año, D-047).
- Los períodos son los meses calendario del ejercicio (el primero y el último se recortan
  a las fechas del ejercicio): 12 para un año civil.
- Cerrar un período bloquea contabilizar y revertir con fecha en él (lo impide también el
  trigger). No se cierra con borradores: se informan para descartarlos o moverlos.
- Reabrir exige motivo y queda auditado. Un ejercicio cerrado no se reabre.

Candados (todas las operaciones toman primero la fila del ejercicio, `FOR UPDATE`):
cerrar o reabrir un período y contabilizar en el mismo ejercicio se serializan.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting.common import apply_changes, flush_translated, now, record
from app.modules.accounting.models import FiscalYear, JournalEntry, Period

MAX_PERIODS = 12


def fiscal_year_not_found() -> NotFound:
    return NotFound("FISCAL_YEAR_NOT_FOUND", "El ejercicio no existe.")


def period_not_found() -> NotFound:
    return NotFound("PERIOD_NOT_FOUND", "El período no existe.")


def get_fiscal_year(
    db: Session, organization_id: uuid.UUID, fiscal_year_id: uuid.UUID, *, lock: bool = False
) -> FiscalYear:
    query = select(FiscalYear).where(
        FiscalYear.id == fiscal_year_id, FiscalYear.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    year = db.scalar(query)
    if year is None:
        raise fiscal_year_not_found()
    return year


def fiscal_year_for(
    db: Session, organization_id: uuid.UUID, day: date, *, lock: bool = False
) -> FiscalYear:
    """Ejercicio que contiene la fecha, o 422 si no hay ninguno creado."""
    query = select(FiscalYear).where(
        FiscalYear.organization_id == organization_id,
        FiscalYear.start_date <= day,
        FiscalYear.end_date >= day,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    year = db.scalar(query)
    if year is None:
        raise AppError(
            "FISCAL_YEAR_NOT_FOUND",
            f"No hay un ejercicio que incluya la fecha {day.isoformat()}: crealo primero.",
            status_code=422,
        )
    return year


def period_for(db: Session, year: FiscalYear, day: date) -> Period:
    period = db.scalar(
        select(Period).where(
            Period.fiscal_year_id == year.id, Period.start_date <= day, Period.end_date >= day
        )
    )
    if period is None:  # pragma: no cover - los períodos cubren todo el ejercicio
        raise period_not_found()
    return period


def periods_of(db: Session, fiscal_year_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Period]]:
    result: dict[uuid.UUID, list[Period]] = {i: [] for i in fiscal_year_ids}
    rows = db.scalars(
        select(Period)
        .where(Period.fiscal_year_id.in_(fiscal_year_ids))
        .order_by(Period.fiscal_year_id, Period.start_date)
    )
    for period in rows:
        result[period.fiscal_year_id].append(period)
    return result


def list_fiscal_years(db: Session, organization_id: uuid.UUID) -> list[FiscalYear]:
    return list(
        db.scalars(
            select(FiscalYear)
            .where(FiscalYear.organization_id == organization_id)
            .order_by(FiscalYear.start_date.desc())
        )
    )


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Meses calendario entre dos fechas, recortados a ellas."""
    ranges = []
    current = start
    while current <= end:
        next_month = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
        ranges.append((current, min(end, next_month - timedelta(days=1))))
        current = next_month
    return ranges


def create_fiscal_year(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    start_date: date,
    end_date: date,
) -> FiscalYear:
    if end_date <= start_date:
        raise AppError(
            "FISCAL_YEAR_INVALID",
            "La fecha de cierre del ejercicio tiene que ser posterior a la de inicio.",
            status_code=422,
        )
    months = month_ranges(start_date, end_date)
    if len(months) > MAX_PERIODS:
        raise AppError(
            "FISCAL_YEAR_INVALID",
            "Un ejercicio abarca a lo sumo 12 meses calendario.",
            status_code=422,
        )
    overlap = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.organization_id == organization_id,
            FiscalYear.start_date <= end_date,
            FiscalYear.end_date >= start_date,
        )
    )
    if overlap is not None:
        raise Conflict("FISCAL_YEAR_OVERLAP", "El ejercicio se superpone con otro existente.")
    year = FiscalYear(organization_id=organization_id, start_date=start_date, end_date=end_date)
    db.add(year)
    flush_translated(db)  # la exclusión de la base cubre una carrera entre dos altas
    for first, last in months:
        db.add(
            Period(
                organization_id=organization_id,
                fiscal_year_id=year.id,
                start_date=first,
                end_date=last,
            )
        )
    db.flush()
    record(
        db,
        organization_id,
        actor_id,
        "fiscal_year",
        "created",
        year.id,
        after={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "periods": len(months),
        },
    )
    db.commit()
    return year


def _locked_period(
    db: Session, organization_id: uuid.UUID, period_id: uuid.UUID
) -> tuple[FiscalYear, Period]:
    found = db.scalar(
        select(Period.fiscal_year_id).where(
            Period.id == period_id, Period.organization_id == organization_id
        )
    )
    if found is None:
        raise period_not_found()
    year = get_fiscal_year(db, organization_id, found, lock=True)
    period = db.scalar(
        select(Period)
        .where(Period.id == period_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert period is not None  # los períodos no se borran
    if year.status == "closed":
        raise Conflict(
            "FISCAL_YEAR_CLOSED", "El ejercicio está cerrado: sus períodos no se modifican."
        )
    return year, period


def drafts_in(
    db: Session, fiscal_year_id: uuid.UUID, start: date | None = None, end: date | None = None
) -> list[dict[str, Any]]:
    query = select(JournalEntry).where(
        JournalEntry.fiscal_year_id == fiscal_year_id, JournalEntry.status == "draft"
    )
    if start is not None:
        query = query.where(JournalEntry.entry_date >= start)
    if end is not None:
        query = query.where(JournalEntry.entry_date <= end)
    return [
        {"id": str(e.id), "entry_date": e.entry_date.isoformat(), "description": e.description}
        for e in db.scalars(query.order_by(JournalEntry.entry_date, JournalEntry.id))
    ]


def close_period(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, period_id: uuid.UUID
) -> Period:
    _year, period = _locked_period(db, organization_id, period_id)
    if period.status == "closed":
        raise Conflict("PERIOD_ALREADY_CLOSED", "El período ya está cerrado.")
    drafts = drafts_in(db, period.fiscal_year_id, period.start_date, period.end_date)
    if drafts:
        raise Conflict(
            "PERIOD_HAS_DRAFTS",
            f"El período tiene {len(drafts)} borrador(es) de asiento: contabilizalos, "
            "descartalos o cambiales la fecha antes de cerrarlo.",
            details={"drafts": drafts},
        )
    before, after = apply_changes(
        period, {"status": "closed", "closed_at": now(), "closed_by": actor_id}
    )
    db.flush()
    record(db, organization_id, actor_id, "period", "closed", period.id, before=before, after=after)
    db.commit()
    return period


def reopen_period(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    period_id: uuid.UUID,
    reason: str,
) -> Period:
    _year, period = _locked_period(db, organization_id, period_id)
    if period.status != "closed":
        raise Conflict("PERIOD_NOT_CLOSED", "El período no está cerrado.")
    before, after = apply_changes(
        period, {"status": "open", "closed_at": None, "closed_by": None, "reopen_reason": reason}
    )
    # El motivo va siempre en la auditoría, aunque repita el de una reapertura anterior.
    after["reopen_reason"] = reason
    db.flush()
    record(
        db, organization_id, actor_id, "period", "reopened", period.id, before=before, after=after
    )
    db.commit()
    return period
