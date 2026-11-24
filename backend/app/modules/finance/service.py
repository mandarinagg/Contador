"""Servicios de finanzas: acceso a contextos, cuentas, categorías y contrapartes.

Reglas transversales:
- **Acceso (D-024):** un contexto personal solo lo ve y opera su dueño, sin importar el
  rol; para los demás no existe (404, no 403). El contexto empresarial exige
  `finance.read` para leer y `finance.manage` para escribir.
- **Auditoría (D-027):** todo alta, cambio, archivo y anulación se registra con
  `audit.record`, con solo los campos que cambian. Lo de un contexto personal se audita
  con `entity_type` `finance.personal.*`, que solo ve su dueño (ver `audit.service`).
- **Nada se borra:** cuentas, categorías y contrapartes se archivan.
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.permissions import Perm
from app.modules.audit import service as audit
from app.modules.finance.models import (
    Account,
    Category,
    Counterparty,
    FinancialContext,
    Transaction,
)
from app.modules.finance.money import AmountError, check_amount

BUSINESS_CONTEXT_NAME = "Empresa"
PERSONAL_PREFIX = "finance.personal"
BUSINESS_PREFIX = "finance"


# --- Utilidades comunes -----------------------------------------------------------------


def now() -> datetime:
    return datetime.now(UTC)


def jsonable(value: Any) -> Any:
    """Valor apto para JSONB de auditoría (Decimal, fechas y UUID como texto)."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def snapshot(obj: object, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: jsonable(getattr(obj, f)) for f in fields}


