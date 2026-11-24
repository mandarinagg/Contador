"""Los reportes contables dan lo mismo que un cálculo de referencia simple en Python (§5.8).

El conjunto es variado a propósito: dos ejercicios (el primero cerrado, con refundición),
asientos de varias líneas, reversiones (en la misma fecha y en otra), borradores y
descartados que no deben contar, una cuenta regularizadora y movimientos justo en los bordes
de los rangos. Todo pasa por la API; la referencia se calcula con lo que la prueba envió,
sin leer los reportes.
"""

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.accounting_utils import (
    ACC,
    RESULTADO_EJERCICIO,
    close_period,
    create_year,
    draft,
    load_chart,
    post,
)
from tests.conftest import auth_header
from tests.finance_utils import ok

ZERO = Decimal(0)
CODES = [
    "1.01.01.02",  # caja
    "1.01.01.04.01",  # banco
    "1.01.03.01",  # deudores por ventas
    "1.02.04.03",  # muebles
    "1.02.04.99.03",  # (-) depreciación acumulada: regularizadora, naturaleza acreedora
    "2.01.01.01",  # proveedores
    "2.01.02.01",  # préstamos
    "3.01.01.01",  # capital
    "4.01.01.01",  # ventas
    "4.99",  # otros ingresos
    "11.04",  # honorarios
    "11.05",  # alquileres
    "15.01",  # depreciaciones
]
DEBIT_KINDS = {"asset", "expense"}


@dataclass
class Line:
    entry: int
    day: date
    code: str
    debit: Decimal
    credit: Decimal
    closing: bool = False


def _natural(kind: str, debit: Decimal, credit: Decimal) -> Decimal:
    return debit - credit if kind in DEBIT_KINDS else credit - debit


def _random_lines(rng: random.Random) -> list[tuple[str, int, int]]:
    count = rng.choice([2, 2, 3, 4, 5])
    amounts = [rng.randint(1, 5000) * 1000 for _ in range(count - 1)]
    codes = rng.sample(CODES, count)
    lines = [(code, amount, 0) for code, amount in zip(codes, amounts, strict=False)]
    if rng.random() < 0.5:
        lines = [(c, 0, a) for c, a, _ in lines]
    total = sum(a + b for _, a, b in lines)
    side_debit = lines[0][1] == 0
    lines.append((codes[-1], total if side_debit else 0, 0 if side_debit else total))
    rng.shuffle(lines)
    return lines


