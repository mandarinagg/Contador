"""Asientos recurrentes (spec 3B §5.6; D-061)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.accounting_utils import ACC, ALQUILERES, BANCOS, create_year, error_code, load_chart
from tests.conftest import auth_header
from tests.finance_utils import ok


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    accounts = load_chart(client, owner_token)
    year = create_year(client, owner_token, 2026)
    return {"token": owner_token, "accounts": accounts, "year": year}


def _template(client: TestClient, books: dict[str, Any], **extra: Any) -> Any:
    body = {
        "description": "Alquiler de la oficina",
        "day_of_month": 31,
        "start_date": "2026-01-01",
        "lines": [
            {"account_id": books["accounts"][ALQUILERES]["id"], "debit": "2500000"},
            {"account_id": books["accounts"][BANCOS]["id"], "credit": "2500000"},
        ],
        **extra,
    }
    return client.post(f"{ACC}/recurring", json=body, headers=auth_header(books["token"]))


def _period(books: dict[str, Any], month: int) -> str:
    return str(books["year"]["periods"][month - 1]["id"])


def _generate(client: TestClient, books: dict[str, Any], month: int) -> Any:
    return client.post(
        f"{ACC}/recurring/generate",
        json={"period_id": _period(books, month)},
        headers=auth_header(books["token"]),
    )


def test_generate_twice_does_not_duplicate(client: TestClient, books: dict[str, Any]) -> None:
    ok(_template(client, books), 201)
    first = ok(_generate(client, books, 3))
    assert len(first["created"]) == 1 and first["existing"] == []
    entry = first["created"][0]
    assert entry["kind"] == "recurring" and entry["status"] == "draft"
    assert entry["entry_date"] == "2026-03-31"
    second = ok(_generate(client, books, 3))
    assert second["created"] == [] and [e["id"] for e in second["existing"]] == [entry["id"]]


def test_day_31_falls_on_last_day_of_short_months(
    client: TestClient, books: dict[str, Any]
) -> None:
    ok(_template(client, books), 201)
    dates = [ok(_generate(client, books, m))["created"][0]["entry_date"] for m in (2, 4, 12)]
    assert dates == ["2026-02-28", "2026-04-30", "2026-12-31"]


def test_discard_then_regenerate(client: TestClient, books: dict[str, Any]) -> None:
    ok(_template(client, books), 201)
    entry = ok(_generate(client, books, 5))["created"][0]
    ok(
        client.post(
            f"{ACC}/entries/{entry['id']}/discard",
            json={"reason": "Monto equivocado"},
            headers=auth_header(books["token"]),
        )
    )
    again = ok(_generate(client, books, 5))
    assert len(again["created"]) == 1 and again["created"][0]["id"] != entry["id"]
    # Una vez contabilizado, revertirlo también libera el período.
    new_id = again["created"][0]["id"]
    headers = auth_header(books["token"])
    ok(client.post(f"{ACC}/entries/{new_id}/post", headers=headers))
    ok(client.post(f"{ACC}/entries/{new_id}/reverse", json={"reason": "Anulado"}, headers=headers))
    assert len(ok(_generate(client, books, 5))["created"]) == 1


def test_validity_and_pause_are_respected(client: TestClient, books: dict[str, Any]) -> None:
    template = ok(_template(client, books, start_date="2026-03-15", end_date="2026-06-10"), 201)
    assert ok(_generate(client, books, 2))["created"] == []  # antes del inicio
    assert len(ok(_generate(client, books, 3))["created"]) == 1  # 31/03 dentro
    assert ok(_generate(client, books, 6))["created"] == []  # 30/06 después del fin
    headers = auth_header(books["token"])
    ok(
        client.patch(
            f"{ACC}/recurring/{template['id']}", json={"status": "paused"}, headers=headers
        )
    )
    assert ok(_generate(client, books, 4))["created"] == []
    due = ok(
        client.get(f"{ACC}/recurring/due", params={"period_id": _period(books, 4)}, headers=headers)
    )
    assert due == []
    ok(
        client.patch(
            f"{ACC}/recurring/{template['id']}", json={"status": "active"}, headers=headers
        )
    )
    due = ok(
        client.get(f"{ACC}/recurring/due", params={"period_id": _period(books, 4)}, headers=headers)
    )
    assert [(d["entry_date"], d["total"]) for d in due] == [("2026-04-30", "2500000")]


def test_template_must_balance_and_closed_period_rejects(
    client: TestClient, books: dict[str, Any]
) -> None:
    res = _template(
        client,
        books,
        lines=[
            {"account_id": books["accounts"][ALQUILERES]["id"], "debit": "100"},
            {"account_id": books["accounts"][BANCOS]["id"], "credit": "90"},
        ],
    )
    assert res.status_code == 422 and error_code(res) == "ENTRY_UNBALANCED"
    ok(_template(client, books), 201)
    headers = auth_header(books["token"])
    ok(client.post(f"{ACC}/periods/{_period(books, 1)}/close", headers=headers))
    res = _generate(client, books, 1)
    assert res.status_code == 409 and error_code(res) == "PERIOD_CLOSED"


def test_generation_is_all_or_nothing(client: TestClient, books: dict[str, Any]) -> None:
    headers = auth_header(books["token"])
    center = ok(
        client.post(f"{ACC}/cost-centers", json={"code": "ADM", "name": "Adm."}, headers=headers),
        201,
    )
    ok(_template(client, books), 201)
    ok(
        _template(
            client,
            books,
            description="Con centro",
            lines=[
                {
                    "account_id": books["accounts"][ALQUILERES]["id"],
                    "debit": "100",
                    "cost_center_id": center["id"],
                },
                {"account_id": books["accounts"][BANCOS]["id"], "credit": "100"},
            ],
        ),
        201,
    )
    ok(client.patch(f"{ACC}/cost-centers/{center['id']}", json={"archived": True}, headers=headers))
    res = _generate(client, books, 7)
    assert res.status_code == 422 and error_code(res) == "COST_CENTER_ARCHIVED"
    assert "Con centro" in res.json()["error"]["message"]
    listed = ok(client.get(f"{ACC}/entries", headers=headers))
    assert [e for e in listed if e["kind"] == "recurring"] == []
