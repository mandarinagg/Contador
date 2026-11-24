"""Avisos tributarios (D-092, D-098), calculados en el momento. No hay procesos de fondo.

- `OBLIGATIONS_OVERDUE`: pendientes con vencimiento anterior a hoy.
- `OBLIGATIONS_DUE_SOON`: pendientes no vencidas cuyo `remind_by` cae dentro de los días de
  anticipación (`tax.settings.alert_days`, 10 por defecto). `remind_by` es la fecha fija
  del calendario sin correr si es anterior al vencimiento (D-098): como no está verificado
  que sábados y feriados corran el plazo (D-F4-11, D-F4-12), se avisa por la fecha más
  temprana y nunca más tarde que el vencimiento real.
- `REGISTER_UNCONFIRMED`: registro de comprobantes (955) de un mes ya terminado sin
  confirmar.
- `MONTHS_WITHOUT_VOUCHERS`: meses (de los últimos 12 y el actual) con movimientos de la
  empresa en finanzas, sin contar transferencias entre cuentas propias, y ningún comprobante.
- `PROFILE_MISSING` y `PROFILE_UNVERIFIED`.
- `RULES_UNVERIFIED`: reglas en uso (las de las obligaciones pendientes y la de tasas del
  IVA vigente) que nadie verificó.
- `COUNTERPARTY_RUC_UNCHECKED`: comprobantes con un RUC antiguo terminado en letra, que se
  aceptaron sin DV y hay que revisar (D-099).

Cada aviso desaparece cuando se resuelve lo que lo causa.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.finance.models import FinancialContext, Transaction
from app.modules.tax import profile as profiles
from app.modules.tax import rules, tax_settings
from app.modules.tax.common import add_months, month_start
from app.modules.tax.models import Obligation, RuleVersion, Voucher

REGISTER_RULE = "REG-COMPROB-MENSUAL"
LOOKBACK_MONTHS = 12


def shift_explanation(obligation: Obligation) -> str | None:
    """Por qué `remind_by` y `due_date` difieren (D-098), o `None` si coinciden."""
    if obligation.remind_by == obligation.due_date:
        return None
    if obligation.exception_id is not None:
        return (
            f"La fecha fija del calendario es el {obligation.nominal_due_date:%d/%m/%Y}; una "
            f"excepción la pasa al {obligation.due_date:%d/%m/%Y}. Se avisa por la fecha fija."
        )
    return (
        f"La fecha fija del calendario es el {obligation.nominal_due_date:%d/%m/%Y}; si el día "
        f"es inhábil, el vencimiento pasa al {obligation.due_date:%d/%m/%Y}, sin verificar. Se "
        "avisa por la fecha fija."
    )


def _obligation_item(obligation: Obligation) -> dict[str, Any]:
    return {
        "id": str(obligation.id),
        "code": obligation.code,
        "dnit_code": obligation.dnit_code,
        "period_start": obligation.period_start.isoformat(),
        "period_end": obligation.period_end.isoformat(),
        "due_date": obligation.due_date.isoformat(),
        "remind_by": obligation.remind_by.isoformat(),
        "shift_explanation": shift_explanation(obligation),
    }


def _alert(
    code: str, severity: str, message: str, items: list[Any] | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "count": len(items) if items is not None else 1,
        "items": items or [],
    }


def compute(db: Session, organization_id: uuid.UUID, today: date) -> dict[str, Any]:
    alerts: list[dict[str, Any]] = []
    days = tax_settings.effective(db, organization_id).alert_days

    pending = list(
        db.scalars(
            select(Obligation)
            .where(Obligation.organization_id == organization_id, Obligation.status == "pending")
            .order_by(Obligation.due_date, Obligation.code)
        )
    )
    overdue = [o for o in pending if o.due_date < today]
    soon = [o for o in pending if o.due_date >= today and o.remind_by <= today + timedelta(days)]
    if overdue:
        alerts.append(
            _alert(
                "OBLIGATIONS_OVERDUE",
                "danger",
                f"{len(overdue)} obligación(es) vencida(s) sin presentar.",
                [_obligation_item(o) for o in overdue],
            )
        )
    if soon:
        alerts.append(
            _alert(
                "OBLIGATIONS_DUE_SOON",
                "warning",
                f"{len(soon)} obligación(es) vencen en los próximos {days} días.",
                [_obligation_item(o) for o in soon],
            )
        )
    unconfirmed = [o for o in pending if o.code == REGISTER_RULE and o.period_end < today]
    if unconfirmed:
        alerts.append(
            _alert(
                "REGISTER_UNCONFIRMED",
                "warning",
                "Hay meses terminados con el registro de comprobantes sin confirmar en "
                "Marangatu: cargá los comprobantes y confirmalo.",
                [_obligation_item(o) for o in unconfirmed],
            )
        )

    first = add_months(month_start(today), -LOOKBACK_MONTHS)
    tx_month = func.date_trunc("month", Transaction.booked_on).cast(Transaction.booked_on.type)
    moved = set(
        db.scalars(
            select(tx_month)
            .join(FinancialContext, FinancialContext.id == Transaction.context_id)
            .where(
                FinancialContext.organization_id == organization_id,
                FinancialContext.kind == "business",
                Transaction.voided_at.is_(None),
                Transaction.transfer_group_id.is_(None),
                Transaction.booked_on >= first,
                Transaction.booked_on <= today,
            )
            .distinct()
        )
    )
    v_month = func.date_trunc("month", Voucher.issued_on).cast(Voucher.issued_on.type)
    with_vouchers = set(
        db.scalars(
            select(v_month)
            .where(
                Voucher.organization_id == organization_id,
                Voucher.voided_at.is_(None),
                Voucher.issued_on >= first,
            )
            .distinct()
        )
    )
    empty = sorted(moved - with_vouchers)
    if empty:
        alerts.append(
            _alert(
                "MONTHS_WITHOUT_VOUCHERS",
                "info",
                "Hay meses con movimientos de la empresa y ningún comprobante cargado: cargá "
                "tus facturas de compra y venta.",
                [{"month": m.isoformat()} for m in empty],
            )
        )

    history = profiles.versions(db, organization_id)
    current = profiles.vigente(history, today)
    if not history:
        alerts.append(
            _alert(
                "PROFILE_MISSING",
                "warning",
                "Falta el perfil fiscal: sin él no se generan obligaciones ni vencimientos.",
            )
        )
    elif current is not None and current.profile.origin != "verified":
        alerts.append(
            _alert(
                "PROFILE_UNVERIFIED",
                "info",
                "El perfil fiscal vigente no está verificado por un contador con la constancia "
                "de RUC.",
            )
        )

    used_ids = {o.rule_version_id for o in pending} | {o.calendar_rule_version_id for o in pending}
    in_use = list(db.scalars(select(RuleVersion).where(RuleVersion.id.in_(used_ids))))
    rates = rules.rule_for(db, "IVA-GENERAL-TASAS", today)
    if rates is not None and rates.id not in used_ids:
        in_use.append(rates)
    unverified = sorted(
        (r for r in in_use if r.validation_status == "pending"), key=lambda r: (r.code, r.version)
    )
    if unverified:
        alerts.append(
            _alert(
                "RULES_UNVERIFIED",
                "info",
                "Hay reglas en uso sin verificar por un contador: los vencimientos y las "
                "estimaciones que dependen de ellas se muestran «sin verificar».",
                [rules.applied(r) for r in unverified],
            )
        )

    legacy = list(
        db.execute(
            select(Voucher.id, Voucher.number, Voucher.counterparty_ruc, Voucher.counterparty_name)
            .where(
                Voucher.organization_id == organization_id,
                Voucher.voided_at.is_(None),
                Voucher.counterparty_ruc.regexp_match("[A-Z]$"),
            )
            .order_by(Voucher.issued_on)
            .limit(200)
        )
    )
    if legacy:
        alerts.append(
            _alert(
                "COUNTERPARTY_RUC_UNCHECKED",
                "info",
                "Hay comprobantes con un RUC antiguo terminado en letra, cargados sin dígito "
                "verificador: revisá que el RUC sea el correcto.",
                [
                    {"voucher_id": str(i), "number": n, "ruc": r, "name": name}
                    for i, n, r, name in legacy
                ],
            )
        )
    return {"as_of": today.isoformat(), "alert_days": days, "count": len(alerts), "alerts": alerts}
