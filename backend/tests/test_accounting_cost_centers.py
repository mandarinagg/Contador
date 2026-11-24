"""Centros de costos (spec 3B §5.5; D-060) por la API. Los rechazos de la base por SQL
directo están en `test_accounting_db_triggers_3b.py`."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.accounting_utils import (
    ACC,
    ALQUILERES,
    BANCOS,
    CAPITAL,
    HONORARIOS,
    VENTAS,
    create_year,
    error_code,
    load_chart,
    post,
)
from tests.conftest import auth_header
from tests.finance_utils import ok


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token, 2026)
    headers = auth_header(owner_token)
    centers = {
        code: ok(
            client.post(
                f"{ACC}/cost-centers",
                json={"code": code, "name": f"Centro {code}"},
                headers=headers,
            ),
            201,
        )
        for code in ("ADM", "OBRA-1")
    }
    return {"token": owner_token, "accounts": accounts, "centers": centers}


def _entry(
    client: TestClient,
    books: dict[str, Any],
    lines: list[tuple[str, int, int, str | None]],
    day: str = "2026-03-10",
) -> Any:
    body = {
        "entry_date": day,
        "description": "Con centros",
        "lines": [
            {
                "account_id": books["accounts"][code]["id"],
                "debit": str(debit),
                "credit": str(credit),
                **({"cost_center_id": books["centers"][center]["id"]} if center else {}),
            }
            for code, debit, credit, center in lines
        ],
    }
    return client.post(f"{ACC}/entries", json=body, headers=auth_header(books["token"]))


def test_cost_center_crud_and_unique_code(client: TestClient, books: dict[str, Any]) -> None:
    headers = auth_header(books["token"])
    dup = client.post(f"{ACC}/cost-centers", json={"code": "ADM", "name": "Otro"}, headers=headers)
    assert dup.status_code == 409 and error_code(dup) == "COST_CENTER_CODE_TAKEN"
    bad = client.post(f"{ACC}/cost-centers", json={"code": "a b", "name": "Otro"}, headers=headers)
    assert bad.status_code == 422
    cid = books["centers"]["ADM"]["id"]
    archived = ok(
        client.patch(f"{ACC}/cost-centers/{cid}", json={"archived": True}, headers=headers)
    )
    assert archived["archived_at"] is not None
    listed = ok(client.get(f"{ACC}/cost-centers", headers=headers))
    assert [c["code"] for c in listed] == ["OBRA-1"]
    all_rows = ok(
        client.get(f"{ACC}/cost-centers", params={"include_archived": "true"}, headers=headers)
    )
    assert [c["code"] for c in all_rows] == ["ADM", "OBRA-1"]
    res = _entry(client, books, [(HONORARIOS, 100, 0, "ADM"), (BANCOS, 0, 100, None)])
    assert res.status_code == 422 and error_code(res) == "COST_CENTER_ARCHIVED"


def test_center_only_on_income_or_expense_lines(client: TestClient, books: dict[str, Any]) -> None:
    res = _entry(client, books, [(HONORARIOS, 100, 0, None), (BANCOS, 0, 100, "ADM")])
    assert res.status_code == 422 and error_code(res) == "COST_CENTER_NOT_ALLOWED"
    entry = ok(_entry(client, books, [(HONORARIOS, 100, 0, "ADM"), (BANCOS, 0, 100, None)]), 201)
    line = next(ln for ln in entry["lines"] if ln["account_code"] == HONORARIOS)
    assert line["cost_center_code"] == "ADM"
    assert line["cost_center_id"] == books["centers"]["ADM"]["id"]


def test_required_centers_block_posting(client: TestClient, books: dict[str, Any]) -> None:
    headers = auth_header(books["token"])
    entry = ok(_entry(client, books, [(HONORARIOS, 100, 0, None), (BANCOS, 0, 100, None)]), 201)
    ok(client.put(f"{ACC}/settings", json={"cost_centers_required": True}, headers=headers))
    res = post(client, books["token"], entry["id"])
    assert res.status_code == 422 and error_code(res) == "COST_CENTER_REQUIRED"
    assert res.json()["error"]["details"]["lines"] == [{"line": 1, "code": HONORARIOS}]
    with_center = ok(
        _entry(client, books, [(HONORARIOS, 100, 0, "ADM"), (BANCOS, 0, 100, None)]), 201
    )
    ok(post(client, books["token"], with_center["id"]))
    # Sin líneas de resultado, no hace falta centro.
    plain = ok(_entry(client, books, [(BANCOS, 100, 0, None), (CAPITAL, 0, 100, None)]), 201)
    ok(post(client, books["token"], plain["id"]))


def test_reversal_copies_centers_even_if_archived(
    client: TestClient, books: dict[str, Any]
) -> None:
    headers = auth_header(books["token"])
    entry = ok(_entry(client, books, [(HONORARIOS, 100, 0, "ADM"), (BANCOS, 0, 100, None)]), 201)
    ok(post(client, books["token"], entry["id"]))
    cid = books["centers"]["ADM"]["id"]
    ok(client.patch(f"{ACC}/cost-centers/{cid}", json={"archived": True}, headers=headers))
    reversal = ok(
        client.post(
            f"{ACC}/entries/{entry['id']}/reverse", json={"reason": "Error"}, headers=headers
        )
    )
    line = next(ln for ln in reversal["lines"] if ln["account_code"] == HONORARIOS)
    assert line["cost_center_id"] == cid and line["credit"] == "100"


def test_income_statement_by_center_adds_up(client: TestClient, books: dict[str, Any]) -> None:
    headers = auth_header(books["token"])
    for lines in (
        [(BANCOS, 1_000_000, 0, None), (VENTAS, 0, 600_000, "OBRA-1"), (VENTAS, 0, 400_000, None)],
        [
            (HONORARIOS, 300_000, 0, "ADM"),
            (ALQUILERES, 200_000, 0, "OBRA-1"),
            (BANCOS, 0, 500_000, None),
        ],
        [(ALQUILERES, 50_000, 0, None), (BANCOS, 0, 50_000, None)],
    ):
        ok(post(client, books["token"], ok(_entry(client, books, lines), 201)["id"]))
    report = ok(
        client.get(
            f"{ACC}/reports/income-statement",
            params={"from": "2026-01-01", "to": "2026-12-31", "by_cost_center": "true"},
            headers=headers,
        )
    )
    columns = report["cost_center_columns"]
    assert [c["code"] for c in columns] == ["ADM", "OBRA-1", None]
    assert columns[-1]["name"] == "Sin centro"
    assert [c["result"] for c in columns] == ["-300000", "400000", "350000"]
    assert sum(int(c["result"]) for c in columns) == int(report["result"]) == 450_000
    assert sum(int(c["total_income"]) for c in columns) == int(report["total_income"])

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            assert len(node["column_amounts"]) == len(columns)
            assert sum(int(a) for a in node["column_amounts"]) == int(node["amount"])
            walk(node["children"])

    walk(report["accounts"])
    plain = ok(
        client.get(
            f"{ACC}/reports/income-statement",
            params={"from": "2026-01-01", "to": "2026-12-31"},
            headers=headers,
        )
    )
    assert plain["cost_center_columns"] is None and plain["result"] == report["result"]
