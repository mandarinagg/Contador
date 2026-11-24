"""Depreciación exacta, corridas y baja de bienes (spec 3B §5.1 a §5.3; D-057 a D-059).

El cálculo de referencia (`_reference_quota`) está escrito aparte, sin usar el servicio:
cuota = (costo - residual) // meses, y la última absorbe la diferencia.
"""

import random
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.modules.accounting import depreciation
from tests.accounting_utils import ACC, BANCOS, error_code, post, posted
from tests.assets_utils import (
    INFORMATICA,
    MUEBLES,
    VEHICULOS,
    balance,
    get_asset,
    months,
    new_asset,
    period_id,
    run,
    run_and_post,
    setup_books,
)
from tests.conftest import auth_header
from tests.finance_utils import ok


def _reference_quota(depreciable: int, n: int, k: int) -> int:
    base = depreciable // n
    return depreciable - base * (n - 1) if k == n else base


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    return setup_books(client, owner_token, (2026, 2027, 2028, 2029))


def _discard(client: TestClient, books: dict[str, Any], entry_id: str) -> None:
    ok(
        client.post(
            f"{ACC}/entries/{entry_id}/discard",
            json={"reason": "Se vuelve a generar"},
            headers=auth_header(books["token"]),
        )
    )


def _reverse(client: TestClient, books: dict[str, Any], entry_id: str) -> Any:
    return client.post(
        f"{ACC}/entries/{entry_id}/reverse",
        json={"reason": "Corrección"},
        headers=auth_header(books["token"]),
    )


# --- §5.1 Depreciación exacta -------------------------------------------------------------


@pytest.mark.parametrize(
    ("depreciable", "n"),
    [(9_000_000, 36), (1_000_000, 7), (100, 1), (10, 3), (999_999_999, 360), (59, 59)],
)
def test_quota_sum_is_exact_and_last_absorbs(depreciable: int, n: int) -> None:
    quotas = [depreciation.quota(Decimal(depreciable), n, k) for k in range(1, n + 1)]
    assert sum(quotas) == depreciable
    assert quotas == [Decimal(_reference_quota(depreciable, n, k)) for k in range(1, n + 1)]
    assert all(q == quotas[0] for q in quotas[:-1])
    assert quotas[-1] >= quotas[0]
    assert depreciation.quota(Decimal(depreciable), n, n + 1) == 0


def test_ten_million_with_one_million_residual_over_36_months(
    client: TestClient, books: dict[str, Any]
) -> None:
    asset = new_asset(
        client, books, cost=10_000_000, residual_value="1000000", useful_life_months=36
    )
    for y, m in months(date(2026, 2, 1), 36):
        run_and_post(client, books, y, m)
    detail = get_asset(client, books, asset["id"])
    amounts = [int(i["amount"]) for i in detail["installments"]]
    assert all(i["status"] == "posted" for i in detail["installments"])
    assert sum(amounts) == 9_000_000 and amounts == [250_000] * 36
    assert detail["accumulated_depreciation"] == "9000000"
    assert detail["net_book_value"] == "1000000"
    # Terminada la vida útil, no hay nada que depreciar.
    res = run(client, books, 2029, 2)
    assert res.status_code == 422 and error_code(res) == "NOTHING_TO_DEPRECIATE"
    assert balance(client, books, "1.02.04.99.03", "2029-01-31") == -9_000_000
    assert balance(client, books, "15.01", "2026-12-31") == 11 * 250_000


def test_inexact_division_one_month_and_zero_residual(
    client: TestClient, books: dict[str, Any]
) -> None:
    odd = new_asset(
        client, books, name="Impar", cost=1_000_001, residual_value="0", useful_life_months=7
    )
    single = new_asset(
        client, books, name="Un mes", cost=500_000, residual_value="0", useful_life_months=1
    )
    for y, m in months(date(2026, 2, 1), 7):
        run_and_post(client, books, y, m)
    odd_amounts = [int(i["amount"]) for i in get_asset(client, books, odd["id"])["installments"]]
    assert odd_amounts == [142_857] * 6 + [1_000_001 - 142_857 * 6]
    single_detail = get_asset(client, books, single["id"])
    assert [i["amount"] for i in single_detail["installments"]] == ["500000"]
    assert single_detail["net_book_value"] == "0"


