"""Plan de cuentas (D-037) y su estado de validación (D-038).

Reglas:
- Un plan por organización, jerárquico por código: el código de una cuenta hija es el de
  su padre más un segmento (`1.01.01` → `1.01.01.04`). El padre es una cuenta agrupadora.
- Una cuenta hija es del mismo estado contable que su padre: patrimonial (activo, pasivo,
  patrimonio) o de resultado (ingreso, gasto). Puede cambiar de tipo dentro del mismo
  estado (por ejemplo, `14.01` es ingreso dentro del grupo 14 de gastos).
- Una cuenta con líneas no cambia código, tipo, naturaleza ni imputabilidad; solo nombre y
  nota, y se puede archivar (BR-ACC-09). También lo impide un trigger.
- No se archiva una cuenta con saldo, con hijas sin archivar, usada en borradores, ni
  asignada en la configuración o en finanzas.
- El plan nace `pending` y solo lo marca `validated` un usuario con `accounting.post`, con
  nombre y matrícula del contador (BR-ACC-10). Un cambio estructural (alta, código, tipo,
  naturaleza, imputabilidad, archivo) lo vuelve a `pending` (D-046).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.accounting import proposed_chart
from app.modules.accounting.balances import (
    BALANCE_KINDS,
    COUNTED_STATUSES,
    Sums,
    account_sums,
    natural,
)
from app.modules.accounting.common import apply_changes, flush_translated, now, record, snapshot
from app.modules.accounting.models import (
    AccountingSettings,
    JournalEntry,
    JournalLine,
    LedgerAccount,
)
from app.modules.finance.models import Account, Category

ACCOUNT_FIELDS = (
    "code",
    "name",
    "kind",
    "normal_side",
    "is_postable",
    "parent_id",
    "origin",
    "note",
)
STRUCTURAL_FIELDS = frozenset({"code", "kind", "normal_side", "is_postable", "archived_at"})

# Vocabulario del YAML de la investigación → vocabulario del esquema.
YAML_KINDS = {
    "activo": "asset",
    "pasivo": "liability",
    "patrimonio": "equity",
    "ingreso": "income",
    "gasto": "expense",
}
YAML_SIDES = {"deudora": "debit", "acreedora": "credit"}
YAML_ORIGINS = {"rg49_2014": "rg49_2014", "propuesta": "proposed"}


def default_side(kind: str) -> str:
    return "debit" if kind in ("asset", "expense") else "credit"


def code_key(code: str) -> tuple[int, ...]:
    """Orden natural de códigos: `1.2` antes que `1.10`."""
    return tuple(int(part) for part in code.split("."))


def statement_of(kind: str) -> str:
    return "balance" if kind in BALANCE_KINDS else "result"


# --- Configuración y estado del plan ---------------------------------------------------


def get_settings(db: Session, organization_id: uuid.UUID) -> AccountingSettings | None:
    return db.scalar(
        select(AccountingSettings).where(AccountingSettings.organization_id == organization_id)
    )


def lock_settings(db: Session, organization_id: uuid.UUID) -> AccountingSettings:
    """Fila de configuración bloqueada (se crea si falta). Serializa cambios del plan."""
    db.execute(
        insert(AccountingSettings)
        .values(organization_id=organization_id)
        .on_conflict_do_nothing(index_elements=["organization_id"])
    )
    settings = db.scalar(
        select(AccountingSettings)
        .where(AccountingSettings.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert settings is not None  # recién insertada o existente
    return settings


def chart_status(db: Session, organization_id: uuid.UUID) -> str:
    settings = get_settings(db, organization_id)
    return settings.chart_status if settings is not None else "none"


SETTINGS_FIELDS = (
    "chart_status",
    "chart_validated_by_name",
    "chart_validated_reference",
    "chart_validated_at",
)


def _set_status(
    db: Session,
    settings: AccountingSettings,
    actor_id: uuid.UUID,
    status: str,
    verb: str,
    *,
    by_name: str | None = None,
    reference: str | None = None,
) -> None:
    validated = status == "validated"
    before, after = apply_changes(
        settings,
        {
            "chart_status": status,
            "chart_validated_by_name": by_name if validated else None,
            "chart_validated_reference": reference if validated else None,
            "chart_validated_at": now() if validated else None,
        },
    )
    if after:
        db.flush()
        record(
            db,
            settings.organization_id,
            actor_id,
            "chart",
            verb,
            settings.organization_id,
            before=before,
            after=after,
        )


def mark_pending(db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Un cambio estructural del plan exige volver a validarlo (D-046)."""
    settings = lock_settings(db, organization_id)
    if settings.chart_status != "pending":
        _set_status(db, settings, actor_id, "pending", "pending")


