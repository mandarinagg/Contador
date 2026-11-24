"""Cuadro de depreciación (RG 77/2020) y valores al cierre del ejercicio (spec 3B §6; D-065 a
D-067)."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.accounting_utils import ACC, BANCOS, CAPITAL, close_period, error_code, posted
from tests.assets_utils import months, new_asset, run_and_post, setup_books
from tests.conftest import auth_header
from tests.finance_utils import ok

COST = 12_000_000


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    books = setup_books(client, owner_token, (2026, 2027))
    accounts = books["accounts"]
    posted(
        client,
        owner_token,
        accounts,
        "2026-01-02",
        [(BANCOS, 50_000_000, 0), (CAPITAL, 0, 50_000_000)],
    )
    posted(
        client, owner_token, accounts, "2026-01-15", [("1.02.04.03", COST, 0), (BANCOS, 0, COST)]
    )
    # Contable: 36 meses sin residual; fiscal: los de la categoría (60 meses, 10 %).
    books["asset"] = new_asset(client, books, cost=COST, residual_value="0", useful_life_months=36)
    return books


def _schedule(client: TestClient, books: dict[str, Any], year: int) -> Any:
    return ok(
        client.get(
            f"{ACC}/reports/depreciation-schedule",
            params={"fiscal_year_id": books["years"][year]["id"]},
            headers=auth_header(books["token"]),
        )
    )


def test_fiscal_and_accounting_differ_with_non_deductible_quota(
    client: TestClient, books: dict[str, Any]
) -> None:
    for y, m in months(date(2026, 2, 1), 11):
        run_and_post(client, books, y, m)
    report = _schedule(client, books, 2026)
    [group] = report["categories"]
    [row] = group["assets"]
    fiscal_quota = 11 * (COST - 1_200_000) // 60
    accounting_quota = 11 * (COST // 36)
    assert row["fiscal_residual_value"] == "1200000"
    assert row["fiscal_useful_life_years"] == "5"
    assert row["fiscal_remaining_months"] == 49
    assert row["fiscal_net_previous"] == str(COST)
    assert row["fiscal_depreciable"] == str(COST - 1_200_000)
    assert row["fiscal_depreciation"] == str(fiscal_quota)
    assert row["fiscal_net_value"] == str(COST - fiscal_quota)
    assert row["accounting_depreciation"] == str(accounting_quota)
    assert row["non_deductible"] == str(accounting_quota - fiscal_quota)
    assert row["accounting_net_value"] == str(COST - accounting_quota)
    assert row["revaluation_coefficient"] == "0"
    assert report["totals"]["accounting_net_value"] == row["accounting_net_value"]
    assert any("IRE SIMPLE" in w for w in report["warnings"])
    assert any("revalúo" in w for w in report["warnings"])


def test_schedule_total_matches_the_balance_sheet(
    client: TestClient, books: dict[str, Any]
) -> None:
    for m in (2, 3, 4):
        run_and_post(client, books, 2026, m)
    report = _schedule(client, books, 2026)
    reconciliation = report["reconciliation"]
    assert reconciliation["reconciled"] is True
    by_code = {line["code"]: line for line in reconciliation["lines"]}
    assert by_code["1.02.04.03"]["ledger_balance"] == str(COST)
    assert by_code["1.02.04.99.03"]["ledger_balance"] == str(-3 * (COST // 36))
    assert reconciliation["schedule_total"] == report["totals"]["accounting_net_value"]
    # El total cuadra con el balance general (activo fijo neto de esas cuentas).
    sheet = ok(
        client.get(
            f"{ACC}/reports/balance-sheet",
            params={"at": "2026-12-31"},
            headers=auth_header(books["token"]),
        )
    )

    def find(nodes: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
        for node in nodes:
            if node["code"] == code:
                return node
            found = find(node["children"], code)
            if found is not None:
                return found
        return None

    ppe = find(sheet["assets"], "1.02.04")
    assert ppe is not None and ppe["amount"] == reconciliation["schedule_total"]
    # Un movimiento en la cuenta que no es de un bien registrado descuadra (se informa).
    posted(
        client,
        books["token"],
        books["accounts"],
        "2026-06-01",
        [("1.02.04.03", 500_000, 0), (BANCOS, 0, 500_000)],
    )
    assert _schedule(client, books, 2026)["reconciliation"]["reconciled"] is False


def _close_year(client: TestClient, books: dict[str, Any], year: int) -> Any:
    token = books["token"]
    for period in books["years"][year]["periods"]:
        close_period(client, token, period["id"])
    return client.post(
        f"{ACC}/fiscal-years/{books['years'][year]['id']}/close", headers=auth_header(token)
    )


def test_year_close_requires_depreciation_and_stores_year_values(
    client: TestClient, books: dict[str, Any], db: Session
) -> None:
    token = books["token"]
    ok(
        client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": books["accounts"]["3.03.02"]["id"]},
            headers=auth_header(token),
        )
    )
    for y, m in months(date(2026, 2, 1), 10):  # falta diciembre
        run_and_post(client, books, y, m)
    res = _close_year(client, books, 2026)
    assert res.status_code == 409 and error_code(res) == "DEPRECIATION_MISSING"
    assert res.json()["error"]["details"]["month"] == "2026-12-01"
    period = books["years"][2026]["periods"][11]["id"]
    ok(
        client.post(
            f"{ACC}/periods/{period}/reopen",
            json={"reason": "Falta la depreciación"},
            headers=auth_header(token),
        )
    )
    run_and_post(client, books, 2026, 12)
    close_period(client, token, period)
    ok(_close_year(client, books, 2026))
    values = db.execute(
        text(
            "SELECT fiscal_net_value, accounting_net_value, fiscal_depreciation,"
            " accounting_depreciation FROM accounting.asset_year_values WHERE asset_id = :a"
        ),
        {"a": books["asset"]["id"]},
    ).one()
    fiscal = 11 * (COST - 1_200_000) // 60
    accounting = 11 * (COST // 36)
    assert [int(v) for v in values] == [COST - fiscal, COST - accounting, fiscal, accounting]
    # El ejercicio siguiente arranca de esos valores.
    [group] = _schedule(client, books, 2027)["categories"]
    assert group["assets"][0]["fiscal_net_previous"] == str(COST - fiscal)
    assert group["assets"][0]["accounting_net_previous"] == str(COST - accounting)


def test_disposed_in_year_shows_zero_net(client: TestClient, books: dict[str, Any]) -> None:
    for m in (2, 3):
        run_and_post(client, books, 2026, m)
    entry = ok(
        client.post(
            f"{ACC}/fixed-assets/{books['asset']['id']}/dispose",
            json={
                "date": "2026-04-10",
                "kind": "scrap",
                "reason": "Destrucción por rotura",
                "document_reference": "Acta del contador 3/2026",
            },
            headers=auth_header(books["token"]),
        ),
        201,
    )
    ok(client.post(f"{ACC}/entries/{entry['id']}/post", headers=auth_header(books["token"])))
    report = _schedule(client, books, 2026)
    row = report["categories"][0]["assets"][0]
    assert row["disposed_on"] == "2026-04-10"
    assert row["accounting_net_value"] == "0" and row["fiscal_net_value"] == "0"
    assert row["accounting_depreciation"] == str(2 * (COST // 36))
    assert report["reconciliation"]["reconciled"] is True
    # En el ejercicio siguiente ya no aparece.
    assert _schedule(client, books, 2027)["categories"] == []
