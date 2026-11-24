"""Finanzas ↔ contabilidad (D-035, D-041, BR-ACC-06/07/11; spec §5.2 y §5.9)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.accounting_utils import (
    ACC,
    ALQUILERES,
    BANCO_USD,
    BANCOS,
    CAJA,
    PROVEEDORES,
    VENTAS,
    create_year,
    error_code,
    load_chart,
    post,
)
from tests.conftest import auth_header
from tests.finance_utils import (
    API,
    audit_entries,
    business_context,
    create_account,
    create_tx,
    ok,
    personal_context,
)


def _category(client: TestClient, token: str, cid: str, name: str, kind: str, **extra: Any) -> str:
    res = client.post(
        f"{API}/contexts/{cid}/categories",
        json={"name": name, "kind": kind, **extra},
        headers=auth_header(token),
    )
    return str(ok(res, 201)["id"])


def _map(client: TestClient, token: str, path: str, ledger_id: str | None) -> Any:
    return client.patch(path, json={"ledger_account_id": ledger_id}, headers=auth_header(token))


@pytest.fixture
def world(client: TestClient, owner_token: str) -> dict[str, Any]:
    token = owner_token
    accounts = load_chart(client, token)
    create_year(client, token, 2026)
    biz = business_context(client, token)
    bank = create_account(client, token, biz, "Banco Itaú")["id"]
    usd = create_account(client, token, biz, "Cuenta USD", currency="USD")["id"]
    sales = _category(client, token, biz, "Ventas", "income")
    rent = _category(client, token, biz, "Alquiler", "expense")
    for path, code in (
        (f"/accounts/{bank}", BANCOS),
        (f"/accounts/{usd}", BANCO_USD),
        (f"/categories/{sales}", VENTAS),
        (f"/categories/{rent}", ALQUILERES),
    ):
        ok(_map(client, token, f"{API}/contexts/{biz}{path}", accounts[code]["id"]))
    return {
        "token": token,
        "accounts": accounts,
        "biz": biz,
        "bank": bank,
        "usd": usd,
        "sales": sales,
        "rent": rent,
    }


def _propose(client: TestClient, w: dict[str, Any], tx_id: str, **body: Any) -> Any:
    return client.post(
        f"{ACC}/entries/from-transaction/{tx_id}",
        json=body or None,
        headers=auth_header(w["token"]),
    )


def _lines(entry: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(ln["account_code"], ln["debit"], ln["credit"]) for ln in entry["lines"]]


# --- Cuentas contables en finanzas --------------------------------------------------------


def test_ledger_accounts_are_assigned_only_in_business_and_with_the_right_kind(
    client: TestClient, world: dict[str, Any]
) -> None:
    w, token = world, world["token"]
    accounts = w["accounts"]
    base = f"{API}/contexts/{w['biz']}"
    res = client.get(f"{base}/accounts", headers=auth_header(token))
    mapped = {a["id"]: a["ledger_account_id"] for a in ok(res)}
    assert mapped[w["bank"]] == accounts[BANCOS]["id"]

    checks = [
        (f"{base}/accounts/{w['bank']}", VENTAS, "LEDGER_ACCOUNT_KIND_MISMATCH"),
        (f"{base}/accounts/{w['bank']}", "1.01.01.04", "ACCOUNT_NOT_POSTABLE"),
        (f"{base}/categories/{w['sales']}", ALQUILERES, "LEDGER_ACCOUNT_KIND_MISMATCH"),
        (f"{base}/categories/{w['rent']}", CAJA, "LEDGER_ACCOUNT_KIND_MISMATCH"),
    ]
    for path, code, expected in checks:
        res = _map(client, token, path, accounts[code]["id"])
        assert res.status_code == 422 and error_code(res) == expected, (path, code)
    # Una tarjeta de crédito es pasivo: se admite.
    card = create_account(client, token, w["biz"], "Tarjeta", kind="credit_card")["id"]
    ok(_map(client, token, f"{base}/accounts/{card}", accounts[PROVEEDORES]["id"]))
    # null la quita, y queda auditado.
    assert ok(_map(client, token, f"{base}/accounts/{card}", None))["ledger_account_id"] is None
    changes = [
        e
        for e in audit_entries(client, token, "finance.account")
        if e["entity_id"] == card and e["action"] == "finance.account.updated"
    ]
    assert changes[0]["after"] == {"ledger_account_id": None}

    per = personal_context(client, token)
    own = create_account(client, token, per, "Personal")["id"]
    res = _map(client, token, f"{API}/contexts/{per}/accounts/{own}", accounts[BANCOS]["id"])
    assert res.status_code == 422 and error_code(res) == "LEDGER_ACCOUNT_BUSINESS_ONLY"


# --- Borrador propuesto -------------------------------------------------------------------


def test_proposed_draft_has_bank_against_category_with_the_right_sign(
    client: TestClient, world: dict[str, Any]
) -> None:
    w = world
    income = create_tx(
        client,
        w["token"],
        w["biz"],
        w["bank"],
        "1500000",
        description="Cobro factura 001-001-0000123",
        reference="001-001-0000123",
        category_id=w["sales"],
    )
    entry = ok(_propose(client, w, income["id"]), 201)
    assert (entry["status"], entry["kind"], entry["number"]) == ("draft", "finance", None)
    assert entry["source_transaction_id"] == income["id"]
    assert entry["source_context_id"] == w["biz"]
    assert entry["entry_date"] == income["booked_on"]
    assert entry["document_reference"] == "001-001-0000123"
    assert _lines(entry) == [(BANCOS, "1500000", "0"), (VENTAS, "0", "1500000")]

    expense = create_tx(client, w["token"], w["biz"], w["bank"], "-2500000", category_id=w["rent"])
    entry = ok(_propose(client, w, expense["id"]), 201)
    assert _lines(entry) == [(ALQUILERES, "2500000", "0"), (BANCOS, "0", "2500000")]
    created = audit_entries(client, w["token"], "accounting.journal_entry")[0]
    assert created["action"] == "accounting.journal_entry.created"
    assert created["after"]["source_transaction_id"] == expense["id"]


def test_only_one_live_entry_per_transaction(client: TestClient, world: dict[str, Any]) -> None:
    w = world
    headers = auth_header(w["token"])
    tx = create_tx(client, w["token"], w["biz"], w["bank"], "50000", category_id=w["sales"])
    first = ok(_propose(client, w, tx["id"]), 201)
    res = _propose(client, w, tx["id"])
    assert res.status_code == 409 and error_code(res) == "TRANSACTION_HAS_ENTRY"
    assert res.json()["error"]["details"]["entry_id"] == first["id"]
    ok(
        client.post(
            f"{ACC}/entries/{first['id']}/discard", json={"reason": "Rehacer"}, headers=headers
        )
    )
    second = ok(_propose(client, w, tx["id"]), 201)
    ok(post(client, w["token"], second["id"]))
    res = _propose(client, w, tx["id"])
    assert res.status_code == 409 and error_code(res) == "TRANSACTION_HAS_ENTRY"
    assert "N° 1" in res.json()["error"]["message"]
    # Revertido el asiento, el movimiento vuelve a admitir una propuesta.
    ok(
        client.post(
            f"{ACC}/entries/{second['id']}/reverse", json={"reason": "Mal"}, headers=headers
        )
    )
    ok(_propose(client, w, tx["id"]), 201)


def test_transactions_show_their_journal_entry_only_in_business(
    client: TestClient, world: dict[str, Any]
) -> None:
    w, token = world, world["token"]
    headers = auth_header(token)
    tx = create_tx(client, token, w["biz"], w["bank"], "70000", category_id=w["sales"])
    assert tx["journal_entry"] is None
    entry = ok(_propose(client, w, tx["id"]), 201)
    listed = ok(client.get(f"{API}/contexts/{w['biz']}/transactions", headers=headers))
    assert listed[0]["journal_entry"] == {"id": entry["id"], "number": None, "status": "draft"}
    ok(post(client, token, entry["id"]))
    listed = ok(client.get(f"{API}/contexts/{w['biz']}/transactions", headers=headers))
    assert listed[0]["journal_entry"] == {"id": entry["id"], "number": 1, "status": "posted"}

    per = personal_context(client, token)
    own = create_account(client, token, per, "Personal")["id"]
    create_tx(client, token, per, own, "-10000")
    listed = ok(client.get(f"{API}/contexts/{per}/transactions", headers=headers))
    assert listed[0]["journal_entry"] is None


def test_transaction_with_posted_entry_cannot_be_voided_or_changed(
    client: TestClient, world: dict[str, Any]
) -> None:
    w, token = world, world["token"]
    headers = auth_header(token)
    tx = create_tx(client, token, w["biz"], w["bank"], "-300000", category_id=w["rent"])
    entry = ok(_propose(client, w, tx["id"]), 201)
    ok(post(client, token, entry["id"]))
    void_url = f"{API}/contexts/{w['biz']}/transactions/{tx['id']}/void"
    res = client.post(void_url, json={"reason": "Duplicado"}, headers=headers)
    assert res.status_code == 409 and error_code(res) == "TRANSACTION_HAS_POSTED_ENTRY"
    assert "revertí primero el asiento N° 1" in res.json()["error"]["message"]
    res = client.patch(
        f"{API}/contexts/{w['biz']}/transactions/{tx['id']}",
        json={"amount": "-310000"},
        headers=headers,
    )
    assert res.status_code == 409 and error_code(res) == "TRANSACTION_HAS_POSTED_ENTRY"
    # La descripción sí se puede corregir.
    ok(
        client.patch(
            f"{API}/contexts/{w['biz']}/transactions/{tx['id']}",
            json={"description": "Alquiler de mayo"},
            headers=headers,
        )
    )
    ok(
        client.post(
            f"{ACC}/entries/{entry['id']}/reverse", json={"reason": "Duplicado"}, headers=headers
        )
    )
    voided = ok(client.post(void_url, json={"reason": "Duplicado"}, headers=headers))
    assert voided[0]["voided_at"] and voided[0]["journal_entry"]["status"] == "reversed"


def test_draft_of_a_voided_transaction_cannot_be_posted(
    client: TestClient, world: dict[str, Any]
) -> None:
    w, token = world, world["token"]
    headers = auth_header(token)
    tx = create_tx(client, token, w["biz"], w["bank"], "90000", category_id=w["sales"])
    entry = ok(_propose(client, w, tx["id"]), 201)
    ok(
        client.post(
            f"{API}/contexts/{w['biz']}/transactions/{tx['id']}/void",
            json={"reason": "Error de carga"},
            headers=headers,
        )
    )
    res = post(client, token, entry["id"])
    assert res.status_code == 409 and error_code(res) == "SOURCE_TRANSACTION_VOIDED"
    res = _propose(client, w, tx["id"])
    assert res.status_code == 409


def test_foreign_currency_needs_a_rate_and_never_rounds_silently(
    client: TestClient, world: dict[str, Any]
) -> None:
    w = world
    tx = create_tx(client, w["token"], w["biz"], w["usd"], "100.25", category_id=w["sales"])
    res = _propose(client, w, tx["id"])
    assert res.status_code == 422 and error_code(res) == "FX_RATE_REQUIRED"
    res = _propose(client, w, tx["id"], fx_rate=7300.5)
    assert res.status_code == 422  # número JSON: se rechaza

    res = _propose(client, w, tx["id"], fx_rate="7300.5")  # 731875.125: no es entero
    assert res.status_code == 422 and error_code(res) == "FX_ROUNDING_REQUIRED"
    assert res.json()["error"]["details"] == {
        "exact": "731875.125",
        "floor": "731875",
        "ceil": "731876",
    }
    res = _propose(client, w, tx["id"], fx_rate="7300.5", amount_pyg="731870")
    assert res.status_code == 422 and error_code(res) == "FX_ROUNDING_INVALID"
    entry = ok(_propose(client, w, tx["id"], fx_rate="7300.5", amount_pyg="731876"), 201)
    assert _lines(entry) == [(BANCO_USD, "731876", "0"), (VENTAS, "0", "731876")]
    line = entry["lines"][0]
    assert (line["fx_currency"], line["fx_amount"], line["fx_rate"]) == ("USD", "100.25", "7300.5")

    exact = create_tx(client, w["token"], w["biz"], w["usd"], "-100.25", category_id=w["rent"])
    entry = ok(_propose(client, w, exact["id"], fx_rate="7300"), 201)  # 731825 exacto
    assert _lines(entry) == [(ALQUILERES, "731825", "0"), (BANCO_USD, "0", "731825")]

    pyg_tx = create_tx(client, w["token"], w["biz"], w["bank"], "1000", category_id=w["sales"])
    res = _propose(client, w, pyg_tx["id"], fx_rate="7300")
    assert res.status_code == 422 and error_code(res) == "FX_NOT_APPLICABLE"


def test_missing_mappings_are_named(client: TestClient, world: dict[str, Any]) -> None:
    w, token = world, world["token"]
    cash = create_account(client, token, w["biz"], "Caja chica")["id"]
    other = _category(client, token, w["biz"], "Servicios", "income")
    tx = create_tx(client, token, w["biz"], cash, "1000", category_id=other)
    res = _propose(client, w, tx["id"])
    assert res.status_code == 422 and error_code(res) == "LEDGER_ACCOUNT_MISSING"
    message = res.json()["error"]["message"]
    assert "Caja chica" in message and "Servicios" in message
    assert [m["kind"] for m in res.json()["error"]["details"]["missing"]] == [
        "account",
        "category",
    ]
    uncategorized = create_tx(client, token, w["biz"], w["bank"], "1000")
    res = _propose(client, w, uncategorized["id"])
    assert res.status_code == 422 and error_code(res) == "CATEGORY_REQUIRED"

    # Una subcategoría sin cuenta contable usa la de su categoría padre.
    child = _category(client, token, w["biz"], "Ventas web", "income", parent_id=w["sales"])
    tx = create_tx(client, token, w["biz"], w["bank"], "2000", category_id=child)
    assert _lines(ok(_propose(client, w, tx["id"]), 201))[1] == (VENTAS, "0", "2000")

    transfer = ok(
        client.post(
            f"{API}/contexts/{w['biz']}/transfers",
            json={
                "from_account_id": w["bank"],
                "to_account_id": cash,
                "booked_on": "2026-03-10",
                "amount_out": "500",
                "amount_in": "500",
                "description": "A caja",
            },
            headers=auth_header(token),
        ),
        201,
    )
    res = _propose(client, w, transfer["outgoing"]["id"])
    assert res.status_code == 422 and error_code(res) == "TRANSFER_NOT_SUPPORTED"


def test_personal_transaction_is_not_found_for_accounting(
    client: TestClient, world: dict[str, Any], make_user: Any
) -> None:
    w, token = world, world["token"]
    per = personal_context(client, token)
    own = create_account(client, token, per, "Personal")["id"]
    tx = create_tx(client, token, per, own, "-10000")
    res = _propose(client, w, tx["id"])
    assert res.status_code == 404 and error_code(res) == "TRANSACTION_NOT_FOUND"
    _, viewer = make_user("viewer")
    business_tx = create_tx(client, token, w["biz"], w["bank"], "100", category_id=w["sales"])
    res = client.post(
        f"{ACC}/entries/from-transaction/{business_tx['id']}", headers=auth_header(viewer)
    )
    assert res.status_code == 403
