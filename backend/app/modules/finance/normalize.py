"""Normalización de textos y clave de duplicados de los movimientos (BR-FIN-03).

Es la **única** implementación de la normalización: la usan el alta manual, la edición y
la importación, así dos movimientos iguales siempre producen la misma clave.
"""

import hashlib
import unicodedata
import uuid
from datetime import date
from decimal import Decimal


def normalize_text(value: str | None) -> str:
    """Minúsculas, sin tildes (NFKD), espacios colapsados y sin espacios al borde."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_marks.lower().split())


def dedupe_key(
    account_id: uuid.UUID,
    booked_on: date,
    amount: Decimal,
    description: str,
    reference: str | None,
) -> bytes:
    """sha256 de `cuenta|fecha|importe|descripción normalizada|referencia normalizada`.

    El importe se escribe siempre con 2 decimales (`-1500.00`) para que `1500` y `1500.00`
    den la misma clave.
    """
    parts = (
        str(account_id),
        booked_on.isoformat(),
        format(amount.quantize(Decimal("0.01")), "f"),
        normalize_text(description),
        normalize_text(reference),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()
