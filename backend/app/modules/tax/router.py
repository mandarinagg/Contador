"""API de tributación (`/api/v1/tax`, FASE4_TRIBUTACION.md §3).

Lectura con `tax.read`; escritura con `tax.manage`; verificar reglas y el perfil, deprecar
reglas y cambiar el estado de un feriado, con `tax.verify` (D-094). Proponer un asiento
desde un comprobante crea un borrador contable: pide además `accounting.manage`.

Después de cambiar el perfil, una regla, un feriado o una excepción se sincroniza el
calendario de la organización (D-087): lo no presentado se recalcula.

Nada de esto presenta nada (regla madre): son borradores, estimaciones y avisos.
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, DbSession, require
from app.core.errors import AppError, Forbidden
from app.core.permissions import Perm
from app.modules.accounting.exports import XLSX_MEDIA_TYPE
from app.modules.accounting.models import JournalEntry
from app.modules.accounting.router import _entry_out
from app.modules.accounting.schemas import EntryOut
from app.modules.finance.service import paginate
from app.modules.organizations.models import Organization
from app.modules.tax import (
    alerts,
    exports,
    holidays,
    irp,
    obligations,
    profile,
    rule_params,
    rules,
    tax_settings,
    vat,
    voucher_entry,
    vouchers,
)
from app.modules.tax.common import pyg
from app.modules.tax.models import Obligation, RuleVersion, Voucher
from app.modules.tax.schemas import Direction as VoucherDirection
from app.modules.tax.schemas import (
    ExceptionIn,
    ExceptionOut,
    ExceptionUpdate,
    FileIn,
    HolidayIn,
    HolidayLoadOut,
    HolidayOut,
    HolidayUpdate,
    ObligationOut,
    ObligationStatus,
    PayIn,
    ProfileIn,
    ProfileObligationOut,
    ProfileOut,
    ProfileVerifyIn,
    ProfileVersionOut,
    ProposeEntryIn,
    ReasonIn,
    RuleBulkVerifyOut,
    RuleLeftPending,
    RuleLoadOut,
    RuleOut,
    RuleStatus,
    RuleVerifyIn,
    SettingsAccountOut,
    SettingsIn,
    SettingsOut,
    SyncOut,
    VoucherIn,
    VoucherOut,
    VoucherType,
    VoucherUpdate,
)

router = APIRouter(prefix="/tax", tags=["tributación"])

Reader = Annotated[AuthContext, Depends(require(Perm.TAX_READ))]
Manager = Annotated[AuthContext, Depends(require(Perm.TAX_MANAGE))]
Verifier = Annotated[AuthContext, Depends(require(Perm.TAX_VERIFY))]
EntryProposer = Annotated[AuthContext, Depends(require(Perm.TAX_MANAGE, Perm.ACCOUNTING_MANAGE))]
Limit = Annotated[int, Query(ge=1, le=200)]
Year = Annotated[int, Query(ge=2000, le=2100)]
Month = Annotated[int, Query(ge=1, le=12)]
Separator = Annotated[Literal["semicolon", "comma"], Query()]
FirstId = Annotated[int, Query(ge=1, le=99999)]


def today() -> date:
    """Fecha de hoy (punto único, para que las pruebas lo puedan fijar)."""
    return date.today()


def _sync(db: Session, auth: AuthContext) -> None:
    obligations.sync(db, auth.organization_id, auth.user_id, today=today())


def _file(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Reglas -----------------------------------------------------------------------------


def _rule_out(rule: RuleVersion) -> RuleOut:
    data = {name: getattr(rule, name) for name in RuleOut.model_fields if hasattr(rule, name)}
    data["used_by_calculations"] = rule_params.schema_for(rule.code) is not None
    data["parameters"] = rule_params.as_text(rule.parameters)
    reason = rules.unverifiable_reason(rule) if rule.validation_status == "pending" else None
    data["verifiable"] = rule.validation_status == "pending" and reason is None
    data["unverifiable_reason"] = reason
    return RuleOut.model_validate(data)


@router.get("/rules", response_model=list[RuleOut])
def list_rules(
    auth: Reader,
    db: DbSession,
    code: Annotated[str | None, Query(max_length=60)] = None,
    rule_status: Annotated[RuleStatus | None, Query(alias="status")] = None,
    at: date | None = None,
) -> list[RuleOut]:
    """Reglas (globales). `at`: solo las vigentes a esa fecha (no deprecadas)."""
    return [_rule_out(r) for r in rules.list_rules(db, code=code, status=rule_status, at=at)]


@router.post("/rules/load-candidates", response_model=RuleLoadOut)
def load_candidate_rules(auth: Manager, db: DbSession) -> RuleLoadOut:
    """Carga idempotente de las reglas candidatas empaquetadas (todas `pending`)."""
    result = rules.load_candidates(db, auth.organization_id, auth.user_id)
    _sync(db, auth)
    return RuleLoadOut(
        created=len(result.created),
        unchanged=len(result.unchanged),
        differing=result.differing,
        rejected=result.rejected,
        exceptions_created=result.exceptions_created,
        total=db.scalar(select(func.count()).select_from(RuleVersion)) or 0,
    )


@router.post("/rules/{rule_id}/verify", response_model=RuleOut)
def verify_rule(rule_id: uuid.UUID, body: RuleVerifyIn, auth: Verifier, db: DbSession) -> RuleOut:
    rule = rules.verify(
        db,
        auth.organization_id,
        auth.user_id,
        rule_id,
        review_note=body.review_note,
    )
    return _rule_out(rule)


@router.post("/rules/verify-verifiable", response_model=RuleBulkVerifyOut)
def verify_verifiable_rules(auth: Verifier, db: DbSession) -> RuleBulkVerifyOut:
    """CONTADOR AI verifica de una vez las pendientes con fuente oficial leída (D-120)."""
    result = rules.verify_verifiable(db, auth.organization_id, auth.user_id)
    return RuleBulkVerifyOut(
        verified=[f"{r.code} v{r.version}" for r in result.verified],
        left_pending=[
            RuleLeftPending(id=r.id, code=r.code, version=r.version, reason=reason)
            for r, reason in result.left_pending
        ],
    )


@router.post("/rules/{rule_id}/deprecate", response_model=RuleOut)
def deprecate_rule(rule_id: uuid.UUID, body: ReasonIn, auth: Verifier, db: DbSession) -> RuleOut:
    rule = rules.deprecate(db, auth.organization_id, auth.user_id, rule_id, body.reason)
    _sync(db, auth)
    return _rule_out(rule)


# --- Feriados -------------------------------------------------------------------------------


@router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(
    auth: Reader,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> list[HolidayOut]:
    return [HolidayOut.model_validate(h) for h in holidays.list_holidays(db, date_from, date_to)]


@router.post("/holidays/load-candidates", response_model=HolidayLoadOut)
def load_candidate_holidays(auth: Manager, db: DbSession) -> HolidayLoadOut:
    """Feriados de la investigación (Ley 7544/2025 y decretos conocidos), todos `pending`."""
    result = holidays.load_candidates(db, auth.organization_id, auth.user_id)
    db.commit()
    _sync(db, auth)
    return HolidayLoadOut(
        created=result.created, unchanged=result.unchanged, differing=result.differing or []
    )


@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def create_holiday(body: HolidayIn, auth: Manager, db: DbSession) -> HolidayOut:
    if body.source_url is None and body.legal_reference is None:
        raise AppError(
            "HOLIDAY_SOURCE_REQUIRED",
            "Un feriado lleva su fuente: la norma o la URL donde se publicó.",
            status_code=422,
        )
    holiday = holidays.create_holiday(db, auth.organization_id, auth.user_id, body.model_dump())
    db.commit()
    _sync(db, auth)
    return HolidayOut.model_validate(holiday)


@router.patch("/holidays/{holiday_id}", response_model=HolidayOut)
def update_holiday(
    holiday_id: uuid.UUID, body: HolidayUpdate, auth: Manager, db: DbSession
) -> HolidayOut:
    changes = body.model_dump(exclude_unset=True)
    if "validation_status" in changes and Perm.TAX_VERIFY.value not in auth.permissions:
        raise Forbidden(
            "FORBIDDEN",
            "Verificar un feriado es de quien tiene `tax.verify`.",
            details={"missing": [Perm.TAX_VERIFY.value]},
        )
    for key in ("day", "name", "validation_status"):
        if key in changes and changes[key] is None:
            raise AppError("FIELD_REQUIRED", f"`{key}` no puede quedar vacío.", status_code=422)
    holiday = holidays.update_holiday(db, auth.organization_id, auth.user_id, holiday_id, changes)
    db.commit()
    _sync(db, auth)
    return HolidayOut.model_validate(holiday)


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(holiday_id: uuid.UUID, auth: Manager, db: DbSession) -> Response:
    holidays.delete_holiday(db, auth.organization_id, auth.user_id, holiday_id)
    db.commit()
    _sync(db, auth)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Excepciones --------------------------------------------------------------------------


@router.get("/due-date-exceptions", response_model=list[ExceptionOut])
def list_exceptions(
    auth: Reader,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    active: bool | None = None,
) -> list[ExceptionOut]:
    return [
        ExceptionOut.model_validate(e)
        for e in holidays.list_exceptions(db, date_from, date_to, active)
    ]


@router.post(
    "/due-date-exceptions", response_model=ExceptionOut, status_code=status.HTTP_201_CREATED
)
def create_exception(body: ExceptionIn, auth: Manager, db: DbSession) -> ExceptionOut:
    exception = holidays.create_exception(db, auth.organization_id, auth.user_id, body.model_dump())
    db.commit()
    _sync(db, auth)
    return ExceptionOut.model_validate(exception)


@router.patch("/due-date-exceptions/{exception_id}", response_model=ExceptionOut)
def update_exception(
    exception_id: uuid.UUID, body: ExceptionUpdate, auth: Manager, db: DbSession
) -> ExceptionOut:
    changes = body.model_dump(exclude_unset=True)
    for key in ("due_month", "new_due_date", "legal_reference", "is_active", "ruc_digits"):
        if key in changes and changes[key] is None:
            raise AppError("FIELD_REQUIRED", f"`{key}` no puede quedar vacío.", status_code=422)
    exception = holidays.update_exception(
        db, auth.organization_id, auth.user_id, exception_id, changes
    )
    db.commit()
    _sync(db, auth)
    return ExceptionOut.model_validate(exception)


# --- Perfil -----------------------------------------------------------------------------


def _version_out(version: profile.ProfileVersion) -> ProfileVersionOut:
    p = version.profile
    return ProfileVersionOut(
        id=p.id,
        valid_from=p.valid_from,
        ire_regime=p.ire_regime,
        fiscal_close_month=p.fiscal_close_month,
        vat_taxpayer=p.vat_taxpayer,
        origin=p.origin,
        verified_by_name=p.verified_by_name,
        verified_license=p.verified_license,
        verified_document_reference=p.verified_document_reference,
        verified_at=p.verified_at,
        notes=p.notes,
        obligations=[
            ProfileObligationOut(
                code=o.code,
                registered_on=o.registered_on,
                supported=o.code in rule_params.RULE_BY_DNIT_CODE,
            )
            for o in version.obligations
        ],
    )


def _profile_out(db: Session, organization_id: uuid.UUID) -> ProfileOut:
    org = db.get(Organization, organization_id)
    assert org is not None
    history = profile.versions(db, organization_id)
    current = profile.vigente(history, today())
    return ProfileOut(
        ruc=org.ruc,
        ruc_check_digit=org.ruc_check_digit,
        current=_version_out(current) if current else None,
        history=[_version_out(v) for v in reversed(history)],
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(auth: Reader, db: DbSession) -> ProfileOut:
    """Perfil vigente hoy e historial (de la versión más nueva a la más vieja)."""
    return _profile_out(db, auth.organization_id)


@router.put("/profile", response_model=ProfileOut)
def put_profile(body: ProfileIn, auth: Manager, db: DbSession) -> ProfileOut:
    """Versión nueva desde `valid_from` (o corrección de la declarada con esa fecha)."""
    data = body.model_dump()
    profile.put_version(db, auth.organization_id, auth.user_id, data)
    db.commit()
    _sync(db, auth)
    return _profile_out(db, auth.organization_id)


@router.post("/profile/{profile_id}/verify", response_model=ProfileOut)
def verify_profile(
    profile_id: uuid.UUID, body: ProfileVerifyIn, auth: Verifier, db: DbSession
) -> ProfileOut:
    profile.verify(
        db,
        auth.organization_id,
        auth.user_id,
        profile_id,
        verified_document_reference=body.verified_document_reference,
    )
    return _profile_out(db, auth.organization_id)


# --- Obligaciones -----------------------------------------------------------------------


def _obligations_out(db: Session, rows: list[Obligation]) -> list[ObligationOut]:
    rule_map = obligations.rules_of(db, rows)
    exception_map = obligations.exceptions_of(db, rows)
    now_day = today()
    result = []
    for o in rows:
        applied_rules = [rule_map[o.rule_version_id]]
        if o.calendar_rule_version_id != o.rule_version_id:  # día fijo de la regla (D-142)
            applied_rules.append(rule_map[o.calendar_rule_version_id])
        exception = exception_map.get(o.exception_id) if o.exception_id else None
        result.append(
            ObligationOut(
                id=o.id,
                code=o.code,
                dnit_code=o.dnit_code,
                period_start=o.period_start,
                period_end=o.period_end,
                nominal_due_date=o.nominal_due_date,
                due_date=o.due_date,
                remind_by=o.remind_by,
                shift_explanation=alerts.shift_explanation(o),
                status=o.status,
                is_overdue=o.status == "pending" and o.due_date < now_day,
                calculated_amount=pyg(o.calculated_amount),
                calculated_credit_balance=pyg(o.calculated_credit_balance),
                filed_on=o.filed_on,
                filing_reference=o.filing_reference,
                declared_amount=pyg(o.declared_amount),
                declared_credit_balance=pyg(o.declared_credit_balance),
                paid_on=o.paid_on,
                paid_amount=pyg(o.paid_amount),
                payment_transaction_id=o.payment_transaction_id,
                not_applicable_reason=o.not_applicable_reason,
                not_applicable_auto=o.not_applicable_auto,
                reopen_reason=o.reopen_reason,
                exception=None
                if exception is None
                else {
                    "id": str(exception.id),
                    "new_due_date": exception.new_due_date.isoformat(),
                    "legal_reference": exception.legal_reference,
                    "source_url": exception.source_url,
                },
                rules_applied=[rules.applied(r) for r in applied_rules],
                rule_status=rules.worst_status(applied_rules),
            )
        )
    return result


def _obligation_out(db: Session, row: Obligation) -> ObligationOut:
    db.refresh(row)
    return _obligations_out(db, [row])[0]


@router.post("/obligations/sync", response_model=SyncOut)
def sync_obligations(auth: Manager, db: DbSession) -> SyncOut:
    """Genera las obligaciones que falten hasta 3 meses adelante (idempotente)."""
    result = obligations.sync(db, auth.organization_id, auth.user_id, today=today())
    return SyncOut(
        created=result.created,
        recalculated=result.recalculated,
        not_applicable=result.not_applicable,
        reactivated=result.reactivated,
        profile_missing=result.profile_missing,
        unsupported_codes=result.unsupported_codes,
        without_rule=result.without_rule,
    )


@router.get("/obligations", response_model=list[ObligationOut])
def list_obligations(
    auth: Reader,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    obligation_status: Annotated[ObligationStatus | None, Query(alias="status")] = None,
    code: Annotated[str | None, Query(max_length=60)] = None,
) -> list[ObligationOut]:
    """Por vencimiento. `status=overdue`: pendientes vencidas (derivado, D-087)."""
    rows = obligations.list_obligations(
        db,
        auth.organization_id,
        date_from=date_from,
        date_to=date_to,
        status=obligation_status,
        code=code,
        today=today(),
    )
    return _obligations_out(db, rows)


@router.post("/obligations/{obligation_id}/file", response_model=ObligationOut)
def file_obligation(
    obligation_id: uuid.UUID, body: FileIn, auth: Manager, db: DbSession
) -> ObligationOut:
    row = obligations.file(
        db,
        auth.organization_id,
        auth.user_id,
        obligation_id,
        filed_on=body.filed_on,
        filing_reference=body.filing_reference,
        declared_amount=_whole(body.declared_amount, "declared_amount"),
        declared_credit_balance=_whole(body.declared_credit_balance, "declared_credit_balance"),
    )
    return _obligation_out(db, row)


@router.post("/obligations/{obligation_id}/pay", response_model=ObligationOut)
def pay_obligation(
    obligation_id: uuid.UUID, body: PayIn, auth: Manager, db: DbSession
) -> ObligationOut:
    amount = _whole(body.paid_amount, "paid_amount")
    assert amount is not None
    row = obligations.pay(
        db,
        auth.organization_id,
        auth.user_id,
        obligation_id,
        paid_on=body.paid_on,
        paid_amount=amount,
        transaction_id=body.transaction_id,
    )
    return _obligation_out(db, row)


@router.post("/obligations/{obligation_id}/not-applicable", response_model=ObligationOut)
def obligation_not_applicable(
    obligation_id: uuid.UUID, body: ReasonIn, auth: Manager, db: DbSession
) -> ObligationOut:
    row = obligations.not_applicable(
        db, auth.organization_id, auth.user_id, obligation_id, body.reason
    )
    return _obligation_out(db, row)


@router.post("/obligations/{obligation_id}/reopen", response_model=ObligationOut)
def reopen_obligation(
    obligation_id: uuid.UUID, body: ReasonIn, auth: Manager, db: DbSession
) -> ObligationOut:
    row = obligations.reopen(db, auth.organization_id, auth.user_id, obligation_id, body.reason)
    return _obligation_out(db, row)


def _whole(value: Any, name: str) -> Any:
    """Guaraníes enteros y no negativos (los importes de las obligaciones)."""
    if value is None:
        return None
    if value < 0 or value != value.to_integral_value():
        raise AppError(
            "INVALID_AMOUNT",
            f"`{name}` va en guaraníes enteros y no negativos.",
            status_code=422,
        )
    return value.quantize(1)


# --- Comprobantes -----------------------------------------------------------------------


def _vouchers_out(db: Session, organization_id: uuid.UUID, rows: list[Voucher]) -> list[VoucherOut]:
    entry_map = vouchers.entries_of(db, rows)
    rule_ids = {v.vat_rule_version_id for v in rows if v.vat_rule_version_id is not None}
    rule_map = {
        r.id: r for r in db.scalars(select(RuleVersion).where(RuleVersion.id.in_(rule_ids)))
    }
    confirmed = vouchers.confirmed_months(
        db, organization_id, {v.issued_on.replace(day=1) for v in rows}
    )
    confirmed_years = vouchers.confirmed_years(
        db, organization_id, {v.issued_on.year for v in rows}
    )
    result = []
    for v in rows:
        entry = entry_map.get(v.journal_entry_id) if v.journal_entry_id else None
        # Un ingreso o un egreso no tiene regla de tasas (D-143).
        rule = rule_map.get(v.vat_rule_version_id) if v.vat_rule_version_id else None
        result.append(
            VoucherOut(
                id=v.id,
                direction=v.direction,
                voucher_type=v.voucher_type,
                is_electronic=v.is_electronic,
                cdc=v.cdc,
                timbrado=v.timbrado,
                number=v.number,
                issued_on=v.issued_on,
                counterparty_doc_type=v.counterparty_doc_type,
                counterparty_ruc=v.counterparty_ruc,
                counterparty_ruc_dv=v.counterparty_ruc_dv,
                counterparty_document=v.counterparty_document,
                counterparty_name=v.counterparty_name,
                counterparty_review_required=vouchers.legacy_ruc(v.counterparty_ruc),
                condition=v.condition,
                currency=v.currency,
                fx_rate=None if v.fx_rate is None else format(v.fx_rate.normalize(), "f"),
                foreign_total=None if v.foreign_total is None else format(v.foreign_total, "f"),
                taxed_10=pyg(v.taxed_10) or "0",
                taxed_5=pyg(v.taxed_5) or "0",
                exempt=pyg(v.exempt) or "0",
                total=pyg(vouchers.total_of(v)) or "0",
                vat_10=pyg(v.vat_10) or "0",
                vat_5=pyg(v.vat_5) or "0",
                imputes_vat=v.imputes_vat,
                imputes_ire=v.imputes_ire,
                imputes_irp=v.imputes_irp,
                related_voucher_id=v.related_voucher_id,
                account_number=v.account_number,
                bank_name=v.bank_name,
                ips_employer_number=v.ips_employer_number,
                document_description=v.document_description,
                related_number=v.related_number,
                related_timbrado=v.related_timbrado,
                finance_counterparty_id=v.finance_counterparty_id,
                transaction_id=v.transaction_id,
                journal_entry_id=v.journal_entry_id,
                journal_entry_status=entry.status if entry is not None else None,
                period_confirmed=v.issued_on.replace(day=1) in confirmed
                or v.issued_on.year in confirmed_years,
                notes=v.notes,
                voided_at=v.voided_at,
                void_reason=v.void_reason,
                created_at=v.created_at,
                rules_applied=[rules.applied(rule)] if rule is not None else [],
                rule_status=rule.validation_status if rule is not None else None,
            )
        )
    return result


def _voucher_out(db: Session, organization_id: uuid.UUID, voucher: Voucher) -> VoucherOut:
    db.refresh(voucher)
    return _vouchers_out(db, organization_id, [voucher])[0]


@router.get("/vouchers", response_model=list[VoucherOut])
def list_vouchers(
    auth: Reader,
    db: DbSession,
    limit: Limit = 50,
    before: uuid.UUID | None = None,
    month: Annotated[date | None, Query(description="Cualquier día del mes")] = None,
    year: Year | None = None,
    direction: VoucherDirection | None = None,
    voucher_type: VoucherType | None = None,
    counterparty_ruc: Annotated[str | None, Query(max_length=9)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    voided: Literal["exclude", "include", "only"] = "exclude",
) -> list[VoucherOut]:
    """Más nuevos primero. Cursor: `before` = id del último de la página anterior."""
    query = vouchers.list_query(
        auth.organization_id,
        month=month,
        year=year,
        direction=direction,
        voucher_type=voucher_type,
        counterparty_ruc=counterparty_ruc,
        q=q,
        voided=voided,
    )
    rows = list(db.scalars(paginate(query, Voucher.id, before).limit(limit)))
    return _vouchers_out(db, auth.organization_id, rows)


@router.post("/vouchers", response_model=VoucherOut, status_code=status.HTTP_201_CREATED)
def create_voucher(body: VoucherIn, auth: Manager, db: DbSession) -> VoucherOut:
    voucher = vouchers.create(db, auth.organization_id, auth.user_id, body.model_dump())
    return _voucher_out(db, auth.organization_id, voucher)


@router.get("/vouchers/export")
def export_vouchers(
    auth: Reader,
    db: DbSession,
    year: Year,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    direction: Literal["purchase", "sale"] | None = None,
    export_format: Annotated[Literal["xlsx", "marangatu"], Query(alias="format")] = "xlsx",
    separator: Separator = "semicolon",
    first_id: FirstId = 1,
    limit: Annotated[int | None, Query(ge=1, le=exports.MAX_ROWS)] = None,
) -> Response:
    """`xlsx`: libro de compras y ventas. `marangatu`: archivo de importación (borrador,
    D-096); mirá antes `/vouchers/export/marangatu-preview`."""
    if export_format == "marangatu":
        if month is None:
            raise AppError(
                "MONTH_REQUIRED",
                "El archivo de importación es de un mes (obligación 955): indicá `month`.",
                status_code=422,
            )
        plan = exports.marangatu_plan(
            db, auth.organization_id, year, month, separator=separator, limit=limit
        )
        name, content = exports.marangatu_file(plan, first_id)
        return _file(content, name, "application/zip")
    content = exports.vouchers_xlsx(
        db, auth.organization_id, year=year, month=month, direction=direction
    )
    which = {"purchase": "compras", "sale": "ventas"}.get(direction or "", "comprobantes")
    period = f"{year}-{month:02d}" if month else str(year)
    return _file(content, f"registro-{which}-{period}.xlsx", XLSX_MEDIA_TYPE)


@router.get("/vouchers/export/marangatu-preview")
def preview_marangatu(
    auth: Reader,
    db: DbSession,
    year: Year,
    month: Month,
    separator: Separator = "semicolon",
    first_id: FirstId = 1,
    limit: Annotated[int | None, Query(ge=1, le=exports.MAX_ROWS)] = None,
) -> dict[str, Any]:
    """Qué iría en el archivo de importación: filas, lotes, excluidos (electrónicos y sin
    imputación) y avisos. El archivo es un borrador."""
    plan = exports.marangatu_plan(
        db, auth.organization_id, year, month, separator=separator, limit=limit
    )
    return exports.marangatu_preview(plan, first_id)


@router.get("/vouchers/export/annual")
def export_annual_register(
    auth: Reader,
    db: DbSession,
    year: Year,
    separator: Separator = "semicolon",
    first_id: FirstId = 1,
    limit: Annotated[int | None, Query(ge=1, le=exports.MAX_ROWS)] = None,
) -> Response:
    """Archivo de importación del registro anual (956, D-143): compras, ventas, ingresos y
    egresos del año, `<RUC>_REG_<AAAA>_<id>.zip`. Borrador, como el mensual."""
    plan = exports.annual_plan(db, auth.organization_id, year, separator=separator, limit=limit)
    name, content = exports.marangatu_file(plan, first_id)
    return _file(content, name, "application/zip")


@router.get("/vouchers/export/annual-preview")
def preview_annual_register(
    auth: Reader,
    db: DbSession,
    year: Year,
    separator: Separator = "semicolon",
    first_id: FirstId = 1,
    limit: Annotated[int | None, Query(ge=1, le=exports.MAX_ROWS)] = None,
) -> dict[str, Any]:
    """Qué iría en el archivo anual (956): filas, lotes, excluidos y avisos."""
    plan = exports.annual_plan(db, auth.organization_id, year, separator=separator, limit=limit)
    return exports.marangatu_preview(plan, first_id)


@router.get("/vouchers/{voucher_id}", response_model=VoucherOut)
def get_voucher(voucher_id: uuid.UUID, auth: Reader, db: DbSession) -> VoucherOut:
    voucher = vouchers.get_voucher(db, auth.organization_id, voucher_id)
    return _vouchers_out(db, auth.organization_id, [voucher])[0]


@router.patch("/vouchers/{voucher_id}", response_model=VoucherOut)
def update_voucher(
    voucher_id: uuid.UUID, body: VoucherUpdate, auth: Manager, db: DbSession
) -> VoucherOut:
    changes = body.model_dump(exclude_unset=True)
    # El timbrado, el número y la contraparte pueden faltar en un ingreso o un egreso: los
    # controla el servicio según el registro (D-143).
    for key in (
        "voucher_type",
        "is_electronic",
        "issued_on",
        "condition",
        "currency",
        "imputes_vat",
        "imputes_ire",
        "imputes_irp",
    ):
        if key in changes and changes[key] is None:
            raise AppError("FIELD_REQUIRED", f"`{key}` no puede quedar vacío.", status_code=422)
    voucher = vouchers.update(db, auth.organization_id, auth.user_id, voucher_id, changes)
    return _voucher_out(db, auth.organization_id, voucher)


@router.post("/vouchers/{voucher_id}/void", response_model=VoucherOut)
def void_voucher(voucher_id: uuid.UUID, body: ReasonIn, auth: Manager, db: DbSession) -> VoucherOut:
    voucher = vouchers.void(db, auth.organization_id, auth.user_id, voucher_id, body.reason)
    return _voucher_out(db, auth.organization_id, voucher)


@router.post(
    "/vouchers/{voucher_id}/propose-entry",
    response_model=EntryOut,
    status_code=status.HTTP_201_CREATED,
)
def propose_entry(
    voucher_id: uuid.UUID, body: ProposeEntryIn, auth: EntryProposer, db: DbSession
) -> EntryOut:
    """Borrador contable desde el comprobante (D-091). Nunca contabiliza."""
    entry: JournalEntry = voucher_entry.propose(
        db, auth.organization_id, auth.user_id, voucher_id, body.model_dump()
    )
    return _entry_out(db, auth.organization_id, entry)


# --- IVA --------------------------------------------------------------------------------


@router.get("/vat/{year}/{month}")
def vat_estimate(
    year: int,
    month: int,
    auth: Reader,
    db: DbSession,
    export_format: Annotated[Literal["json", "xlsx"], Query(alias="format")] = "json",
) -> Any:
    """Estimación del IVA del mes y borrador del Formulario 120 (no es una declaración)."""
    result = vat.estimate(db, auth.organization_id, year, month)
    if export_format == "xlsx":
        content = exports.vat_xlsx(db, auth.organization_id, result)
        return _file(content, f"iva-{year}-{month:02d}.xlsx", XLSX_MEDIA_TYPE)
    return result


@router.post("/vat/{year}/{month}/apply", response_model=ObligationOut)
def vat_apply(year: int, month: int, auth: Manager, db: DbSession) -> ObligationOut:
    """Lleva el estimado a `calculated_amount` de la obligación IVA del mes."""
    obligation, _ = vat.apply(db, auth.organization_id, auth.user_id, year, month)
    return _obligation_out(db, obligation)


# --- IRP ---------------------------------------------------------------------------------


@router.get("/irp/{year}")
def irp_estimate(
    year: int,
    auth: Reader,
    db: DbSession,
    export_format: Annotated[Literal["json", "xlsx"], Query(alias="format")] = "json",
) -> Any:
    """Borrador del IRP-RSP del año y del Formulario 515 (no es una declaración, D-144)."""
    result = irp.estimate(db, auth.organization_id, year)
    if export_format == "xlsx":
        content = exports.irp_xlsx(db, auth.organization_id, result)
        return _file(content, f"irp-{year}.xlsx", XLSX_MEDIA_TYPE)
    return result


# --- Avisos y configuración ---------------------------------------------------------------


@router.get("/alerts")
def get_alerts(auth: Reader, db: DbSession, as_of: date | None = None) -> dict[str, Any]:
    """Avisos calculados en el momento (D-092). `as_of`: otra fecha de referencia."""
    return alerts.compute(db, auth.organization_id, as_of or today())


def _settings_out(db: Session, organization_id: uuid.UUID) -> SettingsOut:
    current = tax_settings.effective(db, organization_id)
    accounts = []
    for name, (default, _, label) in tax_settings.ACCOUNT_FIELDS.items():
        account = current.effective[name]
        accounts.append(
            SettingsAccountOut(
                field=name,
                label=label,
                default_code=default,
                configured_id=current.configured[name],
                effective_id=account.id if account else None,
                effective_code=account.code if account else None,
                effective_name=account.name if account else None,
            )
        )
    return SettingsOut(accounts=accounts, alert_days=current.alert_days)


@router.get("/settings", response_model=SettingsOut)
def get_settings(auth: Reader, db: DbSession) -> SettingsOut:
    return _settings_out(db, auth.organization_id)


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, auth: Manager, db: DbSession) -> SettingsOut:
    """Solo cambian los campos que llegan; `null` en una cuenta vuelve a la del plan."""
    changes = body.model_dump(exclude_unset=True)
    if "alert_days" in changes and changes["alert_days"] is None:
        raise AppError("FIELD_REQUIRED", "`alert_days` no puede quedar vacío.", status_code=422)
    tax_settings.update(db, auth.organization_id, auth.user_id, changes)
    return _settings_out(db, auth.organization_id)
