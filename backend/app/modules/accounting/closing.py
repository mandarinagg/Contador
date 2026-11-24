"""Cierre del ejercicio con asiento de refundición de resultados (D-039, BR-ACC-12).

Exige: todos los períodos cerrados, ningún borrador en el ejercicio y la cuenta de
resultados configurada (patrimonio, imputable). Genera y contabiliza la refundición, que
deja en cero cada cuenta de ingreso y gasto con saldo contra la cuenta de resultados, y
marca el ejercicio cerrado, que no se reabre en esta tanda.

Fase 3B: además exige la depreciación contabilizada de todos los meses del ejercicio con
cuotas, y guarda en la misma transacción los valores por bien del ejercicio (D-066).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.modules.accounting import asset_schedule, chart, depreciation, entries, periods
from app.modules.accounting.balances import RESULT_KINDS, ZERO, account_sums
from app.modules.accounting.common import apply_changes, flush_translated, now, pyg, record
from app.modules.accounting.models import FiscalYear, JournalEntry, LedgerAccount, Period


def close_fiscal_year(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, fiscal_year_id: uuid.UUID
) -> FiscalYear:
    year = periods.get_fiscal_year(db, organization_id, fiscal_year_id, lock=True)
    if year.status != "open":
        raise Conflict("FISCAL_YEAR_CLOSED", "El ejercicio ya está cerrado.")
    open_periods = [
        {
            "id": str(p.id),
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat(),
        }
        for p in db.scalars(
            select(Period)
            .where(Period.fiscal_year_id == year.id, Period.status == "open")
            .order_by(Period.start_date)
        )
    ]
    if open_periods:
        raise Conflict(
            "PERIODS_OPEN",
            f"Para cerrar el ejercicio, cerrá antes sus {len(open_periods)} período(s) abiertos.",
            details={"periods": open_periods},
        )
    drafts = periods.drafts_in(db, year.id)
    if drafts:
        raise Conflict(
            "FISCAL_YEAR_HAS_DRAFTS",
            f"El ejercicio tiene {len(drafts)} borrador(es): contabilizalos o descartalos.",
            details={"drafts": drafts},
        )
    depreciation.check_year_depreciated(db, year)
    settings = chart.get_settings(db, organization_id)
    target_id = settings.retained_earnings_account_id if settings is not None else None
    if target_id is None:
        raise Conflict(
            "RETAINED_EARNINGS_NOT_SET",
            "Configurá la cuenta de resultados del ejercicio (por ejemplo, 3.03.02) antes de "
            "cerrar.",
        )
    target = chart.get_account(db, organization_id, target_id)
    if target.kind != "equity" or not target.is_postable or target.archived_at is not None:
        raise AppError(
            "INVALID_RETAINED_EARNINGS_ACCOUNT",
            "La cuenta de resultados configurada tiene que ser de patrimonio, imputable y no "
            "archivada.",
            status_code=422,
        )

    sums = account_sums(db, organization_id, fiscal_year_id=year.id)
    accounts = {
        a.id: a
        for a in db.scalars(
            select(LedgerAccount).where(
                LedgerAccount.organization_id == organization_id,
                LedgerAccount.kind.in_(RESULT_KINDS),
                LedgerAccount.id.in_(list(sums)),
            )
        )
    }
    lines: list[entries.LineData] = []
    result = ZERO  # haber - debe de las cuentas de resultado: positivo = ganancia
    for account in sorted(accounts.values(), key=lambda a: chart.code_key(a.code)):
        balance = sums[account.id].debit - sums[account.id].credit
        if balance == 0:
            continue
        result -= balance
        lines.append(
            entries.LineData(
                account_id=account.id,
                debit=-balance if balance < 0 else ZERO,
                credit=balance if balance > 0 else ZERO,
                description="Refundición de resultados",
            )
        )
    closing: JournalEntry | None = None
    if lines:
        if result != 0:
            lines.append(
                entries.LineData(
                    account_id=target.id,
                    debit=-result if result < 0 else ZERO,
                    credit=result if result > 0 else ZERO,
                    description="Resultado del ejercicio" + (" (pérdida)" if result < 0 else ""),
                )
            )
        closing = entries.create_draft(
            db,
            organization_id,
            actor_id,
            {
                "entry_date": year.end_date,
                "description": (
                    f"Refundición de resultados del ejercicio {year.start_date:%d/%m/%Y} - "
                    f"{year.end_date:%d/%m/%Y}"
                ),
                "document_reference": None,
            },
            kind="closing",
            lines=lines,
            year=year,
            commit=False,
        )
        entries.post_locked(db, closing, year, actor_id)

    asset_values = asset_schedule.write_year_values(db, year)
    before, after = apply_changes(
        year,
        {
            "status": "closed",
            "closed_at": now(),
            "closed_by": actor_id,
            "closing_entry_id": closing.id if closing is not None else None,
        },
    )
    flush_translated(db)
    after.update(
        {
            "result": pyg(result),
            "closing_entry_number": closing.number if closing is not None else None,
            "asset_year_values": asset_values,
        }
    )
    record(
        db, organization_id, actor_id, "fiscal_year", "closed", year.id, before=before, after=after
    )
    db.commit()
    return year
