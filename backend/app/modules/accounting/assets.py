"""Categorías de activo fijo y bienes (D-056, D-057, D-064, D-065).

Categorías:
- se cargan a pedido desde las 34 candidatas de la investigación (`proposed_asset_categories`,
  sin validar): las cuentas se asignan por código solo si existen en el plan de la
  organización con el tipo correcto;
- una categoría se usa solo completa (D-068): vida útil, porcentaje de valor residual y las
  tres cuentas con el tipo correcto. Si no, 422 diciendo qué falta;
- `validation_status` pasa a `validated` solo con `accounting.post` (como el plan, D-038), y
  vuelve a `pending` con cualquier cambio de vida útil, residual o cuentas.

Bienes:
- costo y residual contable en guaraníes enteros; vida útil contable y fiscal en meses;
  residual fiscal = costo por porcentaje (RG 77/2020, col. 6), con el porcentaje ≤ 20 % (Ley
  6380, art. 11). Por defecto, los parámetros contables son los fiscales de la categoría;
- el inicio de la depreciación sale de la opción del bien (D-064);
- con depreciaciones vivas (borrador o contabilizadas) no cambian los parámetros (D-071).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting import chart, depreciation, proposed_asset_categories
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import (
    apply_changes,
    flush_translated,
    now,
    pyg_amount,
    record,
    snapshot,
)
from app.modules.accounting.models import (
    AssetCategory,
    DepreciationItem,
    DepreciationRun,
    FiscalYear,
    FixedAsset,
    JournalEntry,
    LedgerAccount,
)
from app.modules.finance.models import FinancialContext, Transaction
from app.modules.finance.service import escape_like

MAX_RESIDUAL_RATE = Decimal(20)
# Las candidatas reflejan el art. 31 en la redacción del Decreto 6105/2021 (§6).
NORM_IN_FORCE_SINCE = date(2021, 10, 14)

CATEGORY_FIELDS = (
    "code",
    "name",
    "useful_life_months",
    "residual_rate",
    "asset_account_id",
    "accumulated_account_id",
    "expense_account_id",
    "source_url",
    "legal_reference",
    "citation",
    "note",
)
# Cambiarlos exige volver a validar la categoría.
STRUCTURAL_FIELDS = (
    "useful_life_months",
    "residual_rate",
    "asset_account_id",
    "accumulated_account_id",
    "expense_account_id",
)
ACCOUNT_FIELDS = {
    "asset_account_id": "cuenta de activo",
    "accumulated_account_id": "cuenta de depreciación acumulada",
    "expense_account_id": "cuenta de gasto",
}
ASSET_FIELDS = (
    "category_id",
    "name",
    "description",
    "serial_or_reference",
    "acquired_on",
    "start_rule",
    "depreciation_start",
    "cost",
    "residual_value",
    "useful_life_months",
    "fiscal_useful_life_months",
    "fiscal_residual_rate",
    "fiscal_residual_value",
    "acquisition_entry_id",
    "source_transaction_id",
)
# Parámetros de depreciación: no cambian con depreciaciones vivas.
FINANCIAL_FIELDS = (
    "category_id",
    "acquired_on",
    "start_rule",
    "cost",
    "residual_value",
    "useful_life_months",
    "fiscal_useful_life_months",
    "fiscal_residual_rate",
)


# --- Categorías ---------------------------------------------------------------------------


def category_not_found() -> NotFound:
    return NotFound("ASSET_CATEGORY_NOT_FOUND", "La categoría no existe.")


def get_category(
    db: Session, organization_id: uuid.UUID, category_id: uuid.UUID, *, lock: bool = False
) -> AssetCategory:
    query = select(AssetCategory).where(
        AssetCategory.id == category_id, AssetCategory.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    category = db.scalar(query)
    if category is None:
        raise category_not_found()
    return category


def list_categories(
    db: Session, organization_id: uuid.UUID, *, include_archived: bool = True
) -> list[AssetCategory]:
    query = select(AssetCategory).where(AssetCategory.organization_id == organization_id)
    if not include_archived:
        query = query.where(AssetCategory.archived_at.is_(None))
    return list(db.scalars(query.order_by(AssetCategory.name, AssetCategory.id)))


def _check_rate(rate: Decimal | None, label: str) -> None:
    if rate is None:
        return
    if rate < 0 or rate > MAX_RESIDUAL_RATE or rate != rate.quantize(Decimal("0.01")):
        raise AppError(
            "RESIDUAL_RATE_INVALID",
            f"{label}: va de 0 a 20 % del costo, con hasta dos decimales (Ley 6380, art. 11).",
            status_code=422,
        )


def _check_category_accounts(
    db: Session, organization_id: uuid.UUID, values: dict[str, Any]
) -> None:
    for field, label in ACCOUNT_FIELDS.items():
        account_id = values.get(field)
        if account_id is None:
            continue
        account = db.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == account_id, LedgerAccount.organization_id == organization_id
            )
        )
        if account is None:
            raise AppError(
                "LEDGER_ACCOUNT_NOT_FOUND", f"La {label} no existe en el plan.", status_code=422
            )
        problem = depreciation.account_problem(label, account)
        if problem is not None:
            raise AppError(
                "INVALID_CATEGORY_ACCOUNT", f"La categoría necesita {problem}.", status_code=422
            )


def _category_in_use(db: Session, category_id: uuid.UUID) -> bool:
    """Tiene bienes con depreciaciones vivas (sus cuentas ya recibieron asientos)."""
    return bool(
        db.scalar(
            select(
                exists()
                .where(DepreciationItem.asset_id == FixedAsset.id)
                .where(DepreciationRun.id == DepreciationItem.run_id)
                .where(DepreciationRun.entry_status.in_(depreciation.LIVE))
                .where(FixedAsset.category_id == category_id)
            )
        )
    )


def create_category(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> AssetCategory:
    _check_rate(data.get("residual_rate"), "El porcentaje de valor residual")
    _check_category_accounts(db, organization_id, data)
    category = AssetCategory(
        organization_id=organization_id, **{f: data.get(f) for f in CATEGORY_FIELDS}
    )
    db.add(category)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "asset_category",
        "created",
        category.id,
        after=snapshot(category, (*CATEGORY_FIELDS, "validation_status")),
    )
    db.commit()
    return category


def update_category(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    category_id: uuid.UUID,
    data: dict[str, Any],
) -> AssetCategory:
    category = get_category(db, organization_id, category_id, lock=True)
    changes = {k: v for k, v in data.items() if k in CATEGORY_FIELDS}
    if "name" in changes and changes["name"] is None:
        raise AppError("NAME_REQUIRED", "La categoría lleva nombre.", status_code=422)
    _check_rate(changes.get("residual_rate"), "El porcentaje de valor residual")
    _check_category_accounts(db, organization_id, changes)
    account_change = any(
        f in changes and changes[f] != getattr(category, f) for f in ACCOUNT_FIELDS
    )
    if account_change and _category_in_use(db, category.id):
        raise Conflict(
            "ASSET_CATEGORY_IN_USE",
            "La categoría tiene bienes con depreciaciones: sus cuentas ya no cambian (el saldo "
            "quedaría repartido en dos cuentas).",
        )
    if "archived" in data and data["archived"] is not None:
        archived = bool(data["archived"])
        if archived != (category.archived_at is not None):
            changes["archived_at"] = now() if archived else None
    structural = any(f in changes and changes[f] != getattr(category, f) for f in STRUCTURAL_FIELDS)
    if structural and category.validation_status == "validated":
        changes.update(
            {
                "validation_status": "pending",
                "validated_by_name": None,
                "validated_reference": None,
                "validated_at": None,
            }
        )
    before, after = apply_changes(category, changes)
    if after:
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "asset_category",
            "updated",
            category.id,
            before=before,
            after=after,
        )
    db.commit()
    return category


def validate_category(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    category_id: uuid.UUID,
    by_name: str,
    reference: str,
) -> AssetCategory:
    category = get_category(db, organization_id, category_id, lock=True)
    depreciation.require_complete(db, [category])
    before, after = apply_changes(
        category,
        {
            "validation_status": "validated",
            "validated_by_name": by_name,
            "validated_reference": reference,
            "validated_at": now(),
        },
    )
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "asset_category",
        "validated",
        category.id,
        before=before,
        after=after,
    )
    db.commit()
    return category


def _proposed_account(
    accounts: dict[str, LedgerAccount], code: str | None, label: str
) -> uuid.UUID | None:
    if code is None or code not in accounts:
        return None
    account = accounts[code]
    return account.id if depreciation.account_problem(label, account) is None else None


def load_proposed(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID
) -> list[AssetCategory]:
    """Carga las 34 candidatas (sin validar) si la organización no tiene ninguna categoría."""
    chart.lock_settings(db, organization_id)  # serializa dos cargas simultáneas
    if db.scalar(select(AssetCategory.id).where(AssetCategory.organization_id == organization_id)):
        raise Conflict(
            "ASSET_CATEGORIES_NOT_EMPTY",
            "La organización ya tiene categorías: las candidatas solo se cargan sin ninguna.",
        )
    accounts = {a.code: a for a in chart.list_accounts(db, organization_id)}
    created: list[AssetCategory] = []
    for row in proposed_asset_categories.CATEGORIAS:
        years = row["vida_util_anios"]
        rate = row["valor_residual_pct"]
        category = AssetCategory(
            organization_id=organization_id,
            code=row["codigo"],
            name=row["nombre"],
            useful_life_months=int(years) * 12 if years is not None else None,
            residual_rate=Decimal(str(rate)) if rate is not None else None,
            asset_account_id=_proposed_account(accounts, row["cuenta_activo"], "cuenta de activo"),
            accumulated_account_id=_proposed_account(
                accounts, row["cuenta_depreciacion_acumulada"], "cuenta de depreciación acumulada"
            ),
            expense_account_id=_proposed_account(accounts, row["cuenta_gasto"], "cuenta de gasto"),
            source_url=row["fuente_url"],
            legal_reference=row["referencia_legal"],
            citation=row["cita"],
            note=row["nota"],
        )
        db.add(category)
        created.append(category)
    flush_translated(db)
    for category in created:
        record(
            db,
            organization_id,
            actor_id,
            "asset_category",
            "created",
            category.id,
            after=snapshot(category, (*CATEGORY_FIELDS, "validation_status")),
        )
    record(
        db,
        organization_id,
        actor_id,
        "asset_categories",
        "loaded",
        organization_id,
        after={
            "source": "proposed",
            "categories": len(created),
            "base": proposed_asset_categories.META["base"],
        },
    )
    db.commit()
    return sorted(created, key=lambda c: (c.name, c.id))


# --- Bienes -------------------------------------------------------------------------------


def asset_not_found() -> NotFound:
    return NotFound("FIXED_ASSET_NOT_FOUND", "El bien no existe.")


def get_asset(
    db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID, *, lock: bool = False
) -> FixedAsset:
    query = select(FixedAsset).where(
        FixedAsset.id == asset_id, FixedAsset.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    asset = db.scalar(query)
    if asset is None:
        raise asset_not_found()
    return asset


@dataclass(frozen=True)
class AssetFilters:
    category_id: uuid.UUID | None = None
    status: str | None = None
    q: str | None = None


def list_assets(db: Session, organization_id: uuid.UUID, filters: AssetFilters) -> list[FixedAsset]:
    query = select(FixedAsset).where(FixedAsset.organization_id == organization_id)
    if filters.category_id is not None:
        query = query.where(FixedAsset.category_id == filters.category_id)
    if filters.status is not None:
        query = query.where(FixedAsset.status == filters.status)
    if filters.q and filters.q.strip():
        term = f"%{escape_like(filters.q.strip())}%"
        conditions: list[ColumnElement[bool]] = [
            FixedAsset.name.ilike(term, escape="\\"),
            FixedAsset.description.ilike(term, escape="\\"),
            FixedAsset.serial_or_reference.ilike(term, escape="\\"),
        ]
        query = query.where(or_(*conditions))
    return list(db.scalars(query.order_by(FixedAsset.acquired_on.desc(), FixedAsset.id.desc())))


def fiscal_residual_value(cost: Decimal, rate: Decimal) -> Decimal:
    """RG 77/2020, col. 6: costo por porcentaje, en guaraníes enteros hacia abajo."""
    return (cost * rate / 100).quantize(Decimal(1), rounding=ROUND_FLOOR)


def warnings_for(asset: FixedAsset) -> list[str]:
    result = []
    if asset.acquired_on < NORM_IN_FORCE_SINCE:
        result.append(
            "El bien se adquirió antes del 14/10/2021: puede regirse por otra redacción del "
            "Decreto 3182, art. 31 (art. 30: rige la norma vigente al adquirirlo). Verificá la "
            "vida útil y el residual."
        )
    return result


def _usable_category(
    db: Session, organization_id: uuid.UUID, category_id: uuid.UUID
) -> AssetCategory:
    category = get_category(db, organization_id, category_id)
    if category.archived_at is not None:
        raise AppError("ASSET_CATEGORY_ARCHIVED", "La categoría está archivada.", status_code=422)
    depreciation.require_complete(db, [category])
    return category


def _check_links(db: Session, organization_id: uuid.UUID, values: dict[str, Any]) -> str | None:
    """Asiento de compra y movimiento de finanzas de origen. Devuelve el contexto."""
    entry_id = values.get("acquisition_entry_id")
    if entry_id is not None and not db.scalar(
        select(JournalEntry.id).where(
            JournalEntry.id == entry_id, JournalEntry.organization_id == organization_id
        )
    ):
        raise AppError("ENTRY_NOT_FOUND", "El asiento de compra no existe.", status_code=422)
    transaction_id = values.get("source_transaction_id")
    if transaction_id is None:
        return None
    context_id = db.scalar(
        select(Transaction.context_id)
        .join(FinancialContext, FinancialContext.id == Transaction.context_id)
        .where(
            Transaction.id == transaction_id,
            FinancialContext.organization_id == organization_id,
            FinancialContext.kind == "business",
        )
    )
    if context_id is None:
        raise AppError(
            "TRANSACTION_NOT_FOUND", "El movimiento no existe en la empresa.", status_code=422
        )
    return str(context_id)


def _resolve(db: Session, organization_id: uuid.UUID, values: dict[str, Any]) -> dict[str, Any]:
    """Valida los parámetros completos de un bien y calcula los derivados."""
    category = _usable_category(db, organization_id, values["category_id"])
    assert category.useful_life_months is not None and category.residual_rate is not None
    cost = pyg_amount(values["cost"], field="Costo")
    if cost <= 0:
        raise AppError("INVALID_AMOUNT", "El costo va en positivo.", status_code=422)
    rate = values.get("fiscal_residual_rate")
    rate = category.residual_rate if rate is None else rate
    _check_rate(rate, "El porcentaje de valor residual fiscal")
    fiscal_residual = fiscal_residual_value(cost, rate)
    residual = values.get("residual_value")
    residual = fiscal_residual if residual is None else pyg_amount(residual, field="Residual")
    if residual >= cost:
        raise AppError(
            "RESIDUAL_INVALID",
            "El valor residual contable tiene que ser menor que el costo.",
            status_code=422,
        )
    life = values.get("useful_life_months") or category.useful_life_months
    fiscal_life = values.get("fiscal_useful_life_months") or category.useful_life_months
    for label, months, depreciable in (
        ("contable", life, cost - residual),
        ("fiscal", fiscal_life, cost - fiscal_residual),
    ):
        if depreciable < months:
            raise AppError(
                "DEPRECIABLE_TOO_SMALL",
                f"El importe depreciable {label} ({depreciable:f}) es menor que la vida útil en "
                f"meses ({months}): la cuota mensual daría menos de ₲ 1.",
                status_code=422,
            )
    rule = values.get("start_rule")
    if rule is None:
        settings = chart.get_settings(db, organization_id)
        rule = settings.default_asset_start_rule if settings is not None else "next_month"
    acquired: date = values["acquired_on"]
    start = depreciation.depreciation_start_for(db, organization_id, acquired, rule)
    first_year = db.scalar(
        select(func.min(FiscalYear.start_date)).where(FiscalYear.organization_id == organization_id)
    )
    if first_year is None or start < depreciation.month_start(first_year):
        raise AppError(
            "DEPRECIATION_START_BEFORE_BOOKS",
            f"La depreciación empezaría en {start:%m/%Y}, antes del primer ejercicio contable: "
            "creá ese ejercicio primero (esta versión no carga depreciaciones anteriores a los "
            "libros).",
            status_code=422,
        )
    run_months = depreciation.live_run_months(db, organization_id)
    later = [m for m in run_months if m >= start]
    if later:
        raise Conflict(
            "DEPRECIATION_ALREADY_RUN",
            f"Ya hay corridas de depreciación desde {min(later):%m/%Y}, y el bien empezaría a "
            f"depreciarse en {start:%m/%Y}: revertí o descartá esas corridas para incorporarlo.",
            details={"month": min(later).isoformat()},
        )
    context_id = _check_links(db, organization_id, values)
    return {
        "category_id": category.id,
        "acquired_on": acquired,
        "start_rule": rule,
        "depreciation_start": start,
        "cost": cost,
        "residual_value": residual,
        "useful_life_months": life,
        "fiscal_useful_life_months": fiscal_life,
        "fiscal_residual_rate": rate,
        "fiscal_residual_value": fiscal_residual,
        "acquisition_entry_id": values.get("acquisition_entry_id"),
        "source_transaction_id": values.get("source_transaction_id"),
        "source_context_id": uuid.UUID(context_id) if context_id is not None else None,
        "source_context_kind": "business" if context_id is not None else None,
    }


def create_asset(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> FixedAsset:
    chart.lock_settings(db, organization_id)  # serializa con otras altas y con las corridas
    resolved = _resolve(db, organization_id, data)
    asset = FixedAsset(
        organization_id=organization_id,
        name=data["name"],
        description=data.get("description"),
        serial_or_reference=data.get("serial_or_reference"),
        created_by=actor_id,
        **resolved,
    )
    db.add(asset)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "fixed_asset",
        "created",
        asset.id,
        after=snapshot(asset, ASSET_FIELDS),
    )
    db.commit()
    return asset


def has_live_items(db: Session, asset_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(
                exists()
                .where(DepreciationItem.asset_id == asset_id)
                .where(DepreciationRun.id == DepreciationItem.run_id)
                .where(DepreciationRun.entry_status.in_(depreciation.LIVE))
            )
        )
    )


def update_asset(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    asset_id: uuid.UUID,
    data: dict[str, Any],
) -> FixedAsset:
    chart.lock_settings(db, organization_id)
    asset = get_asset(db, organization_id, asset_id, lock=True)
    for key in ("name", "category_id", "acquired_on", "cost", "start_rule"):
        if key in data and data[key] is None:
            raise AppError("FIELD_REQUIRED", f"`{key}` no puede quedar vacío.", status_code=422)
    changes: dict[str, Any] = {
        k: data[k] for k in ("name", "description", "serial_or_reference") if k in data
    }
    financial = {k: data[k] for k in (*FINANCIAL_FIELDS, "acquisition_entry_id") if k in data}
    if (
        any(financial.get(k, getattr(asset, k)) != getattr(asset, k) for k in FINANCIAL_FIELDS)
        or "acquisition_entry_id" in financial
    ):
        if asset.disposal_entry_id is not None:
            raise Conflict(
                "ASSET_DISPOSED",
                "El bien tiene una baja (borrador o contabilizada): sus datos de compra ya no "
                "cambian.",
            )
        if has_live_items(db, asset.id) and any(
            financial.get(k, getattr(asset, k)) != getattr(asset, k) for k in FINANCIAL_FIELDS
        ):
            raise Conflict(
                "ASSET_HAS_DEPRECIATION",
                "El bien tiene depreciaciones (borrador o contabilizadas): no cambian su costo, "
                "residual, vida útil, inicio ni categoría. Revertí o descartá esas corridas.",
            )
        values = {
            "category_id": asset.category_id,
            "acquired_on": asset.acquired_on,
            "start_rule": asset.start_rule,
            "cost": asset.cost,
            "residual_value": asset.residual_value,
            "useful_life_months": asset.useful_life_months,
            "fiscal_useful_life_months": asset.fiscal_useful_life_months,
            "fiscal_residual_rate": asset.fiscal_residual_rate,
            "acquisition_entry_id": asset.acquisition_entry_id,
            "source_transaction_id": asset.source_transaction_id,
            **financial,
        }
        if has_live_items(db, asset.id):
            # Solo cambia el asiento de compra: el resto ya está validado.
            _check_links(db, organization_id, values)
            changes["acquisition_entry_id"] = values["acquisition_entry_id"]
        else:
            resolved = _resolve(db, organization_id, values)
            changes.update({k: v for k, v in resolved.items() if not k.startswith("source_")})
    before, after = apply_changes(asset, changes)
    if after:
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "fixed_asset",
            "updated",
            asset.id,
            before=before,
            after=after,
        )
    db.commit()
    return asset


# --- Plan de cuotas -----------------------------------------------------------------------


@dataclass(frozen=True)
class Installment:
    installment: int
    month: date
    amount: Decimal
    status: str  # posted | draft | pending
    entry_id: uuid.UUID | None


def accumulated(db: Session, asset: FixedAsset) -> Decimal:
    rows = depreciation.item_rows(
        db, asset.organization_id, asset_ids=[asset.id], statuses=("posted",)
    )
    return sum((r.amount for r in rows), ZERO)


def accumulated_many(
    db: Session, organization_id: uuid.UUID, asset_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    totals: dict[uuid.UUID, Decimal] = dict.fromkeys(asset_ids, ZERO)
    if asset_ids:
        for row in depreciation.item_rows(
            db, organization_id, asset_ids=asset_ids, statuses=("posted",)
        ):
            totals[row.asset_id] += row.amount
    return totals


def installment_plan(db: Session, asset: FixedAsset) -> list[Installment]:
    """Cuotas contabilizadas (las del detalle de las corridas), en borrador y pendientes
    (calculadas). Si el bien tiene baja, termina en el mes anterior a la baja."""
    rows = {
        r.installment: r
        for r in depreciation.item_rows(db, asset.organization_id, asset_ids=[asset.id])
    }
    stop = depreciation.stop_month(asset)
    plan: list[Installment] = []
    for k in range(1, asset.useful_life_months + 1):
        month = depreciation.add_months(asset.depreciation_start, k - 1)
        if stop is not None and month >= stop:
            break
        row = rows.get(k)
        if row is not None:
            plan.append(Installment(k, month, row.amount, row.entry_status, row.entry_id))
        else:
            amount = depreciation.quota(
                depreciation.accounting_depreciable(asset), asset.useful_life_months, k
            )
            plan.append(Installment(k, month, amount, "pending", None))
    return plan