def validate_chart(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, by_name: str, reference: str
) -> AccountingSettings:
    settings = lock_settings(db, organization_id)
    if not _has_accounts(db, organization_id):
        raise Conflict("CHART_EMPTY", "El plan de cuentas está vacío: no hay nada que validar.")
    _set_status(
        db, settings, actor_id, "validated", "validated", by_name=by_name, reference=reference
    )
    db.commit()
    return settings


def invalidate_chart(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID
) -> AccountingSettings:
    settings = lock_settings(db, organization_id)
    if settings.chart_status != "validated":
        raise Conflict("CHART_NOT_VALIDATED", "El plan de cuentas no está validado.")
    _set_status(db, settings, actor_id, "pending", "invalidated")
    db.commit()
    return settings


def set_retained_earnings(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, account_id: uuid.UUID | None
) -> AccountingSettings:
    settings = lock_settings(db, organization_id)
    if account_id is not None:
        account = get_account(db, organization_id, account_id)
        if account.kind != "equity" or not account.is_postable or account.archived_at:
            raise AppError(
                "INVALID_RETAINED_EARNINGS_ACCOUNT",
                "La cuenta de resultados tiene que ser de patrimonio, imputable y no archivada "
                "(por ejemplo, 3.03.02 RESULTADO DEL EJERCICIO).",
                status_code=422,
            )
    before, after = apply_changes(settings, {"retained_earnings_account_id": account_id})
    if after:
        db.flush()
        record(
            db,
            organization_id,
            actor_id,
            "settings",
            "updated",
            settings.organization_id,
            before=before,
            after=after,
        )
    db.commit()
    return settings


# --- Cuentas -----------------------------------------------------------------------------


def account_not_found() -> NotFound:
    return NotFound("LEDGER_ACCOUNT_NOT_FOUND", "La cuenta contable no existe.")


def get_account(
    db: Session, organization_id: uuid.UUID, account_id: uuid.UUID, *, lock: bool = False
) -> LedgerAccount:
    query = select(LedgerAccount).where(
        LedgerAccount.id == account_id, LedgerAccount.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update()
    account = db.scalar(query)
    if account is None:
        raise account_not_found()
    return account


def _has_accounts(db: Session, organization_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(LedgerAccount.id)
            .where(LedgerAccount.organization_id == organization_id)
            .limit(1)
        )
        is not None
    )


def has_lines(db: Session, account_id: uuid.UUID) -> bool:
    return (
        db.scalar(select(JournalLine.id).where(JournalLine.account_id == account_id).limit(1))
        is not None
    )


def accounts_in_use(db: Session, organization_id: uuid.UUID) -> set[uuid.UUID]:
    used = select(LedgerAccount.id).where(
        LedgerAccount.organization_id == organization_id,
        exists().where(JournalLine.account_id == LedgerAccount.id),
    )
    return set(db.scalars(used))


def list_accounts(db: Session, organization_id: uuid.UUID) -> list[LedgerAccount]:
    accounts = list(
        db.scalars(select(LedgerAccount).where(LedgerAccount.organization_id == organization_id))
    )
    return sorted(accounts, key=lambda a: code_key(a.code))


