"""Cuentas, movimientos, anulaciones, transferencias, resúmenes y auditoría de finanzas."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def biz(client: TestClient, owner_token: str) -> str:
    return business_context(client, owner_token)


def _h(token: str) -> dict[str, str]:
    return auth_header(token)


# --- Importes (D-026) -------------------------------------------------------------------


def test_amounts_are_strings_and_exact(client: TestClient, owner_token: str, biz: str) -> None:
    usd = create_account(client, owner_token, biz, "Cuenta USD", currency="USD")
    assert usd["balance"] == "0.00" and usd["opening_balance"] == "0.00"
    create_tx(client, owner_token, biz, usd["id"], "0.1")
    create_tx(client, owner_token, biz, usd["id"], "0.2")
    accounts = ok(client.get(f"{API}/contexts/{biz}/accounts", headers=_h(owner_token)))
    assert next(a for a in accounts if a["id"] == usd["id"])["balance"] == "0.30"

    pyg = create_account(client, owner_token, biz, "Caja", currency="PYG", opening_balance="1000")
    assert pyg["opening_balance"] == "1000"
    tx = create_tx(client, owner_token, biz, pyg["id"], "-150000")
    assert tx["amount"] == "-150000" and tx["currency"] == "PYG"


def test_float_and_bad_decimals_are_rejected(
    client: TestClient, owner_token: str, biz: str
) -> None:
    pyg = create_account(client, owner_token, biz, "Caja")
    usd = create_account(client, owner_token, biz, "USD", currency="USD")
    base = {"booked_on": "2026-03-01", "description": "X"}

    def post(account: str, amount: Any) -> Any:
        return client.post(
            f"{API}/contexts/{biz}/transactions",
            json={**base, "account_id": account, "amount": amount},
            headers=_h(owner_token),
        )

    res = post(usd["id"], 0.1)  # número JSON: llega como float, se rechaza
    assert res.status_code == 422
    assert "texto" in res.json()["error"]["details"][0]["message"]
    assert post(pyg["id"], 1500).status_code == 422  # tampoco enteros JSON
    res = post(pyg["id"], "1500.50")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_AMOUNT"
    assert "PYG" in res.json()["error"]["message"]
    assert post(usd["id"], "1.005").status_code == 422
    assert post(pyg["id"], "0").status_code == 422


def test_pyg_with_decimal_point_is_not_thousands(
    client: TestClient, owner_token: str, biz: str
) -> None:
    pyg = create_account(client, owner_token, biz, "Caja")
    res = client.post(
        f"{API}/contexts/{biz}/transactions",
        json={
            "account_id": pyg["id"],
            "booked_on": "2026-03-01",
            "amount": "1.234",
            "description": "X",
        },
        headers=_h(owner_token),
    )
    assert res.status_code == 422
    res = client.post(
        f"{API}/contexts/{biz}/accounts",
        json={
            "name": "Mal saldo",
            "kind": "cash",
            "currency": "PYG",
            "opening_balance": "10.5",
            "opening_date": "2026-01-01",
        },
        headers=_h(owner_token),
    )
    assert res.status_code == 422


# --- Cuentas ----------------------------------------------------------------------------


def test_account_money_fields_locked_once_it_has_transactions(
    client: TestClient, owner_token: str, biz: str
) -> None:
    account = create_account(client, owner_token, biz, "Banco", number_last4="1234")
    path = f"{API}/contexts/{biz}/accounts/{account['id']}"
    # Sin movimientos: se puede corregir moneda y saldo inicial.
    updated = ok(
        client.patch(
            path, json={"currency": "USD", "opening_balance": "10.50"}, headers=_h(owner_token)
        )
    )
    assert updated["currency"] == "USD" and updated["balance"] == "10.50"
    create_tx(client, owner_token, biz, account["id"], "5.25")
    for body in ({"currency": "PYG"}, {"opening_balance": "11.00"}):
        res = client.patch(path, json=body, headers=_h(owner_token))
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "ACCOUNT_HAS_TRANSACTIONS"
    # Lo descriptivo sí.
    renamed = ok(
        client.patch(
            path,
            json={"name": "Banco Itaú", "institution": "Itaú", "number_last4": "9876"},
            headers=_h(owner_token),
        )
    )
    assert renamed["balance"] == "15.75" and renamed["number_last4"] == "9876"
    res = client.patch(path, json={"number_last4": "123456789"}, headers=_h(owner_token))
    assert res.status_code == 422


def test_account_archive_and_names(client: TestClient, owner_token: str, biz: str) -> None:
    account = create_account(client, owner_token, biz, "Banco")
    res = client.post(
        f"{API}/contexts/{biz}/accounts",
        json={"name": "Banco", "kind": "cash", "currency": "PYG", "opening_date": "2026-01-01"},
        headers=_h(owner_token),
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ACCOUNT_NAME_TAKEN"
    path = f"{API}/contexts/{biz}/accounts/{account['id']}"
    archived = ok(client.patch(path, json={"archived": True}, headers=_h(owner_token)))
    assert archived["archived_at"] is not None
    assert ok(client.get(f"{API}/contexts/{biz}/accounts", headers=_h(owner_token))) == []
    listed = ok(
        client.get(
            f"{API}/contexts/{biz}/accounts",
            params={"include_archived": True},
            headers=_h(owner_token),
        )
    )
    assert [a["id"] for a in listed] == [account["id"]]
    res = client.post(
        f"{API}/contexts/{biz}/transactions",
        json={
            "account_id": account["id"],
            "booked_on": "2026-03-01",
            "amount": "100",
            "description": "X",
        },
        headers=_h(owner_token),
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ACCOUNT_ARCHIVED"
    unarchived = ok(client.patch(path, json={"archived": False}, headers=_h(owner_token)))
    assert unarchived["archived_at"] is None


# --- Categorías y contrapartes ----------------------------------------------------------


def test_categories_one_level_and_suggested(client: TestClient, owner_token: str, biz: str) -> None:
    created = ok(
        client.post(f"{API}/contexts/{biz}/categories/suggested", headers=_h(owner_token)), 201
    )
    names = {c["name"] for c in created}
    assert {"Ventas", "Sueldos y cargas sociales", "Impuestos y tasas"} <= names
    again = client.post(f"{API}/contexts/{biz}/categories/suggested", headers=_h(owner_token))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CATEGORIES_EXIST"

    per = personal_context(client, owner_token)
    personal = ok(
        client.post(f"{API}/contexts/{per}/categories/suggested", headers=_h(owner_token)), 201
    )
    assert "Supermercado" in {c["name"] for c in personal}
    assert "Ventas" not in {c["name"] for c in personal}

    parent = next(c for c in created if c["name"] == "Ventas")
    child = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Ventas online", "kind": "income", "parent_id": parent["id"]},
            headers=_h(owner_token),
        ),
        201,
    )
    grandchild = client.post(
        f"{API}/contexts/{biz}/categories",
        json={"name": "Marketplace", "kind": "income", "parent_id": child["id"]},
        headers=_h(owner_token),
    )
    assert grandchild.status_code == 422
    assert grandchild.json()["error"]["code"] == "CATEGORY_TOO_DEEP"
    mismatch = client.post(
        f"{API}/contexts/{biz}/categories",
        json={"name": "Gasto raro", "kind": "expense", "parent_id": parent["id"]},
        headers=_h(owner_token),
    )
    assert mismatch.json()["error"]["code"] == "CATEGORY_KIND_MISMATCH"
    dup = client.post(
        f"{API}/contexts/{biz}/categories",
        json={"name": "Ventas", "kind": "income"},
        headers=_h(owner_token),
    )
    assert dup.status_code == 409
    # Mismo nombre bajo otro padre: permitido.
    ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Otros ingresos", "kind": "income", "parent_id": parent["id"]},
            headers=_h(owner_token),
        ),
        201,
    )


def test_counterparties_ruc_and_search(client: TestClient, owner_token: str, biz: str) -> None:
    good = ok(
        client.post(
            f"{API}/contexts/{biz}/counterparties",
            json={
                "name": "Proveedora del Este SA",
                "kind": "supplier",
                "ruc": "44444401",
                "ruc_check_digit": "7",
            },
            headers=_h(owner_token),
        ),
        201,
    )
    bad_dv = client.post(
        f"{API}/contexts/{biz}/counterparties",
        json={"name": "X", "kind": "supplier", "ruc": "44444401", "ruc_check_digit": "3"},
        headers=_h(owner_token),
    )
    assert bad_dv.status_code == 422
    dup = client.post(
        f"{API}/contexts/{biz}/counterparties",
        json={"name": "Otra", "kind": "supplier", "ruc": "44444401", "ruc_check_digit": "7"},
        headers=_h(owner_token),
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "COUNTERPARTY_RUC_TAKEN"
    ok(
        client.post(
            f"{API}/contexts/{biz}/counterparties",
            json={"name": "ANDE", "kind": "government"},
            headers=_h(owner_token),
        ),
        201,
    )
    by_name = ok(
        client.get(
            f"{API}/contexts/{biz}/counterparties", params={"q": "este"}, headers=_h(owner_token)
        )
    )
    assert [c["id"] for c in by_name] == [good["id"]]
    by_ruc = ok(
        client.get(
            f"{API}/contexts/{biz}/counterparties", params={"q": "4444"}, headers=_h(owner_token)
        )
    )
    assert [c["id"] for c in by_ruc] == [good["id"]]
    wildcard = ok(
        client.get(
            f"{API}/contexts/{biz}/counterparties", params={"q": "%"}, headers=_h(owner_token)
        )
    )
    assert wildcard == []


# --- Movimientos ------------------------------------------------------------------------


def test_list_filters_and_cursor(client: TestClient, owner_token: str, biz: str) -> None:
    account = create_account(client, owner_token, biz, "Banco")
    other = create_account(client, owner_token, biz, "Caja", kind="cash")
    ids = [
        create_tx(
            client, owner_token, biz, account["id"], f"-{i}000", f"2026-03-{i:02d}", f"Pago {i}"
        )["id"]
        for i in range(1, 6)
    ]
    create_tx(client, owner_token, biz, other["id"], "500", "2026-03-03", "Cobro en caja")
    path = f"{API}/contexts/{biz}/transactions"
    first = ok(client.get(path, params={"limit": 2}, headers=_h(owner_token)))
    assert [t["description"] for t in first] == ["Pago 5", "Pago 4"]
    second = ok(
        client.get(path, params={"limit": 2, "before": first[-1]["id"]}, headers=_h(owner_token))
    )
    # Misma fecha: primero el creado después (id uuidv7 descendente).
    assert [t["description"] for t in second] == ["Cobro en caja", "Pago 3"]
    by_account = ok(client.get(path, params={"account_id": other["id"]}, headers=_h(owner_token)))
    assert len(by_account) == 1
    ranged = ok(
        client.get(path, params={"from": "2026-03-02", "to": "2026-03-03"}, headers=_h(owner_token))
    )
    assert len(ranged) == 3
    found = ok(client.get(path, params={"q": "pago 2"}, headers=_h(owner_token)))
    assert [t["id"] for t in found] == [ids[1]]
    assert ok(client.get(path, params={"unreviewed": True}, headers=_h(owner_token))) == []


def test_edit_rules_for_manual_transactions(client: TestClient, owner_token: str, biz: str) -> None:
    account = create_account(client, owner_token, biz, "Banco")
    usd = create_account(client, owner_token, biz, "USD", currency="USD")
    tx = create_tx(client, owner_token, biz, account["id"], "-1000")
    path = f"{API}/contexts/{biz}/transactions/{tx['id']}"
    edited = ok(
        client.patch(
            path,
            json={"amount": "-2000", "booked_on": "2026-03-11", "reviewed": False},
            headers=_h(owner_token),
        )
    )
    assert edited["amount"] == "-2000" and edited["reviewed_at"] is None
    moved = ok(
        client.patch(
            path, json={"account_id": usd["id"], "amount": "-20.50"}, headers=_h(owner_token)
        )
    )
    assert moved["currency"] == "USD" and moved["amount"] == "-20.50"
    res = client.patch(
        path, json={"account_id": account["id"]}, headers=_h(owner_token)
    )  # -20.50 en PYG: decimales
    assert res.status_code == 422


def test_void_excludes_from_balance_and_summary_and_is_audited(
    client: TestClient, owner_token: str, biz: str
) -> None:
    account = create_account(client, owner_token, biz, "Banco", opening_balance="100000")
    keep = create_tx(client, owner_token, biz, account["id"], "-30000", "2026-03-05")
    wrong = create_tx(client, owner_token, biz, account["id"], "-50000", "2026-03-06")
    void_path = f"{API}/contexts/{biz}/transactions/{wrong['id']}/void"

    for reason in ({}, {"reason": ""}, {"reason": " ab "}):
        assert client.post(void_path, json=reason, headers=_h(owner_token)).status_code == 422
    voided = ok(
        client.post(void_path, json={"reason": "Cargado dos veces"}, headers=_h(owner_token))
    )
    assert voided[0]["voided_at"] is not None
    assert voided[0]["void_reason"] == "Cargado dos veces"
    again = client.post(void_path, json={"reason": "Otra vez"}, headers=_h(owner_token))
    assert again.status_code == 409

    accounts = ok(client.get(f"{API}/contexts/{biz}/accounts", headers=_h(owner_token)))
    assert accounts[0]["balance"] == "70000"
    summary = ok(
        client.get(
            f"{API}/contexts/{biz}/summary",
            params={"from": "2026-01-01", "to": "2026-12-31"},
            headers=_h(owner_token),
        )
    )
    assert summary["totals"] == [
        {"currency": "PYG", "income": "0", "expense": "30000", "net": "-30000"}
    ]
    assert summary["balances"][0]["balance"] == "70000"
    listed = ok(client.get(f"{API}/contexts/{biz}/transactions", headers=_h(owner_token)))
    assert [t["id"] for t in listed] == [keep["id"]]
    with_voided = ok(
        client.get(
            f"{API}/contexts/{biz}/transactions",
            params={"include_voided": True},
            headers=_h(owner_token),
        )
    )
    assert len(with_voided) == 2
    res = client.patch(
        f"{API}/contexts/{biz}/transactions/{wrong['id']}",
        json={"description": "Ya no"},
        headers=_h(owner_token),
    )
    assert res.status_code == 409

    entries = audit_entries(client, owner_token, "finance.transaction")
    void_entry = next(e for e in entries if e["action"] == "finance.transaction.voided")
    assert void_entry["entity_id"] == wrong["id"]
    assert void_entry["before"] == {"voided_at": None, "voided_by": None, "void_reason": None}
    assert void_entry["after"]["void_reason"] == "Cargado dos veces"


def test_transfer_creates_two_linked_movements_outside_income_and_expense(
    client: TestClient, owner_token: str, biz: str
) -> None:
    bank = create_account(client, owner_token, biz, "Banco", opening_balance="1000000")
    cash = create_account(client, owner_token, biz, "Caja", kind="cash")
    usd = create_account(client, owner_token, biz, "Dólares", currency="USD")
    category = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Ventas", "kind": "income"},
            headers=_h(owner_token),
        ),
        201,
    )
    create_tx(client, owner_token, biz, bank["id"], "200000", category_id=category["id"])
    body = {
        "from_account_id": bank["id"],
        "to_account_id": cash["id"],
        "booked_on": "2026-03-15",
        "amount_out": "300000",
        "amount_in": "300000",
        "description": "Retiro para caja chica",
    }
    transfer = ok(
        client.post(f"{API}/contexts/{biz}/transfers", json=body, headers=_h(owner_token)), 201
    )
    out, inc = transfer["outgoing"], transfer["incoming"]
    assert out["amount"] == "-300000" and inc["amount"] == "300000"
    assert out["transfer_group_id"] == inc["transfer_group_id"] == transfer["transfer_group_id"]

    # Distinta moneda: cada pata en la suya.
    fx = ok(
        client.post(
            f"{API}/contexts/{biz}/transfers",
            json={**body, "to_account_id": usd["id"], "amount_out": "73000", "amount_in": "10.00"},
            headers=_h(owner_token),
        ),
        201,
    )
    assert fx["incoming"]["currency"] == "USD" and fx["incoming"]["amount"] == "10.00"
    # Misma moneda con importes distintos: rechazado.
    res = client.post(
        f"{API}/contexts/{biz}/transfers",
        json={**body, "amount_in": "299000"},
        headers=_h(owner_token),
    )
    assert res.json()["error"]["code"] == "TRANSFER_AMOUNTS_DIFFER"
    res = client.post(
        f"{API}/contexts/{biz}/transfers",
        json={**body, "to_account_id": bank["id"]},
        headers=_h(owner_token),
    )
    assert res.json()["error"]["code"] == "TRANSFER_SAME_ACCOUNT"
    # Una transferencia no lleva categoría.
    res = client.patch(
        f"{API}/contexts/{biz}/transactions/{out['id']}",
        json={"category_id": category["id"]},
        headers=_h(owner_token),
    )
    assert res.status_code == 409

    summary = ok(
        client.get(
            f"{API}/contexts/{biz}/summary",
            params={"from": "2026-01-01", "to": "2026-12-31"},
            headers=_h(owner_token),
        )
    )
    assert summary["totals"] == [
        {"currency": "PYG", "income": "200000", "expense": "0", "net": "200000"}
    ]
    balances = {b["name"]: b["balance"] for b in summary["balances"]}
    assert balances == {"Banco": "827000", "Caja": "300000", "Dólares": "10.00"}

    # Anular una pata anula la transferencia entera.
    voided = ok(
        client.post(
            f"{API}/contexts/{biz}/transactions/{inc['id']}/void",
            json={"reason": "Se hizo por error"},
            headers=_h(owner_token),
        )
    )
    assert {t["id"] for t in voided} == {out["id"], inc["id"]}


def test_summary_never_mixes_currencies(client: TestClient, owner_token: str, biz: str) -> None:
    pyg = create_account(client, owner_token, biz, "Guaraníes")
    usd = create_account(client, owner_token, biz, "Dólares", currency="USD")
    groceries = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Insumos", "kind": "expense"},
            headers=_h(owner_token),
        ),
        201,
    )
    create_tx(client, owner_token, biz, pyg["id"], "500000", "2026-01-10")
    create_tx(client, owner_token, biz, pyg["id"], "-120000", "2026-02-10")
    create_tx(
        client,
        owner_token,
        biz,
        pyg["id"],
        "-80000",
        "2026-02-11",
        category_id=groceries["id"],
    )
    create_tx(client, owner_token, biz, usd["id"], "100.00", "2026-02-15")
    create_tx(client, owner_token, biz, usd["id"], "-25.50", "2026-02-16")
    summary = ok(
        client.get(
            f"{API}/contexts/{biz}/summary",
            params={"from": "2026-01-01", "to": "2026-02-28"},
            headers=_h(owner_token),
        )
    )
    assert summary["totals"] == [
        {"currency": "PYG", "income": "500000", "expense": "200000", "net": "300000"},
        {"currency": "USD", "income": "100.00", "expense": "25.50", "net": "74.50"},
    ]
    assert summary["by_month"] == [
        {
            "currency": "PYG",
            "month": "2026-01",
            "income": "500000",
            "expense": "0",
            "net": "500000",
        },
        {
            "currency": "PYG",
            "month": "2026-02",
            "income": "0",
            "expense": "200000",
            "net": "-200000",
        },
        {
            "currency": "USD",
            "month": "2026-02",
            "income": "100.00",
            "expense": "25.50",
            "net": "74.50",
        },
    ]
    assert summary["expenses_by_category"] == [
        {
            "currency": "PYG",
            "category_id": None,
            "category_name": "Sin categoría",
            "amount": "120000",
        },
        {
            "currency": "PYG",
            "category_id": groceries["id"],
            "category_name": "Insumos",
            "amount": "80000",
        },
        {
            "currency": "USD",
            "category_id": None,
            "category_name": "Sin categoría",
            "amount": "25.50",
        },
    ]


def test_consolidated_identifies_each_context(
    client: TestClient, owner_token: str, biz: str
) -> None:
    per = personal_context(client, owner_token)
    company = create_account(client, owner_token, biz, "Banco empresa")
    mine = create_account(client, owner_token, per, "Banco personal")
    create_tx(client, owner_token, biz, company["id"], "1000000", "2026-03-01")
    create_tx(client, owner_token, per, mine["id"], "-40000", "2026-03-02")
    # Aporte del dueño a la empresa: dos movimientos independientes, no una transferencia.
    create_tx(client, owner_token, per, mine["id"], "-200000", "2026-03-03", "Aporte a la EAS")
    create_tx(client, owner_token, biz, company["id"], "200000", "2026-03-03", "Aporte del socio")

    result = ok(
        client.get(
            f"{API}/summary/consolidated",
            params={"from": "2026-03-01", "to": "2026-03-31"},
            headers=_h(owner_token),
        )
    )
    by_kind = {c["context"]["kind"]: c for c in result["contexts"]}
    assert set(by_kind) == {"business", "personal"}
    assert by_kind["business"]["context"]["id"] == biz
    assert by_kind["business"]["totals"] == [
        {
            "currency": "PYG",
            "income": "1200000",
            "expense": "0",
            "net": "1200000",
            "balance": "1200000",
        }
    ]
    assert by_kind["personal"]["totals"] == [
        {
            "currency": "PYG",
            "income": "0",
            "expense": "240000",
            "net": "-240000",
            "balance": "-240000",
        }
    ]
    assert set(result) == {"date_from", "date_to", "contexts"}  # sin total global


def test_summary_range_validation(client: TestClient, owner_token: str, biz: str) -> None:
    res = client.get(
        f"{API}/contexts/{biz}/summary",
        params={"from": "2026-05-01", "to": "2026-01-01"},
        headers=_h(owner_token),
    )
    assert res.status_code == 422
    default = ok(client.get(f"{API}/contexts/{biz}/summary", headers=_h(owner_token)))
    assert default["date_from"].endswith("-01")


# --- Auditoría: solo campos cambiados (D-027) -------------------------------------------


def test_each_entity_audits_creation_and_only_changed_fields(
    client: TestClient, owner_token: str, biz: str
) -> None:
    account = create_account(client, owner_token, biz, "Banco")
    category = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Ventas", "kind": "income"},
            headers=_h(owner_token),
        ),
        201,
    )
    counterparty = ok(
        client.post(
            f"{API}/contexts/{biz}/counterparties",
            json={"name": "Cliente", "kind": "customer"},
            headers=_h(owner_token),
        ),
        201,
    )
    tx = create_tx(client, owner_token, biz, account["id"], "1000", description="Cobro")

    cases = [
        ("account", account["id"], {"name": "Banco Nuevo", "kind": "checking"}, "name"),
        ("category", category["id"], {"name": "Ventas locales"}, "name"),
        (
            "counterparty",
            counterparty["id"],
            {"notes": "Paga a 30 días", "kind": "customer"},
            "notes",
        ),
        (
            "transaction",
            tx["id"],
            {"description": "Cobro factura 12", "category_id": category["id"], "amount": "1000"},
            None,
        ),
    ]
    routes = {
        "account": "accounts",
        "category": "categories",
        "counterparty": "counterparties",
        "transaction": "transactions",
    }
    for entity, entity_id, body, _ in cases:
        res = client.patch(
            f"{API}/contexts/{biz}/{routes[entity]}/{entity_id}", json=body, headers=_h(owner_token)
        )
        assert res.status_code == 200, res.text
        entries = [
            e
            for e in audit_entries(client, owner_token, f"finance.{entity}")
            if e["entity_id"] == entity_id
        ]
        actions = sorted(e["action"] for e in entries)
        assert actions == [f"finance.{entity}.created", f"finance.{entity}.updated"], entity
        created = next(e for e in entries if e["action"].endswith(".created"))
        assert created["before"] is None and created["after"]
        updated = next(e for e in entries if e["action"].endswith(".updated"))
        # Solo lo que cambió: "kind" y "amount" se mandaron iguales y no aparecen.
        assert "kind" not in updated["after"] and "amount" not in updated["after"]
        assert set(updated["before"]) == set(updated["after"])

    tx_update = next(
        e
        for e in audit_entries(client, owner_token, "finance.transaction")
        if e["action"] == "finance.transaction.updated"
    )
    assert tx_update["before"] == {"description": "Cobro", "category_id": None}
    assert tx_update["after"] == {"description": "Cobro factura 12", "category_id": category["id"]}

    # Un PATCH sin cambios reales no agrega auditoría.
    before_count = len(audit_entries(client, owner_token, "finance.account"))
    client.patch(
        f"{API}/contexts/{biz}/accounts/{account['id']}",
        json={"name": "Banco Nuevo"},
        headers=_h(owner_token),
    )
    assert len(audit_entries(client, owner_token, "finance.account")) == before_count
