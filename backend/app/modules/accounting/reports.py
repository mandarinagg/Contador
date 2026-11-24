"""Reportes contables calculados al vuelo desde las líneas contabilizadas (D-042).

- Libro diario: asientos contabilizados (y revertidos) por fecha y número, con sus líneas.
- Libro mayor: saldo anterior al rango, movimientos con saldo acumulado y saldo final, en
  el sentido de la naturaleza de la cuenta (deudora: debe - haber; acreedora: al revés).
- Balance de comprobación: por cuenta imputable con movimiento en el rango o saldo inicial,
  saldo inicial (D-062: todo lo contabilizado antes de `from`, refundición incluida, así que
  las cuentas de resultado arrancan en cero en el ejercicio siguiente a uno cerrado), sumas
  del debe y del haber del rango, saldo del rango y saldo final. Los totales coinciden.
- Balance general: activo, pasivo y patrimonio agrupados por la jerarquía del plan, más el
  resultado no refundido (las cuentas de ingreso y gasto: de los ejercicios cerrados ya
  quedaron en cero por la refundición). Verifica activo = pasivo + patrimonio + resultado.
- Estado de resultados: ingresos y gastos agrupados por la jerarquía (RG 49/2014 Anexo 2),
  sin el asiento de refundición (si no, el resultado de un ejercicio cerrado daría cero).
  Con `by_cost_center`, además una columna por centro de costos y una "sin centro" (D-060):
  las columnas de cada cuenta suman su importe.

Todos devuelven `chart_status`: si no es `validated`, la interfaz muestra el aviso "Plan de
cuentas sin validar por un contador" (D-038).
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.accounting import chart
from app.modules.accounting.balances import (
    BALANCE_KINDS,
    COUNTED_STATUSES,
    RESULT_KINDS,
    ZERO,
    Sums,
    account_sums,
    account_sums_by_center,
    by_side,
    natural,
)
from app.modules.accounting.models import CostCenter, JournalEntry, JournalLine, LedgerAccount


def check_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise AppError("INVALID_RANGE", "La fecha final es anterior a la inicial.", status_code=422)


# --- Libro diario -------------------------------------------------------------------------


@dataclass
class JournalPage:
    entries: list[JournalEntry]
    total_debit: Decimal
    total_credit: Decimal


def journal(
    db: Session,
    organization_id: uuid.UUID,
    date_from: date,
    date_to: date,
    *,
    limit: int,
    after: uuid.UUID | None,
) -> JournalPage:
    check_range(date_from, date_to)
    base = select(JournalEntry).where(
        JournalEntry.organization_id == organization_id,
        JournalEntry.status.in_(COUNTED_STATUSES),
        JournalEntry.entry_date >= date_from,
        JournalEntry.entry_date <= date_to,
    )
    query = base
    if after is not None:
        cursor = db.execute(
            select(JournalEntry.entry_date, JournalEntry.number).where(
                JournalEntry.id == after, JournalEntry.organization_id == organization_id
            )
        ).first()
        if cursor is None:
            raise AppError("INVALID_CURSOR", "El cursor de paginación no es válido.")
        query = query.where(
            tuple_(JournalEntry.entry_date, JournalEntry.number) > tuple_(cursor[0], cursor[1])
        )
    page = list(
        db.scalars(query.order_by(JournalEntry.entry_date, JournalEntry.number).limit(limit))
    )
    totals = db.execute(
        select(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status.in_(COUNTED_STATUSES),
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
        )
    ).one()
    return JournalPage(page, Decimal(totals[0]), Decimal(totals[1]))


@dataclass(frozen=True)
class JournalLineRow:
    entry_date: date
    number: int
    entry_description: str
    document_reference: str | None
    account_code: str
    account_name: str
    cost_center_code: str | None
    line_description: str | None
    debit: Decimal
    credit: Decimal


def journal_lines(
    db: Session, organization_id: uuid.UUID, date_from: date, date_to: date
) -> Iterator[JournalLineRow]:
    """Todas las líneas del diario del rango, sin paginar (para exportar), en una consulta."""
    check_range(date_from, date_to)
    query = (
        select(
            JournalEntry.entry_date,
            JournalEntry.number,
            JournalEntry.description,
            JournalEntry.document_reference,
            LedgerAccount.code,
            LedgerAccount.name,
            CostCenter.code,
            JournalLine.description,
            JournalLine.debit,
            JournalLine.credit,
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
        .outerjoin(CostCenter, CostCenter.id == JournalLine.cost_center_id)
        .where(
            JournalEntry.organization_id == organization_id,
            JournalEntry.status.in_(COUNTED_STATUSES),
            JournalEntry.entry_date >= date_from,
            JournalEntry.entry_date <= date_to,
        )
        .order_by(JournalEntry.entry_date, JournalEntry.number, JournalLine.line_no)
    )
    for (
        entry_date,
        number,
        entry_description,
        reference,
        code,
        name,
        center,
        line_description,
        debit,
        credit,
    ) in db.execute(query.execution_options(yield_per=2000)):
        yield JournalLineRow(
            entry_date,
            number or 0,
            entry_description,
            reference,
            code,
            name,
            center,
            line_description,
            debit,
            credit,
        )


# --- Libro mayor --------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerMovement:
    line_id: uuid.UUID
    entry_id: uuid.UUID
    number: int
    entry_date: date
    entry_description: str
    line_description: str | None
    document_reference: str | None
    debit: Decimal
    credit: Decimal
    balance: Decimal


@dataclass
class LedgerReport:
    account: LedgerAccount
    opening_balance: Decimal
    total_debit: Decimal
    total_credit: Decimal
    closing_balance: Decimal
    movements: list[LedgerMovement]
    next_cursor: uuid.UUID | None


def _ledger_lines(
    organization_id: uuid.UUID, account_id: uuid.UUID
) -> Select[JournalLine, JournalEntry]:
    return (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.organization_id == organization_id,
            JournalEntry.status.in_(COUNTED_STATUSES),
        )
    )


def ledger(
    db: Session,
    organization_id: uuid.UUID,
    account_id: uuid.UUID,
    date_from: date,
    date_to: date,
    *,
    limit: int,
    after: uuid.UUID | None,
) -> LedgerReport:
    check_range(date_from, date_to)
    account = chart.get_account(db, organization_id, account_id)
    if not account.is_postable:
        raise AppError(
            "ACCOUNT_NOT_POSTABLE",
            "El libro mayor es de una cuenta imputable; una agrupadora no tiene movimientos "
            "propios.",
            status_code=422,
        )

    def sums(*conditions: ColumnElement[bool]) -> tuple[Decimal, Decimal]:
        row = db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(
                JournalLine.account_id == account.id,
                JournalEntry.organization_id == organization_id,
                JournalEntry.status.in_(COUNTED_STATUSES),
                *conditions,
            )
        ).one()
        return Decimal(row[0]), Decimal(row[1])

    side = account.normal_side
    before_debit, before_credit = sums(JournalEntry.entry_date < date_from)
    opening = by_side(side, before_debit, before_credit)
    in_range = (JournalEntry.entry_date >= date_from, JournalEntry.entry_date <= date_to)
    total_debit, total_credit = sums(*in_range)
    order_key = tuple_(JournalEntry.entry_date, JournalEntry.number, JournalLine.line_no)

    running = opening
    query = _ledger_lines(organization_id, account.id).where(*in_range)
    if after is not None:
        cursor = db.execute(
            select(JournalEntry.entry_date, JournalEntry.number, JournalLine.line_no)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalLine.id == after, JournalLine.account_id == account.id)
        ).first()
        if cursor is None:
            raise AppError("INVALID_CURSOR", "El cursor de paginación no es válido.")
        cursor_key = tuple_(cursor[0], cursor[1], cursor[2])
        prior_debit, prior_credit = sums(*in_range, order_key <= cursor_key)
        running = opening + by_side(side, prior_debit, prior_credit)
        query = query.where(order_key > cursor_key)
    rows = db.execute(
        query.order_by(JournalEntry.entry_date, JournalEntry.number, JournalLine.line_no).limit(
            limit
        )
    ).all()
    movements: list[LedgerMovement] = []
    for line, entry in rows:
        running += by_side(side, line.debit, line.credit)
        movements.append(
            LedgerMovement(
                line_id=line.id,
                entry_id=entry.id,
                number=entry.number or 0,
                entry_date=entry.entry_date,
                entry_description=entry.description,
                line_description=line.description,
                document_reference=entry.document_reference,
                debit=line.debit,
                credit=line.credit,
                balance=running,
            )
        )
    return LedgerReport(
        account=account,
        opening_balance=opening,
        total_debit=total_debit,
        total_credit=total_credit,
        closing_balance=opening + by_side(side, total_debit, total_credit),
        movements=movements,
        next_cursor=movements[-1].line_id if len(movements) == limit else None,
    )


# --- Balance de comprobación ----------------------------------------------------------------


@dataclass(frozen=True)
class TrialRow:
    account: LedgerAccount
    debit: Decimal
    credit: Decimal
    # Debe - haber de todo lo contabilizado antes del rango (D-062).
    opening: Decimal = ZERO

    @property
    def debit_balance(self) -> Decimal:
        return max(self.debit - self.credit, ZERO)

    @property
    def credit_balance(self) -> Decimal:
        return max(self.credit - self.debit, ZERO)

    @property
    def opening_debit(self) -> Decimal:
        return max(self.opening, ZERO)

    @property
    def opening_credit(self) -> Decimal:
        return max(-self.opening, ZERO)

    @property
    def closing(self) -> Decimal:
        return self.opening + self.debit - self.credit

    @property
    def closing_debit(self) -> Decimal:
        return max(self.closing, ZERO)

    @property
    def closing_credit(self) -> Decimal:
        return max(-self.closing, ZERO)


def trial_balance(
    db: Session, organization_id: uuid.UUID, date_from: date, date_to: date
) -> list[TrialRow]:
    check_range(date_from, date_to)
    sums = account_sums(db, organization_id, date_from=date_from, date_to=date_to)
    # Saldos iniciales: todo lo anterior, con la refundición (D-042: sin asientos de apertura).
    before = account_sums(db, organization_id, date_to=date_from - timedelta(days=1))
    accounts = chart.list_accounts(db, organization_id)
    rows = []
    for a in accounts:
        moved = sums.get(a.id)
        prior = before.get(a.id)
        opening = prior.debit - prior.credit if prior is not None else ZERO
        has_movement = moved is not None and (moved.debit != 0 or moved.credit != 0)
        if has_movement or opening != 0:
            rows.append(
                TrialRow(
                    a,
                    moved.debit if moved is not None else ZERO,
                    moved.credit if moved is not None else ZERO,
                    opening,
                )
            )
    return rows


# --- Estados jerárquicos --------------------------------------------------------------------


@dataclass
class Section:
    kind: str
    nodes: list[chart.Node] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((n.amount for n in self.nodes), ZERO)


def _pruned(nodes: list[chart.Node]) -> list[chart.Node]:
    """Sin las ramas que no tuvieron ningún movimiento."""
    kept = []
    for node in nodes:
        if node.has_movement:
            node.children = _pruned(node.children)
            kept.append(node)
    return kept


def _sections(
    db: Session, organization_id: uuid.UUID, sums: dict[uuid.UUID, Sums], kinds: tuple[str, ...]
) -> dict[str, Section]:
    roots = chart.build_tree(chart.list_accounts(db, organization_id), sums)
    sections = {kind: Section(kind) for kind in kinds}
    for root in _pruned(roots):
        if root.account.kind in sections:
            sections[root.account.kind].nodes.append(root)
    return sections


@dataclass
class BalanceSheet:
    assets: Section
    liabilities: Section
    equity: Section
    result: Decimal

    @property
    def liabilities_and_equity(self) -> Decimal:
        return self.liabilities.total + self.equity.total + self.result

    @property
    def balanced(self) -> bool:
        return self.assets.total == self.liabilities_and_equity


def balance_sheet(db: Session, organization_id: uuid.UUID, at: date) -> BalanceSheet:
    sums = account_sums(db, organization_id, date_to=at)
    sections = _sections(db, organization_id, sums, ("asset", "liability", "equity"))
    accounts = chart.list_accounts(db, organization_id)
    # Resultado no refundido: haber - debe de las cuentas de resultado hasta la fecha.
    result = sum(
        (
            natural("income", sums[a.id])
            for a in accounts
            if a.kind in RESULT_KINDS and a.id in sums
        ),
        ZERO,
    )
    assert all(kind in BALANCE_KINDS for kind in sections)
    return BalanceSheet(sections["asset"], sections["liability"], sections["equity"], result)


@dataclass(frozen=True)
class CenterColumn:
    """Columna del estado de resultados por centro (`center` None = "sin centro")."""

    center: CostCenter | None
    total_income: Decimal
    total_expense: Decimal

    @property
    def result(self) -> Decimal:
        return self.total_income - self.total_expense


@dataclass
class IncomeStatement:
    nodes: list[chart.Node]
    total_income: Decimal
    total_expense: Decimal
    # Solo con `by_cost_center`: las columnas y, por cuenta, su importe en cada columna.
    columns: list[CenterColumn] | None = None
    column_amounts: dict[uuid.UUID, list[Decimal]] = field(default_factory=dict)

    @property
    def result(self) -> Decimal:
        return self.total_income - self.total_expense


def _result_totals(nodes: list[chart.Node]) -> tuple[Decimal, Decimal]:
    income = sum((n.amount for n in nodes if n.account.kind == "income"), ZERO)
    expense = sum((n.amount for n in nodes if n.account.kind == "expense"), ZERO)
    return income, expense


def _amounts(nodes: list[chart.Node], into: dict[uuid.UUID, Decimal]) -> None:
    for node in nodes:
        into[node.account.id] = node.amount
        _amounts(node.children, into)


def income_statement(
    db: Session,
    organization_id: uuid.UUID,
    date_from: date,
    date_to: date,
    *,
    by_cost_center: bool = False,
) -> IncomeStatement:
    check_range(date_from, date_to)
    sums = account_sums(
        db, organization_id, date_from=date_from, date_to=date_to, exclude_closing=True
    )
    accounts = chart.list_accounts(db, organization_id)
    roots = chart.build_tree(accounts, sums)
    nodes = [r for r in _pruned(roots) if r.account.kind in RESULT_KINDS]
    income, expense = _result_totals(nodes)
    statement = IncomeStatement(nodes, income, expense)
    if not by_cost_center:
        return statement
    by_center = account_sums_by_center(
        db, organization_id, date_from=date_from, date_to=date_to, exclude_closing=True
    )
    centers = {
        c.id: c
        for c in db.scalars(
            select(CostCenter).where(
                CostCenter.organization_id == organization_id,
                CostCenter.id.in_([i for i in by_center if i is not None]),
            )
        )
    }
    keys: list[uuid.UUID | None] = [
        *sorted(centers, key=lambda i: centers[i].code),
        None,
    ]
    columns: list[CenterColumn] = []
    amounts: list[dict[uuid.UUID, Decimal]] = []
    for key in keys:
        column_roots = [
            r
            for r in chart.build_tree(accounts, by_center.get(key, {}))
            if r.account.kind in RESULT_KINDS
        ]
        column_income, column_expense = _result_totals(column_roots)
        columns.append(
            CenterColumn(centers[key] if key is not None else None, column_income, column_expense)
        )
        by_account: dict[uuid.UUID, Decimal] = {}
        _amounts(column_roots, by_account)
        amounts.append(by_account)
    flat: dict[uuid.UUID, Decimal] = {}
    _amounts(nodes, flat)
    statement.columns = columns
    statement.column_amounts = {
        account_id: [column.get(account_id, ZERO) for column in amounts] for account_id in flat
    }
    return statement
