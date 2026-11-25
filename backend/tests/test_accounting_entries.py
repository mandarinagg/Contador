"""Asientos, ejercicios y períodos por la API (spec §5.3 a §5.6 y §5.10)."""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.accounting_utils import (
    ACC,
    ALQUILERES,
    BANCOS,
    CAJA,
    CAPITAL,
    GRUPO_DISPONIBILIDADES,
    HONORARIOS,
    PROVEEDORES,
    RESULTADO_EJERCICIO,
    VENTAS,
    close_period,
    create_year,
    draft,
    entry_body,
    error_code,
    load_chart,
    period_for,
    post,
    posted,
)
from tests.conftest import auth_header
from tests.finance_utils import audit_entries, ok


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    accounts = load_chart(client, owner_token)
    year = create_year(client, owner_token, 2026)
    return {"accounts": accounts, "year": year, "token": owner_token}


def _get(client: TestClient, token: str, path: str, **params: Any) -> Any:
    return ok(client.get(f"{ACC}{path}", params=params, headers=auth_header(token)))


# --- Ejercicios ---------------------------------------------------------------------------


def test_fiscal_year_creation_rules(client: TestClient, owner_token: str) -> None:
    headers = auth_header(owner_token)
    year = create_year(client, owner_token, 2026)
    assert (year["start_date"], year["end_date"], year["status"]) == (
        "2026-01-01",
        "2026-12-31",
        "open",
    )
    assert len(year["periods"]) == 12
    assert [(p["start_date"], p["end_date"]) for p in year["periods"][1:3]] == [
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-31"),
    ]
    res = client.post(f"{ACC}/fiscal-years", json={"year": 2026}, headers=headers)
    assert res.status_code == 409 and error_code(res) == "FISCAL_YEAR_OVERLAP"
    # Primer ejercicio irregular: desde el inicio de actividades hasta fin de año.
    short = ok(
        client.post(
            f"{ACC}/fiscal-years",
            json={"start_date": "2025-08-15", "end_date": "2025-12-31"},
            headers=headers,
        ),
        201,
    )
    assert [p["start_date"] for p in short["periods"]] == [
        "2025-08-15",
        "2025-09-01",
        "2025-10-01",
        "2025-11-01",
        "2025-12-01",
    ]
    for body in (
        {"start_date": "2027-03-15", "end_date": "2028-03-14"},  # 13 meses calendario
        {"year": 2027, "start_date": "2027-01-01", "end_date": "2027-12-31"},
        {},
        {"start_date": "2027-02-01", "end_date": "2027-01-01"},
    ):
        res = client.post(f"{ACC}/fiscal-years", json=body, headers=headers)
        assert res.status_code == 422 and error_code(res) == "FISCAL_YEAR_INVALID", body
    years = ok(client.get(f"{ACC}/fiscal-years", headers=headers))
    assert [y["start_date"] for y in years] == ["2026-01-01", "2025-08-15"]


# --- Borradores y contabilización ---------------------------------------------------------