@pytest.fixture
def book(client: TestClient, owner_token: str) -> dict[str, Any]:
    token = owner_token
    headers = auth_header(token)
    rng = random.Random(20261124)  # noqa: S311 - datos de prueba, no criptografía
    accounts = load_chart(client, token)
    kinds = {code: a["kind"] for code, a in accounts.items()}
    years = {y: create_year(client, token, y) for y in (2025, 2026)}
    ok(
        client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": accounts[RESULTADO_EJERCICIO]["id"]},
            headers=headers,
        )
    )
    counted: list[Line] = []
    posted_ids: list[tuple[str, date, list[tuple[str, int, int]]]] = []

    def add(n: int, day: date, lines: list[tuple[str, int, int]], *, closing: bool = False) -> None:
        for code, debit, credit in lines:
            counted.append(Line(n, day, code, Decimal(debit), Decimal(credit), closing))

    days = [date(2025, 1, 1), date(2025, 12, 31), date(2026, 1, 1), date(2026, 6, 30)]
    days += [date(2025, 1, 1) + timedelta(days=rng.randint(0, 729)) for _ in range(76)]
    for n, day in enumerate(sorted(days)):
        lines = _random_lines(rng)
        roll = rng.random()
        entry = draft(client, token, accounts, day.isoformat(), lines, f"Asiento {n}")
        if roll < 0.08:
            continue  # borrador: no cuenta
        if roll < 0.14:
            ok(
                client.post(
                    f"{ACC}/entries/{entry['id']}/discard",
                    json={"reason": "Sobra"},
                    headers=headers,
                )
            )
            continue
        ok(post(client, token, entry["id"]))
        add(n, day, lines)
        posted_ids.append((entry["id"], day, lines))

    # Reversiones: algunas en la misma fecha, otras unos días después (dentro del ejercicio).
    for k, (entry_id, day, lines) in enumerate(rng.sample(posted_ids, 10)):
        on = day if k % 2 == 0 else min(day + timedelta(days=3), date(day.year, 12, 31))
        res = client.post(
            f"{ACC}/entries/{entry_id}/reverse",
            json={"reason": "Corrección", "date": on.isoformat()},
            headers=headers,
        )
        ok(res)
        add(1000 + k, on, [(c, credit, debit) for c, debit, credit in lines])

    # Quedan borradores en 2025: se descartan para poder cerrar.
    for e in ok(
        client.get(f"{ACC}/entries", params={"status": "draft", "limit": 200}, headers=headers)
    ):
        if e["entry_date"] < "2026-01-01":
            ok(
                client.post(
                    f"{ACC}/entries/{e['id']}/discard", json={"reason": "Cierre"}, headers=headers
                )
            )
    for period in years[2025]["periods"]:
        ok(close_period(client, token, period["id"]))
    closed = ok(client.post(f"{ACC}/fiscal-years/{years[2025]['id']}/close", headers=headers))

    # Refundición de referencia: cada cuenta de resultado de 2025 a cero, neto al resultado.
    net: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for line in counted:
        if line.day.year == 2025 and kinds[line.code] in ("income", "expense"):
            net[line.code] += line.debit - line.credit
    closing_lines = [(c, -v, ZERO) if v < 0 else (c, ZERO, v) for c, v in net.items() if v]
    result = -sum(net.values(), ZERO)  # haber - debe: ganancia positiva
    closing_lines.append(
        (RESULTADO_EJERCICIO, ZERO, result) if result > 0 else (RESULTADO_EJERCICIO, -result, ZERO)
    )
    for code, debit, credit in closing_lines:
        counted.append(Line(2000, date(2025, 12, 31), code, debit, credit, closing=True))
    return {
        "token": token,
        "accounts": accounts,
        "kinds": kinds,
        "counted": counted,
        "closing_entry_id": closed["closing_entry_id"],
        "result_2025": result,
        "parents": {code: a["parent_id"] for code, a in accounts.items()},
    }


def _sums(lines: list[Line]) -> dict[str, tuple[Decimal, Decimal]]:
    sums: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for line in lines:
        sums[line.code][0] += line.debit
        sums[line.code][1] += line.credit
    return {code: (d, c) for code, (d, c) in sums.items()}


def _subtree_amount(
    book: dict[str, Any], sums: dict[str, tuple[Decimal, Decimal]], code: str
) -> Decimal:
    """Suma natural de la cuenta y todas sus descendientes (por prefijo de código)."""
    kinds = book["kinds"]
    return sum(
        (
            _natural(kinds[c], d, cr)
            for c, (d, cr) in sums.items()
            if c == code or c.startswith(code + ".")
        ),
        ZERO,
    )


def _walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for node in nodes:
        out.append(node)
        out.extend(_walk(node["children"]))
    return out


def _get(client: TestClient, book: dict[str, Any], path: str, **params: Any) -> Any:
    return ok(client.get(f"{ACC}{path}", params=params, headers=auth_header(book["token"])))


def test_closing_entry_matches_reference(client: TestClient, book: dict[str, Any]) -> None:
    closing = _get(client, book, f"/entries/{book['closing_entry_id']}")
    got = sorted((ln["account_code"], ln["debit"], ln["credit"]) for ln in closing["lines"])
    expected = sorted(
        (line.code, str(line.debit), str(line.credit)) for line in book["counted"] if line.closing
    )
    assert got == expected


