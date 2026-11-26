"""Registro de comprobantes de compras y ventas (D-088, D-089, BR-TAX-07/08/09).

Validaciones (el servicio da el error legible; la base vuelve a validar lo esencial):
- timbrado de 8 dígitos, número `EEE-PPP-NNNNNNN`, fecha;
- contraparte: en compras, RUC con su dígito verificador módulo 11 (D-088; algoritmo de
  `app/modules/organizations/ruc.py`, port del proyecto de facturación SIFEN); en ventas,
  RUC, cédula, documento extranjero o «sin nombre»;
- electrónicos: CDC de 44 dígitos con su DV módulo 11, y coherente con el comprobante
  (RUC y DV del emisor, establecimiento, punto, número, fecha y, en facturas y notas de
  crédito, el tipo de documento: 01 y 05). Estructura del CDC: Manual Técnico SIFEN v150,
  §10.1, tal como la arma `buildCdc` del proyecto de facturación
  (`facturacion-sifen-zestia/apps/api/src/invoicing/sifen/codes.ts`);
- importes en guaraníes enteros, con IVA incluido, como en la factura. El IVA se calcula con
  la regla `IVA-GENERAL-TASAS` vigente a la fecha del comprobante (BR-TAX-09): importe por
  tasa / (1 + tasa) (10 % → /11, 5 % → /21), redondeado al guaraní más cercano con las
  mitades hacia arriba. Se acepta el IVA impreso si difiere en ±1 ₲ y se guarda el impreso;
  ±2 o más se rechaza;
- en otra moneda (D-041): cotización y total en la moneda original; el total en guaraníes
  tiene que ser el producto exacto redondeado hacia abajo o hacia arriba;
- una nota de crédito o de débito referencia una factura viva de la misma contraparte y
  dirección; las notas de crédito vivas de una factura no superan su total;
- contraparte y movimiento de finanzas: solo del contexto de la empresa (un movimiento
  personal no existe para la tributación, D-024);
- duplicados (BR-TAX-07): no hay dos vivos con el mismo tipo, RUC (en compras), timbrado y
  número (D-099);
- mes confirmado (D-089): con el `REG-COMPROB-MENSUAL` del mes presentado, sus
  comprobantes no se crean, modifican ni anulan;
- con asiento vivo (D-091), el comprobante no se modifica ni se anula: primero se descarta o
  se revierte el asiento.

INGRESOS y EGRESOS del IRP-RSP (D-143, `_validated_register`): los tipos 201 a 211 de la Tabla 4
del formato oficial, sin timbrado ni IVA, solo si el perfil vigente al cierre del año incluye
la 956 (la misma regla que genera la obligación). Cada tipo pide sus columnas (número salvo en
205 a 208, período en 206 y 208, cuenta y banco en 207 y 211, empleador en 206, descripción en
209 y 210, comprobante asociado en 201 y 203) y rechaza las que no usa. Anti duplicado: tipo,
contraparte, cuenta y número; sin número, la fecha o el período (y el empleador en 206). El
registro anual confirmado bloquea su año, como el mensual su mes.
"""

import math
import re
import uuid
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from fractions import Fraction
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting.finance_link import business_transaction
from app.modules.accounting.models import JournalEntry
from app.modules.finance.models import Counterparty, FinancialContext
from app.modules.finance.money import CURRENCY_DECIMALS, AmountError, check_amount
from app.modules.finance.service import escape_like
from app.modules.organizations.models import Organization
from app.modules.organizations.ruc import ruc_check_digit
from app.modules.tax import profile as profiles
from app.modules.tax import rule_params, rules
from app.modules.tax.common import (
    ZERO,
    apply_changes,
    flush_translated,
    month_end,
    month_start,
    now,
    record,
    snapshot,
)
from app.modules.tax.models import (
    ACCOUNT_TYPES,
    CREDIT_TYPES,
    DESCRIBED_TYPES,
    DOCUMENT_TYPES,
    EXPENSE_TYPES,
    INCOME_TYPES,
    NO_COUNTERPARTY_TYPES,
    PERIOD_TYPES,
    REGISTER_DIRECTIONS,
    TIMBRADO_TYPES,
    UNNUMBERED,
    Obligation,
    RuleVersion,
    Voucher,
)

VAT_RULE = "IVA-GENERAL-TASAS"
REGISTER_RULE = "REG-COMPROB-MENSUAL"
ANNUAL_REGISTER_RULE = "REG-COMPROB-ANUAL"
ANNUAL_REGISTER = "956"
REGISTER_MIN_DATE = date(2021, 1, 1)
IPS_NAME = "Instituto de Previsión Social"
VAT_TOLERANCE = Decimal(1)
UNNAMED = "Sin nombre"
CDC_DOCUMENT_TYPES = {"invoice": "01", "credit_note": "05"}