def test_draft_can_be_unbalanced_and_is_edited_only_while_draft(
    client: TestClient, books: dict[str, Any]
) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    entry = draft(client, token, accounts, "2026-03-05", [(CAJA, 1000, 0), (CAPITAL, 0, 900)])
    assert entry["status"] == "draft" and entry["number"] is None
    assert (entry["total_debit"], entry["total_credit"], entry["balanced"]) == (
        "1000",
        "900",
        False,
    )

    res = post(client, token, entry["id"])
    assert res.status_code == 422 and error_code(res) == "ENTRY_UNBALANCED"
    assert res.json()["error"]["details"] == {
        "debit": "1000",
        "credit": "900",
        "difference": "100",
    }

    body = entry_body(
        accounts,
        "2026-03-06",
        [(CAJA, 1000, 0), (CAPITAL, 0, 1000)],
        "Aporte de capital",
        document_reference="Acta 1",
    )
    edited = ok(client.patch(f"{ACC}/entries/{entry['id']}", json=body, headers=headers))
    assert edited["entry_date"] == "2026-03-06" and edited["balanced"] is True
    assert [(ln["account_code"], ln["debit"], ln["credit"]) for ln in edited["lines"]] == [
        (CAJA, "1000", "0"),
        (CAPITAL, "0", "1000"),
    ]
    done = ok(post(client, token, entry["id"]))
    assert done["status"] == "posted" and done["number"] == 1 and done["posted_by"]

    res = client.patch(f"{ACC}/entries/{entry['id']}", json=body, headers=headers)
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_DRAFT"
    res = client.post(
        f"{ACC}/entries/{entry['id']}/discard", json={"reason": "No va"}, headers=headers
    )
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_DRAFT"
    res = post(client, token, entry["id"])
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_DRAFT"

    actions = [e["action"] for e in audit_entries(client, token, "accounting.journal_entry")]
    assert actions == [
        "accounting.journal_entry.posted",
        "accounting.journal_entry.updated",
        "accounting.journal_entry.created",
    ]
    updated = audit_entries(client, token, "accounting.journal_entry")[1]
    assert set(updated["after"]) == {"entry_date", "description", "document_reference", "lines"}


def test_posting_errors_are_readable(client: TestClient, books: dict[str, Any]) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    single = draft(client, token, accounts, "2026-03-05", [(CAJA, 1000, 0)])
    res = post(client, token, single["id"])
    assert res.status_code == 422 and error_code(res) == "ENTRY_TOO_FEW_LINES"

    res = client.post(
        f"{ACC}/entries",
        json=entry_body(accounts, "2026-03-05", [(GRUPO_DISPONIBILIDADES, 10, 0), (CAJA, 0, 10)]),
        headers=headers,
    )
    assert res.status_code == 422 and error_code(res) == "ACCOUNT_NOT_POSTABLE"
    assert res.json()["error"]["details"]["lines"][0]["line"] == 1

    res = client.post(
        f"{ACC}/entries",
        json=entry_body(accounts, "2025-03-05", [(CAJA, 10, 0), (CAPITAL, 0, 10)]),
        headers=headers,
    )
    assert res.status_code == 422 and error_code(res) == "FISCAL_YEAR_NOT_FOUND"

    in_march = draft(client, token, accounts, "2026-03-20", [(CAJA, 10, 0), (CAPITAL, 0, 10)])
    ok(
        client.post(
            f"{ACC}/entries/{in_march['id']}/discard", json={"reason": "Mover"}, headers=headers
        )
    )
    ok(close_period(client, token, period_for(books["year"], 2)["id"]))
    in_feb = draft(client, token, accounts, "2026-02-10", [(CAJA, 10, 0), (CAPITAL, 0, 10)])
    res = post(client, token, in_feb["id"])
    assert res.status_code == 409 and error_code(res) == "PERIOD_CLOSED"


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ({"debit": "100", "credit": "100"}, "LINE_DEBIT_XOR_CREDIT"),
        ({"debit": "0", "credit": "0"}, "LINE_DEBIT_XOR_CREDIT"),
        ({"debit": "100.50"}, "INVALID_AMOUNT"),
        ({"debit": "-100"}, "INVALID_AMOUNT"),
        ({"debit": 100}, "VALIDATION_ERROR"),  # número JSON, no string
        ({"debit": "100", "fx_currency": "USD", "fx_amount": "10"}, "FX_INCOMPLETE"),
        (
            {"debit": "100", "fx_currency": "USD", "fx_amount": "10.001", "fx_rate": "7300"},
            "INVALID_AMOUNT",
        ),
        (
            {"debit": "100", "fx_currency": "USD", "fx_amount": "10", "fx_rate": "7300.1234567"},
            "VALIDATION_ERROR",
        ),
    ],
)
def test_line_validation(
    client: TestClient, books: dict[str, Any], line: dict[str, Any], code: str
) -> None:
    body = {
        "entry_date": "2026-03-05",
        "description": "Línea inválida",
        "lines": [{"account_id": books["accounts"][CAJA]["id"], **line}],
    }
    res = client.post(f"{ACC}/entries", json=body, headers=auth_header(books["token"]))
    assert res.status_code == 422 and error_code(res) == code


