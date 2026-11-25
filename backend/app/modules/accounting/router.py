"""API de contabilidad (`/api/v1/accounting`). Especificación: FASE3_CONTABILIDAD.md §4.

Permisos (D-043): `accounting.read` para leer, `accounting.manage` para el plan de cuentas
y los borradores, `accounting.post` para contabilizar, revertir, cerrar, reabrir y validar
el plan. La contabilidad es de la organización activa (D-035).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, DbSession, require
from app.core.errors import AppError
from app.core.permissions import Perm
from app.modules.accounting import (
    chart,
    closing,
    entries,
    exports,
    finance_link,
    periods,
    reports,
)
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import pyg
from app.modules.accounting.models import (
    AccountingSettings,
    CostCenter,
    FiscalYear,
    JournalEntry,
    JournalLine,
    LedgerAccount,
)
from app.modules.accounting.schemas import (
    BalanceSheetOut,
    ChartOut,
    CostCenterColumnOut,
    EntryIn,
    EntryKind,
    EntryLineOut,
    EntryOut,
    EntryStatus,
    FiscalYearCreate,
    FiscalYearOut,
    FromTransactionIn,
    IncomeStatementOut,
    JournalReportOut,
    LedgerAccountCreate,
    LedgerAccountOut,
    LedgerAccountUpdate,
    LedgerMovementOut,
    LedgerReportOut,
    PeriodOut,
    ReasonIn,
    ReverseIn,
    SettingsOut,
    SettingsUpdate,
    StatementNodeOut,
    TrialBalanceOut,
    TrialRowOut,
)
from app.modules.finance.money import format_amount
from app.modules.identity.models import User

router = APIRouter(prefix="/accounting", tags=["accounting"])

Reader = Annotated[AuthContext, Depends(require(Perm.ACCOUNTING_READ))]
Manager = Annotated[AuthContext, Depends(require(Perm.ACCOUNTING_MANAGE))]
Poster = Annotated[AuthContext, Depends(require(Perm.ACCOUNTING_POST))]
Limit = Annotated[int, Query(ge=1, le=200)]
ReportLimit = Annotated[int, Query(ge=1, le=1000)]
Before = Annotated[uuid.UUID | None, Query()]
From = Annotated[date, Query(alias="from")]
To = Annotated[date, Query(alias="to")]
# D-063: `?format=xlsx` devuelve el reporte como planilla.
Format = Annotated[Literal["json", "xlsx"], Query(alias="format")]


# --- Conversión a la salida (importes siempre como string) ------------------------------


def _settings_out(settings: AccountingSettings | None) -> SettingsOut:
    if settings is None:
        return SettingsOut(
            chart_status="none",
            chart_validated_by_name=None,
            chart_validated_reference=None,
            chart_validated_at=None,
            retained_earnings_account_id=None,
        )
    return SettingsOut(
        chart_status=settings.chart_status,
        chart_validated_by_name=settings.chart_validated_by_name,
        chart_validated_reference=settings.chart_validated_reference,
        chart_validated_at=settings.chart_validated_at,
        retained_earnings_account_id=settings.retained_earnings_account_id,
        asset_disposal_account_id=settings.asset_disposal_account_id,
        cost_centers_required=settings.cost_centers_required,
        default_asset_start_rule=settings.default_asset_start_rule,
    )


def _xlsx(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=exports.XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def user_names(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Nombre visible de los usuarios (P-10): solo `full_name`, nada más del usuario."""
    if not user_ids:
        return {}
    rows = db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
    return {user_id: name for user_id, name in rows}


def _account_out(
    account: LedgerAccount,
    *,
    in_use: bool,
    balance: Decimal | None = None,
    children: list[LedgerAccountOut] | None = None,
) -> LedgerAccountOut:
    return LedgerAccountOut(
        id=account.id,
        code=account.code,
        name=account.name,
        kind=account.kind,
        normal_side=account.normal_side,
        is_postable=account.is_postable,
        parent_id=account.parent_id,
        origin=account.origin,
        note=account.note,
        archived_at=account.archived_at,
        in_use=in_use,
        balance=pyg(balance) if balance is not None else None,
        children=children,
    )


