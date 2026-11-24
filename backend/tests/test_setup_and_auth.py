from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.audit.models import SecurityEvent
from app.modules.identity.models import User, UserSession
from tests.conftest import SETUP_BODY, STRONG_PASSWORD, auth_header


def test_health(client: TestClient) -> None:
    res = client.get("/api/v1/system/health")
    assert res.status_code == 200
    assert res.json()["database"] == "ok"
    assert "X-Request-Id" in res.headers


def test_setup_creates_owner_once(client: TestClient) -> None:
    assert client.get("/api/v1/system/setup").json() == {"needs_setup": True}

    res = client.post("/api/v1/system/setup", json=SETUP_BODY)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role"] == "owner"
    assert "users.manage" in body["permissions"]
    assert body["organization"]["legal_form"] == "EAS"

    assert client.get("/api/v1/system/setup").json() == {"needs_setup": False}
    again = client.post("/api/v1/system/setup", json=SETUP_BODY)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_SET_UP"


def test_setup_rejects_weak_password(client: TestClient) -> None:
    body = {**SETUP_BODY, "owner": {**SETUP_BODY["owner"], "password": "corta"}}
    res = client.post("/api/v1/system/setup", json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    body["owner"]["password"] = "solominusculaslarga"
    assert client.post("/api/v1/system/setup", json=body).status_code == 422


def test_password_is_hashed_with_argon2(client: TestClient, owner_token: str, db: Session) -> None:
    user = db.scalar(select(User).where(User.email == "owner@example.com"))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert STRONG_PASSWORD not in user.password_hash


def test_login_me_logout(client: TestClient, owner_token: str) -> None:
    res = client.post(
        "/api/v1/auth/login", json={"email": "OWNER@example.com", "password": STRONG_PASSWORD}
    )
    assert res.status_code == 200, res.text
    token = res.json()["token"]

    me = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@example.com"

    assert client.post("/api/v1/auth/logout", headers=auth_header(token)).status_code == 204
    after = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "SESSION_EXPIRED"


def test_requests_without_token_are_rejected(client: TestClient) -> None:
    for path in ("/api/v1/auth/me", "/api/v1/users", "/api/v1/audit/logs", "/api/v1/organization"):
        res = client.get(path)
        assert res.status_code == 401, path
        assert res.json()["error"]["code"] == "NOT_AUTHENTICATED"
    bogus = client.get("/api/v1/auth/me", headers=auth_header("no-es-un-token"))
    assert bogus.status_code == 401


def test_bad_credentials_do_not_reveal_email(client: TestClient, owner_token: str) -> None:
    wrong_pw = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "x"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nadie@example.com", "password": "x"}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


def test_lockout_after_repeated_failures(client: TestClient, owner_token: str, db: Session) -> None:
    for _ in range(5):
        res = client.post(
            "/api/v1/auth/login", json={"email": "owner@example.com", "password": "mala"}
        )
        assert res.status_code == 401
    locked = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}
    )
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"
    events = db.scalars(select(SecurityEvent.event_type)).all()
    assert "account_locked" in events
    assert "login_blocked" in events


def test_expired_and_idle_sessions_are_rejected(
    client: TestClient, owner_token: str, db: Session
) -> None:
    assert client.get("/api/v1/auth/me", headers=auth_header(owner_token)).status_code == 200
    past = datetime.now(UTC) - timedelta(hours=2)
    db.execute(update(UserSession).values(last_seen_at=past))
    db.commit()
    res = client.get("/api/v1/auth/me", headers=auth_header(owner_token))
    assert res.status_code == 401


def test_change_password_revokes_other_sessions(client: TestClient, owner_token: str) -> None:
    other = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": STRONG_PASSWORD}
    ).json()["token"]
    new_password = "Otra-Clave-Segura-99"
    res = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": STRONG_PASSWORD, "new_password": new_password},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 204, res.text
    assert client.get("/api/v1/auth/me", headers=auth_header(owner_token)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth_header(other)).status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": new_password}
    )
    assert login.status_code == 200


def test_change_password_requires_current(client: TestClient, owner_token: str) -> None:
    res = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "incorrecta", "new_password": "Otra-Clave-Segura-99"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