def test_fx_line_is_informative(client: TestClient, books: dict[str, Any]) -> None:
    accounts = books["accounts"]
    body = {
        "entry_date": "2026-03-05",
        "description": "Compra de dólares",
        "lines": [
            {
                "account_id": accounts["1.01.01.04.03"]["id"],
                "debit": "730025",
                "fx_currency": "USD",
                "fx_amount": "100.00",
                "fx_rate": "7300.250000",
            },
            {"account_id": accounts[BANCOS]["id"], "credit": "730025"},
        ],
    }
    entry = ok(client.post(f"{ACC}/entries", json=body, headers=auth_header(books["token"])), 201)
    fx = entry["lines"][0]
    assert (fx["fx_currency"], fx["fx_amount"], fx["fx_rate"]) == ("USD", "100.00", "7300.25")
    assert ok(post(client, books["token"], entry["id"]))["number"] == 1


# --- §5.3: numeración correlativa sin huecos ----------------------------------------------


def test_numbering_is_correlative_without_gaps_despite_discards(
    client: TestClient, books: dict[str, Any]
) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    lines = [(CAJA, 100, 0), (CAPITAL, 0, 100)]
    numbers = []
    for n in range(6):
        entry = draft(client, token, accounts, f"2026-0{n + 1}-15", lines)
        if n % 2 == 1:
            ok(
                client.post(
                    f"{ACC}/entries/{entry['id']}/discard",
                    json={"reason": "Sobra"},
                    headers=headers,
                )
            )
            continue
        numbers.append(ok(post(client, token, entry["id"]))["number"])
    # Un borrador que se contabiliza más tarde con fecha anterior toma el número siguiente.
    late = draft(client, token, accounts, "2026-01-02", lines)
    numbers.append(ok(post(client, token, late["id"]))["number"])
    assert numbers == [1, 2, 3, 4]
    year = ok(client.get(f"{ACC}/fiscal-years/{books['year']['id']}", headers=headers))
    assert year["last_entry_number"] == 4
    # Cada ejercicio tiene su numeración.
    create_year(client, token, 2027)
    assert posted(client, token, accounts, "2027-01-05", lines)["number"] == 1
    discarded = ok(client.get(f"{ACC}/entries", params={"status": "discarded"}, headers=headers))
    assert len(discarded) == 3 and all(e["number"] is None for e in discarded)


# --- §5.4: reversión ----------------------------------------------------------------------


def _ledger(client: TestClient, token: str, account_id: str, **params: Any) -> Any:
    return _get(client, token, f"/reports/ledger/{account_id}", **params)


