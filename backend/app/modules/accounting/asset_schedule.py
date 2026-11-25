"""Cuadro de depreciación del ejercicio (D-067) y valores por bien al cierre (D-066).

Columnas del Anexo de la RG 77/2020 (`DEPRECIACION_PY.md` §5.2), por bien y agrupadas por
categoría, sin el revalúo:
- **valores fiscales:** los parámetros fiscales del bien (vida útil y residual de la
  categoría). La cuota fiscal del ejercicio es la suma de las cuotas mensuales teóricas de
  sus meses (D-065: prorrata mensual, inferencia pendiente D-DEP-1), aunque la depreciación
  contable se haya corrido o no;
- **valores contables:** los de las corridas contabilizadas, con la acumulada al cierre
  coherente con el mayor (`depreciation.accumulated_by_asset`);
- el coeficiente de revalúo va en cero, con una nota: ningún decreto lo dispuso (D-DEP-7);
- un bien dado de baja en el ejercicio muestra valor neto cero (la baja sacó del mayor su
  costo y su acumulada); los dados de baja en ejercicios anteriores no aparecen;
- la vida útil va en meses (la base del cálculo) y en años, que es como la pide el anexo.

El total del valor neto contable (col. 22) se concilia con el saldo al cierre de las cuentas
de activo y de depreciación acumulada de las categorías (prueba: `reconciliation`).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.modules.accounting import chart, depreciation, periods
from app.modules.accounting.balances import ZERO, account_sums, natural
from app.modules.accounting.models import (
    AssetCategory,
    AssetYearValue,
    FiscalYear,
    FixedAsset,
    LedgerAccount,
)

WARNINGS = (
    "Cuadro interno con las columnas del Anexo de la RG 77/2020, pendiente de verificar "
    "contra la fuente oficial: las vidas útiles y los residuales vienen de las categorías "
    "candidatas.",
    "La cuota fiscal del ejercicio se calcula por meses (prorrata mensual desde el mes de "
    "inicio); el anexo es anual y no aclara la prorrata del primer año (D-DEP-1, D-DEP-2).",
    "Las columnas de revalúo van en cero: ningún decreto dispuso un revalúo (D-DEP-7).",
    "Si la empresa liquida el IRE SIMPLE no hay depreciación fiscal: la compra se deduce de "
    "una vez (Ley 6380, art. 26). El régimen se configura recién en la fase 4.",
)

MONEY_COLUMNS = (
    "cost",
    "fiscal_residual_value",
    "fiscal_net_previous",
    "fiscal_depreciable",
    "fiscal_depreciation",
    "fiscal_accumulated",
    "fiscal_net_value",
    "residual_value",
    "accounting_net_previous",
    "accounting_depreciable",
    "accounting_depreciation",
    "non_deductible",
    "accounting_accumulated",
    "accounting_net_value",
)


def cumulative(depreciable: Decimal, months: int, installments: int) -> Decimal:
    """Suma de las primeras `installments` cuotas (la última absorbe la diferencia)."""
    if installments <= 0:
        return ZERO
    if installments >= months:
        return depreciable
    return (depreciable // months) * installments


def elapsed(asset: FixedAsset, until: date, months: int) -> int:
    """Cuotas transcurridas antes del mes `until` (exclusivo), cortadas en la baja
    contabilizada y en la vida útil."""
    end = until
    if asset.status == "disposed" and asset.disposed_on is not None:
        end = min(end, depreciation.month_start(asset.disposed_on))
    return max(0, min(depreciation.months_between(asset.depreciation_start, end), months))


def years(months: int) -> Decimal:
    return (Decimal(months) / 12).quantize(Decimal("0.01")).normalize()


@dataclass
class ScheduleRow:
    asset: FixedAsset
    category: AssetCategory
    disposed_in_year: bool
    cost: Decimal
    revaluation_coefficient: Decimal
    fiscal_residual_rate: Decimal
    fiscal_residual_value: Decimal
    fiscal_useful_life_months: int
    fiscal_remaining_months: int
    fiscal_net_previous: Decimal
    fiscal_depreciable: Decimal
    fiscal_depreciation: Decimal
    fiscal_accumulated: Decimal
    fiscal_net_value: Decimal
    residual_value: Decimal
    useful_life_months: int
    remaining_months: int
    accounting_net_previous: Decimal
    accounting_depreciable: Decimal
    accounting_depreciation: Decimal
    non_deductible: Decimal
    accounting_accumulated: Decimal
    accounting_net_value: Decimal


@dataclass
class CategoryGroup:
    category: AssetCategory
    rows: list[ScheduleRow] = field(default_factory=list)

    def total(self, column: str) -> Decimal:
        return sum((getattr(r, column) for r in self.rows), ZERO)


@dataclass(frozen=True)
class ReconciliationLine:
    account: LedgerAccount
    ledger_balance: Decimal
    schedule_amount: Decimal


@dataclass
class Schedule:
    year: FiscalYear
    groups: list[CategoryGroup]
    reconciliation: list[ReconciliationLine]
    warnings: list[str]

    def total(self, column: str) -> Decimal:
        return sum((g.total(column) for g in self.groups), ZERO)

    @property
    def ledger_total(self) -> Decimal:
        return sum((r.ledger_balance for r in self.reconciliation), ZERO)

    @property
    def reconciled(self) -> bool:
        return self.ledger_total == self.total("accounting_net_value") and all(
            r.ledger_balance == r.schedule_amount for r in self.reconciliation
        )


def _row(
    asset: FixedAsset,
    category: AssetCategory,
    year: FiscalYear,
    acc_start: Decimal,
    acc_end: Decimal,
) -> ScheduleRow:
    first = depreciation.month_start(year.start_date)
    after = depreciation.add_months(year.end_date, 1)
    disposed_in_year = (
        asset.status == "disposed"
        and asset.disposed_on is not None
        and year.start_date <= asset.disposed_on <= year.end_date
    )
    fiscal_depreciable = depreciation.fiscal_depreciable(asset)
    fiscal_months = asset.fiscal_useful_life_months
    fiscal_start_n = elapsed(asset, first, fiscal_months)
    fiscal_start = cumulative(fiscal_depreciable, fiscal_months, fiscal_start_n)
    fiscal_end_n = elapsed(asset, after, fiscal_months)
    fiscal_end = cumulative(fiscal_depreciable, fiscal_months, fiscal_end_n)
    fiscal_year_quota = fiscal_end - fiscal_start
    fiscal_net_previous = asset.cost - fiscal_start
    accounting_year = acc_end - acc_start
    accounting_net_previous = asset.cost - acc_start
    return ScheduleRow(
        asset=asset,
        category=category,
        disposed_in_year=disposed_in_year,
        cost=asset.cost,
        revaluation_coefficient=ZERO,
        fiscal_residual_rate=asset.fiscal_residual_rate,
        fiscal_residual_value=asset.fiscal_residual_value,
        fiscal_useful_life_months=fiscal_months,
        fiscal_remaining_months=fiscal_months - fiscal_end_n,
        fiscal_net_previous=fiscal_net_previous,
        fiscal_depreciable=fiscal_net_previous - asset.fiscal_residual_value,
        fiscal_depreciation=fiscal_year_quota,
        fiscal_accumulated=fiscal_end,
        fiscal_net_value=ZERO if disposed_in_year else asset.cost - fiscal_end,
        residual_value=asset.residual_value,
        useful_life_months=asset.useful_life_months,
        remaining_months=asset.useful_life_months - elapsed(asset, after, asset.useful_life_months),
        accounting_net_previous=accounting_net_previous,
        accounting_depreciable=accounting_net_previous - asset.residual_value,
        accounting_depreciation=accounting_year,
        non_deductible=max(accounting_year - fiscal_year_quota, ZERO),
        accounting_accumulated=acc_end,
        accounting_net_value=ZERO if disposed_in_year else asset.cost - acc_end,
    )


def schedule(db: Session, organization_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> Schedule:
    year = periods.get_fiscal_year(db, organization_id, fiscal_year_id)
    assets = [
        a
        for a in db.scalars(
            select(FixedAsset)
            .where(
                FixedAsset.organization_id == organization_id,
                FixedAsset.acquired_on <= year.end_date,
            )
            .order_by(FixedAsset.acquired_on, FixedAsset.name, FixedAsset.id)
        )
        if not (
            a.status == "disposed" and a.disposed_on is not None and a.disposed_on < year.start_date
        )
    ]
    categories = {
        c.id: c
        for c in db.scalars(
            select(AssetCategory).where(AssetCategory.organization_id == organization_id)
        )
    }
    acc_start = depreciation.accumulated_by_asset(
        db, organization_id, year.start_date - timedelta(days=1)
    )
    acc_end = depreciation.accumulated_by_asset(db, organization_id, year.end_date)
    groups: dict[uuid.UUID, CategoryGroup] = {}
    for asset in assets:
        category = categories[asset.category_id]
        group = groups.setdefault(category.id, CategoryGroup(category))
        group.rows.append(
            _row(asset, category, year, acc_start.get(asset.id, ZERO), acc_end.get(asset.id, ZERO))
        )
    ordered = sorted(groups.values(), key=lambda g: (g.category.name, g.category.id))
    return Schedule(
        year=year,
        groups=ordered,
        reconciliation=_reconcile(db, organization_id, year, ordered),
        warnings=_warnings(ordered),
    )


def _reconcile(
    db: Session, organization_id: uuid.UUID, year: FiscalYear, groups: list[CategoryGroup]
) -> list[ReconciliationLine]:
    """Saldo al cierre de las cuentas de las categorías frente a lo que dice el cuadro:
    costo de los bienes vigentes en la cuenta de activo y su acumulada (negativa) en la
    regularizadora. Un bien dado de baja en el ejercicio ya no suma en ninguna."""
    expected: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for group in groups:
        asset_account = group.category.asset_account_id
        accumulated_account = group.category.accumulated_account_id
        if asset_account is not None:
            expected[asset_account] += ZERO
        if accumulated_account is not None:
            expected[accumulated_account] += ZERO
        for row in group.rows:
            if row.disposed_in_year:
                continue
            if asset_account is not None:
                expected[asset_account] += row.cost
            if accumulated_account is not None:
                expected[accumulated_account] -= row.accounting_accumulated
    if not expected:
        return []
    sums = account_sums(db, organization_id, date_to=year.end_date)
    accounts = sorted(
        db.scalars(select(LedgerAccount).where(LedgerAccount.id.in_(list(expected)))),
        key=lambda a: chart.code_key(a.code),
    )
    return [
        ReconciliationLine(
            account=a,
            ledger_balance=natural(a.kind, sums[a.id]) if a.id in sums else ZERO,
            schedule_amount=expected[a.id],
        )
        for a in accounts
    ]


def _warnings(groups: list[CategoryGroup]) -> list[str]:
    result = list(WARNINGS)
    pending = sorted(
        {g.category.name for g in groups if g.category.validation_status != "validated"}
    )
    if pending:
        result.append(
            "Categorías sin verificar contra la fuente oficial: " + ", ".join(pending) + "."
        )
    return result


def write_year_values(db: Session, year: FiscalYear) -> int:
    """Al cerrar el ejercicio (D-066), en la misma transacción: neto fiscal y contable y
    depreciación del ejercicio de cada bien del cuadro."""
    report = schedule(db, year.organization_id, year.id)
    rows = [
        {
            "organization_id": year.organization_id,
            "asset_id": row.asset.id,
            "fiscal_year_id": year.id,
            "fiscal_net_value": row.fiscal_net_value,
            "accounting_net_value": row.accounting_net_value,
            "fiscal_depreciation": row.fiscal_depreciation,
            "accounting_depreciation": row.accounting_depreciation,
        }
        for group in report.groups
        for row in group.rows
    ]
    if rows:
        db.execute(insert(AssetYearValue), rows)
    return len(rows)