def _node_out(node: chart.Node, used: set[uuid.UUID], with_balance: bool) -> LedgerAccountOut:
    return _account_out(
        node.account,
        in_use=node.account.id in used,
        balance=node.amount if with_balance else None,
        children=[_node_out(c, used, with_balance) for c in node.children],
    )


def _flat(node: chart.Node, used: set[uuid.UUID], with_balance: bool) -> list[LedgerAccountOut]:
    rows = [
        _account_out(
            node.account,
            in_use=node.account.id in used,
            balance=node.amount if with_balance else None,
        )
    ]
    for child in node.children:
        rows.extend(_flat(child, used, with_balance))
    return rows


def _fiscal_year_out(db: Session, years: list[FiscalYear]) -> list[FiscalYearOut]:
    by_year = periods.periods_of(db, [y.id for y in years])
    return [
        FiscalYearOut(
            id=y.id,
            start_date=y.start_date,
            end_date=y.end_date,
            status=y.status,
            closed_at=y.closed_at,
            closed_by=y.closed_by,
            closing_entry_id=y.closing_entry_id,
            last_entry_number=y.last_entry_number,
            periods=[PeriodOut.model_validate(p) for p in by_year[y.id]],
        )
        for y in years
    ]


def _line_out(
    line: JournalLine, account: LedgerAccount, centers: dict[uuid.UUID, CostCenter]
) -> EntryLineOut:
    return EntryLineOut(
        id=line.id,
        line_no=line.line_no,
        account_id=line.account_id,
        account_code=account.code,
        account_name=account.name,
        debit=pyg(line.debit),
        credit=pyg(line.credit),
        description=line.description,
        fx_currency=line.fx_currency,
        fx_amount=(
            format_amount(line.fx_amount, line.fx_currency)
            if line.fx_amount is not None and line.fx_currency is not None
            else None
        ),
        fx_rate=format(line.fx_rate.normalize(), "f") if line.fx_rate is not None else None,
        cost_center_id=line.cost_center_id,
        cost_center_code=(
            centers[line.cost_center_id].code if line.cost_center_id is not None else None
        ),
    )


def _entries_out(
    db: Session, organization_id: uuid.UUID, items: list[JournalEntry], *, with_lines: bool
) -> list[EntryOut]:
    ids = [e.id for e in items]
    totals = entries.totals_of(db, ids)
    reversals = entries.reversed_by(db, ids)
    lines = entries.lines_of(db, ids) if with_lines else {}
    accounts = (
        entries.account_map(
            db, organization_id, {line.account_id for ls in lines.values() for line in ls}
        )
        if with_lines
        else {}
    )
    center_ids = {
        line.cost_center_id
        for ls in lines.values()
        for line in ls
        if line.cost_center_id is not None
    }
    centers = (
        {c.id: c for c in db.scalars(select(CostCenter).where(CostCenter.id.in_(center_ids)))}
        if center_ids
        else {}
    )
    names = user_names(
        db,
        {e.created_by for e in items} | {e.posted_by for e in items if e.posted_by is not None},
    )
    result = []
    for entry in items:
        debit, credit = totals.get(entry.id, (ZERO, ZERO))
        result.append(
            EntryOut(
                id=entry.id,
                fiscal_year_id=entry.fiscal_year_id,
                entry_date=entry.entry_date,
                number=entry.number,
                status=entry.status,
                kind=entry.kind,
                description=entry.description,
                document_reference=entry.document_reference,
                reverses_entry_id=entry.reverses_entry_id,
                reversed_by_entry_id=reversals.get(entry.id),
                source_transaction_id=entry.source_transaction_id,
                source_context_id=entry.source_context_id,
                total_debit=pyg(debit),
                total_credit=pyg(credit),
                balanced=debit == credit and debit > 0,
                created_by=entry.created_by,
                created_by_name=names.get(entry.created_by),
                created_at=entry.created_at,
                posted_by=entry.posted_by,
                posted_by_name=names.get(entry.posted_by) if entry.posted_by else None,
                posted_at=entry.posted_at,
                discarded_by=entry.discarded_by,
                discarded_at=entry.discarded_at,
                discard_reason=entry.discard_reason,
                lines=(
                    [
                        _line_out(line, accounts[line.account_id], centers)
                        for line in lines[entry.id]
                    ]
                    if with_lines
                    else None
                ),
            )
        )
    return result


