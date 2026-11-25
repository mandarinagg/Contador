"""API de la fase 3B (`/api/v1/accounting`). Especificación: FASE3B_CONTABILIDAD.md §4.

Permisos (§3, sin permisos nuevos): `accounting.read` para leer; `accounting.manage` para
categorías, bienes, centros y plantillas, y para generar los borradores de depreciación,
baja y recurrentes; `accounting.post` para validar categorías (contabilizar esos borradores
es `POST /entries/{id}/post`, como cualquier asiento).
"""

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.modules.accounting import (
    asset_schedule,
    assets,
    chart,
    cost_centers,
    depreciation,
    entries,
    exports,
    periods,
    recurring,
)
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import pyg
from app.modules.accounting.models import (
    AssetCategory,
    DepreciationRun,
    FixedAsset,
    RecurringTemplate,
)
from app.modules.accounting.router import (
    Format,
    Manager,
    Poster,
    Reader,
    _entries_out,
    _entry_out,
    _xlsx,
)
from app.modules.accounting.schemas import EntryOut
from app.modules.accounting.schemas_3b import (
    AssetCategoryCreate,
    AssetCategoryOut,
    AssetCategoryUpdate,
    AssetStatus,
    CostCenterCreate,
    CostCenterOut,
    CostCenterUpdate,
    DepreciationItemOut,
    DepreciationRunOut,
    DepreciationScheduleOut,
    DisposeIn,
    FixedAssetCreate,
    FixedAssetOut,
    FixedAssetUpdate,
    InstallmentOut,
    PeriodIn,
    ReconciliationLineOut,
    ReconciliationOut,
    RecurringDueOut,
    RecurringGenerateOut,
    RecurringLineOut,
    RecurringTemplateCreate,
    RecurringTemplateOut,
    RecurringTemplateUpdate,
    ScheduleCategoryOut,
    ScheduleRowOut,
    ScheduleTotalsOut,
)

router = APIRouter(prefix="/accounting", tags=["accounting"])