def test_reversal_inverts_lines_and_nets_ledger_to_zero(
    client: TestClient, books: dict[str, Any]
) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    original = posted(
        client,
        token,
        accounts,
        "2026-04-10",
        [(ALQUILERES, 2500000, 0), (HONORARIOS, 500000, 0), (BANCOS, 0, 3000000)],
        "Alquiler y honorarios de abril",
    )
    res = client.post(
        f"{ACC}/entries/{original['id']}/reverse", json={"reason": "Mal imputado"}, headers=headers
    )
    reversal = ok(res)
    assert reversal["kind"] == "reversal" and reversal["status"] == "posted"
    assert reversal["number"] == original["number"] + 1
    assert reversal["entry_date"] == "2026-04-10"
    assert reversal["reverses_entry_id"] == original["id"]
    assert "Mal imputado" in reversal["description"]
    assert [(ln["account_code"], ln["debit"], ln["credit"]) for ln in reversal["lines"]] == [
        (ALQUILERES, "0", "2500000"),
        (HONORARIOS, "0", "500000"),
        (BANCOS, "3000000", "0"),
    ]
    stored = ok(client.get(f"{ACC}/entries/{original['id']}", headers=headers))
    assert stored["status"] == "reversed" and stored["reversed_by_entry_id"] == reversal["id"]

    ledger = _ledger(
        client, token, accounts[BANCOS]["id"], **{"from": "2026-01-01", "to": "2026-12-31"}
    )
    assert [m["balance"] for m in ledger["movements"]] == ["-3000000", "0"]
    assert ledger["closing_balance"] == "0"

    res = client.post(
        f"{ACC}/entries/{original['id']}/reverse", json={"reason": "Otra vez"}, headers=headers
    )
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_POSTED"
    res = client.post(
        f"{ACC}/entries/{reversal['id']}/reverse",
        json={"reason": "Revertir la reversión"},
        headers=headers,
    )
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_REVERSIBLE"

    reversed_audit = [
        e
        for e in audit_entries(client, token, "accounting.journal_entry")
        if e["action"] == "accounting.journal_entry.reversed"
    ]
    assert reversed_audit[0]["after"] == {
        "status": "reversed",
        "reversal_entry_id": reversal["id"],
        "reason": "Mal imputado",
    }


def test_reversal_in_closed_period_asks_for_another_date(
    client: TestClient, books: dict[str, Any]
) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    original = posted(client, token, accounts, "2026-04-10", [(CAJA, 900, 0), (CAPITAL, 0, 900)])
    ok(close_period(client, token, period_for(books["year"], 4)["id"]))
    url = f"{ACC}/entries/{original['id']}/reverse"
    res = client.post(url, json={"reason": "Error"}, headers=headers)
    assert res.status_code == 409 and error_code(res) == "PERIOD_CLOSED"
    assert res.json()["error"]["details"]["date"] == "2026-04-10"
    res = client.post(url, json={"reason": "Error", "date": "2026-04-30"}, headers=headers)
    assert res.status_code == 409 and error_code(res) == "PERIOD_CLOSED"
    res = client.post(url, json={"reason": "Error", "date": "2026-03-31"}, headers=headers)
    assert res.status_code == 422 and error_code(res) == "REVERSAL_DATE_INVALID"
    reversal = ok(client.post(url, json={"reason": "Error", "date": "2026-05-02"}, headers=headers))
    assert reversal["entry_date"] == "2026-05-02"
    assert ok(client.get(f"{ACC}/entries/{original['id']}", headers=headers))["status"] == (
        "reversed"
    )


# --- §5.5: períodos -----------------------------------------------------------------------


def test_closing_period_with_drafts_lists_them_and_reopen_needs_reason(
    client: TestClient, books: dict[str, Any]
) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    march = period_for(books["year"], 3)
    pending = draft(client, token, accounts, "2026-03-31", [(CAJA, 10, 0)], "Pendiente")
    res = close_period(client, token, march["id"])
    assert res.status_code == 409 and error_code(res) == "PERIOD_HAS_DRAFTS"
    assert res.json()["error"]["details"]["drafts"] == [
        {"id": pending["id"], "entry_date": "2026-03-31", "description": "Pendiente"}
    ]
    ok(
        client.post(
            f"{ACC}/entries/{pending['id']}/discard",
            json={"reason": "No corresponde"},
            headers=headers,
        )
    )
    closed = ok(close_period(client, token, march["id"]))
    assert closed["status"] == "closed" and closed["closed_by"]
    res = close_period(client, token, march["id"])
    assert res.status_code == 409 and error_code(res) == "PERIOD_ALREADY_CLOSED"

    url = f"{ACC}/periods/{march['id']}/reopen"
    assert client.post(url, json={}, headers=headers).status_code == 422
    assert client.post(url, json={"reason": "  "}, headers=headers).status_code == 422
    reopened = ok(client.post(url, json={"reason": "Falta una factura"}, headers=headers))
    assert reopened["status"] == "open" and reopened["reopen_reason"] == "Falta una factura"
    entries = audit_entries(client, token, "accounting.period")
    assert [e["action"] for e in entries] == [
        "accounting.period.reopened",
        "accounting.period.closed",
    ]
    assert entries[0]["after"]["reopen_reason"] == "Falta una factura"
    assert entries[0]["before"]["status"] == "closed"