def apply_changes(obj: object, changes: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Aplica solo lo que cambia y devuelve (antes, después) de esos campos."""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for key, value in changes.items():
        old = getattr(obj, key)
        if old != value:
            before[key] = jsonable(old)
            after[key] = jsonable(value)
            setattr(obj, key, value)
    return before, after


def entity_type(ctx: FinancialContext, entity: str) -> str:
    prefix = PERSONAL_PREFIX if ctx.kind == "personal" else BUSINESS_PREFIX
    return f"{prefix}.{entity}"


def record(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    entity: str,
    verb: str,
    entity_id: uuid.UUID,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    kind = entity_type(ctx, entity)
    audit.record(
        db,
        action=f"{kind}.{verb}",
        entity_type=kind,
        entity_id=entity_id,
        organization_id=ctx.organization_id,
        actor_user_id=actor_id,
        before=before,
        after=after,
    )


def invalid_amount(exc: AmountError) -> AppError:
    return AppError("INVALID_AMOUNT", str(exc), status_code=422)


def validated_amount(amount: Decimal, currency: str, *, allow_zero: bool) -> Decimal:
    try:
        return check_amount(amount, currency, allow_zero=allow_zero)
    except AmountError as exc:
        raise invalid_amount(exc) from exc


def flush_unique(db: Session, conflicts: Mapping[str, tuple[str, str]]) -> None:
    """`flush` en un SAVEPOINT; traduce violaciones de unicidad conocidas a 409.

    `conflicts`: nombre de restricción → (código, mensaje).
    """
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if isinstance(constraint, str) and constraint in conflicts:
            code, message = conflicts[constraint]
            raise Conflict(code, message) from exc
        raise


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def paginate[T](query: Select[T], id_column: Any, before: uuid.UUID | None) -> Select[T]:
    """Cursor por id (uuidv7, ordenado por creación): más nuevos primero."""
    if before is not None:
        query = query.where(id_column < before)
    return query.order_by(id_column.desc())


# --- Contextos ---------------------------------------------------------------------------


def context_not_found() -> NotFound:
    return NotFound("CONTEXT_NOT_FOUND", "El contexto financiero no existe.")


def resolve_context(
    db: Session, auth: AuthContext, context_id: uuid.UUID, *, write: bool
) -> FinancialContext:
    """Contexto visible para el usuario, o error. Aplica D-024."""
    ctx = db.scalar(
        select(FinancialContext).where(
            FinancialContext.id == context_id,
            FinancialContext.organization_id == auth.organization_id,
        )
    )
    if ctx is None:
        raise context_not_found()
    if ctx.kind == "personal":
        # Privado de su dueño: para cualquier otro usuario, aunque sea propietario, no existe.
        if ctx.owner_user_id != auth.user_id:
            raise context_not_found()
    else:
        needed = Perm.FINANCE_MANAGE if write else Perm.FINANCE_READ
        if needed.value not in auth.permissions:
            raise Forbidden(
                "FORBIDDEN",
                "No tenés permiso para esta acción.",
                details={"missing": [needed.value]},
            )
    if write and not ctx.is_active:
        raise Conflict("CONTEXT_INACTIVE", "El contexto financiero está desactivado.")
    return ctx


def create_business_context(db: Session, organization_id: uuid.UUID) -> FinancialContext:
    """Contexto empresarial de una organización nueva (lo usa la configuración inicial)."""
    ctx = FinancialContext(
        organization_id=organization_id, kind="business", name=BUSINESS_CONTEXT_NAME
    )
    db.add(ctx)
    return ctx


def visible_contexts(db: Session, auth: AuthContext) -> list[FinancialContext]:
    """El de la empresa si tiene `finance.read`, más el personal del usuario si existe."""
    conditions: list[ColumnElement[bool]] = [
        (FinancialContext.kind == "personal") & (FinancialContext.owner_user_id == auth.user_id)
    ]
    if Perm.FINANCE_READ.value in auth.permissions:
        conditions.append(FinancialContext.kind == "business")
    query = (
        select(FinancialContext)
        .where(FinancialContext.organization_id == auth.organization_id, or_(*conditions))
        .order_by(FinancialContext.kind, FinancialContext.created_at)
    )
    return list(db.scalars(query))


def create_personal_context(db: Session, auth: AuthContext) -> FinancialContext:
    existing = db.scalar(
        select(FinancialContext.id).where(
            FinancialContext.organization_id == auth.organization_id,
            FinancialContext.kind == "personal",
            FinancialContext.owner_user_id == auth.user_id,
        )
    )
    if existing is not None:
        raise Conflict("PERSONAL_CONTEXT_EXISTS", "Ya tenés un contexto de finanzas personales.")
    ctx = FinancialContext(
        organization_id=auth.organization_id,
        kind="personal",
        name=f"Personal — {auth.user.full_name}"[:100],
        owner_user_id=auth.user_id,
    )
    db.add(ctx)
    flush_unique(
        db,
        {
            "uq_contexts_personal_per_user": (
                "PERSONAL_CONTEXT_EXISTS",
                "Ya tenés un contexto de finanzas personales.",
            )
        },
    )
    record(
        db,
        ctx,
        auth.user_id,
        "context",
        "created",
        ctx.id,
        after=snapshot(ctx, ("kind", "name", "owner_user_id")),
    )
    db.commit()
    return ctx


# --- Cuentas ----------------------------------------------------------------------------

ACCOUNT_FIELDS = (
    "name",
    "kind",
    "institution",
    "currency",
    "number_last4",
    "opening_balance",
    "opening_date",
)
ACCOUNT_CONFLICTS = {
    "uq_accounts_context_id_name": (
        "ACCOUNT_NAME_TAKEN",
        "Ya existe una cuenta con ese nombre en este contexto.",
    )
}


def account_not_found() -> NotFound:
    return NotFound("ACCOUNT_NOT_FOUND", "La cuenta no existe en este contexto.")


def get_account(
    db: Session, ctx: FinancialContext, account_id: uuid.UUID, *, lock: bool = False
) -> Account:
    query = select(Account).where(Account.id == account_id, Account.context_id == ctx.id)
    if lock:
        query = query.with_for_update()
    account = db.scalar(query)
    if account is None:
        raise account_not_found()
    return account


def usable_account(db: Session, ctx: FinancialContext, account_id: uuid.UUID) -> Account:
    """Cuenta del contexto en la que se pueden registrar movimientos nuevos."""
    account = get_account(db, ctx, account_id)
    if account.archived_at is not None:
        raise Conflict("ACCOUNT_ARCHIVED", "La cuenta está archivada: desarchivala para usarla.")
    return account


def balances(
    db: Session,
    context_id: uuid.UUID,
    *,
    until: date | None = None,
    account_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, Decimal]:
    """Suma de movimientos no anulados por cuenta (sin el saldo inicial)."""
    query = (
        select(Transaction.account_id, func.sum(Transaction.amount))
        .where(Transaction.context_id == context_id, Transaction.voided_at.is_(None))
        .group_by(Transaction.account_id)
    )
    if until is not None:
        query = query.where(Transaction.booked_on <= until)
    if account_ids is not None:
        query = query.where(Transaction.account_id.in_(account_ids))
    return {account_id: total for account_id, total in db.execute(query)}


def list_accounts(
    db: Session,
    ctx: FinancialContext,
    *,
    limit: int,
    before: uuid.UUID | None,
    include_archived: bool,
) -> list[tuple[Account, Decimal]]:
    query = select(Account).where(Account.context_id == ctx.id)
    if not include_archived:
        query = query.where(Account.archived_at.is_(None))
    accounts = list(db.scalars(paginate(query, Account.id, before).limit(limit)))
    sums = balances(db, ctx.id, account_ids=[a.id for a in accounts])
    return [(a, a.opening_balance + sums.get(a.id, Decimal(0))) for a in accounts]


def account_balance(db: Session, account: Account) -> Decimal:
    sums = balances(db, account.context_id, account_ids=[account.id])
    return account.opening_balance + sums.get(account.id, Decimal(0))


def create_account(
    db: Session, ctx: FinancialContext, actor_id: uuid.UUID, data: dict[str, Any]
) -> Account:
    data = dict(data)
    data["opening_balance"] = validated_amount(
        data["opening_balance"], data["currency"], allow_zero=True
    )
    account = Account(context_id=ctx.id, **data)
    db.add(account)
    flush_unique(db, ACCOUNT_CONFLICTS)
    record(
        db, ctx, actor_id, "account", "created", account.id, after=snapshot(account, ACCOUNT_FIELDS)
    )
    db.commit()
    return account


def _has_transactions(db: Session, account_id: uuid.UUID) -> bool:
    return (
        db.scalar(select(Transaction.id).where(Transaction.account_id == account_id).limit(1))
        is not None
    )


def update_account(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    account_id: uuid.UUID,
    data: dict[str, Any],
) -> Account:
    account = get_account(db, ctx, account_id, lock=True)
    changes = dict(data)
    archived = changes.pop("archived", None)
    if archived is not None:
        if archived and account.archived_at is None:
            changes["archived_at"] = now()
        elif not archived and account.archived_at is not None:
            changes["archived_at"] = None

    currency = changes.get("currency") or account.currency
    money_changes = (changes.get("currency") not in (None, account.currency)) or (
        "opening_balance" in changes and changes["opening_balance"] != account.opening_balance
    )
    if money_changes and _has_transactions(db, account.id):
        raise Conflict(
            "ACCOUNT_HAS_TRANSACTIONS",
            "La cuenta ya tiene movimientos: no se puede cambiar la moneda ni el saldo inicial.",
        )
    for key in ("currency", "opening_balance", "opening_date", "name", "kind"):
        if key in changes and changes[key] is None:
            changes.pop(key)  # null en un campo obligatorio = sin cambio
    opening = changes.get("opening_balance", account.opening_balance)
    changes["opening_balance"] = validated_amount(opening, currency, allow_zero=True)

    before, after = apply_changes(account, changes)
    if after:
        flush_unique(db, ACCOUNT_CONFLICTS)
        verb = (
            "archived"
            if after.keys() == {"archived_at"} and account.archived_at is not None
            else "unarchived"
            if after.keys() == {"archived_at"}
            else "updated"
        )
        record(db, ctx, actor_id, "account", verb, account.id, before=before, after=after)
    db.commit()
    return account


# --- Categorías -------------------------------------------------------------------------

CATEGORY_CONFLICTS = {
    "uq_categories_context_id_parent_id_name": (
        "CATEGORY_NAME_TAKEN",
        "Ya existe una categoría con ese nombre en el mismo nivel.",
    )
}


def category_not_found() -> NotFound:
    return NotFound("CATEGORY_NOT_FOUND", "La categoría no existe en este contexto.")


def get_category(db: Session, ctx: FinancialContext, category_id: uuid.UUID) -> Category:
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.context_id == ctx.id)
    )
    if category is None:
        raise category_not_found()
    return category


def usable_category(db: Session, ctx: FinancialContext, category_id: uuid.UUID) -> Category:
    category = get_category(db, ctx, category_id)
    if category.archived_at is not None:
        raise Conflict("CATEGORY_ARCHIVED", "La categoría está archivada.")
    return category


def _check_parent(db: Session, ctx: FinancialContext, parent_id: uuid.UUID, kind: str) -> Category:
    parent = usable_category(db, ctx, parent_id)
    if parent.parent_id is not None:
        raise AppError(
            "CATEGORY_TOO_DEEP",
            "Las categorías tienen un solo nivel: el padre no puede ser una subcategoría.",
            status_code=422,
        )
    if parent.kind != kind:
        raise AppError(
            "CATEGORY_KIND_MISMATCH",
            "La subcategoría tiene que ser del mismo tipo (ingreso o gasto) que su padre.",
            status_code=422,
        )
    return parent


def list_categories(
    db: Session,
    ctx: FinancialContext,
    *,
    limit: int,
    before: uuid.UUID | None,
    include_archived: bool,
) -> list[Category]:
    query = select(Category).where(Category.context_id == ctx.id)
    if not include_archived:
        query = query.where(Category.archived_at.is_(None))
    return list(db.scalars(paginate(query, Category.id, before).limit(limit)))


def create_category(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    *,
    name: str,
    kind: str,
    parent_id: uuid.UUID | None,
    commit: bool = True,
) -> Category:
    if parent_id is not None:
        _check_parent(db, ctx, parent_id, kind)
    category = Category(context_id=ctx.id, name=name, kind=kind, parent_id=parent_id)
    db.add(category)
    flush_unique(db, CATEGORY_CONFLICTS)
    record(
        db,
        ctx,
        actor_id,
        "category",
        "created",
        category.id,
        after=snapshot(category, ("name", "kind", "parent_id")),
    )
    if commit:
        db.commit()
    return category


def update_category(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    category_id: uuid.UUID,
    data: dict[str, Any],
) -> Category:
    category = get_category(db, ctx, category_id)
    changes = dict(data)
    archived = changes.pop("archived", None)
    if archived is not None:
        if archived and category.archived_at is None:
            changes["archived_at"] = now()
        elif not archived and category.archived_at is not None:
            changes["archived_at"] = None
    if "name" in changes and changes["name"] is None:
        changes.pop("name")
    if changes.get("parent_id") is not None and changes["parent_id"] != category.parent_id:
        if changes["parent_id"] == category.id:
            raise AppError(
                "CATEGORY_TOO_DEEP", "Una categoría no puede ser su propio padre.", status_code=422
            )
        _check_parent(db, ctx, changes["parent_id"], category.kind)
        has_children = db.scalar(
            select(Category.id).where(Category.parent_id == category.id).limit(1)
        )
        if has_children is not None:
            raise AppError(
                "CATEGORY_TOO_DEEP",
                "La categoría tiene subcategorías: no puede pasar a ser subcategoría.",
                status_code=422,
            )

    before, after = apply_changes(category, changes)
    if after:
        flush_unique(db, CATEGORY_CONFLICTS)
        record(db, ctx, actor_id, "category", "updated", category.id, before=before, after=after)
    db.commit()
    return category


def has_categories(db: Session, ctx: FinancialContext) -> bool:
    return db.scalar(select(Category.id).where(Category.context_id == ctx.id).limit(1)) is not None


# --- Contrapartes -----------------------------------------------------------------------

COUNTERPARTY_FIELDS = ("name", "ruc", "ruc_check_digit", "kind", "notes")
COUNTERPARTY_CONFLICTS = {
    "uq_counterparties_ruc_per_context": (
        "COUNTERPARTY_RUC_TAKEN",
        "Ya existe una contraparte con ese RUC en este contexto.",
    )
}


def counterparty_not_found() -> NotFound:
    return NotFound("COUNTERPARTY_NOT_FOUND", "La contraparte no existe en este contexto.")


def get_counterparty(
    db: Session, ctx: FinancialContext, counterparty_id: uuid.UUID
) -> Counterparty:
    counterparty = db.scalar(
        select(Counterparty).where(
            Counterparty.id == counterparty_id, Counterparty.context_id == ctx.id
        )
    )
    if counterparty is None:
        raise counterparty_not_found()
    return counterparty


def usable_counterparty(
    db: Session, ctx: FinancialContext, counterparty_id: uuid.UUID
) -> Counterparty:
    counterparty = get_counterparty(db, ctx, counterparty_id)
    if counterparty.archived_at is not None:
        raise Conflict("COUNTERPARTY_ARCHIVED", "La contraparte está archivada.")
    return counterparty


def list_counterparties(
    db: Session,
    ctx: FinancialContext,
    *,
    limit: int,
    before: uuid.UUID | None,
    include_archived: bool,
    q: str | None,
) -> list[Counterparty]:
    query = select(Counterparty).where(Counterparty.context_id == ctx.id)
    if not include_archived:
        query = query.where(Counterparty.archived_at.is_(None))
    if q and q.strip():
        term = escape_like(q.strip())
        query = query.where(
            or_(
                Counterparty.name.ilike(f"%{term}%", escape="\\"),
                Counterparty.ruc.like(f"{term}%", escape="\\"),
            )
        )
    return list(db.scalars(paginate(query, Counterparty.id, before).limit(limit)))


def create_counterparty(
    db: Session, ctx: FinancialContext, actor_id: uuid.UUID, data: dict[str, Any]
) -> Counterparty:
    counterparty = Counterparty(context_id=ctx.id, **data)
    db.add(counterparty)
    flush_unique(db, COUNTERPARTY_CONFLICTS)
    record(
        db,
        ctx,
        actor_id,
        "counterparty",
        "created",
        counterparty.id,
        after=snapshot(counterparty, COUNTERPARTY_FIELDS),
    )
    db.commit()
    return counterparty


def update_counterparty(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    counterparty_id: uuid.UUID,
    data: dict[str, Any],
) -> Counterparty:
    counterparty = get_counterparty(db, ctx, counterparty_id)
    changes = dict(data)
    archived = changes.pop("archived", None)
    if archived is not None:
        if archived and counterparty.archived_at is None:
            changes["archived_at"] = now()
        elif not archived and counterparty.archived_at is not None:
            changes["archived_at"] = None
    for key in ("name", "kind"):
        if key in changes and changes[key] is None:
            changes.pop(key)
    before, after = apply_changes(counterparty, changes)
    if after:
        flush_unique(db, COUNTERPARTY_CONFLICTS)
        record(
            db,
            ctx,
            actor_id,
            "counterparty",
            "updated",
            counterparty.id,
            before=before,
            after=after,
        )
    db.commit()
    return counterparty
