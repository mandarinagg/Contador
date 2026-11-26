"""Obligaciones y calendario (D-087, BR-TAX-04/05/06).

`sync` crea las obligaciones que falten, desde el alta de cada obligación del perfil hasta
3 meses adelante (períodos que empiezan hasta el primer día del tercer mes siguiente), y se
puede llamar las veces que haga falta:
- el período es el mes (obligaciones mensuales) o el ejercicio fiscal (anuales, según el mes
  de cierre del perfil);
- rige el perfil vigente al **último día** del período, y la obligación cuenta si su alta
  es de ese día o anterior;
- la regla de la obligación es la vigente al inicio del período; la del día del calendario
  (DJ o DJI), la vigente al inicio del mes del vencimiento. Sin regla vigente no se genera
  nada (D-082);
- vencimiento: día del calendario por la terminación del RUC sin DV (o el día fijo de la
  regla, como el 26 de febrero del RESIMPLE), corrido al siguiente hábil (D-086, D-142); una
  excepción fechada lo reemplaza;
- lo no presentado (`pending`) se recalcula siempre; lo presentado o pagado, nunca;
- lo que el perfil (o la falta de regla) deja de cubrir pasa a `not_applicable` con motivo
  automático, y vuelve a `pending` si se cubre otra vez (D-098). Nada se borra.

Dos `sync` simultáneos se serializan con un candado de la organización
(`pg_advisory_xact_lock`): el segundo ve lo que dejó el primero y no duplica.

«Vencida» no es un estado: es `pending` con vencimiento anterior a hoy.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting.finance_link import business_transaction
from app.modules.organizations.models import Organization
from app.modules.tax import profile as profiles
from app.modules.tax import rule_params
from app.modules.tax.calendar import BusinessDays, ExceptionMatch, Exceptions
from app.modules.tax.common import (
    add_months,
    flush_translated,
    month_end,
    month_start,
    record,
    snapshot,
)
from app.modules.tax.models import DueDateException, Obligation, RuleVersion
from app.modules.tax.rules import RuleCache

HORIZON_MONTHS = 3
CALENDAR_FIELDS = (
    "nominal_due_date",
    "due_date",
    "rule_version_id",
    "calendar_rule_version_id",
    "exception_id",
)
STATE_FIELDS = (
    "status",
    "filed_on",
    "filing_reference",
    "declared_amount",
    "declared_credit_balance",
    "paid_on",
    "paid_amount",
    "payment_transaction_id",
    "not_applicable_reason",
    "not_applicable_auto",
    "reopen_reason",
)
REASON_NOT_IN_PROFILE = "El perfil fiscal vigente en el período no incluye esta obligación."
REASON_NO_RULE = "No hay una versión vigente de la regla para este período."


@dataclass(frozen=True)
class Planned:
    code: str
    dnit_code: str
    period_start: date
    period_end: date
    nominal_due_date: date
    due_date: date
    rule: RuleVersion
    calendar_rule: RuleVersion
    exception: ExceptionMatch | None

    def calendar_values(self) -> dict[str, Any]:
        return {
            "nominal_due_date": self.nominal_due_date,
            "due_date": self.due_date,
            "rule_version_id": self.rule.id,
            "calendar_rule_version_id": self.calendar_rule.id,
            "exception_id": self.exception.exception.id if self.exception else None,
        }


@dataclass
class SyncResult:
    created: int = 0
    recalculated: int = 0
    not_applicable: int = 0
    reactivated: int = 0
    profile_missing: bool = False
    unsupported_codes: list[str] = field(default_factory=list)
    without_rule: list[dict[str, Any]] = field(default_factory=list)


def obligation_not_found() -> NotFound:
    return NotFound("OBLIGATION_NOT_FOUND", "La obligación no existe.")


def ruc_digit(org: Organization) -> int:
    assert org.ruc is not None
    return int(org.ruc[-1])


def _monthly_periods(first: date, horizon: date) -> Iterator[tuple[date, date]]:
    current = month_start(first)
    while current <= horizon:
        yield current, month_end(current)
        current = add_months(current, 1)


def fiscal_year(day: date, close_month: int) -> tuple[date, date]:
    """Ejercicio fiscal (inicio, fin) que contiene `day`, con cierre en `close_month`."""
    end_year = day.year if day.month <= close_month else day.year + 1
    end = month_end(date(end_year, close_month, 1))
    return add_months(end, -11), end


def _annual_periods(first: date, horizon: date, close_month: int) -> Iterator[tuple[date, date]]:
    start, end = fiscal_year(first, close_month)
    while start <= horizon:
        yield start, end
        start, end = add_months(end, 1), month_end(add_months(end, 12))


def plan_due(
    *,
    code: str,
    period_start: date,
    period_end: date,
    digit: int,
    rules: RuleCache,
    calendar: BusinessDays,
    exceptions: Exceptions,
) -> Planned | RuleVersion | None:
    """Vencimiento de una obligación. `None` = sin regla de la obligación; una `RuleVersion`
    = la de la obligación existe pero falta la del día del calendario."""
    rule = rules.at(code, period_start)
    if rule is None:
        return None
    params = rule_params.parse(code, rule.parameters)
    assert params is not None
    due = rule_params.due_of(params)
    if isinstance(due, rule_params.MonthlyDue):
        due_month = add_months(period_start, due.month_offset)
    else:
        due_month = add_months(period_end, due.months_after_fiscal_close)
    if isinstance(due, rule_params.FixedDayDue):
        # Día fijo de la propia regla (RESIMPLE, 26 de febrero): ella hace de regla del
        # calendario. Se corre al siguiente hábil como todo vencimiento calculado (D-142).
        calendar_rule: RuleVersion | None = rule
        nominal = due_month.replace(day=due.fixed_day)
    else:
        calendar_rule = rules.at(due.day_rule, due_month)
        if calendar_rule is None:
            return rule
        calendar_params = rule_params.parse(calendar_rule.code, calendar_rule.parameters)
        assert isinstance(calendar_params, rule_params.CalendarParams)
        nominal = due_month.replace(day=calendar_params.day_by_digit[str(digit)])
    assert calendar_rule is not None
    match = exceptions.find(code, due_month, digit)
    due_date = (
        match.exception.new_due_date if match is not None else calendar.next_business_day(nominal)
    )
    return Planned(
        code=code,
        dnit_code=rule_params.OBLIGATION_RULES[code],
        period_start=period_start,
        period_end=period_end,
        nominal_due_date=nominal,
        due_date=due_date,
        rule=rule,
        calendar_rule=calendar_rule,
        exception=match,
    )


def _lock_organization(db: Session, organization_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('tax.sync:' || :org, 0))"),
        {"org": str(organization_id)},
    )


def sync(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    today: date,
    commit: bool = True,
) -> SyncResult:
    _lock_organization(db, organization_id)
    result = SyncResult()
    org = db.get(Organization, organization_id)
    history = profiles.versions(db, organization_id)
    if org is None or org.ruc is None or not history:
        result.profile_missing = True
        _mark_uncovered(db, organization_id, actor_id, set(), result)
        if commit:
            db.commit()
        return result
    digit = ruc_digit(org)
    horizon = add_months(month_start(today), HORIZON_MONTHS)

    first_alta: dict[str, date] = {}
    close_months: set[int] = set()
    for version in history:
        close_months.add(version.profile.fiscal_close_month)
        for item in version.obligations:
            code = rule_params.RULE_BY_DNIT_CODE.get(item.code)
            if code is None:
                if item.code not in result.unsupported_codes:
                    result.unsupported_codes.append(item.code)
                continue
            first_alta[code] = min(first_alta.get(code, item.registered_on), item.registered_on)

    candidates: list[tuple[str, date, date]] = []
    for code, alta in first_alta.items():
        if code in rule_params.MONTHLY_RULES:
            candidates.extend((code, s, e) for s, e in _monthly_periods(alta, horizon))
        else:
            for close in sorted(close_months):
                candidates.extend((code, s, e) for s, e in _annual_periods(alta, horizon, close))

    applicable: list[tuple[str, date, date]] = []
    for code, start, end in candidates:
        in_force = profiles.vigente(history, end)
        if in_force is None:
            continue
        annual = code not in rule_params.MONTHLY_RULES
        if annual and fiscal_year(end, in_force.profile.fiscal_close_month) != (start, end):
            continue
        dnit = rule_params.OBLIGATION_RULES[code]
        if any(o.code == dnit and o.registered_on <= end for o in in_force.obligations):
            applicable.append((code, start, end))

    planned: dict[tuple[str, date], Planned] = {}
    if applicable:
        first = min(s for _, s, _ in applicable)
        last = max(e for _, _, e in applicable)
        rules = RuleCache(
            db, [*rule_params.OBLIGATION_RULES, "CAL-PERPETUO-DJ", "CAL-PERPETUO-DJI"]
        )
        calendar = BusinessDays(db, first, add_months(last, 13))
        exceptions = Exceptions(db, first, add_months(last, 13))
        for code, start, end in applicable:
            outcome = plan_due(
                code=code,
                period_start=start,
                period_end=end,
                digit=digit,
                rules=rules,
                calendar=calendar,
                exceptions=exceptions,
            )
            if isinstance(outcome, Planned):
                planned[(code, start)] = outcome
            else:
                missing = code if outcome is None else "calendario"
                result.without_rule.append(
                    {"code": code, "period_start": start.isoformat(), "missing": missing}
                )

    existing = {
        (o.code, o.period_start): o
        for o in db.scalars(
            select(Obligation)
            .where(Obligation.organization_id == organization_id)
            .with_for_update()
        )
    }
    for key, plan in planned.items():
        row = existing.get(key)
        if row is None:
            obligation = Obligation(
                organization_id=organization_id,
                code=plan.code,
                dnit_code=plan.dnit_code,
                period_start=plan.period_start,
                period_end=plan.period_end,
                status="pending",
                **plan.calendar_values(),
            )
            db.add(obligation)
            db.flush()
            record(
                db,
                organization_id,
                actor_id,
                "obligation",
                "created",
                obligation.id,
                after=snapshot(
                    obligation, ("code", "period_start", "period_end", *CALENDAR_FIELDS)
                ),
            )
            result.created += 1
            continue
        if row.status in ("filed", "paid"):
            continue  # BR-TAX-06: lo presentado no se recalcula
        if row.status == "not_applicable" and not row.not_applicable_auto:
            continue  # lo marcó una persona: no se revierte solo
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        if row.status == "not_applicable":
            before = snapshot(row, ("status", "not_applicable_reason", "not_applicable_auto"))
            row.status = "pending"
            row.not_applicable_reason = None
            row.not_applicable_auto = False
            after = snapshot(row, ("status", "not_applicable_reason", "not_applicable_auto"))
            result.reactivated += 1
        changed = {k: v for k, v in plan.calendar_values().items() if getattr(row, k) != v}
        if changed:
            before |= snapshot(row, tuple(changed))
            for name, value in changed.items():
                setattr(row, name, value)
            after |= snapshot(row, tuple(changed))
            if "status" not in after:
                result.recalculated += 1
        if after:
            flush_translated(db)
            verb = "reactivated" if "status" in after else "recalculated"
            record(
                db,
                organization_id,
                actor_id,
                "obligation",
                verb,
                row.id,
                before=before,
                after=after,
            )
    _mark_uncovered(db, organization_id, actor_id, set(planned), result, existing)
    if commit:
        db.commit()
    return result


def _mark_uncovered(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    covered: set[tuple[str, date]],
    result: SyncResult,
    existing: dict[tuple[str, date], Obligation] | None = None,
) -> None:
    """Lo pendiente que ya no corresponde pasa a `not_applicable` con motivo automático."""
    if existing is None:
        existing = {
            (o.code, o.period_start): o
            for o in db.scalars(
                select(Obligation)
                .where(Obligation.organization_id == organization_id)
                .with_for_update()
            )
        }
    without_rule = {(w["code"], date.fromisoformat(w["period_start"])) for w in result.without_rule}
    for key, row in existing.items():
        if key in covered or row.status != "pending":
            continue
        reason = REASON_NO_RULE if key in without_rule else REASON_NOT_IN_PROFILE
        before = snapshot(row, ("status", "not_applicable_reason", "not_applicable_auto"))
        row.status = "not_applicable"
        row.not_applicable_reason = reason
        row.not_applicable_auto = True
        flush_translated(db)
        record(
            db,
            organization_id,
            actor_id,
            "obligation",
            "not_applicable",
            row.id,
            before=before,
            after=snapshot(row, ("status", "not_applicable_reason", "not_applicable_auto")),
        )
        result.not_applicable += 1


# --- Consultas ----------------------------------------------------------------------------


def get_obligation(
    db: Session, organization_id: uuid.UUID, obligation_id: uuid.UUID, *, lock: bool = False
) -> Obligation:
    query = select(Obligation).where(
        Obligation.id == obligation_id, Obligation.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise obligation_not_found()
    return row


def list_obligations(
    db: Session,
    organization_id: uuid.UUID,
    *,
    date_from: date | None,
    date_to: date | None,
    status: str | None,
    code: str | None,
    today: date,
) -> list[Obligation]:
    query = select(Obligation).where(Obligation.organization_id == organization_id)
    if date_from is not None:
        query = query.where(Obligation.due_date >= date_from)
    if date_to is not None:
        query = query.where(Obligation.due_date <= date_to)
    if status == "overdue":
        query = query.where(Obligation.status == "pending", Obligation.due_date < today)
    elif status:
        query = query.where(Obligation.status == status)
    if code:
        query = query.where(Obligation.code == code)
    return list(db.scalars(query.order_by(Obligation.due_date, Obligation.code)))


def rules_of(db: Session, obligations: list[Obligation]) -> dict[uuid.UUID, RuleVersion]:
    ids = {o.rule_version_id for o in obligations} | {
        o.calendar_rule_version_id for o in obligations
    }
    exception_ids = {o.exception_id for o in obligations if o.exception_id is not None}
    if exception_ids:
        ids |= {
            rid
            for rid in db.scalars(
                select(DueDateException.rule_version_id).where(
                    DueDateException.id.in_(exception_ids)
                )
            )
            if rid is not None
        }
    if not ids:
        return {}
    return {r.id: r for r in db.scalars(select(RuleVersion).where(RuleVersion.id.in_(ids)))}


def exceptions_of(db: Session, obligations: list[Obligation]) -> dict[uuid.UUID, DueDateException]:
    ids = {o.exception_id for o in obligations if o.exception_id is not None}
    if not ids:
        return {}
    return {
        e.id: e for e in db.scalars(select(DueDateException).where(DueDateException.id.in_(ids)))
    }


def obligation_for(
    db: Session, organization_id: uuid.UUID, code: str, period_start: date, *, lock: bool = False
) -> Obligation | None:
    query = select(Obligation).where(
        Obligation.organization_id == organization_id,
        Obligation.code == code,
        Obligation.period_start == period_start,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def count_overdue(db: Session, organization_id: uuid.UUID, today: date) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                Obligation.organization_id == organization_id,
                Obligation.status == "pending",
                Obligation.due_date < today,
            )
        )
        or 0
    )


# --- Transiciones -------------------------------------------------------------------------


def _transition(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    obligation_id: uuid.UUID,
    *,
    expected: tuple[str, ...],
    verb: str,
    changes: dict[str, Any],
) -> Obligation:
    row = get_obligation(db, organization_id, obligation_id, lock=True)
    if row.status not in expected:
        raise Conflict(
            "OBLIGATION_INVALID_TRANSITION",
            f"La obligación está {_STATUS_TEXT[row.status]}: no se puede {_VERB_TEXT[verb]}.",
            details={"status": row.status},
        )
    before = snapshot(row, STATE_FIELDS)
    for name, value in changes.items():
        setattr(row, name, value)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "obligation",
        verb,
        row.id,
        before=before,
        after=snapshot(row, STATE_FIELDS),
    )
    db.commit()
    return row


_STATUS_TEXT = {
    "pending": "pendiente",
    "filed": "presentada",
    "paid": "pagada",
    "not_applicable": "marcada como «no aplica»",
}
_VERB_TEXT = {
    "filed": "marcar como presentada",
    "paid": "marcar como pagada",
    "not_applicable": "marcar como «no aplica»",
    "reopened": "reabrir",
}


def file(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    obligation_id: uuid.UUID,
    *,
    filed_on: date,
    filing_reference: str,
    declared_amount: Decimal | None,
    declared_credit_balance: Decimal | None,
) -> Obligation:
    return _transition(
        db,
        organization_id,
        actor_id,
        obligation_id,
        expected=("pending",),
        verb="filed",
        changes={
            "status": "filed",
            "filed_on": filed_on,
            "filing_reference": filing_reference,
            "declared_amount": declared_amount,
            "declared_credit_balance": declared_credit_balance,
            "reopen_reason": None,
        },
    )


def pay(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    obligation_id: uuid.UUID,
    *,
    paid_on: date,
    paid_amount: Decimal,
    transaction_id: uuid.UUID | None,
) -> Obligation:
    changes: dict[str, Any] = {"status": "paid", "paid_on": paid_on, "paid_amount": paid_amount}
    if transaction_id is not None:
        tx = business_transaction(db, organization_id, transaction_id)
        if tx.voided_at is not None:
            raise Conflict("TRANSACTION_VOIDED", "El movimiento está anulado.")
        if tx.amount >= 0:
            raise AppError(
                "PAYMENT_TRANSACTION_NOT_OUTFLOW",
                "El pago se vincula a un egreso (un movimiento con importe negativo).",
                status_code=422,
            )
        changes |= {
            "payment_transaction_id": tx.id,
            "payment_context_id": tx.context_id,
            "payment_context_kind": "business",
        }
    return _transition(
        db,
        organization_id,
        actor_id,
        obligation_id,
        expected=("filed",),
        verb="paid",
        changes=changes,
    )


def not_applicable(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    obligation_id: uuid.UUID,
    reason: str,
) -> Obligation:
    return _transition(
        db,
        organization_id,
        actor_id,
        obligation_id,
        expected=("pending",),
        verb="not_applicable",
        changes={
            "status": "not_applicable",
            "not_applicable_reason": reason,
            "not_applicable_auto": False,
        },
    )


def reopen(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    obligation_id: uuid.UUID,
    reason: str,
) -> Obligation:
    """`filed → pending` (rectificativa o error de carga). Reabrir el registro de
    comprobantes del mes desbloquea sus comprobantes (D-089)."""
    return _transition(
        db,
        organization_id,
        actor_id,
        obligation_id,
        expected=("filed",),
        verb="reopened",
        changes={
            "status": "pending",
            "filed_on": None,
            "filing_reference": None,
            "declared_amount": None,
            "declared_credit_balance": None,
            "reopen_reason": reason,
        },
    )


def set_calculated(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    obligation: Obligation,
    *,
    amount: Decimal,
    credit_balance: Decimal,
    source: dict[str, Any],
) -> Obligation:
    """Lleva un estimado (D-090) a `calculated_amount` de una obligación pendiente."""
    if obligation.status != "pending":
        raise Conflict(
            "OBLIGATION_FILED",
            f"La obligación está {_STATUS_TEXT[obligation.status]}: el estimado ya no se cambia.",
        )
    before = snapshot(obligation, ("calculated_amount", "calculated_credit_balance"))
    obligation.calculated_amount = amount
    obligation.calculated_credit_balance = credit_balance
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "obligation",
        "calculated",
        obligation.id,
        before=before,
        after=snapshot(obligation, ("calculated_amount", "calculated_credit_balance")) | source,
    )
    db.commit()
    return obligation