# --- §5.6: cierre del ejercicio -----------------------------------------------------------


def _sheet(client: TestClient, token: str, at: str) -> Any:
    return _get(client, token, "/reports/balance-sheet", at=at)


def _close_all_periods(client: TestClient, token: str, year: dict[str, Any]) -> None:
    for period in year["periods"]:
        ok(close_period(client, token, period["id"]))


def test_closing_the_fiscal_year(client: TestClient, books: dict[str, Any]) -> None:
    token, accounts, year = books["token"], books["accounts"], books["year"]
    headers = auth_header(token)
    posted(client, token, accounts, "2026-01-02", [(BANCOS, 10000000, 0), (CAPITAL, 0, 10000000)])
    posted(client, token, accounts, "2026-03-15", [(BANCOS, 7000000, 0), (VENTAS, 0, 7000000)])
    posted(client, token, accounts, "2026-06-20", [(ALQUILERES, 2500000, 0), (BANCOS, 0, 2500000)])
    posted(
        client, token, accounts, "2026-09-01", [(HONORARIOS, 800000, 0), (PROVEEDORES, 0, 800000)]
    )
    posted(client, token, accounts, "2026-11-30", [("4.99", 200000, 0), (BANCOS, 0, 200000)])
    before = _sheet(client, token, "2026-12-31")
    assert before["balanced"] is True and before["result"] == "3500000"

    url = f"{ACC}/fiscal-years/{year['id']}/close"
    res = client.post(url, headers=headers)
    assert res.status_code == 409 and error_code(res) == "PERIODS_OPEN"
    assert len(res.json()["error"]["details"]["periods"]) == 12
    _close_all_periods(client, token, year)
    res = client.post(url, headers=headers)
    assert res.status_code == 409 and error_code(res) == "RETAINED_EARNINGS_NOT_SET"
    ok(
        client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": accounts[RESULTADO_EJERCICIO]["id"]},
            headers=headers,
        )
    )
    closed = ok(client.post(url, headers=headers))
    assert closed["status"] == "closed" and closed["closing_entry_id"]
    closing = ok(client.get(f"{ACC}/entries/{closed['closing_entry_id']}", headers=headers))
    assert closing["kind"] == "closing" and closing["status"] == "posted"
    assert closing["entry_date"] == "2026-12-31" and closing["number"] == 6
    assert closing["balanced"] is True
    assert closing["lines"][-1]["account_code"] == RESULTADO_EJERCICIO
    assert closing["lines"][-1]["credit"] == "3500000"

    after = _sheet(client, token, "2026-12-31")
    assert after["balanced"] is True and after["result"] == "0"
    assert after["total_assets"] == before["total_assets"]
    chart = _get(client, token, "/chart", flat="true", balance_at="2026-12-31")
    balances = {a["code"]: a for a in chart["accounts"]}
    result_accounts = [a for a in chart["accounts"] if a["kind"] in ("income", "expense")]
    assert all(a["balance"] == "0" for a in result_accounts)
    assert balances[RESULTADO_EJERCICIO]["balance"] == "3500000"
    # El estado de resultados del ejercicio no cuenta la refundición.
    statement = _get(
        client, token, "/reports/income-statement", **{"from": "2026-01-01", "to": "2026-12-31"}
    )
    assert statement["result"] == "3500000"

    # Cerrado es definitivo: ni asientos, ni reapertura de períodos, ni segundo cierre.
    res = client.post(
        f"{ACC}/entries",
        json=entry_body(accounts, "2026-12-01", [(CAJA, 10, 0), (CAPITAL, 0, 10)]),
        headers=headers,
    )
    assert res.status_code == 409 and error_code(res) == "FISCAL_YEAR_CLOSED"
    res = client.post(
        f"{ACC}/periods/{year['periods'][11]['id']}/reopen",
        json={"reason": "Corregir"},
        headers=headers,
    )
    assert res.status_code == 409 and error_code(res) == "FISCAL_YEAR_CLOSED"
    res = client.post(url, headers=headers)
    assert res.status_code == 409 and error_code(res) == "FISCAL_YEAR_CLOSED"
    res = client.post(
        f"{ACC}/entries/{closing['id']}/reverse", json={"reason": "No corresponde"}, headers=headers
    )
    assert res.status_code == 409 and error_code(res) == "ENTRY_NOT_REVERSIBLE"
    audit = audit_entries(client, token, "accounting.fiscal_year")[0]
    assert audit["action"] == "accounting.fiscal_year.closed"
    assert audit["after"]["result"] == "3500000"


