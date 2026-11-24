"""Finanzas ↔ contabilidad (D-041): cuentas contables en finanzas y asiento propuesto.

- `finance.accounts.ledger_account_id` es la cuenta contable del banco o la caja (activo o
  pasivo: una tarjeta de crédito es pasivo) y `finance.categories.ledger_account_id` la de
  resultado (ingreso o gasto, según la categoría). Solo en el contexto empresarial, de la
  misma organización, imputables y no archivadas; asignarlas exige `accounting.manage`.
- Un movimiento empresarial puede proponer un **borrador**, nunca un asiento contabilizado
  (BR-ACC-06): un ingreso debita el banco y acredita la cuenta de la categoría; un gasto,
  al revés. Si la subcategoría no tiene cuenta contable se usa la de su categoría padre.
- Un movimiento personal no origina asientos (BR-ACC-07): para la contabilidad no existe
  (404), y la base lo impide aunque el código fallara (D-035).
- En otra moneda, la persona escribe la cotización (D-036). Si el importe en guaraníes no
  da entero, no se redondea en silencio: se pide `amount_pyg` explícito (el entero de
  abajo o el de arriba del producto exacto).
- Si un comprobante vinculado al movimiento ya tiene asiento vivo, el movimiento no propone
  otro (409 `TRANSACTION_VOUCHER_HAS_ENTRY`, D-091, BR-TAX-10).
"""

import uuid
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.permissions import Perm
from app.modules.accounting import chart, entries
from app.modules.accounting.balances import ZERO
from app.modules.accounting.common import pyg_amount
from app.modules.accounting.models import JournalEntry, LedgerAccount
from app.modules.finance.models import Account, Category, FinancialContext, Transaction
from app.modules.tax import links as tax_links

BANK_KINDS = ("asset", "liability")


def check_ledger_assignment(
    db: Session,
    auth: AuthContext,
    ctx: FinancialContext,
    ledger_account_id: uuid.UUID | None,
    *,
    target: str,
    category_kind: str | None = None,
) -> None:
    """Valida `ledger_account_id` para una cuenta (`target="account"`) o categoría."""
    if ctx.kind != "business":
        raise AppError(
            "LEDGER_ACCOUNT_BUSINESS_ONLY",
            "Las cuentas contables se asignan solo en las finanzas de la empresa.",
            status_code=422,
        )
    if Perm.ACCOUNTING_MANAGE.value not in auth.permissions:
        raise Forbidden(
            "FORBIDDEN",
            "No tenés permiso para asignar cuentas contables.",
            details={"missing": [Perm.ACCOUNTING_MANAGE.value]},
        )
    if ledger_account_id is None:
        return
    account = db.scalar(
        select(LedgerAccount).where(
            LedgerAccount.id == ledger_account_id,
            LedgerAccount.organization_id == ctx.organization_id,
        )
    )
    if account is None:
        raise AppError("LEDGER_ACCOUNT_NOT_FOUND", "La cuenta contable no existe.", status_code=422)
    if not account.is_postable or account.archived_at is not None:
        raise AppError(
            "ACCOUNT_NOT_POSTABLE",
            f"La cuenta {account.code} es agrupadora o está archivada: elegí una imputable.",
            status_code=422,
        )
    allowed = BANK_KINDS if target == "account" else (category_kind,)
    if account.kind not in allowed:
        expected = (
            "de activo o de pasivo (una tarjeta de crédito es pasivo)"
            if target == "account"
            else "de ingreso"
            if category_kind == "income"
            else "de gasto"
        )
        raise AppError(
            "LEDGER_ACCOUNT_KIND_MISMATCH",
            f"La cuenta contable tiene que ser {expected}; {account.code} es de otro tipo.",
            status_code=422,
        )


