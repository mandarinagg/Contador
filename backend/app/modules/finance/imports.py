"""Importación de extractos por lotes (BR-FIN-03, BR-FIN-08).

Flujo: analizar (`previewed`) → la persona revisa y decide fila por fila → confirmar
(`committed`) o cancelar (`cancelled`). Analizar **no crea movimientos**. Confirmar crea
en una sola transacción los movimientos de las filas `decision='import'` sin error; un
lote confirmado no se vuelve a confirmar (409), así que confirmar dos veces no duplica.

Duplicados: se comparan por `dedupe_key` contra los movimientos no anulados de la misma
cuenta y contra las filas anteriores del mismo archivo. Se **señalan** (nacen con
`decision='skip'`); la persona puede importarlos igual si son legítimos.

Auditoría por lote, no por fila (D-027): un evento al analizar, uno al confirmar y uno al
cancelar.
"""

import hashlib
import uuid
from collections.abc import Iterable
from decimal import Decimal
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.modules.finance import service as fs
from app.modules.finance.importing import ImportMapping, parse_file
from app.modules.finance.models import (
    Account,
    FinancialContext,
    ImportBatch,
    ImportRow,
    Transaction,
)
from app.modules.finance.money import AmountError, check_amount
from app.modules.finance.normalize import dedupe_key


def batch_not_found() -> NotFound:
    return NotFound("IMPORT_NOT_FOUND", "El lote de importación no existe en este contexto.")


def _safe_filename(filename: str | None) -> str:
    name = PureWindowsPath(PurePosixPath(filename or "").name).name.strip()
    return (name or "extracto")[:255]


def _existing_duplicates(
    db: Session, account_id: uuid.UUID, keys: Iterable[bytes]
) -> dict[bytes, uuid.UUID]:
    """Movimientos no anulados de la cuenta con esas claves (el más antiguo de cada una)."""
    unique = list(set(keys))
    found: dict[bytes, uuid.UUID] = {}
    for start in range(0, len(unique), 5000):
        chunk = unique[start : start + 5000]
        rows = db.execute(
            select(Transaction.dedupe_key, Transaction.id)
            .where(
                Transaction.account_id == account_id,
                Transaction.voided_at.is_(None),
                Transaction.dedupe_key.in_(chunk),
            )
            .order_by(Transaction.id)
        )
        for key, tx_id in rows:
            found.setdefault(key, tx_id)
    return found


def preview(
    db: Session,
    ctx: FinancialContext,
    actor_id: uuid.UUID,
    *,
    account_id: uuid.UUID,
    filename: str | None,
    content: bytes,
    mapping: ImportMapping,
) -> ImportBatch:
    account = fs.usable_account(db, ctx, account_id)
    parsed = parse_file(filename or "", content, mapping, account.currency)

    keys: dict[int, bytes] = {}
    for row in parsed.rows:
        if row.error is None and row.booked_on and row.amount is not None and row.description:
            keys[row.row_number] = dedupe_key(
                account.id, row.booked_on, row.amount, row.description, row.reference
            )
    existing = _existing_duplicates(db, account.id, keys.values())

    batch = ImportBatch(
        context_id=ctx.id,
        account_id=account.id,
        filename=_safe_filename(filename),
        file_sha256=hashlib.sha256(content).digest(),
        file_format=parsed.file_format,
        mapping=mapping.model_dump(mode="json"),
        status="previewed",
        created_by=actor_id,
    )
    db.add(batch)
    db.flush()

    first_seen: dict[bytes, int] = {}
    values: list[dict[str, Any]] = []
    errors = duplicates = 0
    for row in parsed.rows:
        key = keys.get(row.row_number)
        duplicate_of = existing.get(key) if key is not None else None
        duplicate_in_file = first_seen.get(key) if key is not None else None
        if key is not None and duplicate_in_file is None:
            first_seen[key] = row.row_number
        is_duplicate = duplicate_of is not None or duplicate_in_file is not None
        errors += row.error is not None
        duplicates += is_duplicate
        values.append(
            {
                "batch_id": batch.id,
                "row_number": row.row_number,
                "raw": row.raw,
                "booked_on": row.booked_on,
                "amount": row.amount,
                "description": row.description,
                "reference": row.reference,
                "error": row.error,
                "duplicate_of": duplicate_of,
                "duplicate_in_file": duplicate_in_file,
                # Duplicados y filas con error nacen descartados; el resto, a importar.
                "decision": "skip" if is_duplicate or row.error else "import",
            }
        )
    db.execute(insert(ImportRow), values)
    batch.rows_total = len(values)
    batch.rows_error = errors
    batch.rows_duplicate = duplicates
    db.flush()
    fs.record(
        db,
        ctx,
        actor_id,
        "import",
        "previewed",
        batch.id,
        after={
            "account_id": str(account.id),
            "filename": batch.filename,
            "file_sha256": batch.file_sha256.hex(),
            "file_format": batch.file_format,
            "rows_total": batch.rows_total,
            "rows_error": errors,
            "rows_duplicate": duplicates,
        },
    )
    db.commit()
    return batch


def get_batch(
    db: Session, ctx: FinancialContext, batch_id: uuid.UUID, *, lock: bool = False
) -> ImportBatch:
    query = select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.context_id == ctx.id)
    if lock:
        query = query.with_for_update()
    batch = db.scalar(query)
    if batch is None:
        raise batch_not_found()
    return batch


def list_batches(
    db: Session,
    ctx: FinancialContext,
    *,
    account_id: uuid.UUID | None,
    limit: int,
    before: uuid.UUID | None,
) -> list[ImportBatch]:
    query = select(ImportBatch).where(ImportBatch.context_id == ctx.id)
    if account_id is not None:
        query = query.where(ImportBatch.account_id == account_id)
    return list(db.scalars(fs.paginate(query, ImportBatch.id, before).limit(limit)))