def _check_child_code(code: str, parent: LedgerAccount | None) -> None:
    if parent is None:
        if "." in code:
            raise AppError(
                "ACCOUNT_CODE_INVALID",
                "Una cuenta sin padre lleva un código de un solo nivel (por ejemplo, 6).",
                status_code=422,
            )
        return
    prefix = parent.code + "."
    rest = code[len(prefix) :]
    if not code.startswith(prefix) or not rest or "." in rest:
        raise AppError(
            "ACCOUNT_CODE_INVALID",
            f"El código tiene que ser el de la cuenta padre más un nivel (por ejemplo, "
            f"{parent.code}.01).",
            status_code=422,
        )


def _check_parent(db: Session, organization_id: uuid.UUID, parent_id: uuid.UUID) -> LedgerAccount:
    parent = get_account(db, organization_id, parent_id)
    if parent.archived_at is not None:
        raise Conflict("ACCOUNT_ARCHIVED", "La cuenta padre está archivada.")
    if parent.is_postable:
        raise AppError(
            "PARENT_IS_POSTABLE",
            "La cuenta padre es imputable: solo una cuenta agrupadora tiene cuentas hijas.",
            status_code=422,
        )
    return parent


def _check_kind(kind: str, parent: LedgerAccount | None) -> None:
    if parent is not None and statement_of(kind) != statement_of(parent.kind):
        raise AppError(
            "ACCOUNT_KIND_MISMATCH",
            "Una cuenta hija es del mismo estado que su padre: patrimonial (activo, pasivo, "
            "patrimonio) o de resultados (ingreso, gasto).",
            status_code=422,
        )


ACCOUNT_CONFLICTS = {
    "uq_ledger_accounts_organization_id_code": (
        "ACCOUNT_CODE_TAKEN",
        "Ya existe una cuenta con ese código.",
    )
}


def create_account(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> LedgerAccount:
    parent = (
        _check_parent(db, organization_id, data["parent_id"])
        if data.get("parent_id") is not None
        else None
    )
    code = data["code"]
    _check_child_code(code, parent)
    kind = data.get("kind") or (parent.kind if parent is not None else None)
    if kind is None:
        raise AppError(
            "ACCOUNT_KIND_REQUIRED", "Indicá el tipo de una cuenta sin padre.", status_code=422
        )
    _check_kind(kind, parent)
    if db.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.organization_id == organization_id, LedgerAccount.code == code
        )
    ):
        raise Conflict("ACCOUNT_CODE_TAKEN", "Ya existe una cuenta con ese código.")
    account = LedgerAccount(
        organization_id=organization_id,
        code=code,
        name=data["name"],
        kind=kind,
        normal_side=data.get("normal_side") or default_side(kind),
        is_postable=data["is_postable"],
        parent_id=parent.id if parent is not None else None,
        origin="user",
        note=data.get("note"),
    )
    db.add(account)
    flush_translated(db)
    record(
        db,
        organization_id,
        actor_id,
        "ledger_account",
        "created",
        account.id,
        after=snapshot(account, ACCOUNT_FIELDS),
    )
    mark_pending(db, organization_id, actor_id)
    db.commit()
    return account


def _balance(db: Session, account: LedgerAccount) -> Decimal:
    """Debe - haber contabilizado de una cuenta (cero = se puede archivar)."""
    total = db.scalar(
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == account.id,
            JournalEntry.status.in_(COUNTED_STATUSES),
        )
    )
    return Decimal(total or 0)


def _check_archivable(db: Session, account: LedgerAccount) -> None:
    if _balance(db, account) != 0:
        raise Conflict(
            "ACCOUNT_HAS_BALANCE", "La cuenta tiene saldo: solo se archiva con saldo cero."
        )
    child = db.scalar(
        select(LedgerAccount.code).where(
            LedgerAccount.parent_id == account.id, LedgerAccount.archived_at.is_(None)
        )
    )
    if child is not None:
        raise Conflict(
            "ACCOUNT_HAS_CHILDREN",
            f"La cuenta tiene cuentas hijas sin archivar (por ejemplo, {child}).",
        )
    in_draft = db.scalar(
        select(JournalEntry.id)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .where(JournalLine.account_id == account.id, JournalEntry.status == "draft")
        .limit(1)
    )
    if in_draft is not None:
        raise Conflict(
            "ACCOUNT_IN_DRAFTS",
            "La cuenta se usa en borradores de asientos: descartalos o cambiales la cuenta.",
        )
    _check_not_assigned(db, account, "archivar")


