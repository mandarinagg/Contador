"""Esquemas de la API de la fase 3B: activos fijos, depreciación, centros y recurrentes.

Mismas convenciones que `schemas.py`: importes como string (guaraníes enteros), entrada
estricta (`extra="forbid"`), nunca números JSON para importes.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.modules.accounting.schemas import (
    Description,
    DocumentReference,
    EntryLineIn,
    EntryOut,
    Reason,
    StartRule,
)
from app.modules.finance.schemas import AmountIn

AssetStatus = Literal["active", "disposed"]
DisposalKind = Literal["sale", "scrap", "donation"]
TemplateStatus = Literal["active", "paused"]

_RATE = re.compile(r"^[0-9]{1,2}(\.[0-9]{1,2})?$")


def _percent_from_json(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str) or not _RATE.match(value.strip()):
        raise ValueError('El porcentaje va como texto, con hasta 2 decimales, por ejemplo "10".')
    return Decimal(value.strip())


PercentIn = Annotated[Decimal, BeforeValidator(_percent_from_json)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Url = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Slug = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9_]{2,80}$", max_length=80)
]
Months = Annotated[int, Field(ge=1, le=1200)]
CenterCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=20
    ),
]
CenterName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Categorías ---------------------------------------------------------------------------


class AssetCategoryCreate(_Strict):
    code: Slug | None = None
    name: Name
    useful_life_months: Months | None = None
    residual_rate: PercentIn | None = None
    asset_account_id: uuid.UUID | None = None
    accumulated_account_id: uuid.UUID | None = None
    expense_account_id: uuid.UUID | None = None
    source_url: Url | None = None
    legal_reference: Url | None = None
    citation: LongText | None = None
    note: LongText | None = None


class AssetCategoryUpdate(_Strict):
    name: Name | None = None
    useful_life_months: Months | None = None
    residual_rate: PercentIn | None = None
    asset_account_id: uuid.UUID | None = None
    accumulated_account_id: uuid.UUID | None = None
    expense_account_id: uuid.UUID | None = None
    source_url: Url | None = None
    legal_reference: Url | None = None
    citation: LongText | None = None
    note: LongText | None = None
    archived: bool | None = None


class AssetCategoryOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    useful_life_months: int | None
    residual_rate: str | None
    asset_account_id: uuid.UUID | None
    accumulated_account_id: uuid.UUID | None
    expense_account_id: uuid.UUID | None
    source_url: str | None
    legal_reference: str | None
    citation: str | None
    note: str | None
    validation_status: str
    validated_by_name: str | None
    validated_reference: str | None
    validated_at: datetime | None
    archived_at: datetime | None
    # Completa = se puede usar (vida útil, residual y las tres cuentas válidas).
    complete: bool
    missing: list[str]


# --- Bienes -------------------------------------------------------------------------------


class FixedAssetCreate(_Strict):
    category_id: uuid.UUID
    name: Name
    description: LongText | None = None
    serial_or_reference: Reference | None = None
    acquired_on: date
    # El costo depreciable excluye gastos de financiación y diferencias de cambio (art. 23).
    cost: AmountIn
    # Por defecto, los de la categoría (residual contable = residual fiscal).
    residual_value: AmountIn | None = None
    useful_life_months: Months | None = None
    fiscal_useful_life_months: Months | None = None
    fiscal_residual_rate: PercentIn | None = None
    # Obligatoria si la vida útil o el residual fiscal difieren de la categoría (D-125).
    fiscal_life_authorization: Reference | None = None
    # Por defecto, `settings.default_asset_start_rule`.
    start_rule: StartRule | None = None
    acquisition_entry_id: uuid.UUID | None = None
    source_transaction_id: uuid.UUID | None = None


class FixedAssetUpdate(_Strict):
    name: Name | None = None
    description: LongText | None = None
    serial_or_reference: Reference | None = None
    # Solo sin depreciaciones vivas (si no, 409 ASSET_HAS_DEPRECIATION).
    category_id: uuid.UUID | None = None
    acquired_on: date | None = None
    cost: AmountIn | None = None
    residual_value: AmountIn | None = None
    useful_life_months: Months | None = None
    fiscal_useful_life_months: Months | None = None
    fiscal_residual_rate: PercentIn | None = None
    fiscal_life_authorization: Reference | None = None
    start_rule: StartRule | None = None
    acquisition_entry_id: uuid.UUID | None = None


class DisposeIn(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    on: date = Field(alias="date")
    kind: DisposalKind
    reason: Reason
    # Acta del contador o constancia del auditor externo (Decreto 3182, art. 58).
    document_reference: DocumentReference


class InstallmentOut(BaseModel):
    installment: int
    month: date
    amount: str
    # posted | draft | pending (calculada, sin corrida)
    status: str
    entry_id: uuid.UUID | None


class FixedAssetOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    name: str
    description: str | None
    serial_or_reference: str | None
    acquired_on: date
    start_rule: str
    depreciation_start: date
    cost: str
    residual_value: str
    useful_life_months: int
    fiscal_useful_life_months: int
    fiscal_residual_rate: str
    fiscal_residual_value: str
    fiscal_life_authorization: str | None
    acquisition_entry_id: uuid.UUID | None
    source_transaction_id: uuid.UUID | None
    status: str
    disposed_on: date | None
    disposal_kind: str | None
    disposal_reason: str | None
    disposal_document_reference: str | None
    disposal_entry_id: uuid.UUID | None
    accumulated_depreciation: str
    net_book_value: str
    warnings: list[str]
    created_at: datetime
    # Solo en el detalle.
    installments: list[InstallmentOut] | None = None


# --- Depreciación -------------------------------------------------------------------------


class PeriodIn(_Strict):
    period_id: uuid.UUID


class DepreciationItemOut(BaseModel):
    asset_id: uuid.UUID
    asset_name: str
    category_id: uuid.UUID
    installment: int
    amount: str


class DepreciationRunOut(BaseModel):
    id: uuid.UUID
    period_id: uuid.UUID
    entry_id: uuid.UUID
    entry_status: str
    total: str
    created_at: datetime
    entry: EntryOut | None = None
    items: list[DepreciationItemOut] | None = None


class ScheduleRowOut(BaseModel):
    asset_id: uuid.UUID
    description: str
    acquired_on: date
    disposed_on: date | None
    cost: str
    revaluation_coefficient: str
    fiscal_residual_rate: str
    fiscal_residual_value: str
    fiscal_useful_life_months: int
    fiscal_useful_life_years: str
    fiscal_remaining_months: int
    fiscal_remaining_years: str
    fiscal_net_previous: str
    fiscal_depreciable: str
    fiscal_depreciation: str
    fiscal_accumulated: str
    fiscal_net_value: str
    residual_value: str
    useful_life_months: int
    useful_life_years: str
    remaining_months: int
    remaining_years: str
    accounting_net_previous: str
    accounting_depreciable: str
    accounting_depreciation: str
    non_deductible: str
    accounting_accumulated: str
    accounting_net_value: str


class ScheduleTotalsOut(BaseModel):
    cost: str
    fiscal_residual_value: str
    fiscal_net_previous: str
    fiscal_depreciable: str
    fiscal_depreciation: str
    fiscal_accumulated: str
    fiscal_net_value: str
    residual_value: str
    accounting_net_previous: str
    accounting_depreciable: str
    accounting_depreciation: str
    non_deductible: str
    accounting_accumulated: str
    accounting_net_value: str


class ScheduleCategoryOut(BaseModel):
    category_id: uuid.UUID
    name: str
    validation_status: str
    assets: list[ScheduleRowOut]
    totals: ScheduleTotalsOut


class ReconciliationLineOut(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    ledger_balance: str
    schedule_amount: str
    difference: str


class ReconciliationOut(BaseModel):
    lines: list[ReconciliationLineOut]
    schedule_total: str
    ledger_total: str
    reconciled: bool


class DepreciationScheduleOut(BaseModel):
    chart_status: str
    fiscal_year_id: uuid.UUID
    date_from: date
    date_to: date
    categories: list[ScheduleCategoryOut]
    totals: ScheduleTotalsOut
    reconciliation: ReconciliationOut
    warnings: list[str]


# --- Centros de costos --------------------------------------------------------------------


class CostCenterCreate(_Strict):
    code: CenterCode
    name: CenterName


class CostCenterUpdate(_Strict):
    code: CenterCode | None = None
    name: CenterName | None = None
    archived: bool | None = None


class CostCenterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    archived_at: datetime | None


# --- Recurrentes --------------------------------------------------------------------------


class RecurringTemplateCreate(_Strict):
    description: Description
    document_reference: DocumentReference | None = None
    day_of_month: Annotated[int, Field(ge=1, le=31)]
    start_date: date
    end_date: date | None = None
    status: TemplateStatus = "active"
    lines: list[EntryLineIn] = Field(min_length=2, max_length=200)


class RecurringTemplateUpdate(_Strict):
    description: Description | None = None
    document_reference: DocumentReference | None = None
    day_of_month: Annotated[int, Field(ge=1, le=31)] | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: TemplateStatus | None = None
    # Si llegan, reemplazan las líneas.
    lines: list[EntryLineIn] | None = Field(default=None, min_length=2, max_length=200)


class RecurringLineOut(BaseModel):
    line_no: int
    account_id: uuid.UUID
    account_code: str
    account_name: str
    debit: str
    credit: str
    description: str | None
    cost_center_id: uuid.UUID | None


class RecurringTemplateOut(BaseModel):
    id: uuid.UUID
    description: str
    document_reference: str | None
    day_of_month: int
    start_date: date
    end_date: date | None
    status: str
    total: str
    lines: list[RecurringLineOut]
    created_at: datetime


class RecurringGenerateOut(BaseModel):
    created: list[EntryOut]
    existing: list[EntryOut]


class RecurringDueOut(BaseModel):
    template_id: uuid.UUID
    description: str
    entry_date: date
    total: str
