"""Resúmenes: saldos, ingresos, gastos y neto por moneda y por mes (BR-FIN-02, D-026).

- Nunca se suman monedas distintas: todo total va con su moneda.
- Se excluyen los movimientos anulados y las transferencias entre cuentas propias (no
  son ingreso ni gasto). Los saldos sí incluyen las transferencias: el dinero se movió.
- Ingreso = suma de importes positivos; gasto = suma de los negativos expresada en
  positivo; neto = ingreso - gasto.
- Lo consolidado va siempre **por contexto identificado**: no existe un total que mezcle
  la empresa y lo personal.

Rendimiento (D-033): saldos, flujo mensual y gasto por categoría salen de **una sola
pasada** sobre los movimientos del contexto (una consulta agrupada por cuenta, mes,
categoría y signo, con una sola suma), no de tres. Las filas que solo cuentan para el
saldo (anteriores al período o transferencias) se agrupan por cuenta y nada más; el resto
se reparte por mes y categoría. Sin cachés ni saldos precalculados: cada pedido lee los
movimientos reales.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, and_, case, cast, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
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


@dataclass
class _Aggregates:
    """Resultado de la pasada única, ya repartido por moneda."""

    balance_sums: dict[uuid.UUID, Decimal]
    by_month: dict[tuple[str, str], Flow]
    expenses: dict[tuple[str, uuid.UUID | None], Decimal]


def _aggregate(
    db: Session,
    ctx: FinancialContext,
    accounts: list[Account],
    date_from: date,
    date_to: date,
    *,
    by_category: bool,
) -> _Aggregates:
    """Una consulta para saldos, ingresos/gastos por mes y gasto por categoría.

    Se lee todo movimiento no anulado hasta `date_to` y se agrupa por
    (cuenta, mes, categoría, signo) con **una sola suma**. Las columnas `mes`, `categoría`
    y `signo` valen NULL cuando la fila no cuenta como flujo (anterior a `date_from` o
    transferencia); la categoría solo se informa en los gastos. Esas filas aportan
    únicamente al saldo; el resto, además, a ingresos (signo positivo) o gastos (negativo).

    La moneda se toma de la cuenta: la clave foránea compuesta (cuenta, contexto, moneda)
    garantiza que es la del movimiento (D-025).
    """
    in_flow = and_(Transaction.transfer_group_id.is_(None), Transaction.booked_on >= date_from)
    month = case(
        (in_flow, func.date_trunc("month", cast(Transaction.booked_on, DateTime))),
    ).label("month")
    positive = case((in_flow, Transaction.amount > 0)).label("positive")
    columns = [Transaction.account_id, month]
    if by_category:
        columns.append(
            case((and_(in_flow, Transaction.amount < 0), Transaction.category_id)).label(
                "category_id"
            )
        )
    columns.append(positive)
    query = (
        select(*columns, func.sum(Transaction.amount))
        .where(
            Transaction.context_id == ctx.id,
            Transaction.voided_at.is_(None),
            Transaction.booked_on <= date_to,
        )
        .group_by(*columns)
    )
    currency_of = {a.id: a.currency for a in accounts}
    balance_sums: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    by_month: dict[tuple[str, str], Flow] = {}
    expenses: dict[tuple[str, uuid.UUID | None], Decimal] = defaultdict(Decimal)
    for row in db.execute(query):
        # Orden de columnas: cuenta, mes, [categoría,] signo, suma.
        account_id, month_start, is_positive, total = row[0], row[1], row[-2], row[-1]
        balance_sums[account_id] += total
        if month_start is None:
            continue
        currency = currency_of[account_id]
        flow = by_month.setdefault((currency, _month_label(month_start)), Flow())
        if is_positive:
            flow.income += total
        else:
            flow.expense -= total
            if by_category:
                expenses[(currency, row[2])] -= total
    return _Aggregates(
        balance_sums=dict(balance_sums),
        by_month=dict(sorted(by_month.items())),
        expenses=dict(expenses),
    )


def _month_label(month_start: datetime) -> str:
    return f"{month_start.year:04d}-{month_start.month:02d}"


def _accounts(db: Session, ctx: FinancialContext) -> list[Account]:
    return list(
        db.scalars(select(Account).where(Account.context_id == ctx.id).order_by(Account.name))
    )


def _with_balances(
    accounts: list[Account], sums: dict[uuid.UUID, Decimal]
) -> list[tuple[Account, Decimal]]:
    return [(a, a.opening_balance + sums.get(a.id, ZERO)) for a in accounts]


def summarize(db: Session, ctx: FinancialContext, date_from: date, date_to: date) -> ContextSummary:
    accounts = _accounts(db, ctx)
    agg = _aggregate(db, ctx, accounts, date_from, date_to, by_category=True)
    totals: dict[str, Flow] = defaultdict(Flow)
    for (currency, _), flow in agg.by_month.items():
        totals[currency].income += flow.income
        totals[currency].expense += flow.expense

    category_ids = [cid for _, cid in agg.expenses if cid is not None]
    names: dict[uuid.UUID, str] = {}
    if category_ids:
        category_names = select(Category.id, Category.name).where(Category.id.in_(category_ids))
        names = {cid: name for cid, name in db.execute(category_names)}
    expenses = sorted(
        (
            (currency, cid, names.get(cid, "Sin categoría") if cid else "Sin categoría", amount)
            for (currency, cid), amount in agg.expenses.items()
        ),
        key=lambda item: (item[0], -item[3], item[2]),
    )
    return ContextSummary(
        balances=_with_balances(accounts, agg.balance_sums),
        totals=dict(sorted(totals.items())),
        by_month=agg.by_month,
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
    accounts = _accounts(db, ctx)
    agg = _aggregate(db, ctx, accounts, date_from, date_to, by_category=False)
    result: dict[str, ContextTotals] = {}
    for account, balance in _with_balances(accounts, agg.balance_sums):
        entry = result.setdefault(account.currency, ContextTotals(flow=Flow(), balance=ZERO))
        entry.balance += balance
    for (currency, _), flow in agg.by_month.items():
        entry = result.setdefault(currency, ContextTotals(flow=Flow(), balance=ZERO))
        entry.flow.income += flow.income
        entry.flow.expense += flow.expense
    return dict(sorted(result.items()))
