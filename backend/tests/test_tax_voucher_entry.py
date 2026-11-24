"""Asiento propuesto desde un comprobante (spec fase 4 §5.8; D-091, BR-TAX-10)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.accounting_utils import (
    ACC,
    BANCOS,
    CAJA,
    HONORARIOS,
    VENTAS,
    create_year,
    load_chart,
)
from tests.conftest import auth_header
from tests.finance_utils import API, business_context, create_account, create_tx, ok
from tests.tax_utils import TAX, create_voucher, dv, rejected, setup_tax

SALE = {"direction": "sale", "counterparty_ruc": "80000011"}


@pytest.fixture
def world(client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    setup_tax(client, owner_token, monkeypatch)
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token, 2026)
    biz = business_context(client, owner_token)
    bank = create_account(client, owner_token, biz, "Banco")["id"]
    ok(
        client.patch(
            f"{API}/contexts/{biz}/accounts/{bank}",
            json={"ledger_account_id": accounts[BANCOS]["id"]},
            headers=auth_header(owner_token),
        )
    )
    return {"token": owner_token, "accounts": accounts, "biz": biz, "bank": bank}


def _propose(client: TestClient, w: dict[str, Any], voucher_id: str, **body: Any) -> Any:
    return client.post(
        f"{TAX}/vouchers/{voucher_id}/propose-entry", json=body, headers=auth_header(w["token"])
    )


def _lines(entry: dict[str, Any]) -> list[tuple[str, str, str]]:
    return sorted((ln["account_code"], ln["debit"], ln["credit"]) for ln in entry["lines"])


def _id(w: dict[str, Any], code: str) -> str:
    return str(w["accounts"][code]["id"])


def test_purchase_on_credit_goes_to_suppliers_with_vat_credit(
    client: TestClient, world: dict[str, Any]
) -> None:
    voucher = create_voucher(
        client, world["token"], condition="credit", taxed_10="110000", taxed_5="21000"
    )
    entry = ok(_propose(client, world, voucher["id"], account_id=_id(world, HONORARIOS)), 201)
    assert entry["status"] == "draft" and entry["kind"] == "manual"
    assert _lines(entry) == sorted(
        [
            (HONORARIOS, "120000", "0"),
            ("1.01.03.05.03.01", "10000", "0"),
            ("1.01.03.05.03.02", "1000", "0"),
            ("2.01.01.01", "0", "131000"),
        ]
    )
    detail = ok(client.get(f"{TAX}/vouchers/{voucher['id']}", headers=auth_header(world["token"])))
    assert detail["journal_entry_id"] == entry["id"] and detail["journal_entry_status"] == "draft"
    res = _propose(client, world, voucher["id"], account_id=_id(world, HONORARIOS))
    assert res.status_code == 409 and res.json()["error"]["code"] == "VOUCHER_HAS_ENTRY"


def test_cash_sale_needs_a_counterpart_and_credit_note_reverses(
    client: TestClient, world: dict[str, Any]
) -> None:
    t = world["token"]
    sale = create_voucher(client, t, **SALE, counterparty_ruc_dv=dv("80000011"), taxed_10="220000")
    res = _propose(client, world, sale["id"], account_id=_id(world, VENTAS))
    assert res.status_code == 422 and res.json()["error"]["code"] == "COUNTERPART_ACCOUNT_REQUIRED"
    res = _propose(
        client,
        world,
        sale["id"],
        account_id=_id(world, HONORARIOS),
        counterpart_account_id=_id(world, CAJA),
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "LEDGER_ACCOUNT_KIND_MISMATCH"
    entry = ok(
        _propose(
            client,
            world,
            sale["id"],
            account_id=_id(world, VENTAS),
            counterpart_account_id=_id(world, CAJA),
        ),
        201,
    )
    assert _lines(entry) == sorted(
        [(CAJA, "220000", "0"), (VENTAS, "0", "200000"), ("2.01.03.01.02.01", "0", "20000")]
    )
    note = create_voucher(
        client,
        t,
        **SALE,
        counterparty_ruc_dv=dv("80000011"),
        voucher_type="credit_note",
        number="001-001-0000002",
        taxed_10="22000",
        related_voucher_id=sale["id"],
        issued_on="2026-10-20",
    )
    reversed_ = ok(
        _propose(
            client,
            world,
            note["id"],
            account_id=_id(world, VENTAS),
            counterpart_account_id=_id(world, CAJA),
        ),
        201,
    )
    assert _lines(reversed_) == sorted(
        [(CAJA, "0", "22000"), (VENTAS, "20000", "0"), ("2.01.03.01.02.01", "2000", "0")]
    )


def test_purchase_not_imputing_vat_puts_it_into_cost(
    client: TestClient, world: dict[str, Any]
) -> None:
    voucher = create_voucher(client, world["token"], imputes_vat=False, imputes_ire=True)
    entry = ok(
        _propose(
            client,
            world,
            voucher["id"],
            account_id=_id(world, HONORARIOS),
            counterpart_account_id=_id(world, CAJA),
        ),
        201,
    )
    assert _lines(entry) == sorted([(HONORARIOS, "110000", "0"), (CAJA, "0", "110000")])


def test_linked_transaction_uses_its_bank_and_one_live_entry_per_fact(
    client: TestClient, world: dict[str, Any], db: Session
) -> None:
    t = world["token"]
    tx = create_tx(client, t, world["biz"], world["bank"], "-110000", booked_on="2026-10-15")
    voucher = create_voucher(client, t, transaction_id=tx["id"])
    entry = ok(_propose(client, world, voucher["id"], account_id=_id(world, HONORARIOS)), 201)
    assert entry["kind"] == "finance"
    assert (BANCOS, "0", "110000") in _lines(entry)
    # La contabilidad no propone otro asiento para el mismo movimiento.
    res = client.post(f"{ACC}/entries/from-transaction/{tx['id']}", headers=auth_header(t))
    assert res.status_code == 409
    assert res.json()["error"]["code"] in ("TRANSACTION_VOUCHER_HAS_ENTRY", "TRANSACTION_HAS_ENTRY")
    # Y la base lo impide aunque el servicio fallara.
    rejected(
        db,
        "INSERT INTO accounting.journal_entries (organization_id, fiscal_year_id, entry_date, kind,"
        " description, source_transaction_id, source_context_id, source_context_kind, created_by)"
        " SELECT organization_id, fiscal_year_id, entry_date, kind, 'otro', source_transaction_id,"
        " source_context_id, source_context_kind, created_by"
        " FROM accounting.journal_entries WHERE id = :id",
        {"id": entry["id"]},
        "trg_journal_entries_voucher_has_entry",
    )
    # Si el movimiento ya tenía asiento propio, el comprobante no propone otro.
    rent = ok(
        client.post(
            f"{API}/contexts/{world['biz']}/categories",
            json={"name": "Honorarios", "kind": "expense"},
            headers=auth_header(t),
        ),
        201,
    )
    ok(
        client.patch(
            f"{API}/contexts/{world['biz']}/categories/{rent['id']}",
            json={"ledger_account_id": _id(world, HONORARIOS)},
            headers=auth_header(t),
        )
    )
    tx2 = create_tx(
        client,
        t,
        world["biz"],
        world["bank"],
        "-55000",
        booked_on="2026-10-16",
        category_id=rent["id"],
    )
    ok(client.post(f"{ACC}/entries/from-transaction/{tx2['id']}", headers=auth_header(t)), 201)
    other = create_voucher(
        client, t, number="001-001-0000009", taxed_10="55000", transaction_id=tx2["id"]
    )
    res = _propose(client, world, other["id"], account_id=_id(world, HONORARIOS))
    assert res.status_code == 409 and res.json()["error"]["code"] == "VOUCHER_TRANSACTION_HAS_ENTRY"
    # Un comprobante con asiento propio tampoco se vincula por SQL a ese movimiento.
    manual = create_voucher(client, t, number="001-001-0000010", condition="credit")
    ok(_propose(client, world, manual["id"], account_id=_id(world, HONORARIOS)), 201)
    rejected(
        db,
        "UPDATE tax.vouchers SET transaction_id = :tx WHERE id = :id",
        {"tx": tx2["id"], "id": manual["id"]},
        "trg_vouchers_transaction_has_entry",
    )


def test_needs_accounting_permission(
    client: TestClient, world: dict[str, Any], make_user: Any
) -> None:
    voucher = create_voucher(client, world["token"], condition="credit")
    _, viewer = make_user("viewer")
    res = client.post(
        f"{TAX}/vouchers/{voucher['id']}/propose-entry",
        json={"account_id": _id(world, HONORARIOS)},
        headers=auth_header(viewer),
    )
    assert res.status_code == 403
