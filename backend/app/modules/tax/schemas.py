"""Esquemas de entrada y salida de la API de tributación (`/api/v1/tax`).

Importes: en JSON siempre son **string** (D-095): la entrada rechaza números JSON y la
salida es texto (`"150000"`). Las cotizaciones, como en contabilidad (hasta 6 decimales).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.accounting.schemas import (
    ProfessionalReference,
    RateIn,
    Reason,
)
from app.modules.finance.schemas import AmountIn, Currency

Direction = Literal["purchase", "sale"]
VoucherType = Literal["invoice", "credit_note", "debit_note"]
DocType = Literal[
    "ruc", "identity_card", "passport", "foreign_id", "unnamed", "diplomatic", "tax_id"
]
Condition = Literal["cash", "credit"]
IreRegime = Literal["ire_general", "ire_simple", "unknown"]
RuleStatus = Literal["pending", "verified", "deprecated"]
HolidayStatus = Literal["pending", "verified"]
ObligationStatus = Literal["pending", "filed", "paid", "not_applicable", "overdue"]

Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Url = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=1000)]
Name150 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
Name200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Timbrado = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{8}$")]
VoucherNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{3}-[0-9]{3}-[0-9]{7}$")
]
Cdc = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{44}$")]
# RUC sin DV: hasta 8 dígitos, o un RUC antiguo terminado en letra (D-099, sin DV).
RucText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[0-9]{1,8}[A-Za-z]?$"),
]
CheckDigit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]
DocumentText = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9A-Za-z.\-/ ]{1,20}$")
]
DnitCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{1,4}$")]
FilingReference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReasonIn(_Strict):
    reason: Reason


class RuleApplied(BaseModel):
    id: uuid.UUID
    code: str
    version: int
    validation_status: str
    legal_reference: str | None


# --- Reglas ---------------------------------------------------------------------------------


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    version: int
    description: str
    parameters: dict[str, Any]
    valid_from: date | None
    valid_to: date | None
    published_at: date | None
    source_url: str | None
    legal_reference: str | None
    consulted_at: date | None
    confidence: str | None
    notes: str | None
    validation_status: str
    reviewed_by_name: str | None
    reviewed_reference: str | None
    reviewed_at: datetime | None
    review_note: str | None
    deprecation_reason: str | None
    deprecated_at: datetime | None
    used_by_calculations: bool
    # D-120: si CONTADOR AI puede verificarla y, si no, por qué.
    verifiable: bool
    unverifiable_reason: str | None


class RuleVerifyIn(_Strict):
    """Verifica CONTADOR AI contra la fuente de la regla (D-120): sin nombre ni matrícula."""

    review_note: Text500 | None = None


class RuleLeftPending(BaseModel):
    id: uuid.UUID
    code: str
    version: int
    reason: str


class RuleBulkVerifyOut(BaseModel):
    verified: list[str]
    left_pending: list[RuleLeftPending]


class RuleLoadOut(BaseModel):
    created: int
    unchanged: int
    differing: list[str]
    rejected: list[dict[str, Any]]
    exceptions_created: int
    total: int


# --- Feriados y excepciones --------------------------------------------------------------


class HolidayIn(_Strict):
    day: date
    name: Name150
    source_url: Url | None = None
    legal_reference: Text300 | None = None
    notes: Text500 | None = None


class HolidayUpdate(_Strict):
    day: date | None = None
    name: Name150 | None = None
    source_url: Url | None = None
    legal_reference: Text300 | None = None
    notes: Text500 | None = None
    # Solo con `tax.verify`.
    validation_status: HolidayStatus | None = None


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day: date
    name: str
    source_url: str | None
    legal_reference: str | None
    validation_status: str
    origin: str
    notes: str | None


class HolidayLoadOut(BaseModel):
    created: int
    unchanged: int
    differing: list[dict[str, Any]]


class ExceptionIn(_Strict):
    obligation_code: str | None = None
    obligation_group: Literal["determinative"] | None = None
    due_month: date
    ruc_digits: list[Annotated[int, Field(ge=0, le=9)]] = Field(default_factory=list)
    new_due_date: date
    legal_reference: Text300
    source_url: Url | None = None
    notes: Text500 | None = None


class ExceptionUpdate(_Strict):
    obligation_code: str | None = None
    obligation_group: Literal["determinative"] | None = None
    due_month: date | None = None
    ruc_digits: list[Annotated[int, Field(ge=0, le=9)]] | None = None
    new_due_date: date | None = None
    legal_reference: Text300 | None = None
    source_url: Url | None = None
    is_active: bool | None = None
    notes: Text500 | None = None


class ExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    obligation_code: str | None
    obligation_group: str | None
    due_month: date
    ruc_digits: list[int]
    new_due_date: date
    legal_reference: str
    source_url: str | None
    rule_version_id: uuid.UUID | None
    origin: str
    is_active: bool
    notes: str | None


# --- Perfil -------------------------------------------------------------------------------


class ProfileObligationIn(_Strict):
    code: DnitCode
    registered_on: date


class ProfileIn(_Strict):
    valid_from: date
    ire_regime: IreRegime
    fiscal_close_month: int = Field(default=12, ge=1, le=12)
    vat_taxpayer: bool
    obligations: list[ProfileObligationIn] = Field(max_length=30)
    notes: Text500 | None = None


class ProfileVerifyIn(_Strict):
    """Verifica CONTADOR AI contra la constancia de RUC (D-120): número o fecha de la constancia."""

    verified_document_reference: ProfessionalReference


class ProfileObligationOut(BaseModel):
    code: str
    registered_on: date
    supported: bool


class ProfileVersionOut(BaseModel):
    id: uuid.UUID
    valid_from: date
    ire_regime: str
    fiscal_close_month: int
    vat_taxpayer: bool
    origin: str
    verified_by_name: str | None
    verified_license: str | None
    verified_document_reference: str | None
    verified_at: datetime | None
    notes: str | None
    obligations: list[ProfileObligationOut]


class ProfileOut(BaseModel):
    ruc: str | None
    ruc_check_digit: str | None
    current: ProfileVersionOut | None
    history: list[ProfileVersionOut]


# --- Obligaciones ---------------------------------------------------------------------


class SyncOut(BaseModel):
    created: int
    recalculated: int
    not_applicable: int
    reactivated: int
    profile_missing: bool
    unsupported_codes: list[str]
    without_rule: list[dict[str, Any]]


class ObligationOut(BaseModel):
    id: uuid.UUID
    code: str
    dnit_code: str
    period_start: date
    period_end: date
    nominal_due_date: date
    due_date: date
    remind_by: date
    shift_explanation: str | None
    status: str
    is_overdue: bool
    calculated_amount: str | None
    calculated_credit_balance: str | None
    filed_on: date | None
    filing_reference: str | None
    declared_amount: str | None
    declared_credit_balance: str | None
    paid_on: date | None
    paid_amount: str | None
    payment_transaction_id: uuid.UUID | None
    not_applicable_reason: str | None
    not_applicable_auto: bool
    reopen_reason: str | None
    exception: dict[str, Any] | None
    rules_applied: list[RuleApplied]
    rule_status: str | None


class FileIn(_Strict):
    filed_on: date
    filing_reference: FilingReference
    declared_amount: AmountIn | None = None
    declared_credit_balance: AmountIn | None = None


class PayIn(_Strict):
    paid_on: date
    paid_amount: AmountIn
    transaction_id: uuid.UUID | None = None


# --- Comprobantes ---------------------------------------------------------------------


class VoucherIn(_Strict):
    direction: Direction
    voucher_type: VoucherType = "invoice"
    is_electronic: bool = False
    cdc: Cdc | None = None
    timbrado: Timbrado
    number: VoucherNumber
    issued_on: date
    counterparty_doc_type: DocType = "ruc"
    counterparty_ruc: RucText | None = None
    counterparty_ruc_dv: CheckDigit | None = None
    counterparty_document: DocumentText | None = None
    counterparty_name: Name200 | None = None
    condition: Condition = "cash"
    currency: Currency = "PYG"
    fx_rate: RateIn | None = None
    foreign_total: AmountIn | None = None
    taxed_10: AmountIn | None = None
    taxed_5: AmountIn | None = None
    exempt: AmountIn | None = None
    vat_10: AmountIn | None = None
    vat_5: AmountIn | None = None
    imputes_vat: bool = True
    imputes_ire: bool = False
    imputes_irp: bool = False
    related_voucher_id: uuid.UUID | None = None
    finance_counterparty_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    notes: Text500 | None = None


class VoucherUpdate(_Strict):
    """Solo cambian los campos que llegan (la dirección no cambia)."""

    voucher_type: VoucherType | None = None
    is_electronic: bool | None = None
    cdc: Cdc | None = None
    timbrado: Timbrado | None = None
    number: VoucherNumber | None = None
    issued_on: date | None = None
    counterparty_doc_type: DocType | None = None
    counterparty_ruc: RucText | None = None
    counterparty_ruc_dv: CheckDigit | None = None
    counterparty_document: DocumentText | None = None
    counterparty_name: Name200 | None = None
    condition: Condition | None = None
    currency: Currency | None = None
    fx_rate: RateIn | None = None
    foreign_total: AmountIn | None = None
    taxed_10: AmountIn | None = None
    taxed_5: AmountIn | None = None
    exempt: AmountIn | None = None
    vat_10: AmountIn | None = None
    vat_5: AmountIn | None = None
    imputes_vat: bool | None = None
    imputes_ire: bool | None = None
    imputes_irp: bool | None = None
    related_voucher_id: uuid.UUID | None = None
    finance_counterparty_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    notes: Text500 | None = None


class VoucherOut(BaseModel):
    id: uuid.UUID
    direction: str
    voucher_type: str
    is_electronic: bool
    cdc: str | None
    timbrado: str
    number: str
    issued_on: date
    counterparty_doc_type: str
    counterparty_ruc: str | None
    counterparty_ruc_dv: str | None
    counterparty_document: str | None
    counterparty_name: str
    counterparty_review_required: bool
    condition: str
    currency: str
    fx_rate: str | None
    foreign_total: str | None
    taxed_10: str
    taxed_5: str
    exempt: str
    total: str
    vat_10: str
    vat_5: str
    imputes_vat: bool
    imputes_ire: bool
    imputes_irp: bool
    related_voucher_id: uuid.UUID | None
    finance_counterparty_id: uuid.UUID | None
    transaction_id: uuid.UUID | None
    journal_entry_id: uuid.UUID | None
    journal_entry_status: str | None
    period_confirmed: bool
    notes: str | None
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime
    rules_applied: list[RuleApplied]
    rule_status: str | None


class ProposeEntryIn(_Strict):
    account_id: uuid.UUID
    counterpart_account_id: uuid.UUID | None = None
    description: Text500 | None = None


# --- Configuración --------------------------------------------------------------------


class SettingsIn(_Strict):
    vat_credit_10_account_id: uuid.UUID | None = None
    vat_credit_5_account_id: uuid.UUID | None = None
    vat_debit_10_account_id: uuid.UUID | None = None
    vat_debit_5_account_id: uuid.UUID | None = None
    suppliers_account_id: uuid.UUID | None = None
    customers_account_id: uuid.UUID | None = None
    alert_days: int | None = Field(default=None, ge=1, le=60)


class SettingsAccountOut(BaseModel):
    field: str
    label: str
    default_code: str
    configured_id: uuid.UUID | None
    effective_id: uuid.UUID | None
    effective_code: str | None
    effective_name: str | None


class SettingsOut(BaseModel):
    accounts: list[SettingsAccountOut]
    alert_days: int
