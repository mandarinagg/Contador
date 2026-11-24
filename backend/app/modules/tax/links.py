"""Vínculo comprobante ↔ movimiento ↔ asiento (D-091, BR-TAX-10).

Lo usa la contabilidad al proponer un asiento desde un movimiento: si un comprobante
vinculado a ese movimiento ya tiene asiento vivo, el movimiento no propone otro (409
`TRANSACTION_VOUCHER_HAS_ENTRY`). El trigger `journal_entries_voucher_guard` lo impide
también en la base. Solo importa modelos, para no crear ciclos entre módulos.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.modules.accounting.models import JournalEntry
from app.modules.tax.models import Voucher


def check_transaction_free(db: Session, transaction_id: uuid.UUID) -> None:
    row = db.execute(
        select(
            Voucher.id, Voucher.number, JournalEntry.id, JournalEntry.number, JournalEntry.status
        )
        .join(JournalEntry, JournalEntry.id == Voucher.journal_entry_id)
        .where(
            Voucher.transaction_id == transaction_id,
            JournalEntry.status.in_(("draft", "posted")),
        )
        .limit(1)
    ).first()
    if row is None:
        return
    voucher_id, voucher_number, entry_id, entry_number, status = row
    what = "un borrador" if status == "draft" else f"el asiento N° {entry_number}"
    raise Conflict(
        "TRANSACTION_VOUCHER_HAS_ENTRY",
        f"El comprobante {voucher_number}, vinculado a este movimiento, ya tiene {what}: el "
        "mismo hecho no se contabiliza dos veces.",
        details={
            "voucher_id": str(voucher_id),
            "entry_id": str(entry_id),
            "number": entry_number,
            "status": status,
        },
    )
