"""Resúmenes: saldos, ingresos, gastos y neto por moneda y por mes (BR-FIN-02, D-026).

- Nunca se suman monedas distintas: todo total va con su moneda.
- Se excluyen los movimientos anulados y las transferencias entre cuentas propias (no
  son ingreso ni gasto). Los saldos sí incluyen las transferencias: el dinero se movió.
- Ingreso = suma de importes positivos; gasto = suma de los negativos expresada en
  positivo; neto = ingreso - gasto.
- Lo consolidado va siempre **por contexto identificado**: no existe un total que mezcle
  la empresa y lo personal.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.finance import service as fs
from app.modules.finance.models import Account, Category, FinancialContext, Transaction

ZERO = Decimal(0)
MAX_RANGE_DAYS = 366 * 10


def default_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Por defecto, los últimos 12 meses calendario hasta hoy (incluido el mes actual)."""
    end = date_to or date.today()
    if date_from is None:
        month_index = end.year * 12 + end.month - 1 - 11
        date_from = date(month_index // 12, month_index % 12 + 1, 1)
    if date_from > end:
        raise AppError(
            "INVALID_RANGE", "La fecha inicial es posterior a la final.", status_code=422
        )
    if (end - date_from).days > MAX_RANGE_DAYS:
        raise AppError("INVALID_RANGE", "El período no puede superar 10 años.", status_code=422)
    return date_from, end


@dataclass
class Flow:
    income: Decimal = ZERO
    expense: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.income - self.expense


@dataclass
class ContextSummary:
    balances: list[tuple[Account, Decimal]]
    totals: dict[str, Flow]
    by_month: dict[tuple[str, str], Flow]
    expenses_by_category: list[tuple[str, uuid.UUID | None, str, Decimal]] = field(
        default_factory=list
    )


def _flow_filters(context_id: uuid.UUID, date_from: date, date_to: date) -> list[object]:
    return [
        Transaction.context_id == context_id,
        Transaction.voided_at.is_(None),
        Transaction.transfer_group_id.is_(None),
        Transaction.booked_on >= date_from,
        Transaction.booked_on <= date_to,
    ]


def _account_balances(
    db: Session, ctx: FinancialContext, date_to: date
) -> list[tuple[Account, Decimal]]:
    accounts = list(
        db.scalars(select(Account).where(Account.context_id == ctx.id).order_by(Account.name))
    )
    sums = fs.balances(db, ctx.id, until=date_to)
    return [(a, a.opening_balance + sums.get(a.id, ZERO)) for a in accounts]


def _monthly_flows(
    db: Session, ctx: FinancialContext, date_from: date, date_to: date
) -> dict[tuple[str, str], Flow]:
    month = func.to_char(Transaction.booked_on, "YYYY-MM")
    query = (
        select(
            Transaction.currency,
            month,
            func.coalesce(func.sum(Transaction.amount).filter(Transaction.amount > 0), ZERO),
            func.coalesce(func.sum(-Transaction.amount).filter(Transaction.amount < 0), ZERO),
        )
        .where(*_flow_filters(ctx.id, date_from, date_to))  # type: ignore[arg-type]
        .group_by(Transaction.currency, month)
        .order_by(Transaction.currency, month)
    )
    return {
        (currency, label): Flow(income=income, expense=expense)
        for currency, label, income, expense in db.execute(query)
    }


def summarize(db: Session, ctx: FinancialContext, date_from: date, date_to: date) -> ContextSummary:
    by_month = _monthly_flows(db, ctx, date_from, date_to)
    totals: dict[str, Flow] = defaultdict(Flow)
    for (currency, _), flow in by_month.items():
        totals[currency].income += flow.income
        totals[currency].expense += flow.expense

    expense_query = (
        select(Transaction.currency, Transaction.category_id, func.sum(-Transaction.amount))
        .where(
            *_flow_filters(ctx.id, date_from, date_to),  # type: ignore[arg-type]
            Transaction.amount < 0,
        )
        .group_by(Transaction.currency, Transaction.category_id)
    )
    expense_rows = list(db.execute(expense_query))
    category_ids = [cid for _, cid, _ in expense_rows if cid is not None]
    category_names = select(Category.id, Category.name).where(Category.id.in_(category_ids))
    names = {cid: name for cid, name in db.execute(category_names)}
    expenses = sorted(
        (
            (currency, cid, names.get(cid, "Sin categoría") if cid else "Sin categoría", amount)
            for currency, cid, amount in expense_rows
        ),
        key=lambda item: (item[0], -item[3], item[2]),
    )
    return ContextSummary(
        balances=_account_balances(db, ctx, date_to),
        totals=dict(sorted(totals.items())),
        by_month=by_month,
        expenses_by_category=expenses,
    )


@dataclass
class ContextTotals:
    flow: Flow
    balance: Decimal


def context_totals(
    db: Session, ctx: FinancialContext, date_from: date, date_to: date
) -> dict[str, ContextTotals]:
    """Totales por moneda de un contexto (para el consolidado)."""
    result: dict[str, ContextTotals] = {}
    for account, balance in _account_balances(db, ctx, date_to):
        entry = result.setdefault(account.currency, ContextTotals(flow=Flow(), balance=ZERO))
        entry.balance += balance
    for (currency, _), flow in _monthly_flows(db, ctx, date_from, date_to).items():
        entry = result.setdefault(currency, ContextTotals(flow=Flow(), balance=ZERO))
        entry.flow.income += flow.income
        entry.flow.expense += flow.expense
    return dict(sorted(result.items()))
