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
from app.modules.tax.models import DOCUMENT_TYPES, Obligation, RuleVersion, Voucher

VAT_RULE = "IVA-GENERAL-TASAS"
REGISTER_RULE = "REG-COMPROB-MENSUAL"
VAT_TOLERANCE = Decimal(1)
UNNAMED = "Sin nombre"
CDC_DOCUMENT_TYPES = {"invoice": "01", "credit_note": "05"}

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


def _check_not_confirmed(db: Session, organization_id: uuid.UUID, *days: date) -> None:
    for day in {month_start(d) for d in days}:
        if month_confirmed(db, organization_id, day):
            raise Conflict(
                "PERIOD_CONFIRMED",
                f"El registro de comprobantes de {day:%m/%Y} está confirmado: para cambiar sus "
                "comprobantes, reabrí primero la obligación del registro (con motivo).",
                details={"month": day.isoformat()},
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


def validated(
    db: Session,
    organization_id: uuid.UUID,
    ctx: FinancialContext,
    data: dict[str, Any],
    *,
    own_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], RuleVersion]:
    """Normaliza y valida los datos completos de un comprobante. Devuelve los campos a
    guardar y la regla de tasas aplicada."""
    org = db.get(Organization, organization_id)
    assert org is not None
    data = dict(data)
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
        vat_rule_version_id=rule.id,
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
            "Un comprobante no cambia de compra a venta: anulalo y cargalo de nuevo.",
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
    values["vat_rule_version_id"] = rule.id
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
    q: str | None,
    voided: str,
) -> Select[Voucher]:
    query = select(Voucher).where(Voucher.organization_id == organization_id)
    if month is not None:
        query = query.where(
            Voucher.issued_on >= month_start(month), Voucher.issued_on <= month_end(month)
        )
    if direction:
        query = query.where(Voucher.direction == direction)
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
