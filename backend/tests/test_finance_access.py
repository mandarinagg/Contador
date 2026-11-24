"""Contextos y acceso (D-023, D-024, BR-FIN-01, BR-FIN-04)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

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


def test_setup_creates_exactly_one_business_context(
    client: TestClient, owner_token: str, db: Session
) -> None:
    contexts = ok(client.get(f"{API}/contexts", headers=auth_header(owner_token)))
    assert [(c["kind"], c["name"], c["owner_user_id"]) for c in contexts] == [
        ("business", "Empresa", None)
    ]
    count = db.scalar(text("SELECT count(*) FROM finance.contexts WHERE kind = 'business'"))
    assert count == 1


def test_personal_context_is_created_once(client: TestClient, owner_token: str) -> None:
    created = ok(client.post(f"{API}/contexts/personal", headers=auth_header(owner_token)), 201)
    assert created["kind"] == "personal"
    assert created["name"] == "Personal — Dueña de Prueba"
    again = client.post(f"{API}/contexts/personal", headers=auth_header(owner_token))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PERSONAL_CONTEXT_EXISTS"
    kinds = [c["kind"] for c in ok(client.get(f"{API}/contexts", headers=auth_header(owner_token)))]
    assert sorted(kinds) == ["business", "personal"]


def test_personal_context_is_invisible_to_everyone_else(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    """Ni el propietario ni un administrador ven las finanzas personales de otro (404)."""
    _, admin_token = make_user("admin")
    _, other_owner_token = make_user("owner", "socia@example.com")
    owner_personal = personal_context(client, owner_token)
    account = create_account(client, owner_token, owner_personal, "Mi caja", kind="cash")
    tx = create_tx(client, owner_token, owner_personal, account["id"], "-50000")

    for token in (admin_token, other_owner_token):
        headers = auth_header(token)
        for path in (
            f"/contexts/{owner_personal}/accounts",
            f"/contexts/{owner_personal}/transactions",
            f"/contexts/{owner_personal}/summary",
            f"/contexts/{owner_personal}/categories",
        ):
            res = client.get(f"{API}{path}", headers=headers)
            assert res.status_code == 404, path
            assert res.json()["error"]["code"] == "CONTEXT_NOT_FOUND"
        res = client.post(
            f"{API}/contexts/{owner_personal}/transactions/{tx['id']}/void",
            json={"reason": "No es mío"},
            headers=headers,
        )
        assert res.status_code == 404
        visible = ok(client.get(f"{API}/contexts", headers=headers))
        assert owner_personal not in {c["id"] for c in visible}
        consolidated = ok(client.get(f"{API}/summary/consolidated", headers=headers))
        assert owner_personal not in {c["context"]["id"] for c in consolidated["contexts"]}

    # El administrador sí ve la empresa, y el dueño su personal.
    biz = business_context(client, admin_token)
    ok(client.get(f"{API}/contexts/{biz}/accounts", headers=auth_header(admin_token)))
    ok(client.get(f"{API}/contexts/{owner_personal}/accounts", headers=auth_header(owner_token)))


def test_viewer_reads_business_but_writes_only_personal(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    _, viewer_token = make_user("viewer")
    biz = business_context(client, owner_token)
    create_account(client, owner_token, biz, "Banco empresa")
    headers = auth_header(viewer_token)

    accounts = ok(client.get(f"{API}/contexts/{biz}/accounts", headers=headers))
    assert [a["name"] for a in accounts] == ["Banco empresa"]
    res = client.post(
        f"{API}/contexts/{biz}/accounts",
        json={"name": "Otra", "kind": "cash", "currency": "PYG", "opening_date": "2026-01-01"},
        headers=headers,
    )
    assert res.status_code == 403
    assert res.json()["error"]["details"]["missing"] == ["finance.manage"]
    res = client.post(f"{API}/contexts/{biz}/categories/suggested", headers=headers)
    assert res.status_code == 403

    mine = personal_context(client, viewer_token)
    account = create_account(client, viewer_token, mine, "Billetera", kind="digital_wallet")
    create_tx(client, viewer_token, mine, account["id"], "-25000")
    # Y el propietario no lo ve.
    res = client.get(f"{API}/contexts/{mine}/accounts", headers=auth_header(owner_token))
    assert res.status_code == 404


def test_accountant_manages_business_finances(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    _, accountant_token = make_user("accountant")
    biz = business_context(client, owner_token)
    account = create_account(client, accountant_token, biz, "Caja chica", kind="cash")
    create_tx(client, accountant_token, biz, account["id"], "150000")


def test_ids_from_another_context_are_not_found(client: TestClient, owner_token: str) -> None:
    """Por la API, usar una cuenta o categoría de otro contexto es 404 (además de la base)."""
    biz = business_context(client, owner_token)
    per = personal_context(client, owner_token)
    biz_account = create_account(client, owner_token, biz, "Banco empresa")
    per_account = create_account(client, owner_token, per, "Banco personal")
    res = client.post(
        f"{API}/contexts/{per}/transactions",
        json={
            "account_id": biz_account["id"],
            "booked_on": "2026-03-01",
            "amount": "-1000",
            "description": "Mezcla",
        },
        headers=auth_header(owner_token),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
    biz_category = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Ventas", "kind": "income"},
            headers=auth_header(owner_token),
        ),
        201,
    )
    res = client.post(
        f"{API}/contexts/{per}/transactions",
        json={
            "account_id": per_account["id"],
            "booked_on": "2026-03-01",
            "amount": "1000",
            "description": "Mezcla",
            "category_id": biz_category["id"],
        },
        headers=auth_header(owner_token),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CATEGORY_NOT_FOUND"
    res = client.patch(
        f"{API}/contexts/{per}/accounts/{biz_account['id']}",
        json={"name": "Robada"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 404


def test_personal_audit_is_private_to_its_owner(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    """D-027 audita todo; D-024 exige que lo personal no se vea en la auditoría de otros."""
    _, admin_token = make_user("admin")
    per = personal_context(client, owner_token)
    create_account(client, owner_token, per, "Ahorro", kind="savings")
    mine = audit_entries(client, owner_token, "finance.personal.account")
    assert [e["action"] for e in mine] == ["finance.personal.account.created"]

    res = client.get("/api/v1/audit/logs", params={"limit": 200}, headers=auth_header(admin_token))
    entity_types = {e["entity_type"] for e in ok(res)}
    assert not any(t.startswith("finance.personal.") for t in entity_types)
    # La cadena de auditoría sigue íntegra (las entradas existen, solo se ocultan).
    verify = ok(client.get("/api/v1/audit/verify", headers=auth_header(admin_token)))
    assert verify["valid"] is True


def test_unauthenticated_is_rejected(client: TestClient) -> None:
    assert client.get(f"{API}/contexts").status_code == 401