def _check_trial_balance_matches_reference(
    client: TestClient, book: dict[str, Any], date_from: str, date_to: str
) -> None:
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    sums = _sums([ln for ln in book["counted"] if start <= ln.day <= end])
    # D-062: saldo inicial = todo lo contabilizado antes de `from`, con la refundición.
    before = _sums([ln for ln in book["counted"] if ln.day < start])
    opening = {c: d - cr for c, (d, cr) in before.items()}
    report = _get(client, book, "/reports/trial-balance", **{"from": date_from, "to": date_to})
    got = {r["code"]: (Decimal(r["debit"]), Decimal(r["credit"])) for r in report["rows"]}
    expected_codes = {c for c, v in sums.items() if v != (ZERO, ZERO)} | {
        c for c, o in opening.items() if o != 0
    }
    assert set(got) == expected_codes
    assert got == {c: sums.get(c, (ZERO, ZERO)) for c in expected_codes}
    assert report["total_debit"] == report["total_credit"]
    assert report["total_debit_balance"] == report["total_credit_balance"]
    assert report["total_opening_debit"] == report["total_opening_credit"]
    assert report["total_closing_debit"] == report["total_closing_credit"]
    assert report["balanced"] is True
    for row in report["rows"]:
        diff = Decimal(row["debit"]) - Decimal(row["credit"])
        assert Decimal(row["debit_balance"]) == max(diff, ZERO)
        assert Decimal(row["credit_balance"]) == max(-diff, ZERO)
        start_balance = opening.get(row["code"], ZERO)
        assert Decimal(row["opening_debit"]) == max(start_balance, ZERO)
        assert Decimal(row["opening_credit"]) == max(-start_balance, ZERO)
        final = start_balance + diff
        assert Decimal(row["closing_debit"]) == max(final, ZERO)
        assert Decimal(row["closing_credit"]) == max(-final, ZERO)
        # Después de la refundición, las cuentas de resultado arrancan en cero.
        if start == date(2026, 1, 1) and book["kinds"][row["code"]] in ("income", "expense"):
            assert row["opening_debit"] == row["opening_credit"] == "0"
    assert [r["code"] for r in report["rows"]] == sorted(
        got, key=lambda c: [int(p) for p in c.split(".")]
    )


def _check_balance_sheet_matches_reference(
    client: TestClient, book: dict[str, Any], at: str
) -> None:
    day = date.fromisoformat(at)
    sums = _sums([ln for ln in book["counted"] if ln.day <= day])
    kinds = book["kinds"]
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for code, (debit, credit) in sums.items():
        totals[kinds[code]] += _natural(kinds[code], debit, credit)
    sheet = _get(client, book, "/reports/balance-sheet", at=at)
    assert Decimal(sheet["total_assets"]) == totals["asset"]
    assert Decimal(sheet["total_liabilities"]) == totals["liability"]
    assert Decimal(sheet["total_equity"]) == totals["equity"]
    assert Decimal(sheet["result"]) == totals["income"] - totals["expense"]
    assert sheet["balanced"] is True
    assert Decimal(sheet["total_assets"]) == Decimal(sheet["total_liabilities_and_equity"])
    for section in ("assets", "liabilities", "equity"):
        for node in _walk(sheet[section]):
            assert Decimal(node["amount"]) == _subtree_amount(book, sums, node["code"]), node[
                "code"
            ]


def _check_income_statement_matches_reference(
    client: TestClient, book: dict[str, Any], date_from: str, date_to: str
) -> None:
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    lines = [ln for ln in book["counted"] if start <= ln.day <= end and not ln.closing]
    sums = _sums(lines)
    kinds = book["kinds"]
    income = sum(
        (_natural("income", d, c) for k, (d, c) in sums.items() if kinds[k] == "income"), ZERO
    )
    expense = sum(
        (_natural("expense", d, c) for k, (d, c) in sums.items() if kinds[k] == "expense"), ZERO
    )
    statement = _get(
        client, book, "/reports/income-statement", **{"from": date_from, "to": date_to}
    )
    assert Decimal(statement["total_income"]) == income
    assert Decimal(statement["total_expense"]) == expense
    assert Decimal(statement["result"]) == income - expense
    for node in _walk(statement["accounts"]):
        assert Decimal(node["amount"]) == _subtree_amount(book, sums, node["code"]), node["code"]
    if (date_from, date_to) == ("2025-01-01", "2025-12-31"):
        assert Decimal(statement["result"]) == book["result_2025"]