def _rate(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value is not None else None


# --- Categorías ---------------------------------------------------------------------------


def _category_out(db: Session, category: AssetCategory) -> AssetCategoryOut:
    missing = depreciation.category_problems(db, category)
    return AssetCategoryOut(
        id=category.id,
        code=category.code,
        name=category.name,
        useful_life_months=category.useful_life_months,
        residual_rate=_rate(category.residual_rate),
        asset_account_id=category.asset_account_id,
        accumulated_account_id=category.accumulated_account_id,
        expense_account_id=category.expense_account_id,
        source_url=category.source_url,
        legal_reference=category.legal_reference,
        citation=category.citation,
        note=category.note,
        validation_status=category.validation_status,
        validated_by_name=category.validated_by_name,
        validated_reference=category.validated_reference,
        validated_at=category.validated_at,
        archived_at=category.archived_at,
        complete=not missing,
        missing=missing,
    )


@router.get("/asset-categories", response_model=list[AssetCategoryOut])
def list_asset_categories(
    auth: Reader, db: DbSession, include_archived: bool = True
) -> list[AssetCategoryOut]:
    rows = assets.list_categories(db, auth.organization_id, include_archived=include_archived)
    return [_category_out(db, c) for c in rows]


@router.post(
    "/asset-categories", response_model=AssetCategoryOut, status_code=status.HTTP_201_CREATED
)
def create_asset_category(
    body: AssetCategoryCreate, auth: Manager, db: DbSession
) -> AssetCategoryOut:
    category = assets.create_category(db, auth.organization_id, auth.user_id, body.model_dump())
    return _category_out(db, category)


@router.post(
    "/asset-categories/load-proposed",
    response_model=list[AssetCategoryOut],
    status_code=status.HTTP_201_CREATED,
)
def load_proposed_categories(auth: Manager, db: DbSession) -> list[AssetCategoryOut]:
    """Carga las 34 categorías candidatas (sin validar). 409 si ya hay categorías."""
    created = assets.load_proposed(db, auth.organization_id, auth.user_id)
    return [_category_out(db, c) for c in created]


@router.get("/asset-categories/{category_id}", response_model=AssetCategoryOut)
def get_asset_category(category_id: uuid.UUID, auth: Reader, db: DbSession) -> AssetCategoryOut:
    return _category_out(db, assets.get_category(db, auth.organization_id, category_id))


@router.patch("/asset-categories/{category_id}", response_model=AssetCategoryOut)
def update_asset_category(
    category_id: uuid.UUID, body: AssetCategoryUpdate, auth: Manager, db: DbSession
) -> AssetCategoryOut:
    """Un cambio de vida útil, residual o cuentas vuelve la categoría a `pending`."""
    category = assets.update_category(
        db, auth.organization_id, auth.user_id, category_id, body.model_dump(exclude_unset=True)
    )
    return _category_out(db, category)


@router.post("/asset-categories/{category_id}/validate", response_model=AssetCategoryOut)
def validate_asset_category(
    category_id: uuid.UUID, auth: Poster, db: DbSession
) -> AssetCategoryOut:
    """La valida CONTADOR AI (D-120): exige la categoría completa y su fuente oficial."""
    category = assets.validate_category(db, auth.organization_id, auth.user_id, category_id)
    return _category_out(db, category)


# --- Bienes -------------------------------------------------------------------------------


def _assets_out(
    db: Session, organization_id: uuid.UUID, items: list[FixedAsset], *, detail: bool = False
) -> list[FixedAssetOut]:
    names = {c.id: c.name for c in assets.list_categories(db, organization_id)}
    accumulated = assets.accumulated_many(db, organization_id, [a.id for a in items])
    result = []
    for asset in items:
        total = accumulated.get(asset.id, ZERO)
        net = ZERO if asset.status == "disposed" else asset.cost - total
        result.append(
            FixedAssetOut(
                id=asset.id,
                category_id=asset.category_id,
                category_name=names.get(asset.category_id, ""),
                name=asset.name,
                description=asset.description,
                serial_or_reference=asset.serial_or_reference,
                acquired_on=asset.acquired_on,
                start_rule=asset.start_rule,
                depreciation_start=asset.depreciation_start,
                cost=pyg(asset.cost),
                residual_value=pyg(asset.residual_value),
                useful_life_months=asset.useful_life_months,
                fiscal_useful_life_months=asset.fiscal_useful_life_months,
                fiscal_residual_rate=_rate(asset.fiscal_residual_rate) or "0",
                fiscal_residual_value=pyg(asset.fiscal_residual_value),
                acquisition_entry_id=asset.acquisition_entry_id,
                source_transaction_id=asset.source_transaction_id,
                status=asset.status,
                disposed_on=asset.disposed_on,
                disposal_kind=asset.disposal_kind,
                disposal_reason=asset.disposal_reason,
                disposal_document_reference=asset.disposal_document_reference,
                disposal_entry_id=asset.disposal_entry_id,
                accumulated_depreciation=pyg(total),
                net_book_value=pyg(net),
                warnings=assets.warnings_for(asset),
                created_at=asset.created_at,
                installments=(
                    [
                        InstallmentOut(
                            installment=i.installment,
                            month=i.month,
                            amount=pyg(i.amount),
                            status=i.status,
                            entry_id=i.entry_id,
                        )
                        for i in assets.installment_plan(db, asset)
                    ]
                    if detail
                    else None
                ),
            )
        )
    return result


@router.get("/fixed-assets", response_model=list[FixedAssetOut])
def list_fixed_assets(
    auth: Reader,
    db: DbSession,
    category_id: uuid.UUID | None = None,
    asset_status: Annotated[AssetStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[FixedAssetOut]:
    filters = assets.AssetFilters(category_id=category_id, status=asset_status, q=q)
    rows = assets.list_assets(db, auth.organization_id, filters)
    return _assets_out(db, auth.organization_id, rows)


@router.post("/fixed-assets", response_model=FixedAssetOut, status_code=status.HTTP_201_CREATED)
def create_fixed_asset(body: FixedAssetCreate, auth: Manager, db: DbSession) -> FixedAssetOut:
    asset = assets.create_asset(db, auth.organization_id, auth.user_id, body.model_dump())
    return _assets_out(db, auth.organization_id, [asset], detail=True)[0]


@router.get("/fixed-assets/{asset_id}", response_model=FixedAssetOut)
def get_fixed_asset(asset_id: uuid.UUID, auth: Reader, db: DbSession) -> FixedAssetOut:
    """Con el plan de cuotas: contabilizadas, en borrador y pendientes (calculadas)."""
    asset = assets.get_asset(db, auth.organization_id, asset_id)
    return _assets_out(db, auth.organization_id, [asset], detail=True)[0]


@router.patch("/fixed-assets/{asset_id}", response_model=FixedAssetOut)
def update_fixed_asset(
    asset_id: uuid.UUID, body: FixedAssetUpdate, auth: Manager, db: DbSession
) -> FixedAssetOut:
    asset = assets.update_asset(
        db, auth.organization_id, auth.user_id, asset_id, body.model_dump(exclude_unset=True)
    )
    return _assets_out(db, auth.organization_id, [asset], detail=True)[0]


@router.post(
    "/fixed-assets/{asset_id}/dispose", response_model=EntryOut, status_code=status.HTTP_201_CREATED
)
def dispose_fixed_asset(
    asset_id: uuid.UUID, body: DisposeIn, auth: Manager, db: DbSession
) -> EntryOut:
    """Borrador de baja (D-059). El bien pasa a `disposed` al contabilizarlo."""
    asset = depreciation.dispose(
        db,
        auth.organization_id,
        auth.user_id,
        asset_id,
        {
            "date": body.on,
            "kind": body.kind,
            "reason": body.reason,
            "document_reference": body.document_reference,
        },
    )
    assert asset.disposal_entry_id is not None
    entry = entries.get_entry(db, auth.organization_id, asset.disposal_entry_id)
    return _entry_out(db, auth.organization_id, entry)


# --- Depreciación -------------------------------------------------------------------------


def _run_out(
    db: Session, organization_id: uuid.UUID, run: DepreciationRun, *, detail: bool
) -> DepreciationRunOut:
    items = depreciation.run_items(db, run.id)
    entry = entries.get_entry(db, organization_id, run.entry_id) if detail else None
    return DepreciationRunOut(
        id=run.id,
        period_id=run.period_id,
        entry_id=run.entry_id,
        entry_status=run.entry_status,
        total=pyg(sum((item.amount for item, _ in items), ZERO)),
        created_at=run.created_at,
        entry=_entry_out(db, organization_id, entry) if entry is not None else None,
        items=(
            [
                DepreciationItemOut(
                    asset_id=asset.id,
                    asset_name=asset.name,
                    category_id=asset.category_id,
                    installment=item.installment,
                    amount=pyg(item.amount),
                )
                for item, asset in items
            ]
            if detail
            else None
        ),
    )


@router.post(
    "/depreciation/run", response_model=DepreciationRunOut, status_code=status.HTTP_201_CREATED
)
def run_depreciation(body: PeriodIn, auth: Manager, db: DbSession) -> DepreciationRunOut:
    """Borrador de depreciación del período (D-058). No contabiliza."""
    run = depreciation.run_depreciation(db, auth.organization_id, auth.user_id, body.period_id)
    return _run_out(db, auth.organization_id, run, detail=True)


@router.get("/depreciation/runs", response_model=list[DepreciationRunOut])
def list_depreciation_runs(
    auth: Reader, db: DbSession, fiscal_year_id: uuid.UUID | None = None
) -> list[DepreciationRunOut]:
    runs = depreciation.list_runs(db, auth.organization_id, fiscal_year_id)
    return [_run_out(db, auth.organization_id, r, detail=False) for r in runs]


@router.get("/depreciation/runs/{run_id}", response_model=DepreciationRunOut)
def get_depreciation_run(run_id: uuid.UUID, auth: Reader, db: DbSession) -> DepreciationRunOut:
    run = depreciation.get_run(db, auth.organization_id, run_id)
    return _run_out(db, auth.organization_id, run, detail=True)


def _totals(total: Callable[[str], Decimal]) -> ScheduleTotalsOut:
    return ScheduleTotalsOut(**{c: pyg(total(c)) for c in asset_schedule.MONEY_COLUMNS})


def _schedule_row(r: asset_schedule.ScheduleRow) -> ScheduleRowOut:
    return ScheduleRowOut(
        asset_id=r.asset.id,
        description=r.asset.name,
        acquired_on=r.asset.acquired_on,
        disposed_on=r.asset.disposed_on if r.disposed_in_year else None,
        revaluation_coefficient="0",
        fiscal_residual_rate=_rate(r.fiscal_residual_rate) or "0",
        fiscal_useful_life_months=r.fiscal_useful_life_months,
        fiscal_useful_life_years=format(asset_schedule.years(r.fiscal_useful_life_months), "f"),
        fiscal_remaining_months=r.fiscal_remaining_months,
        fiscal_remaining_years=format(asset_schedule.years(r.fiscal_remaining_months), "f"),
        useful_life_months=r.useful_life_months,
        useful_life_years=format(asset_schedule.years(r.useful_life_months), "f"),
        remaining_months=r.remaining_months,
        remaining_years=format(asset_schedule.years(r.remaining_months), "f"),
        **{c: pyg(getattr(r, c)) for c in asset_schedule.MONEY_COLUMNS},
    )


@router.get("/reports/depreciation-schedule", response_model=DepreciationScheduleOut)
def depreciation_schedule_report(
    auth: Reader, db: DbSession, fiscal_year_id: uuid.UUID, fmt: Format = "json"
) -> DepreciationScheduleOut | Response:
    """Cuadro de depreciación del ejercicio con las columnas de la RG 77/2020 (D-067)."""
    chart_status = chart.chart_status(db, auth.organization_id)
    if fmt == "xlsx":
        content = exports.schedule_xlsx(db, auth.organization_id, fiscal_year_id, chart_status)
        year = periods.get_fiscal_year(db, auth.organization_id, fiscal_year_id)
        name = f"cuadro-de-depreciacion-{year.start_date}-{year.end_date}.xlsx"
        return _xlsx(content, name)
    report = asset_schedule.schedule(db, auth.organization_id, fiscal_year_id)
    return DepreciationScheduleOut(
        chart_status=chart_status,
        fiscal_year_id=report.year.id,
        date_from=report.year.start_date,
        date_to=report.year.end_date,
        categories=[
            ScheduleCategoryOut(
                category_id=g.category.id,
                name=g.category.name,
                validation_status=g.category.validation_status,
                assets=[_schedule_row(r) for r in g.rows],
                totals=_totals(g.total),
            )
            for g in report.groups
        ],
        totals=_totals(report.total),
        reconciliation=ReconciliationOut(
            lines=[
                ReconciliationLineOut(
                    account_id=line.account.id,
                    code=line.account.code,
                    name=line.account.name,
                    ledger_balance=pyg(line.ledger_balance),
                    schedule_amount=pyg(line.schedule_amount),
                    difference=pyg(line.ledger_balance - line.schedule_amount),
                )
                for line in report.reconciliation
            ],
            schedule_total=pyg(report.total("accounting_net_value")),
            ledger_total=pyg(report.ledger_total),
            reconciled=report.reconciled,
        ),
        warnings=report.warnings,
    )


# --- Centros de costos --------------------------------------------------------------------


@router.get("/cost-centers", response_model=list[CostCenterOut])
def list_cost_centers(
    auth: Reader, db: DbSession, include_archived: bool = False
) -> list[CostCenterOut]:
    rows = cost_centers.list_centers(db, auth.organization_id, include_archived=include_archived)
    return [CostCenterOut.model_validate(c) for c in rows]


@router.post("/cost-centers", response_model=CostCenterOut, status_code=status.HTTP_201_CREATED)
def create_cost_center(body: CostCenterCreate, auth: Manager, db: DbSession) -> CostCenterOut:
    center = cost_centers.create_center(db, auth.organization_id, auth.user_id, body.model_dump())
    return CostCenterOut.model_validate(center)


@router.get("/cost-centers/{center_id}", response_model=CostCenterOut)
def get_cost_center(center_id: uuid.UUID, auth: Reader, db: DbSession) -> CostCenterOut:
    return CostCenterOut.model_validate(
        cost_centers.get_center(db, auth.organization_id, center_id)
    )


@router.patch("/cost-centers/{center_id}", response_model=CostCenterOut)
def update_cost_center(
    center_id: uuid.UUID, body: CostCenterUpdate, auth: Manager, db: DbSession
) -> CostCenterOut:
    center = cost_centers.update_center(
        db, auth.organization_id, auth.user_id, center_id, body.model_dump(exclude_unset=True)
    )
    return CostCenterOut.model_validate(center)


# --- Recurrentes --------------------------------------------------------------------------


def _templates_out(
    db: Session, organization_id: uuid.UUID, templates: list[RecurringTemplate]
) -> list[RecurringTemplateOut]:
    lines = recurring.template_lines(db, [t.id for t in templates])
    accounts = entries.account_map(
        db, organization_id, {line.account_id for ls in lines.values() for line in ls}
    )
    return [
        RecurringTemplateOut(
            id=t.id,
            description=t.description,
            document_reference=t.document_reference,
            day_of_month=t.day_of_month,
            start_date=t.start_date,
            end_date=t.end_date,
            status=t.status,
            total=pyg(sum((line.debit for line in lines[t.id]), ZERO)),
            lines=[
                RecurringLineOut(
                    line_no=line.line_no,
                    account_id=line.account_id,
                    account_code=accounts[line.account_id].code,
                    account_name=accounts[line.account_id].name,
                    debit=pyg(line.debit),
                    credit=pyg(line.credit),
                    description=line.description,
                    cost_center_id=line.cost_center_id,
                )
                for line in lines[t.id]
            ],
            created_at=t.created_at,
        )
        for t in templates
    ]


@router.get("/recurring", response_model=list[RecurringTemplateOut])
def list_recurring(auth: Reader, db: DbSession) -> list[RecurringTemplateOut]:
    return _templates_out(
        db, auth.organization_id, recurring.list_templates(db, auth.organization_id)
    )


@router.post("/recurring", response_model=RecurringTemplateOut, status_code=status.HTTP_201_CREATED)
def create_recurring(
    body: RecurringTemplateCreate, auth: Manager, db: DbSession
) -> RecurringTemplateOut:
    template = recurring.create_template(db, auth.organization_id, auth.user_id, body.model_dump())
    return _templates_out(db, auth.organization_id, [template])[0]


@router.get("/recurring/due", response_model=list[RecurringDueOut])
def recurring_due(
    auth: Reader, db: DbSession, period_id: Annotated[uuid.UUID, Query()]
) -> list[RecurringDueOut]:
    """Qué falta generar en el período (para el aviso de la interfaz)."""
    return [
        RecurringDueOut(
            template_id=d.template.id,
            description=d.template.description,
            entry_date=d.entry_date,
            total=pyg(d.total),
        )
        for d in recurring.due(db, auth.organization_id, period_id)
    ]


@router.post("/recurring/generate", response_model=RecurringGenerateOut)
def generate_recurring(body: PeriodIn, auth: Manager, db: DbSession) -> RecurringGenerateOut:
    """Crea los borradores del período que falten; devuelve también los que ya existían."""
    result = recurring.generate(db, auth.organization_id, auth.user_id, body.period_id)
    return RecurringGenerateOut(
        created=_entries_out(db, auth.organization_id, result.created, with_lines=True),
        existing=_entries_out(db, auth.organization_id, result.existing, with_lines=True),
    )


@router.get("/recurring/{template_id}", response_model=RecurringTemplateOut)
def get_recurring(template_id: uuid.UUID, auth: Reader, db: DbSession) -> RecurringTemplateOut:
    template = recurring.get_template(db, auth.organization_id, template_id)
    return _templates_out(db, auth.organization_id, [template])[0]


@router.patch("/recurring/{template_id}", response_model=RecurringTemplateOut)
def update_recurring(
    template_id: uuid.UUID, body: RecurringTemplateUpdate, auth: Manager, db: DbSession
) -> RecurringTemplateOut:
    template = recurring.update_template(
        db, auth.organization_id, auth.user_id, template_id, body.model_dump(exclude_unset=True)
    )
    return _templates_out(db, auth.organization_id, [template])[0]
