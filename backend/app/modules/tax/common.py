"""Utilidades compartidas de la tributación: auditoría, guaraníes, fechas y errores.

- Auditoría (D-095): todo cambio se registra con `audit.record`, acción `tax.<entidad>.<verbo>`
  y solo los campos que cambian. Las reglas, los feriados y las excepciones son globales,
  pero el cambio se audita en la organización de quien lo hace (es la que lo ve).
- Importes: guaraníes enteros, `Decimal` en Python y string en JSON; nunca `float`.
- Rechazos de la base (triggers `trg_*` y restricciones): el servicio valida antes para dar
  errores legibles; si igual llega un rechazo (una carrera), se traduce acá.
"""

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.modules.audit import service as audit
from app.modules.finance.money import format_amount
from app.modules.finance.service import apply_changes, jsonable, now, snapshot

__all__ = [
    "ZERO",
    "add_months",
    "apply_changes",
    "flush_translated",
    "jsonable",
    "month_end",
    "month_start",
    "now",
    "pyg",
    "record",
    "snapshot",
]

ZERO = Decimal(0)


def record(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    entity: str,
    verb: str,
    entity_id: uuid.UUID,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    kind = f"tax.{entity}"
    audit.record(
        db,
        action=f"{kind}.{verb}",
        entity_type=kind,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_user_id=actor_id,
        before=before,
        after=after,
    )


def pyg(amount: Decimal | None) -> str | None:
    """Guaraníes para la API (`"150000"`, nunca `"-0"`); `None` sigue siendo `None`."""
    return None if amount is None else format_amount(amount, "PYG")


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, months: int) -> date:
    """Primer día del mes que está `months` meses después del mes de `day`."""
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def month_end(day: date) -> date:
    return add_months(day, 1) - timedelta(days=1)


_DB_ERRORS: Mapping[str, tuple[str, str, int]] = {
    "trg_rule_versions_immutable": (
        "RULE_IMMUTABLE",
        "Una versión de regla no se edita: un cambio es una versión nueva.",
        409,
    ),
    "trg_rule_versions_invalid_transition": (
        "RULE_INVALID_TRANSITION",
        "La regla no puede pasar a ese estado.",
        409,
    ),
    "ex_rule_versions_no_overlap": (
        "RULE_VALIDITY_OVERLAP",
        "La vigencia se pisa con otra versión viva del mismo código.",
        409,
    ),
    "trg_obligations_invalid_transition": (
        "OBLIGATION_INVALID_TRANSITION",
        "La obligación no puede pasar a ese estado.",
        409,
    ),
    "trg_obligations_filed_fixed": (
        "OBLIGATION_FILED",
        "La obligación está presentada: no cambia su vencimiento, su regla ni lo presentado.",
        409,
    ),
    "uq_obligations_organization_id_code_period_start": (
        "OBLIGATION_EXISTS",
        "La obligación de ese período ya existe.",
        409,
    ),
    "trg_vouchers_period_locked": (
        "PERIOD_CONFIRMED",
        "El registro de comprobantes del mes está confirmado: reabrilo para cambiar sus "
        "comprobantes.",
        409,
    ),
    "trg_vouchers_voided_final": ("VOUCHER_VOIDED", "El comprobante está anulado.", 409),
    "trg_vouchers_note_mismatch": (
        "VOUCHER_NOTE_MISMATCH",
        "La nota no corresponde a una factura de la misma contraparte.",
        422,
    ),
    "trg_vouchers_transaction_has_entry": (
        "VOUCHER_TRANSACTION_HAS_ENTRY",
        "El movimiento vinculado ya tiene un asiento vivo.",
        409,
    ),
    "uq_vouchers_purchase_live": (
        "VOUCHER_DUPLICATE",
        "Ya hay un comprobante de compra vivo con ese tipo, RUC, timbrado y número.",
        409,
    ),
    "uq_vouchers_sale_live": (
        "VOUCHER_DUPLICATE",
        "Ya hay un comprobante de venta vivo con ese tipo, timbrado y número.",
        409,
    ),
    "trg_profiles_verified_final": (
        "PROFILE_VERIFIED",
        "El perfil está verificado: no cambia. Cargá una versión nueva.",
        409,
    ),
    "trg_profile_obligations_verified_final": (
        "PROFILE_VERIFIED",
        "El perfil está verificado: no cambia. Cargá una versión nueva.",
        409,
    ),
    "trg_profiles_ruc_required": (
        "PROFILE_REQUIRES_RUC",
        "Cargá el RUC de la organización antes del perfil fiscal.",
        422,
    ),
    "uq_profiles_organization_id_valid_from": (
        "PROFILE_VERSION_EXISTS",
        "Ya hay una versión del perfil con esa fecha.",
        409,
    ),
    "trg_holidays_in_use": (
        "HOLIDAY_IN_USE",
        "El feriado corrió un vencimiento ya presentado: no se borra ni cambia de día.",
        409,
    ),
    "uq_holidays_day": ("HOLIDAY_EXISTS", "Ya hay un feriado ese día.", 409),
}


def translate_integrity(exc: IntegrityError) -> AppError | None:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if isinstance(constraint, str) and constraint in _DB_ERRORS:
        code, message, status = _DB_ERRORS[constraint]
        if status == 409:
            return Conflict(code, message)
        return AppError(code, message, status_code=status)
    return None


@contextmanager
def translated() -> Iterator[None]:
    try:
        yield
    except IntegrityError as exc:
        error = translate_integrity(exc)
        if error is not None:
            raise error from exc
        raise


def flush_translated(db: Session) -> None:
    """`flush` en un SAVEPOINT; un rechazo conocido de la base pasa a ser un error de la API."""
    with translated(), db.begin_nested():
        db.flush()
