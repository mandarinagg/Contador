"""API de finanzas (`/api/v1/finance`). Especificación: docs/specs/FASE2_FINANZAS.md §4.

El acceso a cada contexto lo resuelve `service.resolve_context` (D-024): el personal solo
para su dueño (404 para los demás); el empresarial con `finance.read` / `finance.manage`.
Todos los listados se paginan por cursor (`?limit=50&before=<id>`), más nuevos primero.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import Auth, DbSession
from app.core.errors import AppError, Conflict
from app.modules.accounting import finance_link, links
from app.modules.finance import imports, suggested, summary, transactions
from app.modules.finance import service as fs
from app.modules.finance.importing import MAX_FILE_BYTES, ImportMapping, import_error
from app.modules.finance.models import (
    Account,
    FinancialContext,
    ImportBatch,
    ImportRow,
    Transaction,
)
from app.modules.finance.money import format_amount
from app.modules.finance.schemas import (
    AccountBalanceOut,
    AccountCreate,
    AccountOut,
    AccountUpdate,
    CategoryCreate,
    CategoryExpenseOut,
    CategoryOut,
    CategoryUpdate,
    ConsolidatedContextOut,
    ConsolidatedOut,
    ContextOut,
    ContextTotalsOut,
    CounterpartyCreate,
    CounterpartyOut,
    CounterpartyUpdate,
    CurrencyTotalsOut,
    ImportBatchOut,
    ImportRowOut,
    JournalEntryRefOut,
    MonthTotalsOut,
    RowDecisionUpdate,
    SummaryOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
    TransferCreate,
    TransferOut,
    VoidRequest,
)

router = APIRouter(prefix="/finance", tags=["finance"])

Limit = Annotated[int, Query(ge=1, le=200)]
Before = Annotated[uuid.UUID | None, Query()]
RowsLimit = Annotated[int, Query(ge=1, le=1000)]


# --- Conversión a la salida (importes siempre como string) ------------------------------


def _context_out(ctx: FinancialContext) -> ContextOut:
    return ContextOut(
        id=ctx.id,
        kind=ctx.kind,
        name=ctx.name,
        owner_user_id=ctx.owner_user_id,
        is_active=ctx.is_active,
        created_at=ctx.created_at,
    )


def _account_out(account: Account, balance: Decimal) -> AccountOut:
    return AccountOut(
        id=account.id,
        context_id=account.context_id,
        name=account.name,
        kind=account.kind,
        institution=account.institution,
        currency=account.currency,
        number_last4=account.number_last4,
        opening_balance=format_amount(account.opening_balance, account.currency),
        opening_date=account.opening_date,
        balance=format_amount(balance, account.currency),
        ledger_account_id=account.ledger_account_id,
        archived_at=account.archived_at,
        created_at=account.created_at,
    )


def _tx_out(tx: Transaction, ref: links.EntryRef | None = None) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        context_id=tx.context_id,
        account_id=tx.account_id,
        currency=tx.currency,
        booked_on=tx.booked_on,
        amount=format_amount(tx.amount, tx.currency),
        description=tx.description,
        reference=tx.reference,
        category_id=tx.category_id,
        counterparty_id=tx.counterparty_id,
        source=tx.source,
        import_batch_id=tx.import_batch_id,
        transfer_group_id=tx.transfer_group_id,
        reviewed_at=tx.reviewed_at,
        voided_at=tx.voided_at,
        voided_by=tx.voided_by,
        void_reason=tx.void_reason,
        created_by=tx.created_by,
        created_at=tx.created_at,
        journal_entry=(
            JournalEntryRefOut(id=ref.id, number=ref.number, status=ref.status)
            if ref is not None
            else None
        ),
    )


def _txs_out(db: Session, ctx: FinancialContext, txs: list[Transaction]) -> list[TransactionOut]:
    """Movimientos con su asiento contable; solo en el contexto empresarial (D-035)."""
    refs = links.journal_refs(db, [t.id for t in txs]) if ctx.kind == "business" else {}
    return [_tx_out(t, refs.get(t.id)) for t in txs]


def _row_out(row: ImportRow, currency: str) -> ImportRowOut:
    return ImportRowOut(
        row_number=row.row_number,
        raw=row.raw,
        booked_on=row.booked_on,
        amount=format_amount(row.amount, currency) if row.amount is not None else None,
        description=row.description,
        reference=row.reference,
        error=row.error,
        duplicate_of=row.duplicate_of,
        duplicate_in_file=row.duplicate_in_file,
        decision=row.decision,
    )


def _batch_out(
    batch: ImportBatch, currency: str, rows: list[ImportRow] | None = None
) -> ImportBatchOut:
    return ImportBatchOut(
        id=batch.id,
        context_id=batch.context_id,
        account_id=batch.account_id,
        currency=currency,
        filename=batch.filename,
        file_sha256=batch.file_sha256.hex(),
        file_format=batch.file_format,
        mapping=batch.mapping,
        status=batch.status,
        rows_total=batch.rows_total,
        rows_imported=batch.rows_imported,
        rows_duplicate=batch.rows_duplicate,
        rows_error=batch.rows_error,
        created_by=batch.created_by,
        created_at=batch.created_at,
        committed_at=batch.committed_at,
        rows=[_row_out(r, currency) for r in rows] if rows is not None else None,
    )


def _changes(
    body: AccountUpdate | CategoryUpdate | CounterpartyUpdate | TransactionUpdate,
) -> dict[str, Any]:
    """Solo los campos enviados (un `null` explícito significa "borrar el valor")."""
    return body.model_dump(exclude_unset=True)


# --- Contextos ---------------------------------------------------------------------------


@router.get("/contexts", response_model=list[ContextOut])
def list_contexts(auth: Auth, db: DbSession) -> list[ContextOut]:
    return [_context_out(c) for c in fs.visible_contexts(db, auth)]


@router.post("/contexts/personal", response_model=ContextOut, status_code=status.HTTP_201_CREATED)
def create_personal_context(auth: Auth, db: DbSession) -> ContextOut:
    return _context_out(fs.create_personal_context(db, auth))


# --- Cuentas ----------------------------------------------------------------------------


@router.get("/contexts/{cid}/accounts", response_model=list[AccountOut])
def list_accounts(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    limit: Limit = 50,
    before: Before = None,
    include_archived: bool = False,
) -> list[AccountOut]:
    ctx = fs.resolve_context(db, auth, cid, write=False)
    rows = fs.list_accounts(db, ctx, limit=limit, before=before, include_archived=include_archived)
    return [_account_out(a, b) for a, b in rows]


@router.post(
    "/contexts/{cid}/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED
)
def create_account(cid: uuid.UUID, body: AccountCreate, auth: Auth, db: DbSession) -> AccountOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    account = fs.create_account(db, ctx, auth.user_id, body.model_dump())
    return _account_out(account, account.opening_balance)


@router.patch("/contexts/{cid}/accounts/{account_id}", response_model=AccountOut)
def update_account(
    cid: uuid.UUID, account_id: uuid.UUID, body: AccountUpdate, auth: Auth, db: DbSession
) -> AccountOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    changes = _changes(body)
    if "ledger_account_id" in changes:
        fs.get_account(db, ctx, account_id)  # 404 antes que la validación contable
        finance_link.check_ledger_assignment(
            db, auth, ctx, changes["ledger_account_id"], target="account"
        )
    account = fs.update_account(db, ctx, auth.user_id, account_id, changes)
    return _account_out(account, fs.account_balance(db, account))


# --- Categorías -------------------------------------------------------------------------


@router.get("/contexts/{cid}/categories", response_model=list[CategoryOut])
def list_categories(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    limit: Limit = 50,
    before: Before = None,
    include_archived: bool = False,
) -> list[CategoryOut]:
    ctx = fs.resolve_context(db, auth, cid, write=False)
    rows = fs.list_categories(
        db, ctx, limit=limit, before=before, include_archived=include_archived
    )
    return [CategoryOut.model_validate(c) for c in rows]


@router.post(
    "/contexts/{cid}/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED
)
def create_category(cid: uuid.UUID, body: CategoryCreate, auth: Auth, db: DbSession) -> CategoryOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    category = fs.create_category(
        db, ctx, auth.user_id, name=body.name, kind=body.kind, parent_id=body.parent_id
    )
    return CategoryOut.model_validate(category)


@router.post(
    "/contexts/{cid}/categories/suggested",
    response_model=list[CategoryOut],
    status_code=status.HTTP_201_CREATED,
)
def create_suggested_categories(cid: uuid.UUID, auth: Auth, db: DbSession) -> list[CategoryOut]:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    if fs.has_categories(db, ctx):
        raise Conflict(
            "CATEGORIES_EXIST",
            "El contexto ya tiene categorías: las sugeridas solo se crean en uno vacío.",
        )
    created = [
        fs.create_category(
            db, ctx, auth.user_id, name=name, kind=kind, parent_id=None, commit=False
        )
        for name, kind in suggested.for_kind(ctx.kind)
    ]
    db.commit()
    return [CategoryOut.model_validate(c) for c in created]


@router.patch("/contexts/{cid}/categories/{category_id}", response_model=CategoryOut)
def update_category(
    cid: uuid.UUID, category_id: uuid.UUID, body: CategoryUpdate, auth: Auth, db: DbSession
) -> CategoryOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    changes = _changes(body)
    if "ledger_account_id" in changes:
        current = fs.get_category(db, ctx, category_id)
        finance_link.check_ledger_assignment(
            db,
            auth,
            ctx,
            changes["ledger_account_id"],
            target="category",
            category_kind=current.kind,
        )
    category = fs.update_category(db, ctx, auth.user_id, category_id, changes)
    return CategoryOut.model_validate(category)


# --- Contrapartes -----------------------------------------------------------------------


@router.get("/contexts/{cid}/counterparties", response_model=list[CounterpartyOut])
def list_counterparties(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    limit: Limit = 50,
    before: Before = None,
    include_archived: bool = False,
    q: Annotated[str | None, Query(max_length=150)] = None,
) -> list[CounterpartyOut]:
    ctx = fs.resolve_context(db, auth, cid, write=False)
    rows = fs.list_counterparties(
        db, ctx, limit=limit, before=before, include_archived=include_archived, q=q
    )
    return [CounterpartyOut.model_validate(c) for c in rows]


@router.post(
    "/contexts/{cid}/counterparties",
    response_model=CounterpartyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_counterparty(
    cid: uuid.UUID, body: CounterpartyCreate, auth: Auth, db: DbSession
) -> CounterpartyOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    counterparty = fs.create_counterparty(db, ctx, auth.user_id, body.model_dump())
    return CounterpartyOut.model_validate(counterparty)


@router.patch("/contexts/{cid}/counterparties/{counterparty_id}", response_model=CounterpartyOut)
def update_counterparty(
    cid: uuid.UUID,
    counterparty_id: uuid.UUID,
    body: CounterpartyUpdate,
    auth: Auth,
    db: DbSession,
) -> CounterpartyOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    counterparty = fs.update_counterparty(db, ctx, auth.user_id, counterparty_id, _changes(body))
    return CounterpartyOut.model_validate(counterparty)


# --- Movimientos ------------------------------------------------------------------------


@router.get("/contexts/{cid}/transactions", response_model=list[TransactionOut])
def list_transactions(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    limit: Limit = 50,
    before: Before = None,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    counterparty_id: uuid.UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    unreviewed: bool = False,
    include_voided: bool = False,
) -> list[TransactionOut]:
    ctx = fs.resolve_context(db, auth, cid, write=False)
    filters = transactions.TransactionFilters(
        account_id=account_id,
        category_id=category_id,
        counterparty_id=counterparty_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        unreviewed=unreviewed,
        include_voided=include_voided,
    )
    rows = transactions.list_transactions(db, ctx, filters, limit=limit, before=before)
    return _txs_out(db, ctx, rows)


@router.get("/contexts/{cid}/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    cid: uuid.UUID, transaction_id: uuid.UUID, auth: Auth, db: DbSession
) -> TransactionOut:
    """Un movimiento, con las reglas de acceso del listado (P-9). Incluye los anulados."""
    ctx = fs.resolve_context(db, auth, cid, write=False)
    tx = transactions.get_transaction(db, ctx, transaction_id)
    return _txs_out(db, ctx, [tx])[0]


@router.post(
    "/contexts/{cid}/transactions",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    cid: uuid.UUID, body: TransactionCreate, auth: Auth, db: DbSession
) -> TransactionOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    return _tx_out(transactions.create_manual(db, ctx, auth.user_id, body.model_dump()))


@router.patch("/contexts/{cid}/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    cid: uuid.UUID,
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    auth: Auth,
    db: DbSession,
) -> TransactionOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    tx = transactions.update_transaction(db, ctx, auth.user_id, transaction_id, _changes(body))
    return _txs_out(db, ctx, [tx])[0]


@router.post(
    "/contexts/{cid}/transactions/{transaction_id}/void", response_model=list[TransactionOut]
)
def void_transaction(
    cid: uuid.UUID, transaction_id: uuid.UUID, body: VoidRequest, auth: Auth, db: DbSession
) -> list[TransactionOut]:
    """Devuelve los movimientos anulados (dos si era una transferencia)."""
    ctx = fs.resolve_context(db, auth, cid, write=True)
    voided = transactions.void_transaction(db, ctx, auth.user_id, transaction_id, body.reason)
    return _txs_out(db, ctx, voided)


@router.post(
    "/contexts/{cid}/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED
)
def create_transfer(cid: uuid.UUID, body: TransferCreate, auth: Auth, db: DbSession) -> TransferOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    group, outgoing, incoming = transactions.create_transfer(
        db, ctx, auth.user_id, body.model_dump()
    )
    return TransferOut(
        transfer_group_id=group, outgoing=_tx_out(outgoing), incoming=_tx_out(incoming)
    )


# --- Importación ------------------------------------------------------------------------


def _read_upload(file: UploadFile) -> bytes:
    content = file.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise import_error(
            "IMPORT_FILE_TOO_LARGE", "El archivo supera los 10 MB permitidos.", status_code=413
        )
    return content


def _parse_mapping(raw: str) -> ImportMapping:
    try:
        return ImportMapping.model_validate_json(raw)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        raise AppError(
            "VALIDATION_ERROR", "El mapeo de columnas no es válido.", details, status_code=422
        ) from exc


@router.post(
    "/contexts/{cid}/imports", response_model=ImportBatchOut, status_code=status.HTTP_201_CREATED
)
def create_import(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    account_id: Annotated[uuid.UUID, Form()],
    mapping: Annotated[str, Form(max_length=4000)],
    rows_limit: RowsLimit = 200,
) -> ImportBatchOut:
    """Analiza el archivo y devuelve el lote con sus filas. **No crea movimientos.**"""
    ctx = fs.resolve_context(db, auth, cid, write=True)
    parsed_mapping = _parse_mapping(mapping)
    content = _read_upload(file)
    batch = imports.preview(
        db,
        ctx,
        auth.user_id,
        account_id=account_id,
        filename=file.filename,
        content=content,
        mapping=parsed_mapping,
    )
    rows = imports.list_rows(db, batch, limit=rows_limit, after=None)
    return _batch_out(batch, imports.account_currency(db, batch.account_id), rows)


@router.get("/contexts/{cid}/imports", response_model=list[ImportBatchOut])
def list_imports(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    limit: Limit = 50,
    before: Before = None,
    account_id: uuid.UUID | None = None,
) -> list[ImportBatchOut]:
    """Lotes sin sus filas. Con `account_id` y `limit=1`: el mapeo de la última importación."""
    ctx = fs.resolve_context(db, auth, cid, write=False)
    batches = imports.list_batches(db, ctx, account_id=account_id, limit=limit, before=before)
    return [_batch_out(b, imports.account_currency(db, b.account_id)) for b in batches]


@router.get("/contexts/{cid}/imports/{batch_id}", response_model=ImportBatchOut)
def get_import(
    cid: uuid.UUID,
    batch_id: uuid.UUID,
    auth: Auth,
    db: DbSession,
    rows_limit: RowsLimit = 200,
    rows_after: Annotated[int | None, Query(ge=0)] = None,
) -> ImportBatchOut:
    """Lote con sus filas en orden de archivo; `rows_after` = último `row_number` recibido."""
    ctx = fs.resolve_context(db, auth, cid, write=False)
    batch = imports.get_batch(db, ctx, batch_id)
    rows = imports.list_rows(db, batch, limit=rows_limit, after=rows_after)
    return _batch_out(batch, imports.account_currency(db, batch.account_id), rows)


@router.patch("/contexts/{cid}/imports/{batch_id}/rows/{row_number}", response_model=ImportRowOut)
def update_import_row(
    cid: uuid.UUID,
    batch_id: uuid.UUID,
    row_number: int,
    body: RowDecisionUpdate,
    auth: Auth,
    db: DbSession,
) -> ImportRowOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    row = imports.set_decision(db, ctx, batch_id, row_number, body.decision)
    batch = imports.get_batch(db, ctx, batch_id)
    return _row_out(row, imports.account_currency(db, batch.account_id))


@router.post("/contexts/{cid}/imports/{batch_id}/commit", response_model=ImportBatchOut)
def commit_import(cid: uuid.UUID, batch_id: uuid.UUID, auth: Auth, db: DbSession) -> ImportBatchOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    batch = imports.commit(db, ctx, auth.user_id, batch_id)
    return _batch_out(batch, imports.account_currency(db, batch.account_id))


@router.post("/contexts/{cid}/imports/{batch_id}/cancel", response_model=ImportBatchOut)
def cancel_import(cid: uuid.UUID, batch_id: uuid.UUID, auth: Auth, db: DbSession) -> ImportBatchOut:
    ctx = fs.resolve_context(db, auth, cid, write=True)
    batch = imports.cancel(db, ctx, auth.user_id, batch_id)
    return _batch_out(batch, imports.account_currency(db, batch.account_id))


# --- Resúmenes --------------------------------------------------------------------------


def _totals_out(currency: str, flow: summary.Flow) -> CurrencyTotalsOut:
    return CurrencyTotalsOut(
        currency=currency,
        income=format_amount(flow.income, currency),
        expense=format_amount(flow.expense, currency),
        net=format_amount(flow.net, currency),
    )


@router.get("/contexts/{cid}/summary", response_model=SummaryOut)
def context_summary(
    cid: uuid.UUID,
    auth: Auth,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> SummaryOut:
    """Saldos al `to`; ingresos, gastos y neto por moneda y mes; gastos por categoría."""
    ctx = fs.resolve_context(db, auth, cid, write=False)
    start, end = summary.default_range(date_from, date_to)
    result = summary.summarize(db, ctx, start, end)
    return SummaryOut(
        context_id=ctx.id,
        date_from=start,
        date_to=end,
        balances=[
            AccountBalanceOut(
                account_id=a.id,
                name=a.name,
                currency=a.currency,
                balance=format_amount(balance, a.currency),
                archived=a.archived_at is not None,
            )
            for a, balance in result.balances
        ],
        totals=[_totals_out(c, f) for c, f in result.totals.items()],
        by_month=[
            MonthTotalsOut(month=month, **_totals_out(currency, flow).model_dump())
            for (currency, month), flow in result.by_month.items()
        ],
        expenses_by_category=[
            CategoryExpenseOut(
                currency=currency,
                category_id=category_id,
                category_name=name,
                amount=format_amount(amount, currency),
            )
            for currency, category_id, name, amount in result.expenses_by_category
        ],
    )


@router.get("/summary/consolidated", response_model=ConsolidatedOut)
def consolidated_summary(
    auth: Auth,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ConsolidatedOut:
    """Por cada contexto visible, sus totales por moneda. Nunca un total entre contextos."""
    start, end = summary.default_range(date_from, date_to)
    contexts = []
    for ctx in fs.visible_contexts(db, auth):
        totals = summary.context_totals(db, ctx, start, end)
        contexts.append(
            ConsolidatedContextOut(
                context=_context_out(ctx),
                totals=[
                    ContextTotalsOut(
                        balance=format_amount(t.balance, currency),
                        **_totals_out(currency, t.flow).model_dump(),
                    )
                    for currency, t in totals.items()
                ],
            )
        )
    return ConsolidatedOut(date_from=start, date_to=end, contexts=contexts)