def _check_not_assigned(db: Session, account: LedgerAccount, action: str) -> None:
    settings = get_settings(db, account.organization_id)
    if settings is not None and settings.retained_earnings_account_id == account.id:
        raise Conflict(
            "ACCOUNT_IN_SETTINGS",
            f"Es la cuenta de resultados del cierre: cambiala en la configuración antes de "
            f"{action}la.",
        )
    mapped = db.scalar(
        select(
            or_(
                exists().where(Account.ledger_account_id == account.id),
                exists().where(Category.ledger_account_id == account.id),
            )
        )
    )
    if mapped:
        raise Conflict(
            "ACCOUNT_MAPPED_IN_FINANCE",
            f"La cuenta está asignada a una cuenta o categoría de finanzas: quitala allí antes "
            f"de {action}la.",
        )


def update_account(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    account_id: uuid.UUID,
    data: dict[str, Any],
) -> LedgerAccount:
    account = get_account(db, organization_id, account_id, lock=True)
    changes = dict(data)
    archived = changes.pop("archived", None)
    for key in ("name", "code", "kind", "normal_side", "is_postable"):
        if key in changes and changes[key] is None:
            changes.pop(key)  # null en un campo obligatorio = sin cambio
    changes = {k: v for k, v in changes.items() if getattr(account, k) != v}

    structural = changes.keys() & {"code", "kind", "normal_side", "is_postable"}
    if structural and has_lines(db, account.id):
        raise Conflict(
            "ACCOUNT_IN_USE",
            "La cuenta tiene líneas de asiento: solo se cambian el nombre y la nota, o se archiva.",
        )
    has_children = (
        db.scalar(select(LedgerAccount.id).where(LedgerAccount.parent_id == account.id).limit(1))
        is not None
    )
    parent = (
        get_account(db, organization_id, account.parent_id)
        if account.parent_id is not None
        else None
    )
    if "code" in changes:
        if has_children:
            raise Conflict(
                "ACCOUNT_HAS_CHILDREN", "La cuenta tiene cuentas hijas: no cambia de código."
            )
        _check_child_code(changes["code"], parent)
    if changes.get("is_postable") is True and has_children:
        raise Conflict(
            "ACCOUNT_HAS_CHILDREN", "La cuenta tiene cuentas hijas: no puede ser imputable."
        )
    if "kind" in changes:
        _check_kind(changes["kind"], parent)
        if has_children and any(
            statement_of(k) != statement_of(changes["kind"])
            for k in db.scalars(
                select(LedgerAccount.kind).where(LedgerAccount.parent_id == account.id)
            )
        ):
            raise AppError(
                "ACCOUNT_KIND_MISMATCH",
                "Las cuentas hijas quedarían en otro estado contable que su padre.",
                status_code=422,
            )
    if changes.keys() & {"kind", "is_postable"}:
        _check_not_assigned(db, account, "cambiar")

    if archived is True and account.archived_at is None:
        _check_archivable(db, account)
        changes["archived_at"] = now()
    elif archived is False and account.archived_at is not None:
        if parent is not None and parent.archived_at is not None:
            raise Conflict("ACCOUNT_ARCHIVED", "La cuenta padre está archivada.")
        changes["archived_at"] = None

    before, after = apply_changes(account, changes)
    if after:
        if "code" in after and db.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.organization_id == organization_id,
                LedgerAccount.code == account.code,
                LedgerAccount.id != account.id,
            )
        ):
            raise Conflict("ACCOUNT_CODE_TAKEN", "Ya existe una cuenta con ese código.")
        flush_translated(db)
        verb = (
            "archived"
            if after.keys() == {"archived_at"} and account.archived_at is not None
            else "unarchived"
            if after.keys() == {"archived_at"}
            else "updated"
        )
        record(
            db,
            organization_id,
            actor_id,
            "ledger_account",
            verb,
            account.id,
            before=before,
            after=after,
        )
        if after.keys() & STRUCTURAL_FIELDS:
            mark_pending(db, organization_id, actor_id)
    db.commit()
    return account


