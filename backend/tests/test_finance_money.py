"""Importes exactos, monedas y normalización (D-026, BR-FIN-03). Pruebas unitarias."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.finance.importing import ImportMapping, parse_amount
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
