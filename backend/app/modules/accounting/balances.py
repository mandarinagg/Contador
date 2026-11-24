"""Sumas de líneas contabilizadas, calculadas al vuelo (D-042).

Cuentan las líneas de los asientos `posted` y `reversed`: la reversión es otro asiento
que compensa, así que los dos suman. Sin tablas de saldos: no hay nada que desincronizar.

Convención de signo:
- `natural(kind, debe, haber)`: saldo en el sentido del **tipo** de la cuenta (activo y
  gasto: debe - haber; pasivo, patrimonio e ingreso: haber - debe). Lo usan los reportes
  jerárquicos (balance general, estado de resultados, árbol del plan): una cuenta
  regularizadora, como "(-) DEPRECIACIÓN ACUMULADA" dentro del activo, da negativo y resta
  en el subtotal de su grupo.
- `by_side(normal_side, debe, haber)`: saldo según la naturaleza de la cuenta (deudora o
  acreedora); lo usa el libro mayor.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounting.models import JournalEntry, JournalLine

ZERO = Decimal(0)
COUNTED_STATUSES = ("posted", "reversed")
DEBIT_KINDS = frozenset({"asset", "expense"})
BALANCE_KINDS = frozenset({"asset", "liability", "equity"})
RESULT_KINDS = frozenset({"income", "expense"})


@dataclass(frozen=True)
class Sums:
    debit: Decimal = ZERO
    credit: Decimal = ZERO

    def __add__(self, other: "Sums") -> "Sums":
        return Sums(self.debit + other.debit, self.credit + other.credit)


def natural(kind: str, sums: Sums) -> Decimal:
    if kind in DEBIT_KINDS:
        return sums.debit - sums.credit
    return sums.credit - sums.debit


def by_side(normal_side: str, debit: Decimal, credit: Decimal) -> Decimal:
    return debit - credit if normal_side == "debit" else credit - debit


def account_sums(
    db: Session,
    organization_id: uuid.UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    fiscal_year_id: uuid.UUID | None = None,
    exclude_closing: bool = False,
) -> dict[uuid.UUID, Sums]:
    """Debe y haber contabilizados por cuenta, en una sola consulta agrupada."""
    query = (
        select(JournalLine.account_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status.in_(COUNTED_STATUSES),
        )
        .group_by(JournalLine.account_id)
    )
    if date_from is not None:
        query = query.where(JournalEntry.entry_date >= date_from)
    if date_to is not None:
        query = query.where(JournalEntry.entry_date <= date_to)
    if fiscal_year_id is not None:
        query = query.where(JournalEntry.fiscal_year_id == fiscal_year_id)
    if exclude_closing:
        query = query.where(JournalEntry.kind != "closing")
    return {account_id: Sums(debit, credit) for account_id, debit, credit in db.execute(query)}


def account_sums_by_center(
    db: Session,
    organization_id: uuid.UUID,
    *,
    date_from: date,
    date_to: date,
    exclude_closing: bool = False,
) -> dict[uuid.UUID | None, dict[uuid.UUID, Sums]]:
    """Como `account_sums`, separado por centro de costos (`None` = sin centro, D-060)."""
    query = (
        select(
            JournalLine.cost_center_id,
            JournalLine.account_id,
            func.sum(JournalLine.debit),
            func.sum(JournalLine.credit),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status.in_(COUNTED_STATUSES),
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
        )
        .group_by(JournalLine.cost_center_id, JournalLine.account_id)
    )
    if exclude_closing:
        query = query.where(JournalEntry.kind != "closing")
    result: dict[uuid.UUID | None, dict[uuid.UUID, Sums]] = {}
    for center_id, account_id, debit, credit in db.execute(query):
        result.setdefault(center_id, {})[account_id] = Sums(debit, credit)
    return result
