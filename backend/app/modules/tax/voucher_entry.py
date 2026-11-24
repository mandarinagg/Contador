"""Asiento propuesto desde un comprobante (D-091, BR-TAX-10). Siempre un **borrador**.

- **Compra** (factura o nota de débito recibida): debe a la cuenta elegida (gasto o activo)
  por la base, debe a IVA crédito fiscal 10 % y 5 % por el impuesto, y haber a proveedores
  (a crédito) o al banco o la caja del movimiento vinculado (al contado). Si la compra no
  imputa IVA, el impuesto no es crédito: va a la cuenta elegida, como costo.
- **Venta** (factura o nota de débito emitida): lo simétrico, con IVA débito fiscal (una
  venta siempre genera débito) y clientes o el banco del movimiento.
- **Nota de crédito**: los mismos renglones con los lados invertidos.
- Al contado y sin movimiento vinculado, la contrapartida (caja o banco) la elige la persona
  (`counterpart_account_id`).
- Nunca dos asientos vivos para el mismo hecho: si el comprobante ya tiene asiento vivo, 409
  `VOUCHER_HAS_ENTRY`; si el movimiento vinculado ya tiene uno, 409
  `VOUCHER_TRANSACTION_HAS_ENTRY`. Con movimiento, el asiento es de tipo `finance` y lleva el
  movimiento como origen (el índice único de un asiento vivo por movimiento lo respalda);
  sin movimiento, es `manual`. El comprobante guarda el asiento en `journal_entry_id`.
- Contabiliza una persona (BR-ACC-06): esto solo arma el borrador.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.modules.accounting import entries
from app.modules.accounting.finance_link import business_transaction
from app.modules.accounting.models import JournalEntry, LedgerAccount
from app.modules.finance.models import Account, Transaction
from app.modules.tax import tax_settings, vouchers
from app.modules.tax.common import ZERO, record
from app.modules.tax.models import Voucher

ACCOUNT_KINDS = {"purchase": ("expense", "asset"), "sale": ("income",)}
COUNTERPART_KINDS = ("asset", "liability")


def _account(
    db: Session, organization_id: uuid.UUID, account_id: uuid.UUID, kinds: tuple[str, ...]
) -> LedgerAccount:
    account = db.scalar(
        select(LedgerAccount).where(
            LedgerAccount.id == account_id, LedgerAccount.organization_id == organization_id
        )
    )
    if account is None:
        raise AppError("LEDGER_ACCOUNT_NOT_FOUND", "La cuenta no existe.", status_code=422)
    if not account.is_postable or account.archived_at is not None:
        raise AppError(
            "ACCOUNT_NOT_POSTABLE",
            f"La cuenta {account.code} es agrupadora o está archivada: elegí una imputable.",
            status_code=422,
        )
    if account.kind not in kinds:
        names = {
            "expense": "gasto",
            "asset": "activo",
            "income": "ingreso",
            "liability": "pasivo",
        }
        raise AppError(
            "LEDGER_ACCOUNT_KIND_MISMATCH",
            f"La cuenta {account.code} no es de "
            + " ni de ".join(names.get(k, k) for k in kinds)
            + ".",
            status_code=422,
        )
    return account


def _live_entry_of_transaction(db: Session, tx: Transaction) -> JournalEntry | None:
    return db.scalar(
        select(JournalEntry).where(
            JournalEntry.source_transaction_id == tx.id,
            JournalEntry.status.in_(vouchers.LIVE),
        )
    )


def propose(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    voucher_id: uuid.UUID,
    data: dict[str, Any],
) -> JournalEntry:
    voucher = vouchers.get_voucher(db, organization_id, voucher_id, lock=True)
    if voucher.voided_at is not None:
        raise Conflict("VOUCHER_VOIDED", "El comprobante está anulado: no se contabiliza.")
    existing = vouchers.live_entry(db, voucher)
    if existing is not None:
        what = "un borrador" if existing.status == "draft" else f"el asiento N° {existing.number}"
        raise Conflict(
            "VOUCHER_HAS_ENTRY",
            f"El comprobante ya tiene {what}.",
            details={"entry_id": str(existing.id), "status": existing.status},
        )
    tx: Transaction | None = None
    if voucher.transaction_id is not None:
        tx = business_transaction(db, organization_id, voucher.transaction_id)
        if tx.voided_at is not None:
            raise Conflict("TRANSACTION_VOIDED", "El movimiento vinculado está anulado.")
        tx_entry = _live_entry_of_transaction(db, tx)
        if tx_entry is not None:
            what = (
                "un borrador" if tx_entry.status == "draft" else f"el asiento N° {tx_entry.number}"
            )
            raise Conflict(
                "VOUCHER_TRANSACTION_HAS_ENTRY",
                f"El movimiento vinculado ya tiene {what}: el mismo hecho no se contabiliza dos "
                "veces. Descartalo o revertilo, o desvinculá el movimiento del comprobante.",
                details={"entry_id": str(tx_entry.id), "status": tx_entry.status},
            )

    settings = tax_settings.effective(db, organization_id).effective
    main = _account(db, organization_id, data["account_id"], ACCOUNT_KINDS[voucher.direction])
    counterpart = _counterpart(db, organization_id, voucher, tx, data, settings)

    sale = voucher.direction == "sale"
    takes_vat = sale or voucher.imputes_vat
    vat_lines: list[tuple[str, Decimal]] = []
    if takes_vat:
        prefix = "vat_debit" if sale else "vat_credit"
        for rate, amount in (("10", voucher.vat_10), ("5", voucher.vat_5)):
            if amount > 0:
                vat_lines.append((f"{prefix}_{rate}_account_id", amount))
    missing = [name for name, _ in vat_lines if settings[name] is None]
    if missing:
        raise AppError(
            "TAX_ACCOUNT_MISSING",
            "Falta la cuenta de "
            + " y de ".join(tax_settings.ACCOUNT_FIELDS[m][2] for m in missing)
            + ": cargá el plan propuesto o configurala en la tributación.",
            details={"missing": missing},
            status_code=422,
        )
    total = vouchers.total_of(voucher)
    vat_total = sum((amount for _, amount in vat_lines), ZERO)
    base = total - vat_total
    label = f"{_kind_label(voucher)} {voucher.number} — {voucher.counterparty_name}"[:300]
    # (cuenta, importe, ¿al debe en una factura de compra?)
    rows: list[tuple[uuid.UUID, Decimal, bool]] = [(main.id, base, not sale)]
    for name, amount in vat_lines:
        account = settings[name]
        assert account is not None
        rows.append((account.id, amount, not sale))
    rows.append((counterpart.id, total, sale))
    reverse = voucher.voucher_type == "credit_note"
    raw_lines = [
        {
            "account_id": account_id,
            "debit": amount if debit != reverse else ZERO,
            "credit": amount if debit == reverse else ZERO,
            "description": label,
        }
        for account_id, amount, debit in rows
        if amount > 0
    ]
    lines = entries.validated_lines(db, organization_id, raw_lines)
    entry = entries.create_draft(
        db,
        organization_id,
        actor_id,
        {
            "entry_date": voucher.issued_on,
            "description": (data.get("description") or label)[:500],
            "document_reference": f"{voucher.timbrado} {voucher.number}"[:100],
        },
        kind="finance" if tx is not None else "manual",
        source=tx,
        lines=lines,
        commit=False,
    )
    voucher.journal_entry_id = entry.id
    db.flush()
    record(
        db,
        organization_id,
        actor_id,
        "voucher",
        "entry_proposed",
        voucher.id,
        after={"journal_entry_id": str(entry.id)},
    )
    db.commit()
    return entry


def _kind_label(voucher: Voucher) -> str:
    return {
        "invoice": "Factura",
        "credit_note": "Nota de crédito",
        "debit_note": "Nota de débito",
    }[voucher.voucher_type]


def _counterpart(
    db: Session,
    organization_id: uuid.UUID,
    voucher: Voucher,
    tx: Transaction | None,
    data: dict[str, Any],
    settings: dict[str, LedgerAccount | None],
) -> LedgerAccount:
    if voucher.condition == "credit":
        name = "suppliers_account_id" if voucher.direction == "purchase" else "customers_account_id"
        account = settings[name]
        if account is None:
            raise AppError(
                "TAX_ACCOUNT_MISSING",
                f"Falta la cuenta de {tax_settings.ACCOUNT_FIELDS[name][2]}: cargá el plan "
                "propuesto o configurala en la tributación.",
                details={"missing": [name]},
                status_code=422,
            )
        return account
    if tx is not None:
        bank = db.get(Account, tx.account_id)
        assert bank is not None  # clave foránea
        if bank.ledger_account_id is None:
            raise AppError(
                "LEDGER_ACCOUNT_MISSING",
                f"Falta asignar la cuenta contable de la cuenta «{bank.name}».",
                details={"missing": [{"kind": "account", "id": str(bank.id), "name": bank.name}]},
                status_code=422,
            )
        return _account(db, organization_id, bank.ledger_account_id, COUNTERPART_KINDS)
    counterpart_id = data.get("counterpart_account_id")
    if counterpart_id is None:
        raise AppError(
            "COUNTERPART_ACCOUNT_REQUIRED",
            "Es al contado y no tiene movimiento vinculado: elegí la cuenta de caja o banco "
            "(`counterpart_account_id`).",
            status_code=422,
        )
    return _account(db, organization_id, counterpart_id, COUNTERPART_KINDS)
