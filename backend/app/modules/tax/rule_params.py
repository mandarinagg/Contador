"""Esquemas de los `parameters` de cada regla que usa el sistema (D-084, D-085).

Una versión cuyo `parameters` no cumple su esquema no se carga. Los esquemas no aceptan
claves de más (`extra="forbid"`): si la investigación cambia la forma de una regla, la
carga falla y alguien tiene que mirarla, en lugar de usar un dato a medias.

Los números con decimales del YAML (tasas) llegan como `float` de PyYAML o de JSON; antes de
validar se convierten a `Decimal` desde su texto (`Decimal(repr(x))`, `0.1` → `Decimal("0.1")`),
así ningún cálculo usa `float`.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DIGITS = tuple(str(d) for d in range(10))
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

DayRuleCode = Literal["CAL-PERPETUO-DJ", "CAL-PERPETUO-DJI"]


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _all_digits(value: dict[str, Any]) -> dict[str, Any]:
    if tuple(sorted(value)) != DIGITS:
        raise ValueError("Tiene que traer las diez terminaciones del RUC, de 0 a 9.")
    return value


class CalendarParams(_Params):
    """`CAL-PERPETUO-DJ` y `CAL-PERPETUO-DJI`: día del mes por terminación del RUC."""

    key: Literal["ultimo_digito_ruc_sin_dv"]
    day_by_digit: dict[str, int]
    # Solo la trae la DJ; la DJI corre igual los inhábiles (RG 38/2020, D-086).
    non_business_day_shift: Literal["next_business_day"] | None = None

    @field_validator("day_by_digit")
    @classmethod
    def _days(cls, value: dict[str, int]) -> dict[str, int]:
        _all_digits(value)
        if any(not 1 <= day <= 28 for day in value.values()):
            raise ValueError("Los días van de 1 a 28 (existen en todos los meses).")
        return value


class ExceptionParams(_Params):
    """`CAL-EXCEPCION-*`: fecha nueva por terminación para los vencimientos de un mes."""

    month: str
    new_date_by_digit: dict[str, date]
    excludes: list[str] = Field(default_factory=list)

    @field_validator("month")
    @classmethod
    def _month(cls, value: str) -> str:
        if not _MONTH.match(value):
            raise ValueError("El mes va como AAAA-MM.")
        return value

    @field_validator("new_date_by_digit")
    @classmethod
    def _dates(cls, value: dict[str, date]) -> dict[str, date]:
        return _all_digits(value)

    @property
    def due_month(self) -> date:
        year, month = self.month.split("-")
        return date(int(year), int(month), 1)


class VatRatesParams(_Params):
    """`IVA-GENERAL-TASAS`: tasas del IVA (tasa sobre la base, el IVA va incluido)."""

    general_rate: Decimal = Field(gt=0, lt=1)
    reduced_rate: Decimal = Field(gt=0, lt=1)
    reduced_rate_cases_ref: str | None = None


class MonthlyDue(_Params):
    month_offset: int = Field(ge=1, le=12)
    day_rule: DayRuleCode


class AnnualDue(_Params):
    months_after_fiscal_close: int = Field(ge=1, le=12)
    day_rule: DayRuleCode


class FixedDayDue(_Params):
    """Día fijo del mes, igual para todas las terminaciones del RUC (RESIMPLE: el 26 de
    febrero, RG 61/2020, art. 12). Si cae en un día inhábil se corre como cualquier otro
    vencimiento calculado (D-086); que la norma lo corra no está verificado (D-PF-8)."""

    months_after_fiscal_close: int = Field(ge=1, le=12)
    fixed_day: int = Field(ge=1, le=28)


class VatFilingParams(_Params):
    """`IVA-GENERAL-LIQUIDACION` (obligación 211, Formulario 120)."""

    obligation_code: Literal[211]
    form: str
    periodicity: Literal["monthly"]
    due: MonthlyDue
    file_even_if_zero: bool


class VoucherRegisterParams(_Params):
    """`REG-COMPROB-MENSUAL` (obligación 955, RG 90/2021)."""

    obligation_code: Literal[955]
    linked_obligation: int
    periodicity: Literal["monthly"]
    due: MonthlyDue
    confirm_even_if_zero: bool


class IreGeneralParams(_Params):
    """`IRE-GENERAL-DJ` (obligación 700, Formulario 500)."""

    obligation_code: Literal[700]
    form: str
    periodicity: Literal["annual"]
    due: AnnualDue
    file_even_if_zero: bool


class IreSimpleParams(_Params):
    """`IRE-SIMPLE-DJ` (obligación 701, Formulario 501)."""

    obligation_code: Literal[701]
    form: str
    periodicity: Literal["annual"]
    due: AnnualDue
    max_prior_year_income_pyg: int = Field(gt=0)
    presumed_net_income_pct_of_gross: Decimal = Field(gt=0, lt=1)
    rate: Decimal = Field(gt=0, lt=1)
    loss_carryforward: bool
    excluded_if: list[str]


class FinancialStatementsParams(_Params):
    """`EEFF-PRESENTACION` (obligación 948)."""

    obligation_code: Literal[948]
    periodicity: Literal["annual"]
    due: AnnualDue
    model: str
    applies_to: list[str]


class RateBracket(_Params):
    up_to_pyg: int | None = Field(default=..., gt=0)
    rate: Decimal = Field(gt=0, lt=1)


class HousingLossCarryforward(_Params):
    years: int = Field(ge=1)
    max_pct_of_net_income: Decimal = Field(gt=0, lt=1)


class VoucherRegisterByVat(_Params):
    without_vat: Literal[956]
    with_vat: Literal[955]


class IrpServicesParams(_Params):
    """`IRP-RSP-DJ` (obligación 715, Formulario 515): ejercicio = año civil (Ley 6380, art. 52)."""

    obligation_code: Literal[715]
    form: str
    periodicity: Literal["annual"]
    fiscal_year: Literal["calendar"]
    due: AnnualDue
    file_even_if_zero: bool
    not_reached_amount_pyg: int = Field(gt=0)
    registration_deadline_business_days: int = Field(gt=0)
    rate_brackets: list[RateBracket] = Field(min_length=1)
    cease_after_consecutive_years_not_reached: int = Field(ge=1)
    donations_cap_pct_of_gross: Decimal = Field(gt=0, lt=1)
    loss_carryforward: bool
    housing_loss_carryforward: HousingLossCarryforward
    voucher_register: VoucherRegisterByVat


class PresumedNetIncome(_Params):
    sale_pct_of_price: Decimal = Field(gt=0, lt=1)
    rental_pct_of_price: Decimal = Field(gt=0, lt=1)


class EconomicActivity(_Params):
    default: str
    rentals: str


class IrpCapitalParams(_Params):
    """`IRP-RGC-DJ` (obligación 716, Formulario 516): ejercicio = año civil."""

    obligation_code: Literal[716]
    form: str
    periodicity: Literal["annual"]
    fiscal_year: Literal["calendar"]
    due: AnnualDue
    file_even_if_zero: bool | None
    rate: Decimal = Field(gt=0, lt=1)
    presumed_net_income: PresumedNetIncome
    rental_base_excludes_vat: bool
    rental_base: str
    excluded: list[str]
    exempt_movable_sales_up_to_pyg: int = Field(gt=0)
    registration_deadline_business_days: int = Field(gt=0)
    economic_activity: EconomicActivity


class AnnualVoucherRegisterParams(_Params):
    """`REG-COMPROB-ANUAL` (obligación 956, RG 90/2021, art. 7° según la RG DNIT 12/2024)."""

    obligation_code: Literal[956]
    linked_obligation: int
    periodicity: Literal["annual"]
    due: AnnualDue
    confirm_even_if_zero: bool
    replaced_by_if_also_obligation: dict[str, int]
    file_name_pattern: str
    spec_file: str


class QuarterlyPayments(_Params):
    months: list[int] = Field(min_length=1)
    day_rule: DayRuleCode
    frequency: Literal["quarterly"]


class FeeBracket(_Params):
    up_to_pyg: int = Field(gt=0)
    monthly_pyg: int = Field(gt=0)


class IfNotFiled(_Params):
    generated_by_dnit_on: str
    assumed_income_up_to_pyg: int = Field(gt=0)


class IreResimpleParams(_Params):
    """`IRE-RESIMPLE-DJ` (obligación 702, Formulario 502): DJ informativa con día fijo.

    El calendario genera solo la declaración jurada; las cuotas trimestrales (`payments`)
    todavía no (D-PF-9)."""

    obligation_code: Literal[702]
    form: str
    periodicity: Literal["annual"]
    fiscal_year: Literal["calendar"]
    due: FixedDayDue
    payments: QuarterlyPayments
    max_prior_year_income_pyg: int = Field(gt=0)
    monthly_fee_by_prior_year_income: list[FeeBracket] = Field(min_length=1)
    if_not_filed: IfNotFiled
    vat_taxpayer: Literal[False]
    advances: bool
    withholdings: bool
    applies_to: list[str]
    excluded_if: list[str]
    sales_voucher_type: int


SCHEMAS: dict[str, type[_Params]] = {
    "CAL-PERPETUO-DJ": CalendarParams,
    "CAL-PERPETUO-DJI": CalendarParams,
    "IVA-GENERAL-TASAS": VatRatesParams,
    "IVA-GENERAL-LIQUIDACION": VatFilingParams,
    "REG-COMPROB-MENSUAL": VoucherRegisterParams,
    "IRE-GENERAL-DJ": IreGeneralParams,
    "IRE-SIMPLE-DJ": IreSimpleParams,
    "EEFF-PRESENTACION": FinancialStatementsParams,
    "IRP-RSP-DJ": IrpServicesParams,
    "IRP-RGC-DJ": IrpCapitalParams,
    "REG-COMPROB-ANUAL": AnnualVoucherRegisterParams,
    "IRE-RESIMPLE-DJ": IreResimpleParams,
}
EXCEPTION_PREFIX = "CAL-EXCEPCION-"

# Reglas que generan obligaciones, con el código DNIT que cada esquema exige.
OBLIGATION_RULES: dict[str, str] = {
    "IVA-GENERAL-LIQUIDACION": "211",
    "REG-COMPROB-MENSUAL": "955",
    "IRE-GENERAL-DJ": "700",
    "IRE-SIMPLE-DJ": "701",
    "EEFF-PRESENTACION": "948",
    "IRP-RSP-DJ": "715",
    "IRP-RGC-DJ": "716",
    "REG-COMPROB-ANUAL": "956",
    "IRE-RESIMPLE-DJ": "702",
}
RULE_BY_DNIT_CODE: dict[str, str] = {dnit: code for code, dnit in OBLIGATION_RULES.items()}
MONTHLY_RULES = frozenset({"IVA-GENERAL-LIQUIDACION", "REG-COMPROB-MENSUAL"})
# Las «determinativas» de la excepción de grupo (D-086): las que vencen por el calendario
# de las declaraciones juradas determinativas.
DETERMINATIVE_RULES = frozenset(
    {"IVA-GENERAL-LIQUIDACION", "IRE-GENERAL-DJ", "IRE-SIMPLE-DJ", "IRP-RSP-DJ", "IRP-RGC-DJ"}
)


def schema_for(code: str) -> type[_Params] | None:
    if code.startswith(EXCEPTION_PREFIX):
        return ExceptionParams
    return SCHEMAS.get(code)


def due_of(params: _Params) -> MonthlyDue | AnnualDue | FixedDayDue:
    """Cómo vence una obligación (los esquemas de las reglas de obligaciones lo traen)."""
    due = getattr(params, "due", None)  # no todos los esquemas lo tienen
    if not isinstance(due, MonthlyDue | AnnualDue | FixedDayDue):
        raise TypeError("La regla no define un vencimiento.")
    return due


def exact(value: Any) -> Any:
    """Copia con los `float` pasados a `Decimal` desde su texto (nunca se calcula con float)."""
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, dict):
        return {k: exact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [exact(v) for v in value]
    return value


def as_text(value: Any) -> Any:
    """Copia para la API: los números con decimales van como texto (D-095, nunca float)."""
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    if isinstance(value, dict):
        return {k: as_text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_text(v) for v in value]
    return value


def parse(code: str, parameters: dict[str, Any]) -> _Params | None:
    """Parámetros validados de la regla, o `None` si el código no tiene esquema (no se usa)."""
    schema = schema_for(code)
    if schema is None:
        return None
    return schema.model_validate(exact(parameters))


def errors(code: str, parameters: Any) -> list[str]:
    """Errores de validación legibles (lista vacía si los parámetros son válidos)."""
    if not isinstance(parameters, dict):
        return ["`parameters` tiene que ser un objeto."]
    try:
        parse(code, parameters)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in error['loc']) or 'parameters'}: {error['msg']}"
            for error in exc.errors()
        ]
    return []
