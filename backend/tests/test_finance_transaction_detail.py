"""`GET /finance/contexts/{cid}/transactions/{id}` (P-9): las reglas de acceso del listado
(D-024), los anulados incluidos y el mismo esquema que un ítem del listado."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.accounting_utils import ACC, BANCOS, VENTAS, create_year, load_chart, post
from tests.conftest import auth_header
from tests.finance_utils import (
    API,
    business_context,
    create_account,
    create_tx,
    ok,
    personal_context,
)


def _get(client: TestClient, token: str, cid: str, tx_id: str) -> Any:
    return client.get(f"{API}/contexts/{cid}/transactions/{tx_id}", headers=auth_header(token))


def _listed(client: TestClient, token: str, cid: str, tx_id: str) -> Any:
    rows = ok(
        client.get(
            f"{API}/contexts/{cid}/transactions",
            params={"include_voided": "true"},
            headers=auth_header(token),
        )
    )
    return next(r for r in rows if r["id"] == tx_id)


def test_business_transaction_matches_the_list_item_with_its_entry(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token, 2026)
    biz = business_context(client, owner_token)
    bank = create_account(client, owner_token, biz, "Banco Itaú")
    headers = auth_header(owner_token)
    category = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Ventas", "kind": "income"},
            headers=headers,
        ),
        201,
    )
    for path, code in (
        (f"accounts/{bank['id']}", BANCOS),
        (f"categories/{category['id']}", VENTAS),
    ):
        ok(
            client.patch(
                f"{API}/contexts/{biz}/{path}",
                json={"ledger_account_id": accounts[code]["id"]},
                headers=headers,
            )
        )
    tx = create_tx(client, owner_token, biz, bank["id"], "70000", category_id=category["id"])
    entry = ok(client.post(f"{ACC}/entries/from-transaction/{tx['id']}", headers=headers), 201)
    ok(post(client, owner_token, entry["id"]))

    detail = ok(_get(client, owner_token, biz, tx["id"]))
    assert detail == _listed(client, owner_token, biz, tx["id"])
    assert detail["journal_entry"] == {"id": entry["id"], "number": 1, "status": "posted"}
    # El rol Consulta (finance.read) también lo lee.
    _, viewer = make_user("viewer")
    assert ok(_get(client, viewer, biz, tx["id"])) == detail


def test_voided_transaction_is_returned(client: TestClient, owner_token: str) -> None:
    biz = business_context(client, owner_token)
    bank = create_account(client, owner_token, biz, "Banco")
    tx = create_tx(client, owner_token, biz, bank["id"], "-5000")
    ok(
        client.post(
            f"{API}/contexts/{biz}/transactions/{tx['id']}/void",
            json={"reason": "Duplicado"},
            headers=auth_header(owner_token),
        )
    )
    detail = ok(_get(client, owner_token, biz, tx["id"]))
    assert detail["voided_at"] is not None and detail["void_reason"] == "Duplicado"
    assert detail == _listed(client, owner_token, biz, tx["id"])


def test_personal_transaction_is_visible_only_to_its_owner(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    _, admin = make_user("admin")
    _, other_owner = make_user("owner", "socia@example.com")
    mine = personal_context(client, owner_token)
    cash = create_account(client, owner_token, mine, "Mi caja", kind="cash")
    tx = create_tx(client, owner_token, mine, cash["id"], "-50000")
    detail = ok(_get(client, owner_token, mine, tx["id"]))
    assert detail["journal_entry"] is None
    assert detail == _listed(client, owner_token, mine, tx["id"])
    for token in (admin, other_owner):
        res = _get(client, token, mine, tx["id"])
        assert res.status_code == 404 and res.json()["error"]["code"] == "CONTEXT_NOT_FOUND"


def test_business_requires_finance_read(
    client: TestClient, owner_token: str, make_user: Any, db: Session
) -> None:
    biz = business_context(client, owner_token)
    bank = create_account(client, owner_token, biz, "Banco")
    tx = create_tx(client, owner_token, biz, bank["id"], "1000")
    _, viewer = make_user("viewer")
    db.execute(
        text(
            "DELETE FROM core.role_permissions WHERE role_code = 'viewer'"
            " AND permission_code = 'finance.read'"
        )
    )
    res = _get(client, viewer, biz, tx["id"])
    assert res.status_code == 403
    assert res.json()["error"]["details"]["missing"] == ["finance.read"]


def test_transaction_of_another_context_or_unknown_is_not_found(
    client: TestClient, owner_token: str
) -> None:
    biz = business_context(client, owner_token)
    mine = personal_context(client, owner_token)
    bank = create_account(client, owner_token, biz, "Banco")
    tx = create_tx(client, owner_token, biz, bank["id"], "1000")
    res = _get(client, owner_token, mine, tx["id"])
    assert res.status_code == 404 and res.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"
    res = _get(client, owner_token, biz, "01960000-0000-7000-8000-000000000000")
    assert res.status_code == 404
