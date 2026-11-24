from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_DESCRIPTIONS, ROLE_PERMISSIONS
from app.modules.identity.models import PermissionRow, RolePermission
from tests.conftest import STRONG_PASSWORD, auth_header


def test_database_catalog_matches_code(db: Session) -> None:
    assert set(db.scalars(select(PermissionRow.code))) == {p.value for p in PERMISSION_DESCRIPTIONS}
    links = {
        (r, p)
        for r, p in db.execute(select(RolePermission.role_code, RolePermission.permission_code))
    }
    expected = {(r.value, p.value) for r, ps in ROLE_PERMISSIONS.items() for p in ps}
    assert links == expected


def test_owner_creates_and_lists_users(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    make_user("accountant")
    res = client.get("/api/v1/users", headers=auth_header(owner_token))
    assert res.status_code == 200
    roles = {m["user"]["email"]: m["role"] for m in res.json()}
    assert roles == {"owner@example.com": "owner", "accountant@example.com": "accountant"}


def test_duplicate_email_is_rejected(client: TestClient, owner_token: str) -> None:
    res = client.post(
        "/api/v1/users",
        json={
            "email": "Owner@Example.com",
            "full_name": "Otra",
            "password": STRONG_PASSWORD,
            "role": "viewer",
        },
        headers=auth_header(owner_token),
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EMAIL_TAKEN"


def test_viewer_cannot_read_users_or_audit(client: TestClient, make_user: Any) -> None:
    _, token = make_user("viewer")
    for path in ("/api/v1/users", "/api/v1/audit/logs"):
        res = client.get(path, headers=auth_header(token))
        assert res.status_code == 403, path
        assert res.json()["error"]["code"] == "FORBIDDEN"
    assert client.get("/api/v1/organization", headers=auth_header(token)).status_code == 200


def test_accountant_reads_but_cannot_manage(client: TestClient, make_user: Any) -> None:
    _, token = make_user("accountant")
    assert client.get("/api/v1/users", headers=auth_header(token)).status_code == 200
    assert client.get("/api/v1/audit/logs", headers=auth_header(token)).status_code == 200
    res = client.post(
        "/api/v1/users",
        json={
            "email": "x@example.com",
            "full_name": "X Y",
            "password": STRONG_PASSWORD,
            "role": "viewer",
        },
        headers=auth_header(token),
    )
    assert res.status_code == 403
    assert (
        client.patch(
            "/api/v1/organization", json={"legal_name": "Otra"}, headers=auth_header(token)
        ).status_code
        == 403
    )


def test_admin_cannot_create_or_modify_owners(client: TestClient, make_user: Any) -> None:
    _, admin_token = make_user("admin")
    res = client.post(
        "/api/v1/users",
        json={
            "email": "o2@example.com",
            "full_name": "Otro Dueño",
            "password": STRONG_PASSWORD,
            "role": "owner",
        },
        headers=auth_header(admin_token),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "OWNER_ONLY"

    users = client.get("/api/v1/users", headers=auth_header(admin_token)).json()
    owner_id = next(m["user"]["id"] for m in users if m["role"] == "owner")
    res = client.patch(
        f"/api/v1/users/{owner_id}", json={"is_active": False}, headers=auth_header(admin_token)
    )
    assert res.status_code == 403


def test_last_owner_and_self_protection(client: TestClient, owner_token: str) -> None:
    me = client.get("/api/v1/auth/me", headers=auth_header(owner_token)).json()["user"]["id"]
    res = client.patch(
        f"/api/v1/users/{me}", json={"is_active": False}, headers=auth_header(owner_token)
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "SELF_CHANGE_FORBIDDEN"
    res = client.patch(
        f"/api/v1/users/{me}", json={"role": "admin"}, headers=auth_header(owner_token)
    )
    assert res.json()["error"]["code"] == "SELF_CHANGE_FORBIDDEN"


def test_deactivated_user_loses_sessions(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    user_id, token = make_user("accountant")
    res = client.patch(
        f"/api/v1/users/{user_id}", json={"is_active": False}, headers=auth_header(owner_token)
    )
    assert res.status_code == 200
    assert res.json()["user"]["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": "accountant@example.com", "password": STRONG_PASSWORD}
    )
    assert login.status_code == 401


def test_role_change_takes_effect_immediately(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    user_id, token = make_user("accountant")
    assert client.get("/api/v1/users", headers=auth_header(token)).status_code == 200
    client.patch(
        f"/api/v1/users/{user_id}", json={"role": "viewer"}, headers=auth_header(owner_token)
    )
    assert client.get("/api/v1/users", headers=auth_header(token)).status_code == 403


def test_roles_catalog_endpoint(client: TestClient, owner_token: str) -> None:
    roles = client.get("/api/v1/users/roles", headers=auth_header(owner_token)).json()
    assert [r["code"] for r in roles] == ["owner", "admin", "accountant", "viewer"]