def _entry_out(db: Session, organization_id: uuid.UUID, entry: JournalEntry) -> EntryOut:
    return _entries_out(db, organization_id, [entry], with_lines=True)[0]


def _statement_out(
    node: chart.Node, columns: dict[uuid.UUID, list[Decimal]] | None = None
) -> StatementNodeOut:
    return StatementNodeOut(
        account_id=node.account.id,
        code=node.account.code,
        name=node.account.name,
        kind=node.account.kind,
        is_postable=node.account.is_postable,
        amount=pyg(node.amount),
        children=[_statement_out(c, columns) for c in node.children],
        column_amounts=(
            [pyg(a) for a in columns.get(node.account.id, [])] if columns is not None else None
        ),
    )


# --- Plan de cuentas ----------------------------------------------------------------------


@router.get("/chart", response_model=ChartOut)
def get_chart(
    auth: Reader,
    db: DbSession,
    flat: bool = False,
    balance_at: date | None = None,
) -> ChartOut:
    """Árbol por código (o lista plana con `?flat=true`) y el estado del plan."""
    roots, used = chart.chart_tree(db, auth.organization_id, balance_at)
    with_balance = balance_at is not None
    accounts = (
        [row for root in roots for row in _flat(root, used, with_balance)]
        if flat
        else [_node_out(root, used, with_balance) for root in roots]
    )
    settings = _settings_out(chart.get_settings(db, auth.organization_id))
    return ChartOut(**settings.model_dump(), balance_at=balance_at, accounts=accounts)


@router.post(
    "/chart/load-proposed",
    response_model=list[LedgerAccountOut],
    status_code=status.HTTP_201_CREATED,
)
def load_proposed_chart(auth: Manager, db: DbSession) -> list[LedgerAccountOut]:
    """Carga el plan propuesto (RG 49/2014, sin validar). 409 si ya hay cuentas."""
    created = chart.load_proposed(db, auth.organization_id, auth.user_id)
    return [_account_out(a, in_use=False) for a in created]


@router.post(
    "/chart/accounts", response_model=LedgerAccountOut, status_code=status.HTTP_201_CREATED
)
def create_ledger_account(
    body: LedgerAccountCreate, auth: Manager, db: DbSession
) -> LedgerAccountOut:
    account = chart.create_account(db, auth.organization_id, auth.user_id, body.model_dump())
    return _account_out(account, in_use=False)


@router.patch("/chart/accounts/{account_id}", response_model=LedgerAccountOut)
def update_ledger_account(
    account_id: uuid.UUID, body: LedgerAccountUpdate, auth: Manager, db: DbSession
) -> LedgerAccountOut:
    account = chart.update_account(
        db, auth.organization_id, auth.user_id, account_id, body.model_dump(exclude_unset=True)
    )
    return _account_out(account, in_use=chart.has_lines(db, account.id))


@router.post("/chart/validate", response_model=SettingsOut)
def validate_chart(auth: Poster, db: DbSession) -> SettingsOut:
    """Marca el plan como validado por CONTADOR AI (D-038, D-120); sin nombre ni matrícula."""
    settings = chart.validate_chart(db, auth.organization_id, auth.user_id)
    return _settings_out(settings)


@router.post("/chart/invalidate", response_model=SettingsOut)
def invalidate_chart(auth: Poster, db: DbSession) -> SettingsOut:
    return _settings_out(chart.invalidate_chart(db, auth.organization_id, auth.user_id))