def business_transaction(
    db: Session, organization_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    tx = db.scalar(
        select(Transaction)
        .join(FinancialContext, FinancialContext.id == Transaction.context_id)
        .where(
            Transaction.id == transaction_id,
            FinancialContext.organization_id == organization_id,
            FinancialContext.kind == "business",
        )
    )
    if tx is None:
        # Un movimiento personal tampoco existe para la contabilidad (D-024, D-035).
        raise NotFound("TRANSACTION_NOT_FOUND", "El movimiento no existe en la empresa.")
    return tx


def _ledger(db: Session, organization_id: uuid.UUID, account_id: uuid.UUID) -> LedgerAccount:
    return chart.get_account(db, organization_id, account_id)


def _pyg_value(
    tx: Transaction, fx_rate: Decimal | None, amount_pyg: Decimal | None
) -> tuple[Decimal, tuple[str, Decimal, Decimal] | None]:
    magnitude = abs(tx.amount)
    if tx.currency == "PYG":
        if fx_rate is not None or amount_pyg is not None:
            raise AppError(
                "FX_NOT_APPLICABLE",
                "El movimiento es en guaraníes: no lleva cotización.",
                status_code=422,
            )
        return magnitude, None
    if fx_rate is None:
        raise AppError(
            "FX_RATE_REQUIRED",
            f"El movimiento es en {tx.currency}: indicá la cotización (`fx_rate`, guaraníes por "
            f"1 {tx.currency}).",
            status_code=422,
        )
    if fx_rate <= 0:
        raise AppError("INVALID_AMOUNT", "La cotización va en positivo.", status_code=422)
    with localcontext() as context:
        context.prec = 60  # exacto: 16 + 6 dígitos de cotización entran holgados
        exact = magnitude * fx_rate
        floor = exact.to_integral_value(rounding=ROUND_FLOOR)
        ceil = exact.to_integral_value(rounding=ROUND_CEILING)
    if amount_pyg is None:
        if exact != floor:
            raise AppError(
                "FX_ROUNDING_REQUIRED",
                f"{magnitude:f} {tx.currency} por {fx_rate:f} = {exact:f} guaraníes, que no es un "
                f"número entero. Indicá el importe redondeado en `amount_pyg` ({floor:f} o "
                f"{ceil:f}).",
                details={
                    "exact": format(exact, "f"),
                    "floor": format(floor, "f"),
                    "ceil": format(ceil, "f"),
                },
                status_code=422,
            )
        value = floor
    else:
        value = pyg_amount(amount_pyg, field="amount_pyg")
        if value not in (floor, ceil):
            raise AppError(
                "FX_ROUNDING_INVALID",
                f"`amount_pyg` tiene que ser {floor:f} o {ceil:f} (el producto exacto es "
                f"{exact:f}).",
                status_code=422,
            )
    if value <= 0:
        raise AppError(
            "INVALID_AMOUNT",
            "El importe en guaraníes da cero: revisá la cotización.",
            status_code=422,
        )
    return value, (tx.currency, magnitude, fx_rate)


def propose_from_transaction(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    transaction_id: uuid.UUID,
    *,
    fx_rate: Decimal | None,
    amount_pyg: Decimal | None,
) -> JournalEntry:
    tx = business_transaction(db, organization_id, transaction_id)
    if tx.voided_at is not None:
        raise Conflict("TRANSACTION_VOIDED", "El movimiento está anulado.")
    # BR-TAX-10: si un comprobante del movimiento ya tiene asiento vivo, no hay otro.
    tax_links.check_transaction_free(db, tx.id)
    live = db.execute(
        select(JournalEntry.id, JournalEntry.number, JournalEntry.status).where(
            JournalEntry.source_transaction_id == tx.id,
            JournalEntry.status.in_(("draft", "posted")),
        )
    ).first()
    if live is not None:
        entry_id, number, status = live
        what = "un borrador" if status == "draft" else f"el asiento N° {number} contabilizado"
        raise Conflict(
            "TRANSACTION_HAS_ENTRY",
            f"El movimiento ya tiene {what}.",
            details={"entry_id": str(entry_id), "number": number, "status": status},
        )
    if tx.transfer_group_id is not None:
        raise AppError(
            "TRANSFER_NOT_SUPPORTED",
            "Una transferencia entre cuentas propias se registra con un asiento manual.",
            status_code=422,
        )
    bank = db.get(Account, tx.account_id)
    assert bank is not None  # clave foránea
    missing: list[dict[str, Any]] = []
    if bank.ledger_account_id is None:
        missing.append({"kind": "account", "id": str(bank.id), "name": bank.name})
    category = db.get(Category, tx.category_id) if tx.category_id is not None else None
    if tx.category_id is None:
        raise AppError(
            "CATEGORY_REQUIRED",
            "El movimiento no tiene categoría: asignale una para saber a qué cuenta de "
            "resultado va.",
            status_code=422,
        )
    assert category is not None
    category_ledger = category.ledger_account_id
    if category_ledger is None and category.parent_id is not None:
        parent = db.get(Category, category.parent_id)
        category_ledger = parent.ledger_account_id if parent is not None else None
    if category_ledger is None:
        missing.append({"kind": "category", "id": str(category.id), "name": category.name})
    if missing:
        names = " y ".join(
            f"la cuenta «{m['name']}»" if m["kind"] == "account" else f"la categoría «{m['name']}»"
            for m in missing
        )
        raise AppError(
            "LEDGER_ACCOUNT_MISSING",
            f"Falta asignar la cuenta contable de {names}.",
            details={"missing": missing},
            status_code=422,
        )
    assert bank.ledger_account_id is not None and category_ledger is not None
    _ledger(db, organization_id, bank.ledger_account_id)
    _ledger(db, organization_id, category_ledger)

    value, fx = _pyg_value(tx, fx_rate, amount_pyg)
    fx_currency, fx_amount, rate = fx if fx is not None else (None, None, None)
    # Ingreso: debe banco, haber cuenta de la categoría. Gasto: debe categoría, haber banco.
    debit_account, credit_account = (
        (bank.ledger_account_id, category_ledger)
        if tx.amount > 0
        else (category_ledger, bank.ledger_account_id)
    )
    raw_lines: list[dict[str, Any]] = [
        {
            "account_id": account_id,
            "debit": debit,
            "credit": credit,
            "fx_currency": fx_currency,
            "fx_amount": fx_amount,
            "fx_rate": rate,
            "description": tx.description[:300],
        }
        for account_id, debit, credit in (
            (debit_account, value, ZERO),
            (credit_account, ZERO, value),
        )
    ]
    lines = entries.validated_lines(db, organization_id, raw_lines)
    return entries.create_draft(
        db,
        organization_id,
        actor_id,
        {
            "entry_date": tx.booked_on,
            "description": tx.description,
            "document_reference": tx.reference,
        },
        kind="finance",
        source=tx,
        lines=lines,
    )
