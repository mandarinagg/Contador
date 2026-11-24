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
EntryKind = Literal["manual", "finance", "reversal", "closing"]
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


class ChartOut(SettingsOut):
    balance_at: date | None
    accounts: list[LedgerAccountOut]


class ChartValidate(_Strict):
    validated_by_name: PersonName
    validated_reference: ProfessionalReference


class SettingsUpdate(_Strict):
    retained_earnings_account_id: uuid.UUID | None


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
    created_at: datetime
    posted_by: uuid.UUID | None
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
    debit: str
    credit: str
    debit_balance: str
    credit_balance: str


class TrialBalanceOut(ReportOut):
    date_from: date
    date_to: date
    rows: list[TrialRowOut]
    total_debit: str
    total_credit: str
    total_debit_balance: str
    total_credit_balance: str
    balanced: bool


class StatementNodeOut(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    kind: str
    is_postable: bool
    amount: str
    children: list["StatementNodeOut"]


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


class IncomeStatementOut(ReportOut):
    date_from: date
    date_to: date
    # Cuentas raíz de ingreso y gasto en orden de código (RG 49/2014 Anexo 2).
    accounts: list[StatementNodeOut]
    total_income: str
    total_expense: str
    result: str