def test_closing_with_loss_and_drafts(client: TestClient, books: dict[str, Any]) -> None:
    token, accounts, year = books["token"], books["accounts"], books["year"]
    headers = auth_header(token)
    ok(
        client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": accounts[RESULTADO_EJERCICIO]["id"]},
            headers=headers,
        )
    )
    posted(client, token, accounts, "2026-05-05", [(ALQUILERES, 900000, 0), (CAJA, 0, 900000)])
    posted(client, token, accounts, "2026-05-06", [(CAJA, 100000, 0), (VENTAS, 0, 100000)])
    _close_all_periods(client, token, year)
    # Un borrador creado después de cerrar los períodos impide cerrar el ejercicio.
    pending = draft(client, token, accounts, "2026-07-01", [(CAJA, 10, 0)])
    url = f"{ACC}/fiscal-years/{year['id']}/close"
    res = client.post(url, headers=headers)
    assert res.status_code == 409 and error_code(res) == "FISCAL_YEAR_HAS_DRAFTS"
    ok(
        client.post(
            f"{ACC}/entries/{pending['id']}/discard", json={"reason": "Sobra"}, headers=headers
        )
    )
    closed = ok(client.post(url, headers=headers))
    closing = ok(client.get(f"{ACC}/entries/{closed['closing_entry_id']}", headers=headers))
    last = closing["lines"][-1]
    assert (last["account_code"], last["debit"], last["credit"]) == (
        RESULTADO_EJERCICIO,
        "800000",
        "0",
    )
    sheet = _sheet(client, token, "2026-12-31")
    assert sheet["balanced"] is True and sheet["result"] == "0"


def test_closing_a_year_without_results_needs_no_entry(
    client: TestClient, books: dict[str, Any]
) -> None:
    token, accounts, year = books["token"], books["accounts"], books["year"]
    headers = auth_header(token)
    ok(
        client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": accounts[RESULTADO_EJERCICIO]["id"]},
            headers=headers,
        )
    )
    posted(client, token, accounts, "2026-05-05", [(CAJA, 900, 0), (CAPITAL, 0, 900)])
    _close_all_periods(client, token, year)
    closed = ok(client.post(f"{ACC}/fiscal-years/{year['id']}/close", headers=headers))
    assert closed["status"] == "closed" and closed["closing_entry_id"] is None


# --- §5.10: permisos ----------------------------------------------------------------------


