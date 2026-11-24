"""Esquemas de entrada y salida de la API de finanzas.

Importes: en JSON siempre son **string** (D-026). La entrada rechaza números JSON (un
`0.1` llega a Python como `float` y ya perdió exactitud); la salida se arma con
`money.format_amount`, nunca con `float`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, get_args

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    model_validator,
)

from app.modules.finance.money import CURRENCIES, AmountError, parse_amount_text
from app.modules.organizations.ruc import ruc_check_digit


def _amount_from_json(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str):
        raise ValueError('El importe va como texto, por ejemplo "1500.50" (nunca como número).')
    try:
        return parse_amount_text(value)
    except AmountError as exc:
        raise ValueError(str(exc)) from exc


# Importe de entrada: string decimal exacto ("-1500.50"). Los decimales según la moneda
# se validan en el servicio, que conoce la moneda de la cuenta.
AmountIn = Annotated[Decimal, BeforeValidator(_amount_from_json)]

Currency = Literal["PYG", "USD", "BRL", "ARS", "EUR"]
if set(get_args(Currency)) != set(CURRENCIES):  # pragma: no cover - guarda de coherencia
    raise RuntimeError("El Literal de monedas no coincide con el catálogo de money.py")

AccountKind = Literal["cash", "checking", "savings", "credit_card", "digital_wallet", "other"]
CategoryKind = Literal["income", "expense"]
CounterpartyKind = Literal[
    "customer", "supplier", "employee", "bank", "government", "person", "other"
]
Decision = Literal["import", "skip"]


AccountName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
CounterpartyName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)
]
Institution = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
VoidReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
Last4 = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]
Ruc = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,8}$")]
RucCheckDigit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Contextos ---------------------------------------------------------------------------


class ContextOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    owner_user_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


# --- Cuentas ----------------------------------------------------------------------------


class AccountCreate(_Strict):
    name: AccountName
    kind: AccountKind
    institution: Institution | None = None
    currency: Currency
    number_last4: Last4 | None = None
    opening_balance: AmountIn = Decimal(0)
    opening_date: date


class AccountUpdate(_Strict):
    name: AccountName | None = None
    kind: AccountKind | None = None
    institution: Institution | None = None
    number_last4: Last4 | None = None
    archived: bool | None = None
    # Solo si la cuenta todavía no tiene movimientos (si no, 409).
    currency: Currency | None = None
    opening_balance: AmountIn | None = None
    opening_date: date | None = None


class AccountOut(BaseModel):
    id: uuid.UUID
    context_id: uuid.UUID
    name: str
    kind: str
    institution: str | None
    currency: str
    number_last4: str | None
    opening_balance: str
    opening_date: date
    balance: str
    archived_at: datetime | None
    created_at: datetime


# --- Categorías -------------------------------------------------------------------------


class CategoryCreate(_Strict):
    name: CategoryName
    kind: CategoryKind
    parent_id: uuid.UUID | None = None


class CategoryUpdate(_Strict):
    name: CategoryName | None = None
    parent_id: uuid.UUID | None = None
    archived: bool | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    context_id: uuid.UUID
    name: str
    kind: str
    parent_id: uuid.UUID | None
    archived_at: datetime | None
    created_at: datetime


# --- Contrapartes -----------------------------------------------------------------------


class _RucPair(_Strict):
    ruc: Ruc | None = None
    ruc_check_digit: RucCheckDigit | None = None

    @model_validator(mode="after")
    def _ruc_pair(self) -> "_RucPair":
        if (self.ruc is None) != (self.ruc_check_digit is None):
            raise ValueError("El RUC y su dígito verificador van juntos.")
        if self.ruc is not None and ruc_check_digit(self.ruc) != int(self.ruc_check_digit or -1):
            raise ValueError("El dígito verificador no corresponde a ese RUC.")
        return self


class CounterpartyCreate(_RucPair):
    name: CounterpartyName
    kind: CounterpartyKind
    notes: Notes | None = None


class CounterpartyUpdate(_RucPair):
    name: CounterpartyName | None = None
    kind: CounterpartyKind | None = None
    notes: Notes | None = None
    archived: bool | None = None


class CounterpartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    context_id: uuid.UUID
    name: str
    ruc: str | None
    ruc_check_digit: str | None
    kind: str
    notes: str | None
    archived_at: datetime | None
    created_at: datetime


# --- Movimientos ------------------------------------------------------------------------


class TransactionCreate(_Strict):
    account_id: uuid.UUID
    booked_on: date
    amount: AmountIn
    description: Description
    reference: Reference | None = None
    category_id: uuid.UUID | None = None
    counterparty_id: uuid.UUID | None = None


class TransactionUpdate(_Strict):
    category_id: uuid.UUID | None = None
    counterparty_id: uuid.UUID | None = None
    description: Description | None = None
    reference: Reference | None = None
    reviewed: bool | None = None
    # Solo movimientos manuales, no anulados y que no sean parte de una transferencia.
    booked_on: date | None = None
    amount: AmountIn | None = None
    account_id: uuid.UUID | None = None


class VoidRequest(_Strict):
    reason: VoidReason


class TransactionOut(BaseModel):
    id: uuid.UUID
    context_id: uuid.UUID
    account_id: uuid.UUID
    currency: str
    booked_on: date
    amount: str
    description: str
    reference: str | None
    category_id: uuid.UUID | None
    counterparty_id: uuid.UUID | None
    source: str
    import_batch_id: uuid.UUID | None
    transfer_group_id: uuid.UUID | None
    reviewed_at: datetime | None
    voided_at: datetime | None
    voided_by: uuid.UUID | None
    void_reason: str | None
    created_by: uuid.UUID
    created_at: datetime


class TransferCreate(_Strict):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    booked_on: date
    # Magnitudes positivas: sale `amount_out` de una cuenta y entra `amount_in` en la otra.
    amount_out: AmountIn
    amount_in: AmountIn
    description: Description
    reference: Reference | None = None


class TransferOut(BaseModel):
    transfer_group_id: uuid.UUID
    outgoing: TransactionOut
    incoming: TransactionOut


# --- Importación ------------------------------------------------------------------------


class ImportRowOut(BaseModel):
    row_number: int
    raw: dict[str, Any]
    booked_on: date | None
    amount: str | None
    description: str | None
    reference: str | None
    error: str | None
    duplicate_of: uuid.UUID | None
    duplicate_in_file: int | None
    decision: str


class ImportBatchOut(BaseModel):
    id: uuid.UUID
    context_id: uuid.UUID
    account_id: uuid.UUID
    currency: str
    filename: str
    file_sha256: str
    file_format: str
    mapping: dict[str, Any]
    status: str
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_error: int
    created_by: uuid.UUID
    created_at: datetime
    committed_at: datetime | None
    # Presente al analizar y al consultar un lote; ausente en los listados.
    rows: list[ImportRowOut] | None = None


class RowDecisionUpdate(_Strict):
    decision: Decision


# --- Resúmenes --------------------------------------------------------------------------


class AccountBalanceOut(BaseModel):
    account_id: uuid.UUID
    name: str
    currency: str
    balance: str
    archived: bool


class CurrencyTotalsOut(BaseModel):
    currency: str
    income: str
    expense: str
    net: str


class MonthTotalsOut(CurrencyTotalsOut):
    month: str  # "2026-03"


class CategoryExpenseOut(BaseModel):
    currency: str
    category_id: uuid.UUID | None
    category_name: str
    amount: str


class SummaryOut(BaseModel):
    context_id: uuid.UUID
    date_from: date
    date_to: date
    balances: list[AccountBalanceOut]
    totals: list[CurrencyTotalsOut]
    by_month: list[MonthTotalsOut]
    expenses_by_category: list[CategoryExpenseOut]


class ContextTotalsOut(CurrencyTotalsOut):
    balance: str


class ConsolidatedContextOut(BaseModel):
    context: ContextOut
    totals: list[ContextTotalsOut]


class ConsolidatedOut(BaseModel):
    date_from: date
    date_to: date
    contexts: list[ConsolidatedContextOut]