# Columnas propias de INGRESOS y EGRESOS (D-143).
REGISTER_FIELDS = (
    "account_number",
    "bank_name",
    "ips_employer_number",
    "document_description",
    "related_number",
    "related_timbrado",
)
FIELD_LABELS = {
    "account_number": "el número de cuenta o tarjeta",
    "bank_name": "el banco, financiera o cooperativa",
    "ips_employer_number": "el número de empleador en IPS",
    "document_description": "qué tipo de documento es",
    "related_number": "el número del comprobante asociado",
    "related_timbrado": "el timbrado del comprobante asociado",
    "timbrado": "el timbrado",
    "cdc": "el CDC",
    "related_voucher_id": "la factura que corrige",
}
FIELDS = (
    "direction",
    "voucher_type",
    "is_electronic",
    "cdc",
    "timbrado",
    "number",
    "issued_on",
    "counterparty_doc_type",
    "counterparty_ruc",
    "counterparty_ruc_dv",
    "counterparty_document",
    "counterparty_name",
    "condition",
    "currency",
    "fx_rate",
    "foreign_total",
    "taxed_10",
    "taxed_5",
    "exempt",
    "vat_10",
    "vat_5",
    "imputes_vat",
    "imputes_ire",
    "imputes_irp",
    "related_voucher_id",
    "finance_counterparty_id",
    "transaction_id",
    "notes",
    *REGISTER_FIELDS,
)
# Con asiento vivo solo cambian estos (no alteran lo que contabilizó el asiento).
EDITABLE_WITH_ENTRY = frozenset({"notes", "finance_counterparty_id"})
LIVE = ("draft", "posted")


def voucher_not_found() -> NotFound:
    return NotFound("VOUCHER_NOT_FOUND", "El comprobante no existe.")


def total_of(voucher: Voucher) -> Decimal:
    return voucher.taxed_10 + voucher.taxed_5 + voucher.exempt


def included_vat(amount: Decimal, rate: Decimal) -> Decimal:
    """IVA incluido en `amount` a la tasa `rate`, al guaraní más cercano (mitades arriba)."""
    exact = Fraction(amount) * Fraction(rate) / (1 + Fraction(rate))
    return Decimal(math.floor(exact + Fraction(1, 2)))


def vat_rates(rule: RuleVersion) -> rule_params.VatRatesParams:
    params = rule_params.parse(rule.code, rule.parameters)
    assert isinstance(params, rule_params.VatRatesParams)
    return params


def business_context(db: Session, organization_id: uuid.UUID) -> FinancialContext:
    ctx = db.scalar(
        select(FinancialContext).where(
            FinancialContext.organization_id == organization_id,
            FinancialContext.kind == "business",
        )
    )
    if ctx is None:  # pragma: no cover - la configuración inicial lo crea
        raise NotFound("CONTEXT_NOT_FOUND", "La organización no tiene finanzas de la empresa.")
    return ctx


