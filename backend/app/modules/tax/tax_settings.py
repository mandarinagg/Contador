"""Configuración tributaria (`tax.settings`, D-091, D-092, D-096).

Cada cuenta, si no está configurada, es la del plan propuesto con ese código (si la
organización la tiene, imputable y sin archivar). Así funciona sin configurar nada con el
plan propuesto cargado, y se puede cambiar si el plan es otro.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.accounting.models import LedgerAccount
from app.modules.tax.common import apply_changes, flush_translated, record
from app.modules.tax.models import TaxSettings

# Campo → (código por defecto en el plan propuesto, tipos de cuenta admitidos, nombre).
ACCOUNT_FIELDS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "vat_credit_10_account_id": ("1.01.03.05.03.01", ("asset",), "IVA crédito fiscal 10 %"),
    "vat_credit_5_account_id": ("1.01.03.05.03.02", ("asset",), "IVA crédito fiscal 5 %"),
    "vat_debit_10_account_id": ("2.01.03.01.02.01", ("liability",), "IVA débito fiscal 10 %"),
    "vat_debit_5_account_id": ("2.01.03.01.02.02", ("liability",), "IVA débito fiscal 5 %"),
    "suppliers_account_id": ("2.01.01.01", ("liability",), "proveedores"),
    "customers_account_id": ("1.01.03.01", ("asset",), "clientes (deudores por ventas)"),
}
DEFAULT_ALERT_DAYS = 10


@dataclass(frozen=True)
class EffectiveSettings:
    """Lo configurado y lo que efectivamente se usa (configurado o por defecto)."""

    configured: dict[str, uuid.UUID | None]
    effective: dict[str, LedgerAccount | None]
    alert_days: int


def get_row(db: Session, organization_id: uuid.UUID) -> TaxSettings | None:
    return db.scalar(select(TaxSettings).where(TaxSettings.organization_id == organization_id))


def _usable(account: LedgerAccount | None) -> bool:
    return account is not None and account.is_postable and account.archived_at is None


def effective(db: Session, organization_id: uuid.UUID) -> EffectiveSettings:
    row = get_row(db, organization_id)
    configured = {name: getattr(row, name) if row else None for name in ACCOUNT_FIELDS}
    ids = [v for v in configured.values() if v is not None]
    codes = [default for default, _, _ in ACCOUNT_FIELDS.values()]
    accounts = list(
        db.scalars(
            select(LedgerAccount).where(
                LedgerAccount.organization_id == organization_id,
                (LedgerAccount.id.in_(ids)) | (LedgerAccount.code.in_(codes)),
            )
        )
    )
    by_id = {a.id: a for a in accounts}
    by_code = {a.code: a for a in accounts}
    result: dict[str, LedgerAccount | None] = {}
    for name, (default, _, _) in ACCOUNT_FIELDS.items():
        chosen = configured[name]
        account = by_id.get(chosen) if chosen is not None else by_code.get(default)
        result[name] = account if _usable(account) else None
    return EffectiveSettings(
        configured=configured,
        effective=result,
        alert_days=row.alert_days if row else DEFAULT_ALERT_DAYS,
    )


def update(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, data: dict[str, Any]
) -> EffectiveSettings:
    """Cambia solo los campos que llegan; `null` en una cuenta vuelve al valor por defecto."""
    for name, value in data.items():
        if name in ACCOUNT_FIELDS and value is not None:
            _check_account(db, organization_id, name, value)
    row = get_row(db, organization_id)
    if row is None:
        row = TaxSettings(organization_id=organization_id)
        db.add(row)
        flush_translated(db)
        db.refresh(row)
    before, after = apply_changes(row, data)
    flush_translated(db)
    if after:
        record(
            db, organization_id, actor_id, "settings", "updated", row.id, before=before, after=after
        )
    db.commit()
    return effective(db, organization_id)


def _check_account(
    db: Session, organization_id: uuid.UUID, name: str, account_id: uuid.UUID
) -> None:
    _, kinds, label = ACCOUNT_FIELDS[name]
    account = db.scalar(
        select(LedgerAccount).where(
            LedgerAccount.id == account_id, LedgerAccount.organization_id == organization_id
        )
    )
    if account is None:
        raise AppError(
            "LEDGER_ACCOUNT_NOT_FOUND", f"La cuenta de {label} no existe.", status_code=422
        )
    if not _usable(account):
        raise AppError(
            "ACCOUNT_NOT_POSTABLE",
            f"La cuenta {account.code} es agrupadora o está archivada: elegí una imputable.",
            status_code=422,
        )
    if account.kind not in kinds:
        raise AppError(
            "LEDGER_ACCOUNT_KIND_MISMATCH",
            f"La cuenta de {label} tiene que ser "
            + ("de activo" if kinds == ("asset",) else "de pasivo")
            + f"; {account.code} es de otro tipo.",
            status_code=422,
        )