@router.get("/settings", response_model=SettingsOut)
def get_settings(auth: Reader, db: DbSession) -> SettingsOut:
    return _settings_out(chart.get_settings(db, auth.organization_id))


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, auth: Poster, db: DbSession) -> SettingsOut:
    """Cambia solo los campos que llegan: cuenta de resultados del cierre (patrimonio), cuenta
    de la baja de bienes (ingreso o gasto), centros obligatorios e inicio por defecto."""
    settings = chart.update_settings(
        db, auth.organization_id, auth.user_id, body.model_dump(exclude_unset=True)
    )
    return _settings_out(settings)


# --- Ejercicios y períodos ----------------------------------------------------------------


@router.get("/fiscal-years", response_model=list[FiscalYearOut])
def list_fiscal_years(auth: Reader, db: DbSession) -> list[FiscalYearOut]:
    """Todos los ejercicios (más nuevos primero) con sus períodos."""
    return _fiscal_year_out(db, periods.list_fiscal_years(db, auth.organization_id))


@router.post("/fiscal-years", response_model=FiscalYearOut, status_code=status.HTTP_201_CREATED)
def create_fiscal_year(body: FiscalYearCreate, auth: Poster, db: DbSession) -> FiscalYearOut:
    if body.year is not None and (body.start_date is None and body.end_date is None):
        start, end = date(body.year, 1, 1), date(body.year, 12, 31)
    elif body.year is None and body.start_date is not None and body.end_date is not None:
        start, end = body.start_date, body.end_date
    else:
        raise AppError(
            "FISCAL_YEAR_INVALID",
            "Indicá el año (`year`, ejercicio = año civil) o las dos fechas (`start_date` y "
            "`end_date`), no ambos.",
            status_code=422,
        )
    year = periods.create_fiscal_year(
        db, auth.organization_id, auth.user_id, start_date=start, end_date=end
    )
    return _fiscal_year_out(db, [year])[0]


@router.get("/fiscal-years/{fiscal_year_id}", response_model=FiscalYearOut)
def get_fiscal_year(fiscal_year_id: uuid.UUID, auth: Reader, db: DbSession) -> FiscalYearOut:
    year = periods.get_fiscal_year(db, auth.organization_id, fiscal_year_id)
    return _fiscal_year_out(db, [year])[0]


@router.post("/fiscal-years/{fiscal_year_id}/close", response_model=FiscalYearOut)
def close_fiscal_year(fiscal_year_id: uuid.UUID, auth: Poster, db: DbSession) -> FiscalYearOut:
    """Refundición de resultados y cierre definitivo del ejercicio (BR-ACC-12)."""
    year = closing.close_fiscal_year(db, auth.organization_id, auth.user_id, fiscal_year_id)
    return _fiscal_year_out(db, [year])[0]


@router.post("/periods/{period_id}/close", response_model=PeriodOut)
def close_period(period_id: uuid.UUID, auth: Poster, db: DbSession) -> PeriodOut:
    period = periods.close_period(db, auth.organization_id, auth.user_id, period_id)
    return PeriodOut.model_validate(period)


@router.post("/periods/{period_id}/reopen", response_model=PeriodOut)
def reopen_period(period_id: uuid.UUID, body: ReasonIn, auth: Poster, db: DbSession) -> PeriodOut:
    period = periods.reopen_period(db, auth.organization_id, auth.user_id, period_id, body.reason)
    return PeriodOut.model_validate(period)


# --- Asientos -----------------------------------------------------------------------------


