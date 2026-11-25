"""Esquemas de entrada y salida de la API de contabilidad.

Importes: en JSON siempre son **string** (D-036, BR-ACC-05). La entrada rechaza números
JSON; el debe y el haber son guaraníes enteros (`"150000"`); la cotización admite hasta 6
decimales (`"7300.25"`).
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.modules.finance.schemas import AmountIn

AccountKind = Literal["asset", "liability", "equity", "income", "expense"]
NormalSide = Literal["debit", "credit"]
EntryStatus = Literal["draft", "posted", "reversed", "discarded"]
EntryKind = Literal[
    "manual", "finance", "reversal", "closing", "depreciation", "disposal", "recurring"
]
StartRule = Literal["next_month", "next_fiscal_year"]
FxCurrency = Literal["USD", "BRL", "ARS", "EUR"]

_RATE_TEXT = re.compile(r"^[0-9]{1,12}(\.[0-9]{1,6})?$")


def _rate_from_json(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str) or not _RATE_TEXT.match(value.strip()):
        raise ValueError(
            'La cotización va como texto, con hasta 6 decimales, por ejemplo "7300.25".'
        )
    return Decimal(value.strip())


RateIn = Annotated[Decimal, BeforeValidator(_rate_from_json)]

Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]+(\.[0-9]+)*$")]
AccountName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LineDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
DocumentReference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)]
ProfessionalReference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Plan de cuentas ----------------------------------------------------------------------


class LedgerAccountCreate(_Strict):
    parent_id: uuid.UUID | None = None
    code: Code = Field(max_length=30)
    name: AccountName
    # Por defecto, el tipo del padre y la naturaleza que corresponde al tipo.
    kind: AccountKind | None = None
    normal_side: NormalSide | None = None
    is_postable: bool
    note: Note | None = None


class LedgerAccountUpdate(_Strict):
    name: AccountName | None = None
    note: Note | None = None
    # Solo si la cuenta no tiene líneas (si no, 409 ACCOUNT_IN_USE).
    code: Annotated[Code, Field(max_length=30)] | None = None
    kind: AccountKind | None = None
    normal_side: NormalSide | None = None
    is_postable: bool | None = None
    archived: bool | None = None


class LedgerAccountOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    normal_side: str
    is_postable: bool
    parent_id: uuid.UUID | None
    origin: str
    note: str | None
    archived_at: datetime | None
    in_use: bool
    # Solo con `?balance_at=`: saldo al cierre de esa fecha, en el sentido del tipo de la
    # cuenta (las agrupadoras suman su subárbol).
    balance: str | None = None
    # Solo en el árbol (sin `?flat=true`).
    children: list["LedgerAccountOut"] | None = None


class SettingsOut(BaseModel):
    chart_status: str
    chart_validated_by_name: str | None
    chart_validated_reference: str | None
    chart_validated_at: datetime | None
    retained_earnings_account_id: uuid.UUID | None
    # 3B: cuenta de la baja de bienes (si es null se usa la 17.01), centros obligatorios e
    # inicio de depreciación por defecto.
    asset_disposal_account_id: uuid.UUID | None = None
    cost_centers_required: bool = False
    default_asset_start_rule: str = "next_month"


class ChartOut(SettingsOut):
    balance_at: date | None
    accounts: list[LedgerAccountOut]


class SettingsUpdate(_Strict):
    """Solo cambian los campos que llegan."""

    retained_earnings_account_id: uuid.UUID | None = None
    asset_disposal_account_id: uuid.UUID | None = None
    cost_centers_required: bool | None = None
    default_asset_start_rule: StartRule | None = None


# --- Ejercicios y períodos ------------------------------------------------------------------


class FiscalYearCreate(_Strict):
    """Por defecto, el año civil `year`. Con `start_date` y `end_date`, otro rango."""

    year: int | None = Field(default=None, ge=1990, le=2200)
    start_date: date | None = None
    end_date: date | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fiscal_year_id: uuid.UUID
    start_date: date
    end_date: date
    status: str
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    reopen_reason: str | None


class FiscalYearOut(BaseModel):
    id: uuid.UUID
    start_date: date
    end_date: date
    status: str
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    closing_entry_id: uuid.UUID | None
    last_entry_number: int
    periods: list[PeriodOut]


class ReasonIn(_Strict):
    reason: Reason


# --- Asientos -----------------------------------------------------------------------------


class EntryLineIn(_Strict):
    account_id: uuid.UUID
    debit: AmountIn = Decimal(0)
    credit: AmountIn = Decimal(0)
    description: LineDescription | None = None
    # Moneda extranjera informativa (D-036): los tres juntos o ninguno.
    fx_currency: FxCurrency | None = None
    fx_amount: AmountIn | None = None
    fx_rate: RateIn | None = None
    # Solo en cuentas de ingreso o gasto (D-060).
    cost_center_id: uuid.UUID | None = None


class EntryIn(_Strict):
    entry_date: date
    description: Description
    document_reference: DocumentReference | None = None
    lines: list[EntryLineIn] = Field(min_length=1, max_length=500)


class ReverseIn(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    reason: Reason
    # `date` en el JSON. Por defecto, la fecha del asiento original.
    on: date | None = Field(default=None, alias="date")


class FromTransactionIn(_Strict):
    fx_rate: RateIn | None = None
    # Solo si el producto importe por cotización no da un entero (se pide redondear a mano).
    amount_pyg: AmountIn | None = None


class EntryLineOut(BaseModel):
    id: uuid.UUID
    line_no: int
    account_id: uuid.UUID
    account_code: str
    account_name: str
    debit: str
    credit: str
    description: str | None
    fx_currency: str | None
    fx_amount: str | None
    fx_rate: str | None
    cost_center_id: uuid.UUID | None = None
    cost_center_code: str | None = None


class EntryOut(BaseModel):
    id: uuid.UUID
    fiscal_year_id: uuid.UUID
    entry_date: date
    number: int | None
    status: str
    kind: str
    description: str
    document_reference: str | None
    reverses_entry_id: uuid.UUID | None
    reversed_by_entry_id: uuid.UUID | None
    source_transaction_id: uuid.UUID | None
    source_context_id: uuid.UUID | None
    total_debit: str
    total_credit: str
    balanced: bool
    created_by: uuid.UUID
    # P-10: nombre visible del usuario (nada más), para quien no puede leer `/users`.
    created_by_name: str | None = None
    created_at: datetime
    posted_by: uuid.UUID | None
    posted_by_name: str | None = None
    posted_at: datetime | None
    discarded_by: uuid.UUID | None
    discarded_at: datetime | None
    discard_reason: str | None
    # Presentes en el detalle y en las respuestas de las acciones; ausentes en el listado.
    lines: list[EntryLineOut] | None = None


class EntryRefOut(BaseModel):
    """Asiento de un movimiento de finanzas empresarial (en `TransactionOut.journal_entry`)."""

    id: uuid.UUID
    number: int | None
    status: str


# --- Reportes -----------------------------------------------------------------------------


class ReportOut(BaseModel):
    chart_status: str


class JournalReportOut(ReportOut):
    date_from: date
    date_to: date
    total_debit: str
    total_credit: str
    entries: list[EntryOut]
    next_cursor: uuid.UUID | None


class LedgerMovementOut(BaseModel):
    line_id: uuid.UUID
    entry_id: uuid.UUID
    number: int
    entry_date: date
    entry_description: str
    line_description: str | None
    document_reference: str | None
    debit: str
    credit: str
    balance: str


class LedgerReportOut(ReportOut):
    account: LedgerAccountOut
    date_from: date
    date_to: date
    opening_balance: str
    total_debit: str
    total_credit: str
    closing_balance: str
    movements: list[LedgerMovementOut]
    next_cursor: uuid.UUID | None


class TrialRowOut(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    kind: str
    # D-062: saldo de todo lo contabilizado antes de `from` (refundición incluida).
    opening_debit: str
    opening_credit: str
    debit: str
    credit: str
    # Saldo del movimiento del rango.
    debit_balance: str
    credit_balance: str
    # Saldo final: inicial + movimiento del rango.
    closing_debit: str
    closing_credit: str


class TrialBalanceOut(ReportOut):
    date_from: date
    date_to: date
    rows: list[TrialRowOut]
    total_opening_debit: str
    total_opening_credit: str
    total_debit: str
    total_credit: str
    total_debit_balance: str
    total_credit_balance: str
    total_closing_debit: str
    total_closing_credit: str
    balanced: bool


class StatementNodeOut(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    kind: str
    is_postable: bool
    amount: str
    children: list["StatementNodeOut"]
    # Solo con `?by_cost_center=true`: el importe en cada columna de `cost_center_columns`.
    column_amounts: list[str] | None = None


class BalanceSheetOut(ReportOut):
    at: date
    assets: list[StatementNodeOut]
    liabilities: list[StatementNodeOut]
    equity: list[StatementNodeOut]
    total_assets: str
    total_liabilities: str
    total_equity: str
    # Resultado no refundido (ingresos - gastos de los ejercicios no cerrados).
    result: str
    total_liabilities_and_equity: str
    balanced: bool


class CostCenterColumnOut(BaseModel):
    """Columna del estado de resultados por centro; `cost_center_id` null = sin centro."""

    cost_center_id: uuid.UUID | None
    code: str | None
    name: str
    total_income: str
    total_expense: str
    result: str


class IncomeStatementOut(ReportOut):
    date_from: date
    date_to: date
    # Cuentas raíz de ingreso y gasto en orden de código (RG 49/2014 Anexo 2).
    accounts: list[StatementNodeOut]
    total_income: str
    total_expense: str
    result: str
    # Solo con `?by_cost_center=true` (D-060): una columna por centro y la última "sin centro".
    cost_center_columns: list[CostCenterColumnOut] | None = None
