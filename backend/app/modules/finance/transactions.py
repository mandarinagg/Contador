"""Movimientos: alta manual, edición, anulación, transferencias y listado.

- Signo: positivo = entra dinero, negativo = sale (D-026).
- Nada se borra: un movimiento se anula con motivo y deja de contar (D-027).
- Una transferencia entre cuentas propias son dos movimientos con el mismo
  `transfer_group_id`, sin categoría; no son ingreso ni gasto (BR-FIN-09). Anular una pata
  anula las dos: una transferencia a medias dejaría dinero creado o perdido.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting import links
from app.modules.finance import service as fs
from app.modules.finance.models import FinancialContext, Transaction
from app.modules.finance.normalize import dedupe_key

TRANSACTION_FIELDS = (
    "account_id",
    "currency",
    "booked_on",
    "amount",
    "description",
    "reference",
    "category_id",
    "counterparty_id",
    "source",
    "import_batch_id",
    "transfer_group_id",
)


def transaction_not_found() -> NotFound:
    return NotFound("TRANSACTION_NOT_FOUND", "El movimiento no existe en este contexto.")


def get_transaction(
    db: Session, ctx: FinancialContext, transaction_id: uuid.UUID, *, lock: bool = False
) -> Transaction:
    query = select(Transaction).where(
        Transaction.id == transaction_id, Transaction.context_id == ctx.id
    )
    if lock:
        query = query.with_for_update()
    tx = db.scalar(query)
    if tx is None:
        raise transaction_not_found()
    return tx


def _refresh_dedupe_key(tx: Transaction) -> None:
    tx.dedupe_key = dedupe_key(tx.account_id, tx.booked_on, tx.amount, tx.description, tx.reference)


def create_manual(
    db: Session, ctx: FinancialContext, actor_id: uuid.UUID, data: dict[str, Any]
) -> Transaction:
    account = fs.usable_account(db, ctx, data["account_id"])
    if data.get("category_id") is not None:
        fs.usable_category(db, ctx, data["category_id"])
    if data.get("counterparty_id") is not None:
        fs.usable_counterparty(db, ctx, data["counterparty_id"])
    amount = fs.validated_amount(data["amount"], account.currency, allow_zero=False)
    tx = Transaction(
        context_id=ctx.id,
        account_id=account.id,
        currency=account.currency,
        booked_on=data["booked_on"],
        amount=amount,
        description=data["description"],
        reference=data.get("reference"),
        category_id=data.get("category_id"),
        counterparty_id=data.get("counterparty_id"),
        source="manual",
        created_by=actor_id,
        # Lo cargó una persona: nace revisado (los importados nacen sin revisar).
        reviewed_at=fs.now(),
    )
    _refresh_dedupe_key(tx)
    db.add(tx)
    db.flush()
    fs.record(
        db,
        ctx,
        actor_id,
        "transaction",
        "created",
        tx.id,
        after=fs.snapshot(tx, TRANSACTION_FIELDS),
    )
    db.commit()
    return tx


@dataclass(frozen=True)
class TransactionFilters:
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    counterparty_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None
    unreviewed: bool = False
    include_voided: bool = False


def list_transactions(
    db: Session,
    ctx: FinancialContext,
    filters: TransactionFilters,
    *,
    limit: int,
    before: uuid.UUID | None,
) -> list[Transaction]:
    """Más recientes primero (fecha, id). El cursor `before` es el id del último recibido."""
    query = select(Transaction).where(Transaction.context_id == ctx.id)
    if filters.account_id is not None:
        query = query.where(Transaction.account_id == filters.account_id)
    if filters.category_id is not None:
        query = query.where(Transaction.category_id == filters.category_id)
    if filters.counterparty_id is not None:
        query = query.where(Transaction.counterparty_id == filters.counterparty_id)
    if filters.date_from is not None:
        query = query.where(Transaction.booked_on >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(Transaction.booked_on <= filters.date_to)
    if filters.q and filters.q.strip():
        term = f"%{fs.escape_like(filters.q.strip())}%"
        query = query.where(
            or_(
                Transaction.description.ilike(term, escape="\\"),
                Transaction.reference.ilike(term, escape="\\"),
            )
        )
    if filters.unreviewed:
        query = query.where(Transaction.reviewed_at.is_(None))
    if not filters.include_voided:
        query = query.where(Transaction.voided_at.is_(None))
    if before is not None:
        cursor = db.execute(
            select(Transaction.booked_on, Transaction.id).where(
                Transaction.id == before, Transaction.context_id == ctx.id
            )
        ).first()
        if cursor is None:
            raise AppError("INVALID_CURSOR", "El cursor de paginación no es válido.")
        query = query.where(
            tuple_(Transaction.booked_on, Transaction.id) < tuple_(cursor[0], cursor[1])
        )
    query = query.order_by(Transaction.booked_on.desc(), Transaction.id.desc()).limit(limit)
    return list(db.scalars(query))


def update_transaction(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    transaction_id: uuid.UUID,
    data: dict[str, Any],
) -> Transaction:
    tx = get_transaction(db, ctx, transaction_id, lock=True)
    if tx.voided_at is not None:
        raise Conflict("TRANSACTION_VOIDED", "El movimiento está anulado: no se puede editar.")
    changes = dict(data)

    reviewed = changes.pop("reviewed", None)
    if reviewed is True and tx.reviewed_at is None:
        changes["reviewed_at"] = fs.now()
    elif reviewed is False and tx.reviewed_at is not None:
        changes["reviewed_at"] = None

    if "description" in changes and changes["description"] is None:
        changes.pop("description")

    core_keys = {"booked_on", "amount", "account_id"}
    core = {k: v for k, v in changes.items() if k in core_keys and v is not None}
    for key in core_keys:
        changes.pop(key, None)
    core = {k: v for k, v in core.items() if getattr(tx, k) != v}
    if core:
        if tx.source != "manual":
            raise Conflict(
                "TRANSACTION_NOT_EDITABLE",
                "La fecha, el importe y la cuenta de un movimiento importado no se cambian: "
                "anulalo y cargalo de nuevo si hace falta.",
            )
        if tx.transfer_group_id is not None:
            raise Conflict(
                "TRANSACTION_NOT_EDITABLE",
                "Es parte de una transferencia: anulala y cargala de nuevo.",
            )
        # El asiento contabilizado quedaría distinto del movimiento (D-048).
        links.ensure_no_posted_entry(db, [tx.id], "modificar")
        account = fs.usable_account(db, ctx, core["account_id"]) if "account_id" in core else None
        currency = account.currency if account is not None else tx.currency
        amount = core.get("amount", tx.amount)
        core["amount"] = fs.validated_amount(amount, currency, allow_zero=False)
        if account is not None:
            core["currency"] = account.currency
        changes.update(core)

    if changes.get("category_id") is not None and changes["category_id"] != tx.category_id:
        if tx.transfer_group_id is not None:
            raise Conflict(
                "TRANSFER_HAS_NO_CATEGORY",
                "Una transferencia entre cuentas propias no lleva categoría.",
            )
        fs.usable_category(db, ctx, changes["category_id"])
    if (
        changes.get("counterparty_id") is not None
        and changes["counterparty_id"] != tx.counterparty_id
    ):
        fs.usable_counterparty(db, ctx, changes["counterparty_id"])

    before, after = fs.apply_changes(tx, changes)
    if after:
        if after.keys() & {"booked_on", "amount", "account_id", "description", "reference"}:
            _refresh_dedupe_key(tx)
        db.flush()
        fs.record(db, ctx, actor_id, "transaction", "updated", tx.id, before=before, after=after)
    db.commit()
    return tx


def void_transaction(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    transaction_id: uuid.UUID,
    reason: str,
) -> list[Transaction]:
    """Anula el movimiento (y la otra pata si es una transferencia). Devuelve los anulados."""
    tx = get_transaction(db, ctx, transaction_id, lock=True)
    if tx.voided_at is not None:
        raise Conflict("ALREADY_VOIDED", "El movimiento ya está anulado.")
    targets = [tx]
    if tx.transfer_group_id is not None:
        targets = list(
            db.scalars(
                select(Transaction)
                .where(
                    Transaction.context_id == ctx.id,
                    Transaction.transfer_group_id == tx.transfer_group_id,
                    Transaction.voided_at.is_(None),
                )
                .order_by(Transaction.id)
                .with_for_update()
            )
        )
    # BR-ACC-11: con un asiento contabilizado, primero se revierte el asiento (D-041).
    links.ensure_no_posted_entry(db, [t.id for t in targets], "anular")
    when = fs.now()
    for target in targets:
        before, after = fs.apply_changes(
            target, {"voided_at": when, "voided_by": actor_id, "void_reason": reason}
        )
        fs.record(db, ctx, actor_id, "transaction", "voided", target.id, before=before, after=after)
    db.commit()
    return targets


def create_transfer(
    db: Session, ctx: FinancialContext, actor_id: uuid.UUID, data: dict[str, Any]
) -> tuple[uuid.UUID, Transaction, Transaction]:
    if data["from_account_id"] == data["to_account_id"]:
        raise AppError(
            "TRANSFER_SAME_ACCOUNT",
            "La cuenta de origen y la de destino tienen que ser distintas.",
            status_code=422,
        )
    source = fs.usable_account(db, ctx, data["from_account_id"])
    target = fs.usable_account(db, ctx, data["to_account_id"])
    amount_out = fs.validated_amount(data["amount_out"], source.currency, allow_zero=False)
    amount_in = fs.validated_amount(data["amount_in"], target.currency, allow_zero=False)
    if amount_out < 0 or amount_in < 0:
        raise AppError(
            "INVALID_AMOUNT",
            "En una transferencia los importes van en positivo (lo que sale y lo que entra).",
            status_code=422,
        )
    if source.currency == target.currency and amount_out != amount_in:
        raise AppError(
            "TRANSFER_AMOUNTS_DIFFER",
            "Entre cuentas de la misma moneda, lo que sale tiene que ser igual a lo que entra. "
            "Las comisiones se cargan como un gasto aparte.",
            status_code=422,
        )
    group = uuid.uuid4()
    legs: list[Transaction] = []
    for account, amount in ((source, -amount_out), (target, amount_in)):
        leg = Transaction(
            context_id=ctx.id,
            account_id=account.id,
            currency=account.currency,
            booked_on=data["booked_on"],
            amount=amount,
            description=data["description"],
            reference=data.get("reference"),
            source="manual",
            transfer_group_id=group,
            created_by=actor_id,
            reviewed_at=fs.now(),
        )
        _refresh_dedupe_key(leg)
        db.add(leg)
        legs.append(leg)
    db.flush()
    for leg in legs:
        fs.record(
            db,
            ctx,
            actor_id,
            "transaction",
            "created",
            leg.id,
            after=fs.snapshot(leg, TRANSACTION_FIELDS),
        )
    db.commit()
    return group, legs[0], legs[1]