@router.get("/entries", response_model=list[EntryOut])
def list_entries(
    auth: Reader,
    db: DbSession,
    limit: Limit = 50,
    before: Before = None,
    fiscal_year_id: uuid.UUID | None = None,
    entry_status: Annotated[EntryStatus | None, Query(alias="status")] = None,
    kind: EntryKind | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    account_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[EntryOut]:
    """Más recientes primero (fecha, id), sin líneas. Cursor: `before` = id del último."""
    filters = entries.EntryFilters(
        fiscal_year_id=fiscal_year_id,
        status=entry_status,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        q=q,
    )
    rows = entries.list_entries(db, auth.organization_id, filters, limit=limit, before=before)
    return _entries_out(db, auth.organization_id, rows, with_lines=False)


@router.post("/entries", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: EntryIn, auth: Manager, db: DbSession) -> EntryOut:
    """Borrador con líneas (puede estar desbalanceado mientras sea borrador)."""
    data = body.model_dump()
    entry = entries.create_draft(db, auth.organization_id, auth.user_id, data)
    return _entry_out(db, auth.organization_id, entry)


@router.post(
    "/entries/from-transaction/{transaction_id}",
    response_model=EntryOut,
    status_code=status.HTTP_201_CREATED,
)
def propose_from_transaction(
    transaction_id: uuid.UUID,
    auth: Manager,
    db: DbSession,
    body: FromTransactionIn | None = None,
) -> EntryOut:
    """Borrador propuesto desde un movimiento de la empresa (D-041). Nunca contabiliza."""
    body = body or FromTransactionIn()
    entry = finance_link.propose_from_transaction(
        db,
        auth.organization_id,
        auth.user_id,
        transaction_id,
        fx_rate=body.fx_rate,
        amount_pyg=body.amount_pyg,
    )
    return _entry_out(db, auth.organization_id, entry)


@router.get("/entries/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: uuid.UUID, auth: Reader, db: DbSession) -> EntryOut:
    return _entry_out(
        db, auth.organization_id, entries.get_entry(db, auth.organization_id, entry_id)
    )


@router.patch("/entries/{entry_id}", response_model=EntryOut)
def update_entry(entry_id: uuid.UUID, body: EntryIn, auth: Manager, db: DbSession) -> EntryOut:
    """Reemplaza cabecera y líneas, solo en borrador (409 si no)."""
    entry = entries.update_draft(
        db, auth.organization_id, auth.user_id, entry_id, body.model_dump()
    )
    return _entry_out(db, auth.organization_id, entry)


@router.post("/entries/{entry_id}/post", response_model=EntryOut)
def post_entry(entry_id: uuid.UUID, auth: Poster, db: DbSession) -> EntryOut:
    """Valida y contabiliza; asigna el número correlativo del ejercicio."""
    entry = entries.post_entry(db, auth.organization_id, auth.user_id, entry_id)
    return _entry_out(db, auth.organization_id, entry)


@router.post("/entries/{entry_id}/reverse", response_model=EntryOut)
def reverse_entry(entry_id: uuid.UUID, body: ReverseIn, auth: Poster, db: DbSession) -> EntryOut:
    """Contabiliza la reversión (que devuelve) y deja el original `reversed`."""
    reversal = entries.reverse_entry(
        db, auth.organization_id, auth.user_id, entry_id, reason=body.reason, on=body.on
    )
    return _entry_out(db, auth.organization_id, reversal)


@router.post("/entries/{entry_id}/discard", response_model=EntryOut)
def discard_entry(entry_id: uuid.UUID, body: ReasonIn, auth: Manager, db: DbSession) -> EntryOut:
    entry = entries.discard_draft(db, auth.organization_id, auth.user_id, entry_id, body.reason)
    return _entry_out(db, auth.organization_id, entry)


# --- Reportes -----------------------------------------------------------------------------


@router.get("/reports/journal", response_model=JournalReportOut)
def journal_report(
    auth: Reader,
    db: DbSession,
    date_from: From,
    date_to: To,
    limit: ReportLimit = 200,
    after: Annotated[uuid.UUID | None, Query()] = None,
    fmt: Format = "json",
) -> JournalReportOut | Response:
    """Libro diario por fecha y número. Cursor: `after` = id del último asiento recibido.
    Con `?format=xlsx`, el diario completo (sin paginar)."""
    if fmt == "xlsx":
        content = exports.journal_xlsx(
            db,
            auth.organization_id,
            date_from,
            date_to,
            chart.chart_status(db, auth.organization_id),
        )
        return _xlsx(content, f"libro-diario-{date_from}-{date_to}.xlsx")
    page = reports.journal(db, auth.organization_id, date_from, date_to, limit=limit, after=after)
    return JournalReportOut(
        chart_status=chart.chart_status(db, auth.organization_id),
        date_from=date_from,
        date_to=date_to,
        total_debit=pyg(page.total_debit),
        total_credit=pyg(page.total_credit),
        entries=_entries_out(db, auth.organization_id, page.entries, with_lines=True),
        next_cursor=page.entries[-1].id if len(page.entries) == limit else None,
    )


@router.get("/reports/ledger/{account_id}", response_model=LedgerReportOut)
def ledger_report(
    account_id: uuid.UUID,
    auth: Reader,
    db: DbSession,
    date_from: From,
    date_to: To,
    limit: ReportLimit = 200,
    after: Annotated[uuid.UUID | None, Query()] = None,
    fmt: Format = "json",
) -> LedgerReportOut | Response:
    """Libro mayor. Cursor: `after` = `line_id` del último movimiento recibido. Con
    `?format=xlsx`, el mayor completo (sin paginar)."""
    if fmt == "xlsx":
        content = exports.ledger_xlsx(
            db,
            auth.organization_id,
            account_id,
            date_from,
            date_to,
            chart.chart_status(db, auth.organization_id),
        )
        return _xlsx(content, f"libro-mayor-{date_from}-{date_to}.xlsx")
    report = reports.ledger(
        db, auth.organization_id, account_id, date_from, date_to, limit=limit, after=after
    )
    return LedgerReportOut(
        chart_status=chart.chart_status(db, auth.organization_id),
        account=_account_out(report.account, in_use=chart.has_lines(db, report.account.id)),
        date_from=date_from,
        date_to=date_to,
        opening_balance=pyg(report.opening_balance),
        total_debit=pyg(report.total_debit),
        total_credit=pyg(report.total_credit),
        closing_balance=pyg(report.closing_balance),
        movements=[
            LedgerMovementOut(
                line_id=m.line_id,
                entry_id=m.entry_id,
                number=m.number,
                entry_date=m.entry_date,
                entry_description=m.entry_description,
                line_description=m.line_description,
                document_reference=m.document_reference,
                debit=pyg(m.debit),
                credit=pyg(m.credit),
                balance=pyg(m.balance),
            )
            for m in report.movements
        ],
        next_cursor=report.next_cursor,
    )


@router.get("/reports/trial-balance", response_model=TrialBalanceOut)
def trial_balance_report(
    auth: Reader, db: DbSession, date_from: From, date_to: To, fmt: Format = "json"
) -> TrialBalanceOut | Response:
    """Sumas y saldos con saldos iniciales (D-062) y finales."""
    if fmt == "xlsx":
        content = exports.trial_balance_xlsx(
            db,
            auth.organization_id,
            date_from,
            date_to,
            chart.chart_status(db, auth.organization_id),
        )
        return _xlsx(content, f"balance-de-comprobacion-{date_from}-{date_to}.xlsx")
    rows = reports.trial_balance(db, auth.organization_id, date_from, date_to)

    def total(name: str) -> Decimal:
        return sum((getattr(r, name) for r in rows), ZERO)

    total_debit = total("debit")
    total_credit = total("credit")
    total_debit_balance = total("debit_balance")
    total_credit_balance = total("credit_balance")
    totals = {
        name: total(name)
        for name in ("opening_debit", "opening_credit", "closing_debit", "closing_credit")
    }
    return TrialBalanceOut(
        chart_status=chart.chart_status(db, auth.organization_id),
        date_from=date_from,
        date_to=date_to,
        rows=[
            TrialRowOut(
                account_id=r.account.id,
                code=r.account.code,
                name=r.account.name,
                kind=r.account.kind,
                opening_debit=pyg(r.opening_debit),
                opening_credit=pyg(r.opening_credit),
                debit=pyg(r.debit),
                credit=pyg(r.credit),
                debit_balance=pyg(r.debit_balance),
                credit_balance=pyg(r.credit_balance),
                closing_debit=pyg(r.closing_debit),
                closing_credit=pyg(r.closing_credit),
            )
            for r in rows
        ],
        total_opening_debit=pyg(totals["opening_debit"]),
        total_opening_credit=pyg(totals["opening_credit"]),
        total_debit=pyg(total_debit),
        total_credit=pyg(total_credit),
        total_debit_balance=pyg(total_debit_balance),
        total_credit_balance=pyg(total_credit_balance),
        total_closing_debit=pyg(totals["closing_debit"]),
        total_closing_credit=pyg(totals["closing_credit"]),
        balanced=total_debit == total_credit
        and total_debit_balance == total_credit_balance
        and totals["opening_debit"] == totals["opening_credit"]
        and totals["closing_debit"] == totals["closing_credit"],
    )


@router.get("/reports/balance-sheet", response_model=BalanceSheetOut)
def balance_sheet_report(
    auth: Reader, db: DbSession, at: Annotated[date, Query()], fmt: Format = "json"
) -> BalanceSheetOut | Response:
    if fmt == "xlsx":
        content = exports.balance_sheet_xlsx(
            db, auth.organization_id, at, chart.chart_status(db, auth.organization_id)
        )
        return _xlsx(content, f"balance-general-{at}.xlsx")
    sheet = reports.balance_sheet(db, auth.organization_id, at)
    return BalanceSheetOut(
        chart_status=chart.chart_status(db, auth.organization_id),
        at=at,
        assets=[_statement_out(n) for n in sheet.assets.nodes],
        liabilities=[_statement_out(n) for n in sheet.liabilities.nodes],
        equity=[_statement_out(n) for n in sheet.equity.nodes],
        total_assets=pyg(sheet.assets.total),
        total_liabilities=pyg(sheet.liabilities.total),
        total_equity=pyg(sheet.equity.total),
        result=pyg(sheet.result),
        total_liabilities_and_equity=pyg(sheet.liabilities_and_equity),
        balanced=sheet.balanced,
    )


@router.get("/reports/income-statement", response_model=IncomeStatementOut)
def income_statement_report(
    auth: Reader,
    db: DbSession,
    date_from: From,
    date_to: To,
    by_cost_center: bool = False,
    fmt: Format = "json",
) -> IncomeStatementOut | Response:
    """Con `?by_cost_center=true`, una columna por centro de costos y una "sin centro"."""
    if fmt == "xlsx":
        content = exports.income_statement_xlsx(
            db,
            auth.organization_id,
            date_from,
            date_to,
            chart.chart_status(db, auth.organization_id),
            by_cost_center=by_cost_center,
        )
        return _xlsx(content, f"estado-de-resultados-{date_from}-{date_to}.xlsx")
    statement = reports.income_statement(
        db, auth.organization_id, date_from, date_to, by_cost_center=by_cost_center
    )
    columns = statement.column_amounts if statement.columns is not None else None
    return IncomeStatementOut(
        chart_status=chart.chart_status(db, auth.organization_id),
        date_from=date_from,
        date_to=date_to,
        accounts=[_statement_out(n, columns) for n in statement.nodes],
        total_income=pyg(statement.total_income),
        total_expense=pyg(statement.total_expense),
        result=pyg(statement.result),
        cost_center_columns=(
            [
                CostCenterColumnOut(
                    cost_center_id=c.center.id if c.center is not None else None,
                    code=c.center.code if c.center is not None else None,
                    name=c.center.name if c.center is not None else "Sin centro",
                    total_income=pyg(c.total_income),
                    total_expense=pyg(c.total_expense),
                    result=pyg(c.result),
                )
                for c in statement.columns
            ]
            if statement.columns is not None
            else None
        ),
    )
