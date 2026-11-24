"""Monedas e importes (D-026).

Reglas:
- Los importes son `Decimal` en Python, `NUMERIC(18,2)` en la base y string en JSON.
  Nunca `float`.
- Cada moneda tiene una cantidad de decimales. Un importe con más decimales que su moneda
  se **rechaza**; nunca se redondea.
- No se suman ni se convierten monedas distintas.
"""

import re
from decimal import Decimal, InvalidOperation

# Catálogo cerrado de monedas permitidas y sus decimales.
CURRENCY_DECIMALS: dict[str, int] = {
    "PYG": 0,
    "USD": 2,
    "BRL": 2,
    "ARS": 2,
    "EUR": 2,
}
CURRENCIES: tuple[str, ...] = tuple(CURRENCY_DECIMALS)

# NUMERIC(18,2): hasta 16 dígitos enteros.
MAX_ABS_AMOUNT = Decimal("9999999999999999.99")

# Forma canónica de un importe en JSON: signo opcional, dígitos y punto decimal opcional.
_AMOUNT_TEXT = re.compile(r"^[+-]?[0-9]{1,16}(\.[0-9]+)?$")

_STORAGE_QUANTUM = Decimal("0.01")


class AmountError(ValueError):
    """Importe inválido; el mensaje está pensado para la persona usuaria."""


def currency_sql_list() -> str:
    """Lista SQL de monedas del catálogo, para las restricciones CHECK."""
    return ", ".join(f"'{c}'" for c in CURRENCIES)


def parse_amount_text(value: str) -> Decimal:
    """Convierte el string canónico de la API (`"-1500.50"`) a `Decimal` exacto."""
    text = value.strip()
    if not _AMOUNT_TEXT.match(text):
        raise AmountError(
            f"Importe inválido: {value!r}. Usá dígitos y punto decimal, sin separador de miles."
        )
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - la expresión regular ya lo impide
        raise AmountError(f"Importe inválido: {value!r}.") from exc


def decimals_of(amount: Decimal) -> int:
    """Cantidad de decimales significativos (`1.50` → 1, `1.00` → 0, `100` → 0)."""
    normalized = amount.normalize()
    exponent = normalized.as_tuple().exponent
    if not isinstance(exponent, int):
        raise AmountError("El importe no es un número finito.")
    return max(0, -exponent)


def check_amount(amount: Decimal, currency: str, *, allow_zero: bool = True) -> Decimal:
    """Valida un importe para una moneda y lo devuelve con la escala de la base (2 decimales).

    Rechaza: monedas fuera del catálogo, valores no finitos, más decimales que la moneda,
    valores fuera de rango y, si se pide, el cero.
    """
    if currency not in CURRENCY_DECIMALS:
        raise AmountError(f"Moneda no admitida: {currency}.")
    if not amount.is_finite():
        raise AmountError("El importe no es un número finito.")
    allowed = CURRENCY_DECIMALS[currency]
    if decimals_of(amount) > allowed:
        if allowed == 0:
            raise AmountError(f"Los importes en {currency} no llevan decimales.")
        raise AmountError(f"Los importes en {currency} llevan como máximo {allowed} decimales.")
    if abs(amount) > MAX_ABS_AMOUNT:
        raise AmountError("El importe es demasiado grande.")
    if not allow_zero and amount == 0:
        raise AmountError("El importe no puede ser cero.")
    # Exacto: ya se verificó que no hay más de 2 decimales, así que no hay redondeo.
    return amount.quantize(_STORAGE_QUANTUM)


def format_amount(amount: Decimal, currency: str) -> str:
    """String para la API con los decimales de la moneda (`PYG` → `"150000"`, `USD` → `"0.30"`).

    Los importes guardados ya respetan los decimales de su moneda, así que no hay redondeo.
    """
    allowed = CURRENCY_DECIMALS.get(currency, 2)
    quantum = Decimal(1).scaleb(-allowed)
    value = amount.quantize(quantum)
    if value == 0:
        value = abs(value)  # nunca "-0"
    return format(value, "f")
