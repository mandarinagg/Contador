"""Utilidades compartidas de la contabilidad: auditoría, importes en guaraníes y errores.

- Importes (D-036): el debe y el haber son guaraníes enteros. `Decimal` en Python,
  `NUMERIC(18,2)` en la base y string en JSON; nunca `float` (BR-ACC-05).
- Auditoría (BR-AUD-01): todo alta, cambio, contabilización, reversión, descarte, cierre y
  reapertura se registra con `audit.record`, con solo los campos que cambian.
- Triggers: la base rechaza lo prohibido con SQLSTATE 23000 y un nombre `trg_*`. El
  servicio valida antes para dar errores legibles; si igual llega un rechazo de la base
  (por ejemplo, una carrera), `translate_integrity` lo convierte en un error de la API.
"""

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.modules.audit import service as audit
from app.modules.finance.money import AmountError, check_amount, format_amount
from app.modules.finance.service import apply_changes, jsonable, now, snapshot

__all__ = [
    "ZERO",
    "apply_changes",
    "flush_translated",
    "jsonable",
    "now",
    "pyg",
    "pyg_amount",
    "record",
    "snapshot",
    "translate_integrity",
]

ZERO = Decimal(0)
FUNCTIONAL_CURRENCY = "PYG"


def record(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    entity: str,
    verb: str,
    entity_id: uuid.UUID,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    kind = f"accounting.{entity}"
    audit.record(
        db,
        action=f"{kind}.{verb}",
        entity_type=kind,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_user_id=actor_id,
        before=before,
        after=after,
    )


def pyg(amount: Decimal) -> str:
    """Importe en guaraníes para la API (`"150000"`, nunca `"-0"`)."""
    return format_amount(amount, FUNCTIONAL_CURRENCY)


def pyg_amount(amount: Decimal, *, field: str) -> Decimal:
    """Valida un importe de línea: guaraníes enteros, no negativo."""
    try:
        value = check_amount(amount, FUNCTIONAL_CURRENCY)
    except AmountError as exc:
        raise AppError("INVALID_AMOUNT", f"{field}: {exc}", status_code=422) from exc
    if value < 0:
        raise AppError(
            "INVALID_AMOUNT", f"{field}: el debe y el haber van en positivo.", status_code=422
        )
    return value


# Rechazos de los triggers y restricciones que pueden llegar por una carrera, traducidos.
_TRIGGER_ERRORS: Mapping[str, tuple[str, str, int]] = {
    "trg_journal_entries_unbalanced": ("ENTRY_UNBALANCED", "El asiento no balancea.", 422),
    "trg_journal_entries_min_lines": (
        "ENTRY_TOO_FEW_LINES",
        "Un asiento se contabiliza con al menos dos líneas.",
        422,
    ),
    "trg_journal_entries_period_closed": (
        "PERIOD_CLOSED",
        "El período de la fecha del asiento está cerrado.",
        409,
    ),
    "trg_journal_entries_year_closed": ("FISCAL_YEAR_CLOSED", "El ejercicio está cerrado.", 409),
    "trg_journal_entries_account_not_postable": (
        "ACCOUNT_NOT_POSTABLE",
        "El asiento usa una cuenta agrupadora o archivada.",
        422,
    ),
    "trg_journal_lines_account_not_postable": (
        "ACCOUNT_NOT_POSTABLE",
        "Solo las cuentas imputables y no archivadas reciben líneas.",
        422,
    ),
    "trg_journal_lines_entry_not_draft": (
        "ENTRY_NOT_DRAFT",
        "El asiento ya no es un borrador: no se modifica.",
        409,
    ),
    "trg_journal_entries_posted_immutable": (
        "ENTRY_NOT_DRAFT",
        "El asiento está contabilizado: no se modifica, se revierte.",
        409,
    ),
    "trg_journal_entries_final": ("ENTRY_NOT_DRAFT", "El asiento ya no se modifica.", 409),
    "trg_journal_entries_source_voided": (
        "SOURCE_TRANSACTION_VOIDED",
        "El movimiento de finanzas de origen está anulado.",
        409,
    ),
    "trg_ledger_accounts_in_use": (
        "ACCOUNT_IN_USE",
        "La cuenta tiene líneas de asiento: no cambia de código, tipo, naturaleza ni "
        "imputabilidad.",
        409,
    ),
    "uq_journal_entries_live_source": (
        "TRANSACTION_HAS_ENTRY",
        "El movimiento ya tiene un asiento vivo (borrador o contabilizado).",
        409,
    ),
    "uq_ledger_accounts_organization_id_code": (
        "ACCOUNT_CODE_TAKEN",
        "Ya existe una cuenta con ese código.",
        409,
    ),
    "ex_fiscal_years_no_overlap": (
        "FISCAL_YEAR_OVERLAP",
        "El ejercicio se superpone con otro existente.",
        409,
    ),
}


def translate_integrity(exc: IntegrityError) -> AppError | None:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if isinstance(constraint, str) and constraint in _TRIGGER_ERRORS:
        code, message, status = _TRIGGER_ERRORS[constraint]
        if status == 409:
            return Conflict(code, message)
        return AppError(code, message, status_code=status)
    return None


@contextmanager
def translated() -> Iterator[None]:
    try:
        yield
    except IntegrityError as exc:
        error = translate_integrity(exc)
        if error is not None:
            raise error from exc
        raise


def flush_translated(db: Session) -> None:
    """`flush` en un SAVEPOINT; un rechazo conocido de la base pasa a ser un error de la API."""
    with translated(), db.begin_nested():
        db.flush()