def list_rows(db: Session, batch: ImportBatch, *, limit: int, after: int | None) -> list[ImportRow]:
    query = select(ImportRow).where(ImportRow.batch_id == batch.id)
    if after is not None:
        query = query.where(ImportRow.row_number > after)
    return list(db.scalars(query.order_by(ImportRow.row_number).limit(limit)))


def _require_previewed(batch: ImportBatch) -> None:
    if batch.status == "committed":
        raise Conflict("IMPORT_ALREADY_COMMITTED", "El lote ya fue importado.")
    if batch.status == "cancelled":
        raise Conflict("IMPORT_CANCELLED", "El lote fue cancelado.")


def set_decision(
    db: Session,
    ctx: FinancialContext,
    batch_id: uuid.UUID,
    row_number: int,
    decision: str,
) -> ImportRow:
    """Decisión de una fila antes de confirmar (no se audita: el lote aún no tuvo efecto)."""
    batch = get_batch(db, ctx, batch_id, lock=True)
    _require_previewed(batch)
    row = db.scalar(
        select(ImportRow).where(ImportRow.batch_id == batch.id, ImportRow.row_number == row_number)
    )
    if row is None:
        raise NotFound("IMPORT_ROW_NOT_FOUND", "La fila no existe en este lote.")
    if decision == "import" and row.error is not None:
        raise Conflict(
            "IMPORT_ROW_HAS_ERROR",
            "La fila tiene errores: no se puede importar.",
            details=row.error,
        )
    row.decision = decision
    db.commit()
    return row


def commit(
    db: Session, ctx: FinancialContext, actor_id: uuid.UUID, batch_id: uuid.UUID
) -> ImportBatch:
    batch = get_batch(db, ctx, batch_id, lock=True)
    _require_previewed(batch)
    # El candado de la cuenta serializa confirmaciones simultáneas sobre la misma cuenta.
    account = fs.get_account(db, ctx, batch.account_id, lock=True)
    if account.archived_at is not None:
        raise Conflict("ACCOUNT_ARCHIVED", "La cuenta está archivada: desarchivala para usarla.")

    rows = list(
        db.scalars(
            select(ImportRow)
            .where(
                ImportRow.batch_id == batch.id,
                ImportRow.decision == "import",
                ImportRow.error.is_(None),
            )
            .order_by(ImportRow.row_number)
        )
    )
    prepared: list[tuple[ImportRow, Decimal, bytes]] = []
    for row in rows:
        if row.booked_on is None or row.amount is None or row.description is None:
            raise AppError("IMPORT_STALE", "El lote está incompleto: analizá el archivo de nuevo.")
        try:
            amount = check_amount(row.amount, account.currency, allow_zero=False)
        except AmountError as exc:
            raise Conflict(
                "IMPORT_STALE",
                "La cuenta cambió desde el análisis: analizá el archivo de nuevo.",
            ) from exc
        key = dedupe_key(account.id, row.booked_on, amount, row.description, row.reference)
        prepared.append((row, amount, key))

    # Duplicados nuevos: movimientos cargados después del análisis (otro lote, alta manual).
    unflagged = [
        (row, key)
        for row, _, key in prepared
        if row.duplicate_of is None and row.duplicate_in_file is None
    ]
    existing = _existing_duplicates(db, account.id, (key for _, key in unflagged))
    new_duplicates = [(row, existing[key]) for row, key in unflagged if key in existing]
    if new_duplicates:
        for row, tx_id in new_duplicates:
            row.duplicate_of = tx_id
            row.decision = "skip"
        batch.rows_duplicate += len(new_duplicates)
        db.commit()  # se guarda la señal para que la persona la revise
        raise Conflict(
            "IMPORT_NEW_DUPLICATES",
            "Desde el análisis aparecieron movimientos iguales en la cuenta. "
            "Se marcaron como duplicados: revisalos y confirmá de nuevo.",
            details={"rows": [row.row_number for row, _ in new_duplicates]},
        )

    if prepared:
        db.execute(
            insert(Transaction),
            [
                {
                    "context_id": ctx.id,
                    "account_id": account.id,
                    "currency": account.currency,
                    "booked_on": row.booked_on,
                    "amount": amount,
                    "description": row.description,
                    "reference": row.reference,
                    "source": "import",
                    "import_batch_id": batch.id,
                    "dedupe_key": key,
                    "created_by": actor_id,
                    "reviewed_at": None,  # los importados nacen sin revisar
                }
                for row, amount, key in prepared
            ],
        )
    batch.status = "committed"
    batch.committed_at = fs.now()
    batch.rows_imported = len(prepared)
    db.flush()
    fs.record(
        db,
        ctx,
        actor_id,
        "import",
        "committed",
        batch.id,
        before={"status": "previewed"},
        after={
            "status": "committed",
            "account_id": str(account.id),
            "rows_imported": batch.rows_imported,
            "rows_skipped": batch.rows_total - batch.rows_imported,
        },
    )
    db.commit()
    return batch


def cancel(
    db: Session, ctx: FinancialContext, actor_id: uuid.UUID, batch_id: uuid.UUID
) -> ImportBatch:
    batch = get_batch(db, ctx, batch_id, lock=True)
    _require_previewed(batch)
    batch.status = "cancelled"
    fs.record(
        db,
        ctx,
        actor_id,
        "import",
        "cancelled",
        batch.id,
        before={"status": "previewed"},
        after={"status": "cancelled"},
    )
    db.commit()
    return batch


def account_currency(db: Session, account_id: uuid.UUID) -> str:
    return db.scalars(select(Account.currency).where(Account.id == account_id)).one()
