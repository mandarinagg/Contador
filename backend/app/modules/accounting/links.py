"""Consultas de la contabilidad que usa el módulo de finanzas (sin importar sus servicios).

`finance.transactions` las usa para no anular ni cambiar un movimiento con asiento
contabilizado (D-041, BR-ACC-11), y `finance.router` para informar el asiento de cada
movimiento empresarial. Solo depende de los modelos, para no crear ciclos de importación.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.modules.accounting.models import JournalEntry


@dataclass(frozen=True)
class EntryRef:
    id: uuid.UUID
    number: int | None
    status: str


def journal_refs(db: Session, transaction_ids: list[uuid.UUID]) -> dict[uuid.UUID, EntryRef]:
    """Asiento de cada movimiento: el vivo (borrador o contabilizado) o, si no hay, el último
    revertido. Los descartados no cuentan."""
    if not transaction_ids:
        return {}
    rows = db.execute(
        select(
            JournalEntry.source_transaction_id,
            JournalEntry.id,
            JournalEntry.number,
            JournalEntry.status,
        )
        .where(
            JournalEntry.source_transaction_id.in_(transaction_ids),
            JournalEntry.status != "discarded",
        )
        .order_by(JournalEntry.source_transaction_id, JournalEntry.id)
    )
    result: dict[uuid.UUID, EntryRef] = {}
    for tx_id, entry_id, number, status in rows:
        if tx_id is None:  # pragma: no cover - filtrado por la consulta
            continue
        current = result.get(tx_id)
        # El vivo gana; entre revertidos, el más nuevo (ids uuidv7 en orden).
        if current is None or current.status == "reversed":
            result[tx_id] = EntryRef(entry_id, number, status)
    return result


def ensure_no_posted_entry(db: Session, transaction_ids: list[uuid.UUID], action: str) -> None:
    """409 si alguno de los movimientos tiene un asiento contabilizado."""
    posted = db.execute(
        select(JournalEntry.id, JournalEntry.number)
        .where(
            JournalEntry.source_transaction_id.in_(transaction_ids),
            JournalEntry.status == "posted",
        )
        .limit(1)
    ).first()
    if posted is not None:
        entry_id, number = posted
        raise Conflict(
            "TRANSACTION_HAS_POSTED_ENTRY",
            f"El movimiento tiene el asiento N° {number} contabilizado: revertí primero el "
            f"asiento N° {number} para {action}lo.",
            details={"entry_id": str(entry_id), "number": number},
        )