def load_proposed(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID
) -> list[LedgerAccount]:
    """Carga el plan propuesto (159 cuentas) si la organización no tiene ninguna."""
    settings = lock_settings(db, organization_id)  # serializa dos cargas simultáneas
    if _has_accounts(db, organization_id):
        raise Conflict(
            "CHART_NOT_EMPTY",
            "La organización ya tiene cuentas: el plan propuesto solo se carga en un plan vacío.",
        )
    rows = sorted(proposed_chart.CUENTAS, key=lambda r: code_key(str(r["codigo"])))
    by_code: dict[str, LedgerAccount] = {}
    # Por niveles: el padre ya tiene id cuando se inserta la hija.
    for depth in sorted({str(r["codigo"]).count(".") for r in rows}):
        level = []
        for row in rows:
            code = str(row["codigo"])
            if code.count(".") != depth:
                continue
            parent_code = row["padre"]
            account = LedgerAccount(
                organization_id=organization_id,
                code=code,
                name=row["nombre"],
                kind=YAML_KINDS[row["tipo"]],
                normal_side=YAML_SIDES[row["naturaleza"]],
                is_postable=bool(row["imputable"]),
                parent_id=by_code[parent_code].id if parent_code is not None else None,
                origin=YAML_ORIGINS[row["origen"]],
                note=row.get("nota"),
            )
            db.add(account)
            level.append(account)
            by_code[code] = account
        db.flush()
        for account in level:
            record(
                db,
                organization_id,
                actor_id,
                "ledger_account",
                "created",
                account.id,
                after=snapshot(account, ACCOUNT_FIELDS),
            )
    record(
        db,
        organization_id,
        actor_id,
        "chart",
        "loaded",
        organization_id,
        after={"source": "proposed", "accounts": len(by_code), "base": proposed_chart.META["base"]},
    )
    _set_status(db, settings, actor_id, "pending", "pending")
    db.commit()
    return sorted(by_code.values(), key=lambda a: code_key(a.code))


# --- Árbol con saldos --------------------------------------------------------------------


@dataclass
class Node:
    account: LedgerAccount
    sums: Sums = field(default_factory=Sums)
    children: list["Node"] = field(default_factory=list)

    @property
    def amount(self) -> Decimal:
        return natural(self.account.kind, self.sums)

    @property
    def has_movement(self) -> bool:
        return self.sums.debit != 0 or self.sums.credit != 0


def build_tree(accounts: list[LedgerAccount], sums: dict[uuid.UUID, Sums]) -> list[Node]:
    """Árbol ordenado por código; cada nodo suma el debe y el haber de su subárbol."""
    nodes = {a.id: Node(a, sums.get(a.id, Sums())) for a in accounts}
    roots: list[Node] = []
    for account in sorted(accounts, key=lambda a: code_key(a.code)):
        node = nodes[account.id]
        parent = nodes.get(account.parent_id) if account.parent_id is not None else None
        (parent.children if parent is not None else roots).append(node)

    def total(node: Node) -> Sums:
        for child in node.children:
            node.sums = node.sums + total(child)
        return node.sums

    for root in roots:
        total(root)
    return roots


def chart_tree(
    db: Session, organization_id: uuid.UUID, balance_at: date | None
) -> tuple[list[Node], set[uuid.UUID]]:
    accounts = list_accounts(db, organization_id)
    sums = account_sums(db, organization_id, date_to=balance_at) if balance_at else {}
    return build_tree(accounts, sums), accounts_in_use(db, organization_id)