def _check_ledger_borders_and_running_balance(
    client: TestClient, book: dict[str, Any], code: str, date_from: str, date_to: str
) -> None:
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    account = book["accounts"][code]
    side = account["normal_side"]

    def signed(debit: Decimal, credit: Decimal) -> Decimal:
        return debit - credit if side == "debit" else credit - debit

    mine = [ln for ln in book["counted"] if ln.code == code]
    opening = sum((signed(ln.debit, ln.credit) for ln in mine if ln.day < start), ZERO)
    in_range = [ln for ln in mine if start <= ln.day <= end]
    expected_closing = opening + sum((signed(ln.debit, ln.credit) for ln in in_range), ZERO)

    # Se recorre con páginas chicas para probar el cursor y el saldo acumulado entre páginas.
    movements: list[dict[str, Any]] = []
    after = None
    while True:
        params: dict[str, Any] = {"from": date_from, "to": date_to, "limit": 7}
        if after:
            params["after"] = after
        page = _get(client, book, f"/reports/ledger/{account['id']}", **params)
        assert Decimal(page["opening_balance"]) == opening
        assert Decimal(page["closing_balance"]) == expected_closing
        movements.extend(page["movements"])
        after = page["next_cursor"]
        if after is None:
            break
    assert len(movements) == len(in_range)
    assert Decimal(page["total_debit"]) == sum((ln.debit for ln in in_range), ZERO)
    assert Decimal(page["total_credit"]) == sum((ln.credit for ln in in_range), ZERO)
    running = opening
    for movement in movements:
        running += signed(Decimal(movement["debit"]), Decimal(movement["credit"]))
        assert Decimal(movement["balance"]) == running
        assert start <= date.fromisoformat(movement["entry_date"]) <= end
    assert running == expected_closing
    keys = [(m["entry_date"], m["number"]) for m in movements]
    assert keys == sorted(keys)


TRIAL_RANGES = [
    ("2025-01-01", "2025-12-31"),
    ("2026-01-01", "2026-12-31"),
    ("2025-01-01", "2026-12-31"),
    ("2025-12-31", "2026-01-01"),
    ("2025-03-10", "2025-03-10"),
    ("2026-02-01", "2026-06-30"),
]
SHEET_DATES = ["2025-06-30", "2025-12-30", "2025-12-31", "2026-03-31", "2026-12-31"]
INCOME_RANGES = [
    ("2025-01-01", "2025-12-31"),
    ("2026-01-01", "2026-12-31"),
    ("2025-07-01", "2026-06-30"),
]
LEDGER_RANGES = [
    ("2025-01-01", "2025-12-31"),
    ("2025-12-31", "2026-01-01"),
    ("2026-01-01", "2026-06-30"),
    ("2025-05-01", "2026-12-31"),
]
LEDGER_CODES = ["1.01.01.04.01", "1.02.04.99.03", "4.01.01.01"]


# Un solo conjunto de datos por prueba (cargarlo cuesta segundos): cada prueba recorre sus
# rangos en lugar de parametrizarse.


def test_trial_balance_matches_reference(client: TestClient, book: dict[str, Any]) -> None:
    for date_from, date_to in TRIAL_RANGES:
        _check_trial_balance_matches_reference(client, book, date_from, date_to)


def test_balance_sheet_matches_reference(client: TestClient, book: dict[str, Any]) -> None:
    for at in SHEET_DATES:
        _check_balance_sheet_matches_reference(client, book, at)


def test_income_statement_matches_reference(client: TestClient, book: dict[str, Any]) -> None:
    for date_from, date_to in INCOME_RANGES:
        _check_income_statement_matches_reference(client, book, date_from, date_to)


def test_ledger_borders_and_running_balance(client: TestClient, book: dict[str, Any]) -> None:
    for code in LEDGER_CODES:
        for date_from, date_to in LEDGER_RANGES:
            _check_ledger_borders_and_running_balance(client, book, code, date_from, date_to)