def get_voucher(
    db: Session, organization_id: uuid.UUID, voucher_id: uuid.UUID, *, lock: bool = False
) -> Voucher:
    query = select(Voucher).where(
        Voucher.id == voucher_id, Voucher.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    voucher = db.scalar(query)
    if voucher is None:
        raise voucher_not_found()
    return voucher


def month_confirmed(db: Session, organization_id: uuid.UUID, day: date) -> bool:
    status = db.scalar(
        select(Obligation.status).where(
            Obligation.organization_id == organization_id,
            Obligation.code == REGISTER_RULE,
            Obligation.period_start == month_start(day),
        )
    )
    return status in ("filed", "paid")


def confirmed_months(db: Session, organization_id: uuid.UUID, months: set[date]) -> set[date]:
    if not months:
        return set()
    return set(
        db.scalars(
            select(Obligation.period_start).where(
                Obligation.organization_id == organization_id,
                Obligation.code == REGISTER_RULE,
                Obligation.period_start.in_(months),
                Obligation.status.in_(("filed", "paid")),
            )
        )
    )


def confirmed_years(db: Session, organization_id: uuid.UUID, years: set[int]) -> set[int]:
    """Años con el registro anual (956) presentado: bloquea sus comprobantes (D-143)."""
    if not years:
        return set()
    starts = db.scalars(
        select(Obligation.period_start).where(
            Obligation.organization_id == organization_id,
            Obligation.code == ANNUAL_REGISTER_RULE,
            Obligation.period_start.in_({date(y, 1, 1) for y in years}),
            Obligation.status.in_(("filed", "paid")),
        )
    )
    return {start.year for start in starts}


def _check_not_confirmed(db: Session, organization_id: uuid.UUID, *days: date) -> None:
    for day in {month_start(d) for d in days}:
        if month_confirmed(db, organization_id, day):
            raise Conflict(
                "PERIOD_CONFIRMED",
                f"El registro de comprobantes de {day:%m/%Y} está confirmado: para cambiar sus "
                "comprobantes, reabrí primero la obligación del registro (con motivo).",
                details={"month": day.isoformat()},
            )
    years = sorted(confirmed_years(db, organization_id, {d.year for d in days}))
    if years:
        raise Conflict(
            "PERIOD_CONFIRMED",
            f"El registro anual de comprobantes (956) de {years[0]} está confirmado: para "
            "cambiar sus comprobantes, reabrí primero la obligación del registro (con motivo).",
            details={"year": years[0]},
        )


def annual_register_applies(db: Session, organization_id: uuid.UUID, year: int) -> bool:
    """Si el año lleva el registro anual (956): el perfil vigente al cierre la incluye, con el
    alta a esa fecha. Es la misma regla que genera la obligación (D-087, D-142)."""
    end = date(year, 12, 31)
    current = profiles.vigente(profiles.versions(db, organization_id), end)
    return current is not None and any(
        o.code == ANNUAL_REGISTER and o.registered_on <= end for o in current.obligations
    )


def live_entry(db: Session, voucher: Voucher) -> JournalEntry | None:
    if voucher.journal_entry_id is None:
        return None
    entry = db.get(JournalEntry, voucher.journal_entry_id)
    return entry if entry is not None and entry.status in LIVE else None


def _check_no_live_entry(db: Session, voucher: Voucher, action: str) -> None:
    entry = live_entry(db, voucher)
    if entry is not None:
        what = "un borrador" if entry.status == "draft" else f"el asiento N° {entry.number}"
        raise Conflict(
            "VOUCHER_HAS_ENTRY",
            f"El comprobante tiene {what}: descartalo o revertilo antes de {action} el "
            "comprobante.",
            details={"entry_id": str(entry.id), "number": entry.number, "status": entry.status},
        )


def _pyg(value: Any, label: str) -> Decimal:
    try:
        amount = check_amount(Decimal(value), "PYG")
    except AmountError as exc:
        raise AppError("INVALID_AMOUNT", f"{label}: {exc}", status_code=422) from exc
    if amount < 0:
        raise AppError("INVALID_AMOUNT", f"{label}: va en positivo.", status_code=422)
    return amount.quantize(Decimal(1))


_RUC_NUMERIC = re.compile(r"^[0-9]{1,8}$")
_RUC_LEGACY = re.compile(r"^[0-9]{1,8}[A-Z]$")


def legacy_ruc(ruc: str | None) -> bool:
    """RUC antiguo terminado en letra (D-F4-10): se acepta sin DV y queda a revisar (D-099)."""
    return ruc is not None and _RUC_LEGACY.match(ruc) is not None


def _check_counterparty(data: dict[str, Any]) -> None:
    doc_type = data["counterparty_doc_type"]
    if data["direction"] == "purchase" and doc_type != "ruc":
        raise AppError(
            "COUNTERPARTY_RUC_REQUIRED",
            "En una compra el proveedor va con su RUC y dígito verificador.",
            status_code=422,
        )
    if doc_type == "ruc":
        ruc = (data.get("counterparty_ruc") or "").strip().upper()
        dv = data.get("counterparty_ruc_dv")
        data["counterparty_ruc"] = ruc or None
        data["counterparty_document"] = None
        if legacy_ruc(ruc):
            # Sin DV que validar: se guarda tal cual y la respuesta lo marca para revisar.
            data["counterparty_ruc_dv"] = None
        elif not _RUC_NUMERIC.match(ruc) or dv is None:
            raise AppError(
                "COUNTERPARTY_RUC_REQUIRED",
                "Indicá el RUC de la contraparte (hasta 8 dígitos, sin el DV) y su dígito "
                "verificador.",
                status_code=422,
            )
        elif ruc_check_digit(ruc) != int(dv):
            raise AppError(
                "RUC_CHECK_DIGIT_INVALID",
                f"El dígito verificador {dv} no corresponde al RUC {ruc} (debería ser "
                f"{ruc_check_digit(ruc)}).",
                status_code=422,
            )
    else:
        data["counterparty_ruc"] = data["counterparty_ruc_dv"] = None
        if doc_type in DOCUMENT_TYPES:
            if not data.get("counterparty_document"):
                raise AppError(
                    "COUNTERPARTY_DOCUMENT_REQUIRED",
                    "Indicá el número de documento de la contraparte.",
                    status_code=422,
                )
        else:
            data["counterparty_document"] = None
            data["counterparty_name"] = data.get("counterparty_name") or UNNAMED
    if not data.get("counterparty_name"):
        raise AppError(
            "COUNTERPARTY_NAME_REQUIRED",
            "Indicá el nombre o la razón social de la contraparte.",
            status_code=422,
        )


def _check_cdc(data: dict[str, Any], org: Organization) -> None:
    cdc = data.get("cdc")
    if not data["is_electronic"]:
        if cdc is not None:
            raise AppError(
                "CDC_NOT_APPLICABLE",
                "Solo los comprobantes electrónicos llevan CDC.",
                status_code=422,
            )
        return
    if cdc is None:
        raise AppError(
            "CDC_REQUIRED",
            "Un comprobante electrónico lleva su CDC (los 44 dígitos del KuDE).",
            status_code=422,
        )
    if ruc_check_digit(cdc[:43]) != int(cdc[43]):
        raise AppError(
            "CDC_CHECK_DIGIT_INVALID",
            "El dígito verificador del CDC no corresponde: revisá los 44 dígitos.",
            status_code=422,
        )
    if data["direction"] == "purchase":
        emitter, emitter_dv = data["counterparty_ruc"], data["counterparty_ruc_dv"]
    else:
        emitter, emitter_dv = org.ruc, org.ruc_check_digit
    problems: list[str] = []
    if legacy_ruc(emitter):
        problems.append("el RUC del emisor (el RUC con letra no puede figurar en un CDC)")
    elif emitter is not None and (cdc[2:10] != emitter.zfill(8) or cdc[10] != emitter_dv):
        problems.append("el RUC del emisor")
    establishment, point, number = data["number"].split("-")
    if cdc[11:14] != establishment or cdc[14:17] != point or cdc[17:24] != number:
        problems.append("el número")
    if cdc[25:33] != data["issued_on"].strftime("%Y%m%d"):
        problems.append("la fecha de emisión")
    expected_type = CDC_DOCUMENT_TYPES.get(data["voucher_type"])
    if expected_type is not None and cdc[:2] != expected_type:
        problems.append("el tipo de documento")
    if problems:
        raise AppError(
            "CDC_MISMATCH",
            "El CDC no coincide con " + ", ".join(problems) + " del comprobante.",
            details={"fields": problems},
            status_code=422,
        )


def _check_currency(data: dict[str, Any], total: Decimal) -> None:
    currency = data["currency"]
    if currency == "PYG":
        if data.get("fx_rate") is not None or data.get("foreign_total") is not None:
            raise AppError(
                "FX_NOT_APPLICABLE",
                "Un comprobante en guaraníes no lleva cotización ni total en otra moneda.",
                status_code=422,
            )
        return
    rate, foreign = data.get("fx_rate"), data.get("foreign_total")
    if rate is None or foreign is None:
        raise AppError(
            "FX_RATE_REQUIRED",
            f"El comprobante es en {currency}: indicá la cotización (`fx_rate`) y el total en "
            f"{currency} (`foreign_total`). Los importes se cargan en guaraníes.",
            status_code=422,
        )
    if rate <= 0:
        raise AppError("INVALID_AMOUNT", "La cotización va en positivo.", status_code=422)
    try:
        foreign = check_amount(foreign, currency, allow_zero=False)
    except AmountError as exc:
        raise AppError("INVALID_AMOUNT", f"Total en {currency}: {exc}", status_code=422) from exc
    if foreign <= 0:
        raise AppError("INVALID_AMOUNT", "El total en otra moneda va en positivo.", status_code=422)
    data["foreign_total"] = foreign
    with localcontext() as context:
        context.prec = 60
        exact = foreign * rate
        floor = exact.to_integral_value(rounding=ROUND_FLOOR)
        ceil = exact.to_integral_value(rounding=ROUND_CEILING)
    if total not in (floor, ceil):
        decimals = CURRENCY_DECIMALS[currency]
        raise AppError(
            "FX_TOTAL_MISMATCH",
            f"{foreign:.{decimals}f} {currency} por {rate:f} = {exact:f} guaraníes: el total en "
            f"guaraníes del comprobante tiene que ser {floor:f} o {ceil:f}, y es {total:f}.",
            details={"floor": format(floor, "f"), "ceil": format(ceil, "f")},
            status_code=422,
        )


def _check_vat(db: Session, data: dict[str, Any]) -> RuleVersion:
    rule = rules.require_rule(db, VAT_RULE, data["issued_on"])
    rates = vat_rates(rule)
    for base, vat, rate, label in (
        ("taxed_10", "vat_10", rates.general_rate, "general"),
        ("taxed_5", "vat_5", rates.reduced_rate, "reducida"),
    ):
        expected = included_vat(data[base], rate)
        printed = data.get(vat)
        if printed is None:
            data[vat] = expected
            continue
        if abs(printed - expected) > VAT_TOLERANCE:
            raise AppError(
                "VAT_MISMATCH",
                f"El IVA a la tasa {label} ({rate * 100:g} %) de {data[base]:f} es {expected:f}; "
                f"el impreso ({printed:f}) difiere en más de 1 guaraní. Revisá los importes.",
                details={"field": vat, "expected": format(expected, "f")},
                status_code=422,
            )
    return rule


def _check_note(db: Session, organization_id: uuid.UUID, data: dict[str, Any], own_id: Any) -> None:
    related_id = data.get("related_voucher_id")
    if data["voucher_type"] == "invoice":
        if related_id is not None:
            raise AppError(
                "RELATED_NOT_APPLICABLE",
                "Solo una nota de crédito o de débito referencia otro comprobante.",
                status_code=422,
            )
        return
    if related_id is None:
        raise AppError(
            "RELATED_VOUCHER_REQUIRED",
            "Una nota de crédito o de débito referencia la factura que corrige.",
            status_code=422,
        )
    original = db.scalar(
        select(Voucher).where(Voucher.id == related_id, Voucher.organization_id == organization_id)
    )
    if original is None:
        raise AppError(
            "RELATED_VOUCHER_NOT_FOUND", "El comprobante original no existe.", status_code=422
        )
    if original.voucher_type != "invoice" or original.voided_at is not None:
        raise AppError(
            "RELATED_VOUCHER_INVALID",
            "El comprobante original tiene que ser una factura viva (no anulada).",
            status_code=422,
        )
    if original.direction != data["direction"] or (
        original.counterparty_doc_type,
        original.counterparty_ruc,
        original.counterparty_document,
    ) != (
        data["counterparty_doc_type"],
        data["counterparty_ruc"],
        data["counterparty_document"],
    ):
        raise AppError(
            "VOUCHER_NOTE_MISMATCH",
            "La nota tiene que ser de la misma dirección y contraparte que la factura original.",
            status_code=422,
        )
    if data["issued_on"] < original.issued_on:
        raise AppError(
            "RELATED_VOUCHER_INVALID",
            "La nota no puede ser anterior a la factura que corrige.",
            status_code=422,
        )
    if data["voucher_type"] == "credit_note":
        query = select(
            func.coalesce(func.sum(Voucher.taxed_10 + Voucher.taxed_5 + Voucher.exempt), 0)
        ).where(
            Voucher.related_voucher_id == original.id,
            Voucher.voucher_type == "credit_note",
            Voucher.voided_at.is_(None),
        )
        if own_id is not None:
            query = query.where(Voucher.id != own_id)
        credited = db.scalar(query) or ZERO
        total = data["taxed_10"] + data["taxed_5"] + data["exempt"]
        credited += total
        if credited > total_of(original):
            raise AppError(
                "CREDIT_NOTE_EXCEEDS_ORIGINAL",
                f"Las notas de crédito de la factura {original.number} sumarían {credited:f}"
                f" y la factura es de {total_of(original):f}.",
                status_code=422,
            )


def _check_links(db: Session, ctx: FinancialContext, data: dict[str, Any]) -> None:
    counterparty_id = data.get("finance_counterparty_id")
    if counterparty_id is not None:
        counterparty = db.scalar(
            select(Counterparty).where(
                Counterparty.id == counterparty_id, Counterparty.context_id == ctx.id
            )
        )
        if counterparty is None:
            # Una contraparte personal tampoco existe para la tributación (D-024).
            raise NotFound(
                "COUNTERPARTY_NOT_FOUND", "La contraparte no existe en las finanzas de la empresa."
            )
        if counterparty.ruc is not None and (
            counterparty.ruc,
            counterparty.ruc_check_digit,
        ) != (data.get("counterparty_ruc"), data.get("counterparty_ruc_dv")):
            raise AppError(
                "COUNTERPARTY_RUC_MISMATCH",
                f"La contraparte de finanzas tiene el RUC {counterparty.ruc}-"
                f"{counterparty.ruc_check_digit}, distinto del comprobante.",
                status_code=422,
            )
    transaction_id = data.get("transaction_id")
    if transaction_id is not None:
        tx = business_transaction(db, ctx.organization_id, transaction_id)
        if tx.voided_at is not None:
            raise Conflict("TRANSACTION_VOIDED", "El movimiento está anulado.")


def _duplicate(db: Session, organization_id: uuid.UUID, data: dict[str, Any], own_id: Any) -> None:
    query = select(Voucher.id).where(
        Voucher.organization_id == organization_id,
        Voucher.direction == data["direction"],
        Voucher.voucher_type == data["voucher_type"],
        Voucher.timbrado == data["timbrado"],
        Voucher.number == data["number"],
        Voucher.voided_at.is_(None),
    )
    if data["direction"] == "purchase":
        query = query.where(Voucher.counterparty_ruc == data["counterparty_ruc"])
    if own_id is not None:
        query = query.where(Voucher.id != own_id)
    existing = db.scalar(query)
    if existing is not None:
        raise Conflict(
            "VOUCHER_DUPLICATE",
            f"El comprobante {data['number']} (timbrado {data['timbrado']}) ya está cargado.",
            details={"voucher_id": str(existing)},
        )


def _register_label(data: dict[str, Any]) -> str:
    when = data["issued_on"]
    period = f"{when:%m/%Y}" if data["voucher_type"] in PERIOD_TYPES else f"{when:%d/%m/%Y}"
    if data["number"] is not None:
        return f"El comprobante {data['number']} de {data['counterparty_name']}"
    return f"El comprobante de {data['counterparty_name']} del {period}"


def _duplicate_register(
    db: Session, organization_id: uuid.UUID, data: dict[str, Any], own_id: Any
) -> None:
    """D-143: los que no tienen timbrado se identifican por el tipo, la contraparte (como se
    cargó), la cuenta y el número; sin número, por la fecha o el período y el empleador. Igual
    que los índices `uq_vouchers_register_*` (NULL igual a NULL)."""
    query = select(Voucher.id).where(
        Voucher.organization_id == organization_id,
        Voucher.direction == data["direction"],
        Voucher.voucher_type == data["voucher_type"],
        Voucher.voided_at.is_(None),
        Voucher.counterparty_doc_type.is_not_distinct_from(data["counterparty_doc_type"]),
        Voucher.counterparty_ruc.is_not_distinct_from(data["counterparty_ruc"]),
        Voucher.counterparty_document.is_not_distinct_from(data["counterparty_document"]),
        Voucher.account_number.is_not_distinct_from(data["account_number"]),
    )
    if data["number"] is not None:
        query = query.where(Voucher.number == data["number"])
    else:
        query = query.where(
            Voucher.number.is_(None),
            Voucher.ips_employer_number.is_not_distinct_from(data["ips_employer_number"]),
            Voucher.issued_on == data["issued_on"],
        )
    if own_id is not None:
        query = query.where(Voucher.id != own_id)
    existing = db.scalar(query)
    if existing is not None:
        raise Conflict(
            "VOUCHER_DUPLICATE",
            f"{_register_label(data)} ya está cargado.",
            details={"voucher_id": str(existing)},
        )


def _text(value: Any) -> str | None:
    text = " ".join(str(value).split()) if value is not None else ""
    return text or None


_NUMBER = re.compile(r"^[0-9]{3}-[0-9]{3}-[0-9]{7}$")
_TIMBRADO = re.compile(r"^[0-9]{8}$")
# Tipos de identificación que admite cada tipo (columna 5 de INGRESOS y EGRESOS).
_REGISTER_DOC_TYPES: dict[tuple[str, str], tuple[str, ...]] = {
    ("income", "payslip"): ("ruc",),
    ("income", "other_income"): ("ruc", "identity_card", "passport"),
    ("expense", "public_entity"): ("ruc",),
    ("expense", "e_ticketing"): ("ruc",),
    ("expense", "foreign_voucher"): ("tax_id",),
}


def _not_applicable(name: str, why: str) -> AppError:
    return AppError(
        "FIELD_NOT_APPLICABLE",
        f"{why} no lleva {FIELD_LABELS.get(name, name)}.",
        details={"field": name},
        status_code=422,
    )


def _validated_register(
    db: Session,
    organization_id: uuid.UUID,
    ctx: FinancialContext,
    data: dict[str, Any],
    own_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Un ingreso o un egreso del registro anual (D-143). Ver el docstring del módulo."""
    direction, vtype = data["direction"], data["voucher_type"]
    register = "INGRESOS" if direction == "income" else "EGRESOS"
    if vtype not in (INCOME_TYPES if direction == "income" else EXPENSE_TYPES):
        raise AppError(
            "VOUCHER_TYPE_INVALID",
            f"Ese tipo de comprobante no va en {register} (Tabla 4 del formato de la RG 90/2021).",
            details={"field": "voucher_type"},
            status_code=422,
        )
    if vtype in PERIOD_TYPES:
        data["issued_on"] = data["issued_on"].replace(day=1)
    issued: date = data["issued_on"]
    if issued < REGISTER_MIN_DATE:
        raise AppError(
            "DATE_BEFORE_REGISTER",
            "El registro de comprobantes no admite fechas anteriores al 01/01/2021.",
            details={"field": "issued_on"},
            status_code=422,
        )
    if not annual_register_applies(db, organization_id, issued.year):
        raise AppError(
            "REGISTER_NOT_AVAILABLE",
            f"Los ingresos y egresos son del registro anual de comprobantes (956), y el perfil "
            f"fiscal vigente al cierre de {issued.year} no la incluye. Con IVA, todo va en "
            "compras y ventas del registro mensual (955).",
            details={"year": issued.year},
            status_code=422,
        )
    why = "Un ingreso o un egreso (sin timbrado)"
    for name in ("timbrado", "cdc", "related_voucher_id"):
        if data.get(name) is not None:
            raise _not_applicable(name, why)
    if data.get("is_electronic"):
        raise AppError(
            "CDC_NOT_APPLICABLE",
            "Los ingresos y egresos no son comprobantes electrónicos: los que tienen CDC van "
            "como compra o venta.",
            status_code=422,
        )
    data.update(is_electronic=False, condition=data.get("condition") or "cash")
    data["number"] = _text(data.get("number"))
    if data["number"] is None and (direction, vtype) not in UNNUMBERED:
        raise AppError(
            "VOUCHER_NUMBER_REQUIRED",
            "Indicá el número del comprobante o de la transacción.",
            details={"field": "number"},
            status_code=422,
        )
    needed = {
        "account_number": direction == "expense" and vtype in ACCOUNT_TYPES,
        "bank_name": direction == "expense" and vtype in ACCOUNT_TYPES,
        "ips_employer_number": vtype == "ips_statement",
        "document_description": vtype in DESCRIBED_TYPES,
        "related_number": vtype in CREDIT_TYPES,
        "related_timbrado": vtype in CREDIT_TYPES,
    }
    for name, need in needed.items():
        value = _text(data.get(name))
        if need and value is None:
            raise AppError(
                "FIELD_REQUIRED",
                f"Este tipo de comprobante lleva {FIELD_LABELS[name]}.",
                details={"field": name},
                status_code=422,
            )
        if not need and value is not None:
            raise _not_applicable(name, "Este tipo de comprobante")
        data[name] = value
    if data["related_number"] is not None and not _NUMBER.match(data["related_number"]):
        raise AppError(
            "VOUCHER_NUMBER_INVALID",
            "El número del comprobante asociado va como 001-001-0000001.",
            details={"field": "related_number"},
            status_code=422,
        )
    if data["related_timbrado"] is not None and not _TIMBRADO.match(data["related_timbrado"]):
        raise AppError(
            "TIMBRADO_INVALID",
            "El timbrado del comprobante asociado tiene 8 dígitos.",
            details={"field": "related_timbrado"},
            status_code=422,
        )

    doc_type = data.get("counterparty_doc_type")
    if vtype == "ips_statement":
        data["counterparty_name"] = data.get("counterparty_name") or IPS_NAME
    if doc_type is None:
        if not (direction == "expense" and vtype in NO_COUNTERPARTY_TYPES):
            raise AppError(
                "COUNTERPARTY_REQUIRED",
                "Este tipo de comprobante lleva la identificación de la contraparte.",
                details={"field": "counterparty_doc_type"},
                status_code=422,
            )
        data["counterparty_ruc"] = data["counterparty_ruc_dv"] = None
        data["counterparty_document"] = None
        if not data.get("counterparty_name"):
            raise AppError(
                "COUNTERPARTY_NAME_REQUIRED",
                "Indicá el nombre de la contraparte o una descripción.",
                status_code=422,
            )
    else:
        allowed = _REGISTER_DOC_TYPES.get((direction, vtype))
        if doc_type == "unnamed" or (allowed is not None and doc_type not in allowed):
            raise AppError(
                "COUNTERPARTY_DOC_TYPE_INVALID",
                "Ese tipo de identificación no corresponde a este comprobante (columna 5 del "
                "formato de la RG 90/2021).",
                details={"field": "counterparty_doc_type", "allowed": list(allowed or ())},
                status_code=422,
            )
        _check_counterparty(data)

    for name in ("taxed_5", "vat_10", "vat_5"):
        if data.get(name):
            raise AppError(
                "AMOUNT_NOT_APPLICABLE",
                "Un ingreso o un egreso no lleva IVA ni importes por tasa.",
                details={"field": name},
                status_code=422,
            )
    taxed = _pyg(data.get("taxed_10") or ZERO, "taxed_10")
    exempt = _pyg(data.get("exempt") or ZERO, "exempt")
    if direction == "expense" and exempt:
        raise AppError(
            "AMOUNT_NOT_APPLICABLE",
            "Un egreso lleva solo el monto total (`taxed_10`).",
            details={"field": "exempt"},
            status_code=422,
        )
    data.update(taxed_10=taxed, exempt=exempt, taxed_5=ZERO, vat_10=ZERO, vat_5=ZERO)
    if taxed + exempt <= 0:
        raise AppError(
            "VOUCHER_TOTAL_ZERO", "El comprobante tiene que tener algún importe.", status_code=422
        )
    if data.get("imputes_vat"):
        raise AppError(
            "IMPUTES_VAT_NOT_APPLICABLE",
            "Con el registro anual (956) no hay IVA: la 956 no va con la 211 (RG 90/2021, "
            "art. 7°).",
            details={"field": "imputes_vat"},
            status_code=422,
        )
    data["imputes_vat"] = False
    data["imputes_ire"] = bool(data.get("imputes_ire"))
    data["imputes_irp"] = True if data.get("imputes_irp") is None else data["imputes_irp"]
    _check_currency(data, taxed + exempt)
    _check_links(db, ctx, data)
    _duplicate_register(db, organization_id, data, own_id)
    return {k: data.get(k) for k in FIELDS}


def _check_timbrado_fields(data: dict[str, Any]) -> None:
    """Compras y ventas: timbrado, número `EEE-PPP-NNNNNNN`, contraparte identificada y sin
    las columnas de INGRESOS y EGRESOS."""
    if data["voucher_type"] not in TIMBRADO_TYPES:
        raise AppError(
            "VOUCHER_TYPE_INVALID",
            "Una compra o una venta es una factura o una nota de crédito o de débito.",
            details={"field": "voucher_type"},
            status_code=422,
        )
    if data.get("timbrado") is None or not _TIMBRADO.match(data["timbrado"]):
        raise AppError(
            "TIMBRADO_REQUIRED",
            "Una compra o una venta lleva el timbrado (8 dígitos).",
            details={"field": "timbrado"},
            status_code=422,
        )
    if data.get("number") is None or not _NUMBER.match(data["number"]):
        raise AppError(
            "VOUCHER_NUMBER_INVALID",
            "El número va como 001-001-0000001 (establecimiento, punto y número).",
            details={"field": "number"},
            status_code=422,
        )
    if data.get("counterparty_doc_type") is None:
        raise AppError(
            "COUNTERPARTY_REQUIRED",
            "Indicá la identificación de la contraparte.",
            details={"field": "counterparty_doc_type"},
            status_code=422,
        )
    for name in REGISTER_FIELDS:
        if data.get(name) is not None:
            raise _not_applicable(name, "Una compra o una venta")
    data["imputes_vat"] = True if data.get("imputes_vat") is None else data["imputes_vat"]
    data["imputes_ire"] = bool(data.get("imputes_ire"))
    data["imputes_irp"] = bool(data.get("imputes_irp"))


def validated(
    db: Session,
    organization_id: uuid.UUID,
    ctx: FinancialContext,
    data: dict[str, Any],
    *,
    own_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], RuleVersion | None]:
    """Normaliza y valida los datos completos de un comprobante. Devuelve los campos a
    guardar y la regla de tasas aplicada (ninguna en un ingreso o un egreso)."""
    org = db.get(Organization, organization_id)
    assert org is not None
    data = dict(data)
    if data["direction"] in REGISTER_DIRECTIONS:
        return _validated_register(db, organization_id, ctx, data, own_id), None
    _check_timbrado_fields(data)
    if data["direction"] == "sale" and org.ruc is None:
        raise AppError(
            "ORGANIZATION_RUC_REQUIRED",
            "Cargá el RUC de la organización antes de registrar ventas.",
            status_code=422,
        )
    for name in ("taxed_10", "taxed_5", "exempt"):
        data[name] = _pyg(data.get(name) or ZERO, name)
    for name in ("vat_10", "vat_5"):
        if data.get(name) is not None:
            data[name] = _pyg(data[name], name)
    total = data["taxed_10"] + data["taxed_5"] + data["exempt"]
    if total <= 0:
        raise AppError(
            "VOUCHER_TOTAL_ZERO", "El comprobante tiene que tener algún importe.", status_code=422
        )
    _check_counterparty(data)
    _check_cdc(data, org)
    _check_currency(data, total)
    rule = _check_vat(db, data)
    _check_note(db, organization_id, data, own_id)
    _check_links(db, ctx, data)
    _duplicate(db, organization_id, data, own_id)
    return {k: data.get(k) for k in FIELDS}, rule


def create(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> Voucher:
    ctx = business_context(db, organization_id)
    _check_not_confirmed(db, organization_id, data["issued_on"])
    values, rule = validated(db, organization_id, ctx, data)
    voucher = Voucher(
        organization_id=organization_id,
        context_id=ctx.id,
        context_kind="business",
        vat_rule_version_id=rule.id if rule is not None else None,
        created_by=actor_id,
        **values,
    )
    db.add(voucher)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "voucher",
        "created",
        voucher.id,
        after=snapshot(voucher, (*FIELDS, "vat_rule_version_id")),
    )
    db.commit()
    return voucher


def update(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    voucher_id: uuid.UUID,
    changes: dict[str, Any],
) -> Voucher:
    voucher = get_voucher(db, organization_id, voucher_id, lock=True)
    if voucher.voided_at is not None:
        raise Conflict("VOUCHER_VOIDED", "El comprobante está anulado: no se modifica.")
    if "direction" in changes and changes["direction"] != voucher.direction:
        raise AppError(
            "VOUCHER_DIRECTION_FIXED",
            "Un comprobante no cambia de registro (compra, venta, ingreso o egreso): anulalo "
            "y cargalo de nuevo.",
            status_code=422,
        )
    merged = {k: getattr(voucher, k) for k in FIELDS} | changes
    real = {k for k, v in changes.items() if getattr(voucher, k) != v}
    if real - EDITABLE_WITH_ENTRY:
        _check_no_live_entry(db, voucher, "modificar")
    _check_not_confirmed(db, organization_id, voucher.issued_on, merged["issued_on"])
    # El IVA impreso se vuelve a validar contra los importes nuevos (o se recalcula si no
    # vino y cambiaron las bases).
    for vat, base in (("vat_10", "taxed_10"), ("vat_5", "taxed_5")):
        if vat not in changes and base in changes:
            merged[vat] = None
    values, rule = validated(
        db, organization_id, business_context(db, organization_id), merged, own_id=voucher.id
    )
    values["vat_rule_version_id"] = rule.id if rule is not None else None
    before, after = apply_changes(voucher, values)
    if after:
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "voucher",
            "updated",
            voucher.id,
            before=before,
            after=after,
        )
    db.commit()
    return voucher


def void(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    voucher_id: uuid.UUID,
    reason: str,
) -> Voucher:
    voucher = get_voucher(db, organization_id, voucher_id, lock=True)
    if voucher.voided_at is not None:
        raise Conflict("VOUCHER_VOIDED", "El comprobante ya está anulado.")
    _check_not_confirmed(db, organization_id, voucher.issued_on)
    _check_no_live_entry(db, voucher, "anular")
    notes = db.scalar(
        select(func.count()).where(
            Voucher.related_voucher_id == voucher.id, Voucher.voided_at.is_(None)
        )
    )
    if notes:
        raise Conflict(
            "VOUCHER_HAS_NOTES",
            "La factura tiene notas de crédito o débito vivas: anulá primero las notas.",
        )
    before = snapshot(voucher, ("voided_at", "void_reason"))
    voucher.voided_at = now()
    voucher.voided_by = actor_id
    voucher.void_reason = reason
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "voucher",
        "voided",
        voucher.id,
        before=before,
        after=snapshot(voucher, ("voided_at", "void_reason")),
    )
    db.commit()
    return voucher


def list_query(
    organization_id: uuid.UUID,
    *,
    month: date | None,
    direction: str | None,
    counterparty_ruc: str | None,
    voucher_type: str | None = None,
    year: int | None = None,
    q: str | None,
    voided: str,
) -> Select[Voucher]:
    query = select(Voucher).where(Voucher.organization_id == organization_id)
    if month is not None:
        query = query.where(
            Voucher.issued_on >= month_start(month), Voucher.issued_on <= month_end(month)
        )
    if year is not None:
        query = query.where(
            Voucher.issued_on >= date(year, 1, 1), Voucher.issued_on <= date(year, 12, 31)
        )
    if direction:
        query = query.where(Voucher.direction == direction)
    if voucher_type:
        query = query.where(Voucher.voucher_type == voucher_type)
    if counterparty_ruc:
        query = query.where(Voucher.counterparty_ruc == counterparty_ruc)
    if q:
        pattern = f"%{escape_like(q.strip())}%"
        query = query.where(
            or_(
                Voucher.counterparty_name.ilike(pattern, escape="\\"),
                Voucher.number.ilike(pattern, escape="\\"),
                Voucher.timbrado.ilike(pattern, escape="\\"),
            )
        )
    if voided == "exclude":
        query = query.where(Voucher.voided_at.is_(None))
    elif voided == "only":
        query = query.where(Voucher.voided_at.is_not(None))
    return query


def entries_of(db: Session, vouchers: list[Voucher]) -> dict[uuid.UUID, JournalEntry]:
    ids = {v.journal_entry_id for v in vouchers if v.journal_entry_id is not None}
    if not ids:
        return {}
    return {e.id: e for e in db.scalars(select(JournalEntry).where(JournalEntry.id.in_(ids)))}
