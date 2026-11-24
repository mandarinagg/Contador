"""Importes exactos, monedas y normalización (D-026, BR-FIN-03). Pruebas unitarias."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.finance.importing import ImportMapping, parse_amount, parse_date
from app.modules.finance.money import AmountError, check_amount, format_amount, parse_amount_text
from app.modules.finance.normalize import dedupe_key, normalize_text


def test_decimal_arithmetic_is_exact() -> None:
    total = parse_amount_text("0.1") + parse_amount_text("0.2")
    assert format_amount(check_amount(total, "USD"), "USD") == "0.30"


def test_amount_decimals_are_rejected_not_rounded() -> None:
    with pytest.raises(AmountError, match="no llevan decimales"):
        check_amount(Decimal("1500.5"), "PYG")
    with pytest.raises(AmountError, match="como máximo 2"):
        check_amount(Decimal("10.001"), "USD")
    # Ceros a la derecha no son decimales reales.
    assert check_amount(Decimal("1500.00"), "PYG") == Decimal("1500.00")
    assert format_amount(Decimal("1500.00"), "PYG") == "1500"
    assert format_amount(Decimal("-0.00"), "USD") == "0.00"


def test_amount_limits_and_catalog() -> None:
    with pytest.raises(AmountError, match="Moneda no admitida"):
        check_amount(Decimal(1), "XYZ")
    with pytest.raises(AmountError, match="demasiado grande"):
        check_amount(Decimal("99999999999999999"), "PYG")
    with pytest.raises(AmountError, match="cero"):
        check_amount(Decimal(0), "PYG", allow_zero=False)
    with pytest.raises(AmountError):
        check_amount(Decimal("NaN"), "USD")


def test_amount_text_format() -> None:
    assert parse_amount_text("-1500.50") == Decimal("-1500.50")
    for bad in ("1,5", "1e3", "abc", "", "1.234.567"):
        with pytest.raises(AmountError):
            parse_amount_text(bad)


def test_normalize_text() -> None:
    assert normalize_text("  Pago   ANDE  Señor Ñandú ") == "pago ande senor nandu"
    assert normalize_text("Café\tcon\nLECHE") == "cafe con leche"
    assert normalize_text(None) == ""


def test_dedupe_key_ignores_case_accents_spaces_and_scale() -> None:
    account = uuid.uuid4()
    day = date(2026, 3, 1)
    a = dedupe_key(account, day, Decimal("-1500"), "Café  Central", "N° 12")
    b = dedupe_key(account, day, Decimal("-1500.00"), "cafe central", " n° 12 ")
    assert a == b and len(a) == 32
    assert a != dedupe_key(account, day, Decimal("-1501"), "cafe central", "n° 12")
    assert a != dedupe_key(uuid.uuid4(), day, Decimal("-1500"), "cafe central", "n° 12")
    assert a != dedupe_key(account, day, Decimal("-1500"), "cafe central", None)


def test_parse_amount_paraguayan_formats() -> None:
    py = ImportMapping.model_validate(
        {
            "date_column": "F",
            "description_column": "D",
            "amount": {"mode": "single", "column": "I"},
        }
    )
    assert parse_amount("1.234.567", py) == Decimal("1234567")
    assert parse_amount("1.234,50", py) == Decimal("1234.50")
    assert parse_amount("-150.000", py) == Decimal("-150000")
    assert parse_amount("(2.000)", py) == Decimal("-2000")
    assert parse_amount("2.000-", py) == Decimal("-2000")
    assert parse_amount("", py) is None
    for bad in ("1.23.4", "12,3,4", "abc", "1.2345"):
        with pytest.raises(ValueError, match="Importe inválido"):
            parse_amount(bad, py)
    us = py.model_copy(update={"decimal_separator": ".", "thousands_separator": ","})
    assert parse_amount("1,234.56", us) == Decimal("1234.56")
    # Celdas XLSX numéricas: nunca se arrastra el error binario del float.
    assert parse_amount(0.1, py) == Decimal("0.1")
    assert parse_amount(1234.5, py) == Decimal("1234.5")
    assert parse_amount(150000, py) == Decimal(150000)
    # Celdas calculadas: se leen como las muestra Excel (15 dígitos), sin decimales fantasma.
    assert parse_amount(1234.5600000000001, py) == Decimal("1234.56")
    assert parse_amount(0.1 + 0.2, py) == Decimal("0.3")
    assert parse_amount(1500000.0, py) == Decimal(1500000)
    # Tres decimales reales se conservan: los rechaza después check_amount.
    assert parse_amount(15.555, py) == Decimal("15.555")
    # Celdas absurdas no rompen la lectura: check_amount las rechaza después.
    assert parse_amount(1e30, py) == Decimal("1E+30")
    assert not parse_amount(float("inf"), py).is_finite()  # type: ignore[union-attr]


def test_parse_amount_with_written_currency() -> None:
    py = ImportMapping.model_validate(
        {
            "date_column": "F",
            "description_column": "D",
            "amount": {"mode": "single", "column": "I"},
        }
    )
    assert parse_amount("Gs. 4.500.000", py, "PYG") == Decimal("4500000")
    assert parse_amount("Gs. -85.000", py, "PYG") == Decimal("-85000")
    assert parse_amount("-Gs. 85.000", py, "PYG") == Decimal("-85000")
    assert parse_amount("(Gs. 2.000)", py, "PYG") == Decimal("-2000")
    assert parse_amount("₲ 1.000", py, "PYG") == Decimal("1000")
    assert parse_amount("1.500.000 Gs", py, "PYG") == Decimal("1500000")
    assert parse_amount("2.000- PYG", py, "PYG") == Decimal("-2000")
    assert parse_amount("US$ 1.234,50", py, "USD") == Decimal("1234.50")
    assert parse_amount("u$s 10", py, "USD") == Decimal("10")
    # La moneda escrita tiene que ser la de la cuenta: nunca se convierte (D-026).
    with pytest.raises(ValueError, match="está en USD y la cuenta en PYG"):
        parse_amount("US$ 100", py, "PYG")
    with pytest.raises(ValueError, match="está en PYG y la cuenta en USD"):
        parse_amount("Gs. 100", py, "USD")
    # Sin moneda de referencia, el texto con moneda sigue siendo inválido.
    with pytest.raises(ValueError, match="Importe inválido"):
        parse_amount("Gs. 100", py)
    for bad in ("Gs.", "Gs. abc", "Gs. 1.2345"):
        with pytest.raises(ValueError):
            parse_amount(bad, py, "PYG")


def test_parse_date_ignores_time_and_reads_excel_serials() -> None:
    assert parse_date("15/01/2026", "%d/%m/%Y") == date(2026, 1, 15)
    assert parse_date("15/01/2026 10:23", "%d/%m/%Y") == date(2026, 1, 15)
    assert parse_date("15/01/2026 10:23:59", "%d/%m/%Y") == date(2026, 1, 15)
    assert parse_date("15/01/2026 10:23 p. m.", "%d/%m/%Y") == date(2026, 1, 15)
    assert parse_date("2026-01-15T10:23:05", "%Y-%m-%d") == date(2026, 1, 15)
    assert parse_date("15/01/2026 10:23", "%d/%m/%Y %H:%M") == date(2026, 1, 15)
    # Celda XLSX numérica sin formato de fecha: número de serie de Excel.
    assert parse_date(46034, "%d/%m/%Y") == date(2026, 1, 12)
    assert parse_date(46034.75, "%d/%m/%Y") == date(2026, 1, 12)
    for bad, fmt in (
        ("31/02/2026", "%d/%m/%Y"),
        ("31/02/2026 10:00", "%d/%m/%Y"),
        ("15/01/2026 hola", "%d/%m/%Y"),
        ("15/01/2026 25:99", "%d/%m/%Y %H:%M"),
        (150000, "%d/%m/%Y"),
        (12, "%d/%m/%Y"),
    ):
        with pytest.raises(ValueError, match="Fecha inválida"):
            parse_date(bad, fmt)
