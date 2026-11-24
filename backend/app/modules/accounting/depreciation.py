"""Depreciación lineal mensual, corridas por período y baja de bienes (D-057 a D-059, D-064).

Cálculo (D-057): cuota = (costo - residual) / vida útil en meses, en guaraníes enteros. Las
cuotas se redondean hacia abajo y la última absorbe la diferencia: la suma es exactamente el
importe depreciable. Todo con `Decimal`, nunca `float`. La cuota `k` corresponde al mes
`depreciation_start + (k - 1)`. El mes de la baja ya no se deprecia (D-073).

Corrida de un período (D-058): un borrador con una línea de gasto y una de depreciación
acumulada por cuenta contable, y el detalle por bien en `depreciation_items`. Una sola
corrida viva por período (índice único parcial sobre `entry_status`, que mantienen los
triggers) y sin saltear meses: un mes anterior con bienes depreciables tiene que tener su
corrida contabilizada. La corrida no se contabiliza sola (BR-ACC-06).

Baja (D-059): un borrador que da de baja el costo y la acumulada contra la cuenta de
resultado de la baja. Mientras es borrador el bien sigue `active` con los datos de la baja;
al contabilizarla pasa a `disposed`; descartarla o revertirla lo deja como estaba.

Candados: primero la fila del ejercicio (`FOR UPDATE`), como todo el núcleo (D-049).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting import chart, entries, periods
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import apply_changes, flush_translated, pyg, record
from app.modules.accounting.models import (
    AssetCategory,
    DepreciationItem,
    DepreciationRun,
    FiscalYear,
    FixedAsset,
    JournalEntry,
    LedgerAccount,
    Period,
)

LIVE = ("draft", "posted")
DISPOSAL_KIND_LABELS = {"sale": "venta", "scrap": "destrucción", "donation": "donación"}
DEFAULT_DISPOSAL_ACCOUNT_CODE = "17.01"


# --- Cálculo ------------------------------------------------------------------------------


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, months: int) -> date:
    """Primer día del mes que está `months` meses después del mes de `day`."""
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def installment_for(start: date, month: date) -> int:
    """Número de cuota del mes `month` para un bien que empieza en `start` (1 = el primero)."""
    return months_between(start, month) + 1


def quota(depreciable: Decimal, months: int, installment: int) -> Decimal:
    """Cuota `installment` (1..months): hacia abajo, y la última absorbe la diferencia."""
    if installment < 1 or installment > months:
        return ZERO
    base = depreciable // months
    if installment < months:
        return base
    return depreciable - base * (months - 1)


def accounting_depreciable(asset: FixedAsset) -> Decimal:
    return asset.cost - asset.residual_value


def fiscal_depreciable(asset: FixedAsset) -> Decimal:
    return asset.cost - asset.fiscal_residual_value


def stop_month(asset: FixedAsset) -> date | None:
    """Mes de la baja (pendiente o contabilizada): desde ese mes no se deprecia."""
    return month_start(asset.disposed_on) if asset.disposed_on is not None else None


def accounting_quota_for(asset: FixedAsset, month: date) -> Decimal:
    """Cuota contable teórica del mes (cero fuera de la vida útil o desde el mes de baja)."""
    stop = stop_month(asset)
    if month < asset.depreciation_start or (stop is not None and month >= stop):
        return ZERO
    return quota(
        accounting_depreciable(asset),
        asset.useful_life_months,
        installment_for(asset.depreciation_start, month),
    )


def fiscal_quota_for(asset: FixedAsset, month: date) -> Decimal:
    """Cuota fiscal teórica del mes (D-065): mismos inicio y baja, parámetros fiscales."""
    stop = stop_month(asset)
    if month < asset.depreciation_start or (stop is not None and month >= stop):
        return ZERO
    return quota(
        fiscal_depreciable(asset),
        asset.fiscal_useful_life_months,
        installment_for(asset.depreciation_start, month),
    )


def is_due(asset: FixedAsset, month: date) -> bool:
    return accounting_quota_for(asset, month) > 0


def depreciation_start_for(
    db: Session, organization_id: uuid.UUID, acquired_on: date, rule: str
) -> date:
    """Primer mes de depreciación según la opción del bien (D-064, Decreto 3182 art. 30).

    - `next_month`: el mes siguiente al de la adquisición.
    - `next_fiscal_year`: el ejercicio siguiente. Si el ejercicio de la adquisición no está
      creado, se toma el año civil (D-039); si el siguiente no empieza un día 1, desde el
      primer mes completo.
    """
    if rule == "next_month":
        return add_months(acquired_on, 1)
    year_end = db.scalar(
        select(FiscalYear.end_date).where(
            FiscalYear.organization_id == organization_id,
            FiscalYear.start_date <= acquired_on,
            FiscalYear.end_date >= acquired_on,
        )
    )
    following = (
        year_end + timedelta(days=1) if year_end is not None else date(acquired_on.year + 1, 1, 1)
    )
    return following if following.day == 1 else add_months(following, 1)


# --- Lecturas compartidas -----------------------------------------------------------------


def category_problems(db: Session, category: AssetCategory) -> list[str]:
    """Qué le falta a una categoría para usarse (vacío = completa y con cuentas válidas)."""
    missing: list[str] = []
    if category.useful_life_months is None:
        missing.append("vida útil")
    if category.residual_rate is None:
        missing.append("porcentaje de valor residual")
    ids = {
        "cuenta de activo": category.asset_account_id,
        "cuenta de depreciación acumulada": category.accumulated_account_id,
        "cuenta de gasto": category.expense_account_id,
    }
    accounts = entries.account_map(
        db, category.organization_id, {i for i in ids.values() if i is not None}
    )
    for label, account_id in ids.items():
        if account_id is None:
            missing.append(label)
            continue
        problem = account_problem(label, accounts[account_id])
        if problem is not None:
            missing.append(problem)
    return missing


def account_problem(label: str, account: LedgerAccount) -> str | None:
    """La cuenta de activo es de activo deudora; la acumulada, de activo acreedora
    (regularizadora); la de gasto, de gasto. Las tres imputables y sin archivar."""
    if not account.is_postable or account.archived_at is not None:
        return f"{label} ({account.code}) imputable y sin archivar"
    expected = {
        "cuenta de activo": ("asset", "debit"),
        "cuenta de depreciación acumulada": ("asset", "credit"),
        "cuenta de gasto": ("expense", None),
    }[label]
    kind, side = expected
    if account.kind != kind or (side is not None and account.normal_side != side):
        return {
            "cuenta de activo": f"{label} ({account.code}) de activo y naturaleza deudora",
            "cuenta de depreciación acumulada": (
                f"{label} ({account.code}) de activo y naturaleza acreedora (regularizadora)"
            ),
            "cuenta de gasto": f"{label} ({account.code}) de gasto",
        }[label]
    return None


def require_complete(db: Session, categories: list[AssetCategory]) -> None:
    problems = {c.name: category_problems(db, c) for c in categories}
    bad = {name: p for name, p in problems.items() if p}
    if bad:
        raise AppError(
            "ASSET_CATEGORY_INCOMPLETE",
            "Categoría incompleta: "
            + "; ".join(f"{name} (falta: {', '.join(p)})" for name, p in bad.items())
            + ". Completala antes de usarla.",
            details={"categories": [{"name": n, "missing": p} for n, p in bad.items()]},
            status_code=422,
        )


@dataclass(frozen=True)
class ItemRow:
    run_id: uuid.UUID
    entry_id: uuid.UUID
    entry_status: str
    month: date
    asset_id: uuid.UUID
    installment: int
    amount: Decimal


def item_rows(
    db: Session,
    organization_id: uuid.UUID,
    *,
    asset_ids: list[uuid.UUID] | None = None,
    statuses: tuple[str, ...] = LIVE,
) -> list[ItemRow]:
    query = (
        select(
            DepreciationRun.id,
            DepreciationRun.entry_id,
            DepreciationRun.entry_status,
            Period.start_date,
            DepreciationItem.asset_id,
            DepreciationItem.installment,
            DepreciationItem.amount,
        )
        .join(DepreciationRun, DepreciationRun.id == DepreciationItem.run_id)
        .join(Period, Period.id == DepreciationRun.period_id)
        .where(
            DepreciationItem.organization_id == organization_id,
            DepreciationRun.entry_status.in_(statuses),
        )
    )
    if asset_ids is not None:
        query = query.where(DepreciationItem.asset_id.in_(asset_ids))
    return [
        ItemRow(run, entry, status, month_start(start), asset, installment, amount)
        for run, entry, status, start, asset, installment, amount in db.execute(query)
    ]


def posted_months(db: Session, organization_id: uuid.UUID) -> set[date]:
    return {
        month_start(start)
        for start in db.scalars(
            select(Period.start_date)
            .join(DepreciationRun, DepreciationRun.period_id == Period.id)
            .where(
                DepreciationRun.organization_id == organization_id,
                DepreciationRun.entry_status == "posted",
            )
        )
    }


def live_run_months(db: Session, organization_id: uuid.UUID) -> dict[date, DepreciationRun]:
    rows = db.execute(
        select(Period.start_date, DepreciationRun)
        .join(Period, Period.id == DepreciationRun.period_id)
        .where(
            DepreciationRun.organization_id == organization_id,
            DepreciationRun.entry_status.in_(LIVE),
        )
    )
    return {month_start(start): run for start, run in rows}


def org_assets(db: Session, organization_id: uuid.UUID) -> list[FixedAsset]:
    return list(
        db.scalars(
            select(FixedAsset)
            .where(FixedAsset.organization_id == organization_id)
            .order_by(FixedAsset.depreciation_start, FixedAsset.id)
        )
    )


def first_missing_month(
    db: Session,
    organization_id: uuid.UUID,
    before: date,
    *,
    since: date | None = None,
    assets: list[FixedAsset] | None = None,
) -> date | None:
    """Primer mes anterior a `before` (y desde `since`) con cuotas pero sin corrida
    contabilizada."""
    assets = org_assets(db, organization_id) if assets is None else assets
    if not assets:
        return None
    done = posted_months(db, organization_id)
    month = min(a.depreciation_start for a in assets)
    if since is not None:
        month = max(month, month_start(since))
    while month < before:
        if month not in done and any(is_due(a, month) for a in assets):
            return month
        month = add_months(month, 1)
    return None


def missing_month_conflict(month: date) -> Conflict:
    return Conflict(
        "DEPRECIATION_MONTH_MISSING",
        f"Falta contabilizar la depreciación de {month:%m/%Y}: los meses no se saltean.",
        details={"month": month.isoformat()},
    )


# --- Corridas -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DueItem:
    asset: FixedAsset
    category: AssetCategory
    installment: int
    amount: Decimal


def _due_items(db: Session, organization_id: uuid.UUID, month: date) -> list[DueItem]:
    assets = org_assets(db, organization_id)
    missing = first_missing_month(db, organization_id, month, assets=assets)
    if missing is not None:
        raise missing_month_conflict(missing)
    due = [a for a in assets if a.status == "active" and is_due(a, month)]
    if not due:
        return []
    posted: dict[uuid.UUID, int] = defaultdict(int)
    for row in item_rows(db, organization_id, statuses=("posted",)):
        if row.month < month:
            posted[row.asset_id] += 1
    out_of_sequence = [
        a for a in due if posted[a.id] != installment_for(a.depreciation_start, month) - 1
    ]
    if out_of_sequence:
        raise Conflict(
            "DEPRECIATION_OUT_OF_SEQUENCE",
            "La depreciación de estos bienes no está al día con el mes anterior: "
            + ", ".join(a.name for a in out_of_sequence[:10])
            + ".",
            details={"assets": [str(a.id) for a in out_of_sequence]},
        )
    categories = {
        c.id: c
        for c in db.scalars(
            select(AssetCategory).where(AssetCategory.id.in_({a.category_id for a in due}))
        )
    }
    require_complete(db, sorted(categories.values(), key=lambda c: c.name))
    return [
        DueItem(
            asset=a,
            category=categories[a.category_id],
            installment=installment_for(a.depreciation_start, month),
            amount=accounting_quota_for(a, month),
        )
        for a in due
    ]


def _run_lines(
    db: Session, organization_id: uuid.UUID, items: list[DueItem]
) -> "list[entries.LineData]":
    debit: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    credit: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    names: dict[uuid.UUID, set[str]] = defaultdict(set)
    for item in items:
        expense = item.category.expense_account_id
        accumulated = item.category.accumulated_account_id
        assert expense is not None and accumulated is not None  # categoría completa
        debit[expense] += item.amount
        credit[accumulated] += item.amount
        names[expense].add(item.category.name)
        names[accumulated].add(item.category.name)
    accounts = entries.account_map(db, organization_id, set(debit) | set(credit))

    def describe(account_id: uuid.UUID) -> str:
        return ("Depreciación: " + ", ".join(sorted(names[account_id])))[:300]

    def ordered(ids: dict[uuid.UUID, Decimal]) -> list[uuid.UUID]:
        return sorted(ids, key=lambda i: chart.code_key(accounts[i].code))

    return [
        *(
            entries.LineData(account_id=i, debit=debit[i], credit=ZERO, description=describe(i))
            for i in ordered(debit)
        ),
        *(
            entries.LineData(account_id=i, debit=ZERO, credit=credit[i], description=describe(i))
            for i in ordered(credit)
        ),
    ]


def locked_open_period(
    db: Session, organization_id: uuid.UUID, period_id: uuid.UUID
) -> tuple[FiscalYear, Period]:
    """Ejercicio (`FOR UPDATE`) y período abiertos (409 si alguno está cerrado)."""
    year_id = db.scalar(
        select(Period.fiscal_year_id).where(
            Period.id == period_id, Period.organization_id == organization_id
        )
    )
    if year_id is None:
        raise periods.period_not_found()
    year = periods.get_fiscal_year(db, organization_id, year_id, lock=True)
    period = db.scalar(
        select(Period).where(Period.id == period_id).execution_options(populate_existing=True)
    )
    assert period is not None  # los períodos no se borran
    if year.status != "open":
        raise Conflict("FISCAL_YEAR_CLOSED", "El ejercicio está cerrado.")
    if period.status != "open":
        raise Conflict(
            "PERIOD_CLOSED",
            f"El período {period.start_date:%m/%Y} está cerrado: reabrilo primero.",
            details={"period_id": str(period.id)},
        )
    return year, period


def run_depreciation(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, period_id: uuid.UUID
) -> DepreciationRun:
    """Genera el borrador de depreciación del período (D-058). No contabiliza."""
    year, period = locked_open_period(db, organization_id, period_id)
    month = month_start(period.start_date)
    # Una sola corrida viva por mes, aunque el mes esté partido entre dos ejercicios.
    live = live_run_months(db, organization_id).get(month)
    if live is not None:
        raise Conflict(
            "DEPRECIATION_RUN_EXISTS",
            f"{month:%m/%Y} ya tiene una corrida de depreciación "
            f"({'borrador' if live.entry_status == 'draft' else 'contabilizada'}). Para volver "
            "a correrla, descartá el borrador o revertí el asiento.",
            details={"run_id": str(live.id), "entry_id": str(live.entry_id)},
        )
    # Serializa con el alta y los cambios de bienes (que toman el mismo candado): un bien
    # nuevo no puede quedar afuera de una corrida que se está generando.
    chart.lock_settings(db, organization_id)
    items = _due_items(db, organization_id, month)
    if not items:
        raise AppError(
            "NOTHING_TO_DEPRECIATE",
            f"No hay bienes con cuota de depreciación en {month:%m/%Y}.",
            status_code=422,
        )
    entry = entries.create_draft(
        db,
        organization_id,
        actor_id,
        {
            "entry_date": period.end_date,
            "description": f"Depreciación del activo fijo de {month:%m/%Y}",
            "document_reference": None,
        },
        kind="depreciation",
        lines=_run_lines(db, organization_id, items),
        year=year,
        commit=False,
    )
    run = DepreciationRun(
        organization_id=organization_id,
        period_id=period.id,
        entry_id=entry.id,
        created_by=actor_id,
    )
    db.add(run)
    flush_translated(db)
    db.execute(
        insert(DepreciationItem),
        [
            {
                "organization_id": organization_id,
                "run_id": run.id,
                "asset_id": item.asset.id,
                "installment": item.installment,
                "amount": item.amount,
            }
            for item in items
        ],
    )
    total = sum((item.amount for item in items), ZERO)
    record(
        db,
        organization_id,
        actor_id,
        "depreciation_run",
        "created",
        run.id,
        after={
            "period_id": str(period.id),
            "entry_id": str(entry.id),
            "assets": len(items),
            "total": pyg(total),
        },
    )
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> DepreciationRun:
    run = db.scalar(
        select(DepreciationRun).where(
            DepreciationRun.id == run_id, DepreciationRun.organization_id == organization_id
        )
    )
    if run is None:
        raise NotFound("DEPRECIATION_RUN_NOT_FOUND", "La corrida de depreciación no existe.")
    return run


def list_runs(
    db: Session, organization_id: uuid.UUID, fiscal_year_id: uuid.UUID | None = None
) -> list[DepreciationRun]:
    query = (
        select(DepreciationRun)
        .join(Period, Period.id == DepreciationRun.period_id)
        .where(DepreciationRun.organization_id == organization_id)
    )
    if fiscal_year_id is not None:
        query = query.where(Period.fiscal_year_id == fiscal_year_id)
    return list(
        db.scalars(query.order_by(Period.start_date.desc(), DepreciationRun.created_at.desc()))
    )


def run_items(db: Session, run_id: uuid.UUID) -> list[tuple[DepreciationItem, FixedAsset]]:
    return [
        (item, asset)
        for item, asset in db.execute(
            select(DepreciationItem, FixedAsset)
            .join(FixedAsset, FixedAsset.id == DepreciationItem.asset_id)
            .where(DepreciationItem.run_id == run_id)
            .order_by(FixedAsset.name, FixedAsset.id)
        )
    ]


def _run_of(db: Session, entry: JournalEntry) -> tuple[DepreciationRun, date]:
    row = db.execute(
        select(DepreciationRun, Period.start_date)
        .join(Period, Period.id == DepreciationRun.period_id)
        .where(DepreciationRun.entry_id == entry.id)
    ).first()
    if row is None:
        raise Conflict("DEPRECIATION_RUN_NOT_FOUND", "El asiento no tiene su corrida.")
    return row[0], month_start(row[1])


def check_run_postable(db: Session, entry: JournalEntry) -> None:
    """Al contabilizar una corrida se repiten los controles de la generación: puede haber
    cambiado algo desde entonces (una corrida anterior revertida, una baja nueva)."""
    run, month = _run_of(db, entry)
    missing = first_missing_month(db, entry.organization_id, month)
    if missing is not None:
        raise missing_month_conflict(missing)
    items = run_items(db, run.id)
    posted: dict[uuid.UUID, int] = defaultdict(int)
    for row in item_rows(
        db, entry.organization_id, asset_ids=[a.id for _, a in items], statuses=("posted",)
    ):
        if row.month < month:
            posted[row.asset_id] += 1
    for item, asset in items:
        stop = stop_month(asset)
        if asset.status != "active" or (stop is not None and stop <= month):
            raise Conflict(
                "ASSET_DISPOSED",
                f"El bien {asset.name} tiene una baja desde {month:%m/%Y} o antes: descartá "
                "esta corrida y volvé a generarla.",
                details={"asset_id": str(asset.id)},
            )
        if posted[asset.id] != item.installment - 1:
            raise Conflict(
                "DEPRECIATION_OUT_OF_SEQUENCE",
                f"La cuota {item.installment} del bien {asset.name} ya no sigue a las "
                "contabilizadas: descartá esta corrida y volvé a generarla.",
                details={"asset_id": str(asset.id)},
            )


def check_reversible(db: Session, original: JournalEntry, day: date) -> None:
    """Revertir una corrida o una baja (D-058, D-059) con controles extra (D-074):

    - la reversión va en el mismo ejercicio que el original;
    - una corrida solo se revierte si es la última viva y ninguno de sus bienes tiene baja;
    - una baja solo se revierte si no hay corridas vivas desde su mes (el bien las habría
      salteado).
    """
    year = periods.fiscal_year_for(db, original.organization_id, day)
    if year.id != original.fiscal_year_id:
        raise Conflict(
            "REVERSAL_OTHER_YEAR",
            "Una depreciación o una baja se revierte dentro de su mismo ejercicio.",
        )
    if original.kind == "depreciation":
        run, month = _run_of(db, original)
        later = [m for m in live_run_months(db, original.organization_id) if m > month]
        if later:
            raise Conflict(
                "DEPRECIATION_RUN_NOT_LAST",
                f"Hay corridas posteriores ({max(later):%m/%Y}): revertilas primero, de la más "
                "nueva a la más vieja.",
            )
        disposed = [a for _, a in run_items(db, run.id) if a.disposal_entry_id is not None]
        if disposed:
            raise Conflict(
                "ASSET_DISPOSED",
                "La corrida incluye bienes con baja (borrador o contabilizada): "
                + ", ".join(a.name for a in disposed[:10])
                + ". Descartá o revertí antes la baja.",
            )
        return
    asset = _disposed_asset(db, original)
    stop = stop_month(asset)
    assert stop is not None  # la baja tiene fecha
    after = [m for m in live_run_months(db, original.organization_id) if m >= stop]
    if after:
        raise Conflict(
            "DEPRECIATION_AFTER_DISPOSAL",
            f"Hay corridas de depreciación desde el mes de la baja ({min(after):%m/%Y}): el bien "
            "las habría salteado. Revertilas antes de revertir la baja.",
        )


# --- Baja ---------------------------------------------------------------------------------


def _disposed_asset(db: Session, entry: JournalEntry) -> FixedAsset:
    asset = db.scalar(
        select(FixedAsset)
        .where(FixedAsset.disposal_entry_id == entry.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if asset is None:
        raise Conflict("DISPOSAL_WITHOUT_ASSET", "El asiento de baja no corresponde a ningún bien.")
    return asset


def disposal_account(db: Session, organization_id: uuid.UUID) -> LedgerAccount:
    """La de `settings.asset_disposal_account_id` o, si no está configurada, la 17.01."""
    settings = chart.get_settings(db, organization_id)
    account_id = settings.asset_disposal_account_id if settings is not None else None
    if account_id is not None:
        account: LedgerAccount | None = chart.get_account(db, organization_id, account_id)
    else:
        account = db.scalar(
            select(LedgerAccount).where(
                LedgerAccount.organization_id == organization_id,
                LedgerAccount.code == DEFAULT_DISPOSAL_ACCOUNT_CODE,
            )
        )
    if (
        account is None
        or account.kind not in ("income", "expense")
        or not account.is_postable
        or account.archived_at is not None
    ):
        raise AppError(
            "DISPOSAL_ACCOUNT_NOT_SET",
            "Configurá la cuenta de resultado de la baja de bienes (por ejemplo, 17.01): de "
            "ingreso o de gasto, imputable y sin archivar.",
            status_code=422,
        )
    return account


def _check_up_to_date(db: Session, asset: FixedAsset, day: date) -> Decimal:
    """Depreciación al día hasta el mes anterior a la baja y nada desde ese mes. Devuelve la
    acumulada contabilizada."""
    stop = month_start(day)
    rows = item_rows(db, asset.organization_id, asset_ids=[asset.id])
    after = [r for r in rows if r.month >= stop]
    if after:
        first = min(r.month for r in after)
        raise Conflict(
            "DEPRECIATION_AFTER_DISPOSAL",
            f"El bien tiene depreciación desde el mes de la baja ({first:%m/%Y}): descartá o "
            "revertí esa corrida primero.",
        )
    posted = [r for r in rows if r.entry_status == "posted"]
    expected = max(
        0, min(installment_for(asset.depreciation_start, stop) - 1, asset.useful_life_months)
    )
    if len(posted) != expected:
        raise Conflict(
            "DEPRECIATION_NOT_UP_TO_DATE",
            f"La depreciación del bien tiene que estar contabilizada hasta el mes anterior a la "
            f"baja ({add_months(stop, -1):%m/%Y}): tiene {len(posted)} de {expected} cuotas.",
            details={"posted": len(posted), "expected": expected},
        )
    return sum((r.amount for r in posted), ZERO)


def dispose(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    asset_id: uuid.UUID,
    data: dict[str, Any],
) -> FixedAsset:
    """Borrador de baja (D-059): debe la acumulada y la diferencia en la cuenta de resultado,
    haber el costo. Si hubo venta, el cobro va por separado (finanzas)."""
    day: date = data["date"]
    found = db.scalar(
        select(FixedAsset.id).where(
            FixedAsset.id == asset_id, FixedAsset.organization_id == organization_id
        )
    )
    if found is None:
        raise NotFound("FIXED_ASSET_NOT_FOUND", "El bien no existe.")
    year = periods.fiscal_year_for(db, organization_id, day, lock=True)
    asset = db.scalar(
        select(FixedAsset)
        .where(FixedAsset.id == asset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert asset is not None
    if asset.status != "active":
        raise Conflict("ASSET_ALREADY_DISPOSED", "El bien ya está dado de baja.")
    if asset.disposal_entry_id is not None:
        raise Conflict(
            "ASSET_DISPOSAL_PENDING",
            "El bien ya tiene un borrador de baja: contabilizalo o descartalo.",
            details={"entry_id": str(asset.disposal_entry_id)},
        )
    if day < asset.acquired_on:
        raise AppError(
            "DISPOSAL_DATE_INVALID",
            "La baja no puede ser anterior a la adquisición del bien.",
            status_code=422,
        )
    if year.status != "open":
        raise Conflict("FISCAL_YEAR_CLOSED", "El ejercicio de la fecha de la baja está cerrado.")
    period = periods.period_for(db, year, day)
    if period.status != "open":
        raise Conflict(
            "PERIOD_CLOSED",
            f"El período {period.start_date:%m/%Y} está cerrado.",
            details={"period_id": str(period.id)},
        )
    category = db.get_one(AssetCategory, asset.category_id)
    require_complete(db, [category])
    accumulated = _check_up_to_date(db, asset, day)
    result_account = disposal_account(db, organization_id)
    assert category.asset_account_id is not None and category.accumulated_account_id is not None
    net = asset.cost - accumulated
    lines = []
    if accumulated > 0:
        lines.append(
            entries.LineData(
                account_id=category.accumulated_account_id,
                debit=accumulated,
                credit=ZERO,
                description="Baja: depreciación acumulada",
            )
        )
    if net > 0:
        lines.append(
            entries.LineData(
                account_id=result_account.id,
                debit=net,
                credit=ZERO,
                description="Baja: valor neto contable",
            )
        )
    lines.append(
        entries.LineData(
            account_id=category.asset_account_id,
            debit=ZERO,
            credit=asset.cost,
            description="Baja: costo del bien",
        )
    )
    label = DISPOSAL_KIND_LABELS[data["kind"]]
    entry = entries.create_draft(
        db,
        organization_id,
        actor_id,
        {
            "entry_date": day,
            "description": f"Baja del bien {asset.name} ({label}): {data['reason']}"[:500],
            "document_reference": data["document_reference"],
        },
        kind="disposal",
        lines=lines,
        year=year,
        commit=False,
    )
    before, after = apply_changes(
        asset,
        {
            "disposed_on": day,
            "disposal_kind": data["kind"],
            "disposal_reason": data["reason"],
            "disposal_document_reference": data["document_reference"],
            "disposal_entry_id": entry.id,
        },
    )
    flush_translated(db)
    after.update({"accumulated": pyg(accumulated), "net_book_value": pyg(net)})
    record(
        db,
        organization_id,
        actor_id,
        "fixed_asset",
        "disposal_drafted",
        asset.id,
        before=before,
        after=after,
    )
    db.commit()
    return asset


def check_disposal_postable(db: Session, entry: JournalEntry) -> None:
    asset = _disposed_asset(db, entry)
    assert asset.disposed_on is not None
    _check_up_to_date(db, asset, asset.disposed_on)


def disposal_posted(db: Session, entry: JournalEntry, actor_id: uuid.UUID) -> None:
    asset = _disposed_asset(db, entry)
    before, after = apply_changes(asset, {"status": "disposed"})
    flush_translated(db)
    record(
        db,
        asset.organization_id,
        actor_id,
        "fixed_asset",
        "disposed",
        asset.id,
        before=before,
        after=after,
    )


_CLEAR_DISPOSAL = {
    "status": "active",
    "disposed_on": None,
    "disposal_kind": None,
    "disposal_reason": None,
    "disposal_document_reference": None,
    "disposal_entry_id": None,
}


def disposal_discarded(db: Session, entry: JournalEntry, actor_id: uuid.UUID) -> None:
    asset = _disposed_asset(db, entry)
    before, after = apply_changes(asset, _CLEAR_DISPOSAL)
    flush_translated(db)
    record(
        db,
        asset.organization_id,
        actor_id,
        "fixed_asset",
        "disposal_discarded",
        asset.id,
        before=before,
        after=after,
    )


def disposal_reversed(db: Session, entry: JournalEntry, actor_id: uuid.UUID) -> None:
    asset = _disposed_asset(db, entry)
    before, after = apply_changes(asset, _CLEAR_DISPOSAL)
    flush_translated(db)
    record(
        db,
        asset.organization_id,
        actor_id,
        "fixed_asset",
        "disposal_reversed",
        asset.id,
        before=before,
        after=after,
    )


# --- Cierre del ejercicio -----------------------------------------------------------------


def check_year_depreciated(db: Session, year: FiscalYear) -> None:
    """Al cerrar el ejercicio, todos sus meses con cuotas tienen su corrida contabilizada."""
    missing = first_missing_month(
        db, year.organization_id, add_months(year.end_date, 1), since=year.start_date
    )
    if missing is not None:
        raise Conflict(
            "DEPRECIATION_MISSING",
            f"Para cerrar el ejercicio falta contabilizar la depreciación de {missing:%m/%Y}.",
            details={"month": missing.isoformat()},
        )


def accumulated_by_asset(
    db: Session, organization_id: uuid.UUID, at: date
) -> dict[uuid.UUID, Decimal]:
    """Depreciación contable acumulada al cierre de `at`, coherente con el mayor: las
    corridas contabilizadas o revertidas con fecha hasta `at`, menos las revertidas con
    reversión hasta `at`."""
    reversal_date = (
        select(JournalEntry.entry_date)
        .where(JournalEntry.reverses_entry_id == DepreciationRun.entry_id)
        .correlate(DepreciationRun)
        .scalar_subquery()
    )
    rows = db.execute(
        select(DepreciationItem.asset_id, func.sum(DepreciationItem.amount))
        .join(DepreciationRun, DepreciationRun.id == DepreciationItem.run_id)
        .join(JournalEntry, JournalEntry.id == DepreciationRun.entry_id)
        .where(
            DepreciationItem.organization_id == organization_id,
            JournalEntry.status.in_(("posted", "reversed")),
            JournalEntry.entry_date <= at,
            (JournalEntry.status == "posted") | (reversal_date > at),
        )
        .group_by(DepreciationItem.asset_id)
    )
    return {asset_id: Decimal(total) for asset_id, total in rows}
