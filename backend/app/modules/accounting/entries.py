"""Asientos de partida doble (D-040): borrador → contabilizado → revertido, o descartado.

- Un borrador puede estar desbalanceado y cambiar por completo (cabecera y líneas).
- Contabilizar valida (al menos dos líneas, Σ debe = Σ haber > 0 en guaraníes, cuentas
  imputables, ejercicio y período abiertos) y asigna el número correlativo del ejercicio.
  El servicio valida para dar errores legibles; el trigger de la base vuelve a validar
  todo y es quien asigna el número (BR-ACC-01/03/08).
- Lo contabilizado no se modifica: se corrige con una reversión (líneas invertidas) que se
  contabiliza en el mismo acto y deja el original `reversed` (BR-ACC-02).
- Nada se borra: un borrador se descarta con motivo.

Candados, siempre en este orden: fila del ejercicio (`FOR UPDATE`) y después la del
asiento. El cierre de períodos y del ejercicio toma el mismo candado del ejercicio.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, delete, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting import periods
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import (
    apply_changes,
    flush_translated,
    jsonable,
    now,
    pyg,
    pyg_amount,
    record,
    snapshot,
)
from app.modules.accounting.models import FiscalYear, JournalEntry, JournalLine, LedgerAccount
from app.modules.finance.models import Transaction
from app.modules.finance.money import AmountError, check_amount
from app.modules.finance.service import escape_like

HEADER_FIELDS = ("entry_date", "description", "document_reference")
LINE_FIELDS = (
    "line_no",
    "account_id",
    "debit",
    "credit",
    "description",
    "fx_currency",
    "fx_amount",
    "fx_rate",
)
REVERSIBLE_KINDS = ("manual", "finance")


@dataclass(frozen=True)
class LineData:
    account_id: uuid.UUID
    debit: Decimal
    credit: Decimal
    description: str | None = None
    fx_currency: str | None = None
    fx_amount: Decimal | None = None
    fx_rate: Decimal | None = None


def entry_not_found() -> NotFound:
    return NotFound("ENTRY_NOT_FOUND", "El asiento no existe.")


def get_entry(
    db: Session, organization_id: uuid.UUID, entry_id: uuid.UUID, *, lock: bool = False
) -> JournalEntry:
    query = select(JournalEntry).where(
        JournalEntry.id == entry_id, JournalEntry.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    entry = db.scalar(query)
    if entry is None:
        raise entry_not_found()
    return entry


def lines_of(db: Session, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[JournalLine]]:
    result: dict[uuid.UUID, list[JournalLine]] = defaultdict(list)
    if entry_ids:
        rows = db.scalars(
            select(JournalLine)
            .where(JournalLine.entry_id.in_(entry_ids))
            .order_by(JournalLine.entry_id, JournalLine.line_no)
            .execution_options(populate_existing=True)
        )
        for line in rows:
            result[line.entry_id].append(line)
    return result


def totals_of(db: Session, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    if not entry_ids:
        return {}
    rows = db.execute(
        select(JournalLine.entry_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .where(JournalLine.entry_id.in_(entry_ids))
        .group_by(JournalLine.entry_id)
    )
    return {entry_id: (debit, credit) for entry_id, debit, credit in rows}


def reversed_by(db: Session, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    if not entry_ids:
        return {}
    rows = db.execute(
        select(JournalEntry.reverses_entry_id, JournalEntry.id).where(
            JournalEntry.reverses_entry_id.in_(entry_ids)
        )
    )
    return {original: reversal for original, reversal in rows if original is not None}


def account_map(
    db: Session, organization_id: uuid.UUID, account_ids: set[uuid.UUID]
) -> dict[uuid.UUID, LedgerAccount]:
    if not account_ids:
        return {}
    rows = db.scalars(
        select(LedgerAccount).where(
            LedgerAccount.organization_id == organization_id, LedgerAccount.id.in_(account_ids)
        )
    )
    return {a.id: a for a in rows}


# --- Validación de líneas -----------------------------------------------------------------


def _fx(line: dict[str, Any], label: str) -> tuple[str | None, Decimal | None, Decimal | None]:
    currency, amount, rate = line.get("fx_currency"), line.get("fx_amount"), line.get("fx_rate")
    if currency is None and amount is None and rate is None:
        return None, None, None
    if currency is None or amount is None or rate is None:
        raise AppError(
            "FX_INCOMPLETE",
            f"{label}: la moneda extranjera lleva moneda, importe y cotización, los tres juntos.",
            status_code=422,
        )
    try:
        fx_amount = check_amount(amount, currency, allow_zero=False)
    except AmountError as exc:
        raise AppError("INVALID_AMOUNT", f"{label}: {exc}", status_code=422) from exc
    if fx_amount < 0 or rate <= 0:
        raise AppError(
            "INVALID_AMOUNT",
            f"{label}: el importe en moneda extranjera y la cotización van en positivo.",
            status_code=422,
        )
    return currency, fx_amount, rate


def validated_lines(
    db: Session, organization_id: uuid.UUID, raw_lines: list[dict[str, Any]]
) -> list[LineData]:
    """Importes en guaraníes enteros, uno solo de debe o haber, cuentas imputables."""
    lines: list[LineData] = []
    for index, raw in enumerate(raw_lines, start=1):
        label = f"Línea {index}"
        debit = pyg_amount(raw.get("debit") or ZERO, field=f"{label}, debe")
        credit = pyg_amount(raw.get("credit") or ZERO, field=f"{label}, haber")
        if (debit > 0) == (credit > 0):
            raise AppError(
                "LINE_DEBIT_XOR_CREDIT",
                f"{label}: lleva un importe en el debe o en el haber, no en los dos ni en ninguno.",
                status_code=422,
            )
        fx_currency, fx_amount, fx_rate = _fx(raw, label)
        lines.append(
            LineData(
                account_id=raw["account_id"],
                debit=debit,
                credit=credit,
                description=raw.get("description"),
                fx_currency=fx_currency,
                fx_amount=fx_amount,
                fx_rate=fx_rate,
            )
        )
    accounts = account_map(db, organization_id, {line.account_id for line in lines})
    bad: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        account = accounts.get(line.account_id)
        if account is None:
            raise AppError(
                "LEDGER_ACCOUNT_NOT_FOUND",
                f"Línea {index}: la cuenta contable no existe.",
                status_code=422,
            )
        if not account.is_postable or account.archived_at is not None:
            bad.append({"line": index, "code": account.code, "name": account.name})
    if bad:
        raise AppError(
            "ACCOUNT_NOT_POSTABLE",
            "Solo las cuentas imputables y no archivadas reciben líneas: "
            + ", ".join(f"línea {b['line']} ({b['code']} {b['name']})" for b in bad)
            + ".",
            details={"lines": bad},
            status_code=422,
        )
    return lines


def _insert_lines(db: Session, entry: JournalEntry, lines: list[LineData]) -> None:
    for line_no, line in enumerate(lines, start=1):
        db.add(
            JournalLine(
                organization_id=entry.organization_id,
                entry_id=entry.id,
                line_no=line_no,
                account_id=line.account_id,
                debit=line.debit,
                credit=line.credit,
                description=line.description,
                fx_currency=line.fx_currency,
                fx_amount=line.fx_amount,
                fx_rate=line.fx_rate,
            )
        )


def _lines_snapshot(lines: list[LineData]) -> list[dict[str, Any]]:
    return [
        {
            "line_no": n,
            "account_id": jsonable(line.account_id),
            "debit": jsonable(line.debit),
            "credit": jsonable(line.credit),
            "description": line.description,
            "fx_currency": line.fx_currency,
            "fx_amount": jsonable(line.fx_amount),
            "fx_rate": jsonable(line.fx_rate),
        }
        for n, line in enumerate(lines, start=1)
    ]


def _stored_lines(db: Session, entry_id: uuid.UUID) -> list[LineData]:
    return [
        LineData(
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
            description=line.description,
            fx_currency=line.fx_currency,
            fx_amount=line.fx_amount,
            fx_rate=line.fx_rate,
        )
        for line in lines_of(db, [entry_id]).get(entry_id, [])
    ]


def _open_year_for(db: Session, organization_id: uuid.UUID, day: date) -> FiscalYear:
    year = periods.fiscal_year_for(db, organization_id, day)
    if year.status != "open":
        raise Conflict(
            "FISCAL_YEAR_CLOSED",
            f"El ejercicio {year.start_date.year} está cerrado: no admite asientos nuevos.",
        )
    return year


# --- Borradores ---------------------------------------------------------------------------


def create_draft(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    data: dict[str, Any],
    *,
    kind: str = "manual",
    source: Transaction | None = None,
    reverses: JournalEntry | None = None,
    lines: list[LineData] | None = None,
    year: FiscalYear | None = None,
    commit: bool = True,
) -> JournalEntry:
    """Alta de un borrador. Las líneas llegan crudas (`data["lines"]`) o ya validadas."""
    if year is None:
        year = _open_year_for(db, organization_id, data["entry_date"])
    if lines is None:
        lines = validated_lines(db, organization_id, data["lines"])
    entry = JournalEntry(
        organization_id=organization_id,
        fiscal_year_id=year.id,
        entry_date=data["entry_date"],
        status="draft",
        kind=kind,
        description=data["description"],
        document_reference=data.get("document_reference"),
        reverses_entry_id=reverses.id if reverses is not None else None,
        source_transaction_id=source.id if source is not None else None,
        source_context_id=source.context_id if source is not None else None,
        source_context_kind="business" if source is not None else None,
        created_by=actor_id,
    )
    db.add(entry)
    flush_translated(db)
    _insert_lines(db, entry, lines)
    flush_translated(db)
    after = snapshot(entry, (*HEADER_FIELDS, "kind", "fiscal_year_id"))
    if reverses is not None:
        after["reverses_entry_id"] = str(reverses.id)
    if source is not None:
        after["source_transaction_id"] = str(source.id)
    after["lines"] = _lines_snapshot(lines)
    record(db, organization_id, actor_id, "journal_entry", "created", entry.id, after=after)
    if commit:
        db.commit()
    return entry


def update_draft(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    entry_id: uuid.UUID,
    data: dict[str, Any],
) -> JournalEntry:
    """Reemplaza cabecera y líneas de un borrador (409 si ya no es borrador)."""
    entry = get_entry(db, organization_id, entry_id, lock=True)
    if entry.status != "draft":
        raise Conflict(
            "ENTRY_NOT_DRAFT",
            "Solo se edita un borrador: un asiento contabilizado se corrige con una reversión.",
        )
    year = _open_year_for(db, organization_id, data["entry_date"])
    lines = validated_lines(db, organization_id, data["lines"])
    old_lines = _stored_lines(db, entry.id)
    changes = {k: data.get(k) for k in HEADER_FIELDS}
    changes["fiscal_year_id"] = year.id
    before, after = apply_changes(entry, changes)
    if lines != old_lines:
        before["lines"] = _lines_snapshot(old_lines)
        after["lines"] = _lines_snapshot(lines)
        db.execute(delete(JournalLine).where(JournalLine.entry_id == entry.id))
        flush_translated(db)
        _insert_lines(db, entry, lines)
    flush_translated(db)
    if after:
        record(
            db,
            organization_id,
            actor_id,
            "journal_entry",
            "updated",
            entry.id,
            before=before,
            after=after,
        )
    db.commit()
    return entry


def discard_draft(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    entry_id: uuid.UUID,
    reason: str,
) -> JournalEntry:
    entry = get_entry(db, organization_id, entry_id, lock=True)
    if entry.status != "draft":
        raise Conflict(
            "ENTRY_NOT_DRAFT",
            "Solo se descarta un borrador: un asiento contabilizado se revierte.",
        )
    before, after = apply_changes(
        entry,
        {
            "status": "discarded",
            "discarded_at": now(),
            "discarded_by": actor_id,
            "discard_reason": reason,
        },
    )
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "journal_entry",
        "discarded",
        entry.id,
        before=before,
        after=after,
    )
    db.commit()
    return entry


# --- Contabilización ----------------------------------------------------------------------


def _check_postable(db: Session, entry: JournalEntry, year: FiscalYear) -> None:
    """Las mismas reglas que el trigger, con mensajes legibles."""
    lines = lines_of(db, [entry.id]).get(entry.id, [])
    if len(lines) < 2:
        raise AppError(
            "ENTRY_TOO_FEW_LINES",
            f"Un asiento se contabiliza con al menos dos líneas (tiene {len(lines)}).",
            status_code=422,
        )
    debit = sum((line.debit for line in lines), ZERO)
    credit = sum((line.credit for line in lines), ZERO)
    if debit != credit or debit == 0:
        difference = debit - credit
        raise AppError(
            "ENTRY_UNBALANCED",
            f"El asiento no balancea: debe {pyg(debit)} y haber {pyg(credit)} "
            f"(diferencia {pyg(difference)}).",
            details={"debit": pyg(debit), "credit": pyg(credit), "difference": pyg(difference)},
            status_code=422,
        )
    accounts = account_map(db, entry.organization_id, {line.account_id for line in lines})
    bad = [
        {"line": line.line_no, "code": accounts[line.account_id].code}
        for line in lines
        if not accounts[line.account_id].is_postable
        or accounts[line.account_id].archived_at is not None
    ]
    if bad:
        raise AppError(
            "ACCOUNT_NOT_POSTABLE",
            "El asiento usa cuentas agrupadoras o archivadas: "
            + ", ".join(f"línea {b['line']} ({b['code']})" for b in bad)
            + ".",
            details={"lines": bad},
            status_code=422,
        )
    if year.status != "open":
        raise Conflict("FISCAL_YEAR_CLOSED", "El ejercicio está cerrado.")
    if entry.kind != "closing":
        period = periods.period_for(db, year, entry.entry_date)
        if period.status != "open":
            raise Conflict(
                "PERIOD_CLOSED",
                f"El período {period.start_date:%m/%Y} está cerrado: reabrilo o cambiá la fecha "
                "del asiento.",
                details={"period_id": str(period.id)},
            )
    if entry.source_transaction_id is not None:
        voided = db.scalar(
            select(Transaction.voided_at).where(Transaction.id == entry.source_transaction_id)
        )
        if voided is not None:
            raise Conflict(
                "SOURCE_TRANSACTION_VOIDED",
                "El movimiento de finanzas de origen está anulado: descartá este borrador.",
            )


def post_locked(
    db: Session, entry: JournalEntry, year: FiscalYear, actor_id: uuid.UUID
) -> JournalEntry:
    """Contabiliza un borrador con el ejercicio ya bloqueado. No hace commit."""
    _check_postable(db, entry, year)
    entry.status = "posted"
    entry.posted_by = actor_id
    entry.posted_at = now()
    flush_translated(db)
    db.refresh(entry, ["number"])  # lo asignó el trigger
    record(
        db,
        entry.organization_id,
        actor_id,
        "journal_entry",
        "posted",
        entry.id,
        before={"status": "draft", "number": None},
        after={"status": "posted", "number": entry.number},
    )
    return entry


def _lock_year_then_entry(
    db: Session, organization_id: uuid.UUID, entry_id: uuid.UUID
) -> tuple[FiscalYear, JournalEntry]:
    entry = get_entry(db, organization_id, entry_id)
    year = periods.get_fiscal_year(db, organization_id, entry.fiscal_year_id, lock=True)
    entry = get_entry(db, organization_id, entry_id, lock=True)
    if entry.fiscal_year_id != year.id:
        raise Conflict("ENTRY_CHANGED", "El asiento cambió de ejercicio mientras tanto: reintentá.")
    return year, entry


def post_entry(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, entry_id: uuid.UUID
) -> JournalEntry:
    year, entry = _lock_year_then_entry(db, organization_id, entry_id)
    if entry.status != "draft":
        raise Conflict("ENTRY_NOT_DRAFT", "El asiento ya no es un borrador.")
    post_locked(db, entry, year, actor_id)
    db.commit()
    return entry


def reverse_entry(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    entry_id: uuid.UUID,
    *,
    reason: str,
    on: date | None,
) -> JournalEntry:
    """Crea y contabiliza la reversión, y deja el original `reversed`. Devuelve la reversión."""
    original = get_entry(db, organization_id, entry_id)
    if original.status != "posted":
        raise Conflict(
            "ENTRY_NOT_POSTED",
            "Solo se revierte un asiento contabilizado"
            + (" (este ya fue revertido)." if original.status == "reversed" else "."),
        )
    if original.kind not in REVERSIBLE_KINDS:
        raise Conflict(
            "ENTRY_NOT_REVERSIBLE",
            "Una reversión o una refundición no se revierte: cargá un asiento nuevo.",
        )
    day = on or original.entry_date
    if day < original.entry_date:
        raise AppError(
            "REVERSAL_DATE_INVALID",
            "La reversión no puede tener fecha anterior al asiento que revierte.",
            status_code=422,
        )
    year = periods.fiscal_year_for(db, organization_id, day, lock=True)
    original = get_entry(db, organization_id, entry_id, lock=True)
    if original.status != "posted":
        raise Conflict("ENTRY_NOT_POSTED", "El asiento ya fue revertido.")
    if year.status != "open":
        raise Conflict(
            "FISCAL_YEAR_CLOSED",
            f"El ejercicio de la fecha {day:%d/%m/%Y} está cerrado: indicá una fecha de un "
            "ejercicio abierto.",
        )
    period = periods.period_for(db, year, day)
    if period.status != "open":
        raise Conflict(
            "PERIOD_CLOSED",
            f"El período {period.start_date:%m/%Y} está cerrado: indicá una fecha (`date`) de "
            "un período abierto para la reversión.",
            details={"period_id": str(period.id), "date": day.isoformat()},
        )
    lines = [
        LineData(
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
            description=line.description,
            fx_currency=line.fx_currency,
            fx_amount=line.fx_amount,
            fx_rate=line.fx_rate,
        )
        for line in _stored_lines(db, original.id)
    ]
    reversal = create_draft(
        db,
        organization_id,
        actor_id,
        {
            "entry_date": day,
            "description": f"Reversión del asiento N° {original.number}: {reason}"[:500],
            "document_reference": original.document_reference,
        },
        kind="reversal",
        reverses=original,
        lines=lines,
        year=year,
        commit=False,
    )
    post_locked(db, reversal, year, actor_id)
    before, after = apply_changes(original, {"status": "reversed"})
    flush_translated(db)
    after.update({"reversal_entry_id": str(reversal.id), "reason": reason})
    record(
        db,
        organization_id,
        actor_id,
        "journal_entry",
        "reversed",
        original.id,
        before=before,
        after=after,
    )
    db.commit()
    return reversal


# --- Listado ------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntryFilters:
    fiscal_year_id: uuid.UUID | None = None
    status: str | None = None
    kind: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    account_id: uuid.UUID | None = None
    q: str | None = None


def list_entries(
    db: Session,
    organization_id: uuid.UUID,
    filters: EntryFilters,
    *,
    limit: int,
    before: uuid.UUID | None,
) -> list[JournalEntry]:
    """Más recientes primero (fecha, id). El cursor `before` es el id del último recibido."""
    query = select(JournalEntry).where(JournalEntry.organization_id == organization_id)
    if filters.fiscal_year_id is not None:
        query = query.where(JournalEntry.fiscal_year_id == filters.fiscal_year_id)
    if filters.status is not None:
        query = query.where(JournalEntry.status == filters.status)
    if filters.kind is not None:
        query = query.where(JournalEntry.kind == filters.kind)
    if filters.date_from is not None:
        query = query.where(JournalEntry.entry_date >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(JournalEntry.entry_date <= filters.date_to)
    if filters.account_id is not None:
        query = query.where(
            select(JournalLine.id)
            .where(
                JournalLine.entry_id == JournalEntry.id,
                JournalLine.account_id == filters.account_id,
            )
            .exists()
        )
    if filters.q and filters.q.strip():
        term = f"%{escape_like(filters.q.strip())}%"
        conditions: list[ColumnElement[bool]] = [
            JournalEntry.description.ilike(term, escape="\\"),
            JournalEntry.document_reference.ilike(term, escape="\\"),
        ]
        if filters.q.strip().isdigit():
            conditions.append(JournalEntry.number == int(filters.q.strip()))
        query = query.where(or_(*conditions))
    if before is not None:
        cursor = db.execute(
            select(JournalEntry.entry_date, JournalEntry.id).where(
                JournalEntry.id == before, JournalEntry.organization_id == organization_id
            )
        ).first()
        if cursor is None:
            raise AppError("INVALID_CURSOR", "El cursor de paginación no es válido.")
        query = query.where(
            tuple_(JournalEntry.entry_date, JournalEntry.id) < tuple_(cursor[0], cursor[1])
        )
    query = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).limit(limit)
    return list(db.scalars(query))