def test_permissions_by_role(client: TestClient, books: dict[str, Any], make_user: Any) -> None:
    token, accounts, year = books["token"], books["accounts"], books["year"]
    _, viewer = make_user("viewer")
    _, admin = make_user("admin")
    _, accountant = make_user("accountant")
    body = entry_body(accounts, "2026-02-03", [(CAJA, 50, 0), (CAPITAL, 0, 50)])
    entry = draft(client, token, accounts, "2026-02-02", [(CAJA, 50, 0), (CAPITAL, 0, 50)])

    # Consulta: solo lee.
    v = auth_header(viewer)
    for path in (
        "/chart",
        "/fiscal-years",
        "/entries",
        f"/entries/{entry['id']}",
        "/reports/balance-sheet?at=2026-12-31",
    ):
        assert client.get(f"{ACC}{path}", headers=v).status_code == 200, path
    assert client.post(f"{ACC}/entries", json=body, headers=v).status_code == 403
    assert client.post(f"{ACC}/chart/load-proposed", headers=v).status_code == 403

    # Administrador: gestiona borradores, pero no contabiliza ni cierra.
    a = auth_header(admin)
    own = ok(client.post(f"{ACC}/entries", json=body, headers=a), 201)
    forbidden = [
        client.post(f"{ACC}/entries/{own['id']}/post", headers=a),
        client.post(f"{ACC}/entries/{entry['id']}/reverse", json={"reason": "x" * 5}, headers=a),
        client.post(f"{ACC}/periods/{year['periods'][0]['id']}/close", headers=a),
        client.post(
            f"{ACC}/periods/{year['periods'][0]['id']}/reopen", json={"reason": "Por"}, headers=a
        ),
        client.post(f"{ACC}/fiscal-years/{year['id']}/close", headers=a),
        client.post(f"{ACC}/fiscal-years", json={"year": 2027}, headers=a),
        client.post(
            f"{ACC}/chart/validate",
            headers=a,
        ),
    ]
    for res in forbidden:
        assert res.status_code == 403
        assert res.json()["error"]["details"]["missing"] == ["accounting.post"]

    # Contador: contabiliza y cierra.
    c = auth_header(accountant)
    assert ok(client.post(f"{ACC}/entries/{own['id']}/post", headers=c))["number"] == 1
    assert ok(close_period(client, accountant, year["periods"][0]["id"]))["status"] == "closed"


def test_entries_listing_filters_and_cursor(client: TestClient, books: dict[str, Any]) -> None:
    token, accounts = books["token"], books["accounts"]
    headers = auth_header(token)
    for day in range(1, 8):
        entry = draft(
            client,
            token,
            accounts,
            f"2026-03-{day:02d}",
            [(CAJA, day * 100, 0), (CAPITAL, 0, day * 100)],
            f"Aporte {day}",
        )
        if day % 2:
            ok(post(client, token, entry["id"]))
    page = ok(client.get(f"{ACC}/entries", params={"limit": 3}, headers=headers))
    assert [e["entry_date"] for e in page] == ["2026-03-07", "2026-03-06", "2026-03-05"]
    assert all(e["lines"] is None for e in page)
    rest = ok(
        client.get(
            f"{ACC}/entries", params={"limit": 10, "before": page[-1]["id"]}, headers=headers
        )
    )
    assert [e["entry_date"][-2:] for e in rest] == ["04", "03", "02", "01"]
    assert len(ok(client.get(f"{ACC}/entries", params={"status": "posted"}, headers=headers))) == 4
    found = ok(client.get(f"{ACC}/entries", params={"q": "aporte 6"}, headers=headers))
    assert [e["description"] for e in found] == ["Aporte 6"]
    by_number = ok(client.get(f"{ACC}/entries", params={"q": "2"}, headers=headers))
    assert {e["number"] for e in by_number} >= {2}
    ranged = ok(
        client.get(
            f"{ACC}/entries", params={"from": "2026-03-02", "to": "2026-03-03"}, headers=headers
        )
    )
    assert len(ranged) == 2
    by_account = ok(
        client.get(f"{ACC}/entries", params={"account_id": accounts[BANCOS]["id"]}, headers=headers)
    )
    assert by_account == []
    total = sum(Decimal(e["total_debit"]) for e in rest)
    assert total == Decimal(1000)