def test_service_matches_reference_on_varied_assets(
    client: TestClient, books: dict[str, Any]
) -> None:
    rng = random.Random(3182)  # noqa: S311 - datos de prueba reproducibles
    specs = []
    for i in range(12):
        cost = rng.randrange(100_000, 90_000_000)
        life = rng.choice([1, 3, 7, 12, 24, 36, 60])
        residual = rng.randrange(0, cost // 5)
        acquired = date(2026, rng.randrange(1, 7), rng.randrange(1, 28))
        rule = rng.choice(["next_month", "next_fiscal_year"])
        asset = new_asset(
            client,
            books,
            name=f"Bien {i}",
            category=rng.choice([MUEBLES, INFORMATICA, VEHICULOS]),
            cost=cost,
            residual_value=str(residual),
            useful_life_months=life,
            acquired_on=acquired.isoformat(),
            start_rule=rule,
        )
        specs.append((asset, cost - residual, life))
    expected_by_month: dict[tuple[int, int], int] = {}
    for y, m in months(date(2026, 2, 1), 23):
        res = run(client, books, y, m)
        month = date(y, m, 1)
        due = 0
        for asset, depreciable, life in specs:
            start = date.fromisoformat(asset["depreciation_start"])
            k = depreciation.months_between(start, month) + 1
            if 1 <= k <= life:
                due += _reference_quota(depreciable, life, k)
        expected_by_month[(y, m)] = due
        if due == 0:
            assert res.status_code == 422
            continue
        created = ok(res, 201)
        assert int(created["total"]) == due
        ok(post(client, books["token"], created["entry_id"]))
    for asset, depreciable, life in specs:
        detail = get_asset(client, books, asset["id"])
        start = date.fromisoformat(asset["depreciation_start"])
        elapsed = max(0, min(depreciation.months_between(start, date(2028, 1, 1)), life))
        expected = sum(_reference_quota(depreciable, life, k) for k in range(1, elapsed + 1))
        assert int(detail["accumulated_depreciation"]) == expected, asset["name"]
    total = sum(expected_by_month.values())
    assert balance(client, books, "15.01", "2027-12-31") == total


# --- §5.2 Corridas ------------------------------------------------------------------------


def test_one_live_run_per_period_and_discard_frees_it(
    client: TestClient, books: dict[str, Any]
) -> None:
    new_asset(client, books)
    first = ok(run(client, books, 2026, 2), 201)
    assert first["entry"]["kind"] == "depreciation" and first["entry"]["status"] == "draft"
    assert first["entry"]["entry_date"] == "2026-02-28"
    again = run(client, books, 2026, 2)
    assert again.status_code == 409 and error_code(again) == "DEPRECIATION_RUN_EXISTS"
    _discard(client, books, first["entry_id"])
    second = ok(run(client, books, 2026, 2), 201)
    assert second["id"] != first["id"]
    ok(post(client, books["token"], second["entry_id"]))
    posted_again = run(client, books, 2026, 2)
    assert posted_again.status_code == 409


def test_months_are_not_skipped(client: TestClient, books: dict[str, Any]) -> None:
    new_asset(client, books)
    skipped = run(client, books, 2026, 3)
    assert skipped.status_code == 409 and error_code(skipped) == "DEPRECIATION_MONTH_MISSING"
    assert skipped.json()["error"]["details"]["month"] == "2026-02-01"
    feb = ok(run(client, books, 2026, 2), 201)
    # Con febrero en borrador todavía no se corre marzo.
    assert run(client, books, 2026, 3).status_code == 409
    ok(post(client, books["token"], feb["entry_id"]))
    ok(run(client, books, 2026, 3), 201)


def test_reversal_frees_the_run_and_only_the_last_one_reverses(
    client: TestClient, books: dict[str, Any]
) -> None:
    asset = new_asset(client, books)
    feb = run_and_post(client, books, 2026, 2)
    mar = run_and_post(client, books, 2026, 3)
    res = _reverse(client, books, feb["entry_id"])
    assert res.status_code == 409 and error_code(res) == "DEPRECIATION_RUN_NOT_LAST"
    ok(_reverse(client, books, mar["entry_id"]))
    assert get_asset(client, books, asset["id"])["accumulated_depreciation"] == "150000"
    redo = run_and_post(client, books, 2026, 3)
    assert redo["id"] != mar["id"]
    assert get_asset(client, books, asset["id"])["accumulated_depreciation"] == "300000"


def test_asset_starting_after_the_period_is_not_included(
    client: TestClient, books: dict[str, Any]
) -> None:
    early = new_asset(client, books, name="Temprano")
    late = new_asset(client, books, name="Tardío", acquired_on="2026-04-10")
    feb = ok(run(client, books, 2026, 2), 201)
    assert [i["asset_id"] for i in feb["items"]] == [early["id"]]
    ok(post(client, books["token"], feb["entry_id"]))
    run_and_post(client, books, 2026, 3)
    run_and_post(client, books, 2026, 4)
    may = ok(run(client, books, 2026, 5), 201)
    assert {i["asset_id"] for i in may["items"]} == {early["id"], late["id"]}
    late_item = next(i for i in may["items"] if i["asset_id"] == late["id"])
    assert late_item["installment"] == 1


def test_new_asset_before_an_existing_run_is_rejected(
    client: TestClient, books: dict[str, Any]
) -> None:
    new_asset(client, books)
    run_and_post(client, books, 2026, 2)
    res = new_asset(client, books, acquired_on="2026-01-20", expect=409)
    assert error_code(res) == "DEPRECIATION_ALREADY_RUN"


def test_run_lines_group_by_account_and_reject_incomplete_category(
    client: TestClient, books: dict[str, Any]
) -> None:
    new_asset(client, books, name="Silla", category=MUEBLES, cost=1_200_000)
    new_asset(client, books, name="Notebook", category=INFORMATICA, cost=2_400_000)
    created = ok(run(client, books, 2026, 2), 201)
    by_code = {(ln["account_code"], ln["debit"], ln["credit"]) for ln in created["entry"]["lines"]}
    assert by_code == {
        ("15.01", "108000", "0"),  # 18.000 + 90.000 (una sola línea por cuenta)
        ("1.02.04.99.03", "0", "18000"),
        ("1.02.04.99.05", "0", "90000"),
    }
    _discard(client, books, created["entry_id"])
    # Si la categoría queda incompleta, la corrida dice cuál.
    cid = books["categories"][INFORMATICA]["id"]
    ok(
        client.patch(
            f"{ACC}/asset-categories/{cid}",
            json={"expense_account_id": None},
            headers=auth_header(books["token"]),
        )
    )
    res = run(client, books, 2026, 2)
    assert res.status_code == 422 and error_code(res) == "ASSET_CATEGORY_INCOMPLETE"
    assert "Equipos de informática" in res.json()["error"]["message"]


def test_depreciation_draft_is_not_editable_and_closed_period_rejects(
    client: TestClient, books: dict[str, Any]
) -> None:
    new_asset(client, books)
    created = ok(run(client, books, 2026, 2), 201)
    res = client.patch(
        f"{ACC}/entries/{created['entry_id']}",
        json={
            "entry_date": "2026-02-28",
            "description": "Cambio a mano",
            "lines": [
                {"account_id": books["accounts"]["15.01"]["id"], "debit": "1"},
                {"account_id": books["accounts"]["1.02.04.99.03"]["id"], "credit": "1"},
            ],
        },
        headers=auth_header(books["token"]),
    )
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_EDITABLE"
    _discard(client, books, created["entry_id"])
    res = client.post(
        f"{ACC}/periods/{period_id(books, 2026, 2)}/close", headers=auth_header(books["token"])
    )
    ok(res)
    closed = run(client, books, 2026, 2)
    assert closed.status_code == 409 and error_code(closed) == "PERIOD_CLOSED"


def test_parameters_locked_once_depreciated(client: TestClient, books: dict[str, Any]) -> None:
    asset = new_asset(client, books)
    created = ok(run(client, books, 2026, 2), 201)
    headers = auth_header(books["token"])
    res = client.patch(
        f"{ACC}/fixed-assets/{asset['id']}", json={"useful_life_months": 24}, headers=headers
    )
    assert res.status_code == 409 and error_code(res) == "ASSET_HAS_DEPRECIATION"
    ok(client.patch(f"{ACC}/fixed-assets/{asset['id']}", json={"name": "Nuevo"}, headers=headers))
    _discard(client, books, created["entry_id"])
    ok(
        client.patch(
            f"{ACC}/fixed-assets/{asset['id']}", json={"useful_life_months": 24}, headers=headers
        )
    )
    # Tampoco cambian las cuentas de una categoría con bienes depreciados.
    run_and_post(client, books, 2026, 2)
    cid = books["categories"][MUEBLES]["id"]
    res = client.patch(
        f"{ACC}/asset-categories/{cid}",
        json={"expense_account_id": books["accounts"]["15.02"]["id"]},
        headers=headers,
    )
    assert res.status_code == 409 and error_code(res) == "ASSET_CATEGORY_IN_USE"


# --- §5.3 Baja ----------------------------------------------------------------------------


def _dispose(
    client: TestClient, books: dict[str, Any], asset_id: str, day: str, **extra: Any
) -> Any:
    body = {
        "date": day,
        "kind": "sale",
        "reason": "Venta del bien",
        "document_reference": "Acta 1/2026",
        **extra,
    }
    return client.post(
        f"{ACC}/fixed-assets/{asset_id}/dispose", json=body, headers=auth_header(books["token"])
    )


def _buy(client: TestClient, books: dict[str, Any], code: str, cost: int) -> None:
    posted(
        client,
        books["token"],
        books["accounts"],
        "2026-01-15",
        [(code, cost, 0), (BANCOS, 0, cost)],
        "Compra del bien",
    )


def test_disposal_zeroes_the_asset_and_books_the_result(
    client: TestClient, books: dict[str, Any]
) -> None:
    posted(
        client,
        books["token"],
        books["accounts"],
        "2026-01-02",
        [(BANCOS, 50_000_000, 0), ("3.01.01.01", 0, 50_000_000)],
    )
    _buy(client, books, "1.02.04.03", 10_000_000)
    asset = new_asset(client, books)
    for m in (2, 3, 4):
        run_and_post(client, books, 2026, m)
    # Mayo no está corrido: la baja de junio no procede.
    res = _dispose(client, books, asset["id"], "2026-06-10")
    assert res.status_code == 409 and error_code(res) == "DEPRECIATION_NOT_UP_TO_DATE"
    entry = ok(_dispose(client, books, asset["id"], "2026-05-20"), 201)
    assert entry["kind"] == "disposal" and entry["status"] == "draft"
    lines = {(ln["account_code"], ln["debit"], ln["credit"]) for ln in entry["lines"]}
    assert lines == {
        ("1.02.04.99.03", "450000", "0"),
        ("17.01", "9550000", "0"),
        ("1.02.04.03", "0", "10000000"),
    }
    pending = get_asset(client, books, asset["id"])
    assert pending["status"] == "active" and pending["disposal_entry_id"] == entry["id"]
    # Una corrida de mayo ya no incluye el bien (se da de baja en mayo).
    may = run(client, books, 2026, 5)
    assert may.status_code == 422
    ok(post(client, books["token"], entry["id"]))
    disposed = get_asset(client, books, asset["id"])
    assert disposed["status"] == "disposed" and disposed["net_book_value"] == "0"
    assert balance(client, books, "1.02.04.03", "2026-05-31") == 0
    assert balance(client, books, "1.02.04.99.03", "2026-05-31") == 0
    assert balance(client, books, "17.01", "2026-05-31") == -9_550_000  # pérdida (ingreso)
    assert installments_until(disposed) == 3


def installments_until(asset: dict[str, Any]) -> int:
    return len(asset["installments"])


def test_disposal_of_a_fully_depreciated_asset(client: TestClient, books: dict[str, Any]) -> None:
    asset = new_asset(
        client, books, cost=300_000, residual_value="0", useful_life_months=3, category=INFORMATICA
    )
    for m in (2, 3, 4):
        run_and_post(client, books, 2026, m)
    entry = ok(_dispose(client, books, asset["id"], "2026-09-01", kind="scrap"), 201)
    lines = {(ln["account_code"], ln["debit"], ln["credit"]) for ln in entry["lines"]}
    # Sin valor neto: no hay línea de resultado.
    assert lines == {("1.02.04.99.05", "300000", "0"), ("1.02.04.05.01", "0", "300000")}


def test_disposal_reversal_and_discard_return_the_asset(
    client: TestClient, books: dict[str, Any]
) -> None:
    asset = new_asset(client, books)
    run_and_post(client, books, 2026, 2)
    entry = ok(_dispose(client, books, asset["id"], "2026-03-05"), 201)
    again = _dispose(client, books, asset["id"], "2026-03-05")
    assert again.status_code == 409 and error_code(again) == "ASSET_DISPOSAL_PENDING"
    _discard(client, books, entry["id"])
    back = get_asset(client, books, asset["id"])
    assert back["status"] == "active" and back["disposal_entry_id"] is None
    entry = ok(_dispose(client, books, asset["id"], "2026-03-05"), 201)
    ok(post(client, books["token"], entry["id"]))
    # Un bien dado de baja no se deprecia más; su corrida no se revierte.
    assert run(client, books, 2026, 3).status_code == 422
    feb_entry = ok(client.get(f"{ACC}/depreciation/runs", headers=auth_header(books["token"])))[0][
        "entry_id"
    ]
    res = _reverse(client, books, feb_entry)
    assert res.status_code == 409 and error_code(res) == "ASSET_DISPOSED"
    reversal = ok(_reverse(client, books, entry["id"]))
    assert reversal["kind"] == "reversal"
    active = get_asset(client, books, asset["id"])
    assert active["status"] == "active" and active["disposed_on"] is None
    run_and_post(client, books, 2026, 3)


def test_disposal_requires_document_and_reason(client: TestClient, books: dict[str, Any]) -> None:
    asset = new_asset(client, books)
    headers = auth_header(books["token"])
    body = {"date": "2026-02-01", "kind": "donation", "reason": "Donación"}
    res = client.post(f"{ACC}/fixed-assets/{asset['id']}/dispose", json=body, headers=headers)
    assert res.status_code == 422
    res = client.post(
        f"{ACC}/fixed-assets/{asset['id']}/dispose",
        json={**body, "document_reference": "  "},
        headers=headers,
    )
    assert res.status_code == 422
    res = _dispose(client, books, asset["id"], "2026-01-01")
    assert res.status_code == 422 and error_code(res) == "DISPOSAL_DATE_INVALID"


def test_disposal_reversal_blocked_by_later_runs(client: TestClient, books: dict[str, Any]) -> None:
    keep = new_asset(client, books, name="Queda")
    gone = new_asset(client, books, name="Se va")
    run_and_post(client, books, 2026, 2)
    entry = ok(_dispose(client, books, gone["id"], "2026-03-15"), 201)
    ok(post(client, books["token"], entry["id"]))
    march = run_and_post(client, books, 2026, 3)
    assert [i["asset_id"] for i in march["items"]] == [keep["id"]]
    res = _reverse(client, books, entry["id"])
    assert res.status_code == 409 and error_code(res) == "DEPRECIATION_AFTER_DISPOSAL"
