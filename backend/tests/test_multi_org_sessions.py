"""Varias organizaciones por usuario (fase M2 del plan multiempresa, D-135 a D-139).

La A es la de `owner_token` (setup); la B, la de `other_org`. Cubre la lista de organizaciones,
el cambio de organización (token nuevo, el viejo deja de valer), el ingreso con o sin
organización, el alta de organizaciones, sumar a un usuario existente, el RUC único y las
migraciones 0008 y 0009.
"""

import json
import uuid
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.identity.models import User
from app.modules.organizations.models import Organization
from tests.conftest import SETUP_BODY, STRONG_PASSWORD, OtherOrg, auth_header
from tests.finance_utils import ok
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture

V1 = "/api/v1"
OWNER_A = "owner@example.com"
RUC, RUC_DV = "44444401", "7"


def _login(client: TestClient, email: str, org: object | None = None) -> Any:
    body: dict[str, Any] = {"email": email, "password": STRONG_PASSWORD}
    if org is not None:
        body["organization_id"] = str(org)
    return client.post(f"{V1}/auth/login", json=body)


def _org_a(client: TestClient, token: str) -> str:
    return str(ok(client.get(f"{V1}/auth/me", headers=auth_header(token)))["organization"]["id"])


def _add_existing(client: TestClient, token: str, email: str, role: str) -> Any:
    return client.post(
        f"{V1}/users/existing", json={"email": email, "role": role}, headers=auth_header(token)
    )


def _new_user(client: TestClient, token: str, email: str, role: str) -> str:
    body = {"email": email, "full_name": "Persona Nueva", "password": STRONG_PASSWORD, "role": role}
    return str(
        ok(client.post(f"{V1}/users", json=body, headers=auth_header(token)), 201)["user"]["id"]
    )


def _events(client: TestClient, token: str, event_type: str) -> list[dict[str, Any]]:
    events = ok(client.get(f"{V1}/audit/security-events", headers=auth_header(token)))
    return [e for e in events if e["event_type"] == event_type]


@pytest.fixture
def both(client: TestClient, owner_token: str, other_org: OtherOrg) -> dict[str, str]:
    """La dueña de B también es contadora en A. Su última sesión es la de B (`other_org`)."""
    ok(_add_existing(client, owner_token, other_org.email, "accountant"), 201)
    return {"a": _org_a(client, owner_token), "b": str(other_org.organization_id)}


# --- Lista y elección al ingresar ---------------------------------------------------------


def test_login_lists_memberships_and_opens_last_used(
    client: TestClient, other_org: OtherOrg, both: dict[str, str]
) -> None:
    body = ok(_login(client, other_org.email))
    assert body["organization"]["id"] == both["b"]  # la usada por última vez
    orgs = {o["id"]: o for o in body["organizations"]}
    assert set(orgs) == {both["a"], both["b"]}
    assert orgs[both["a"]]["role"] == "accountant" and not orgs[both["a"]]["is_current"]
    assert orgs[both["b"]]["role"] == "owner" and orgs[both["b"]]["is_current"]
    assert set(orgs[both["a"]]) == {
        "id",
        "legal_name",
        "trade_name",
        "legal_form",
        "ruc",
        "ruc_check_digit",
        "role",
        "is_current",
    }

    chosen = ok(_login(client, other_org.email, both["a"]))
    assert chosen["organization"]["id"] == both["a"]
    assert chosen["role"] == "accountant"
    assert "users.manage" not in chosen["permissions"]
    # Ahora la última usada es la A.
    assert ok(_login(client, other_org.email))["organization"]["id"] == both["a"]

    listed = ok(client.get(f"{V1}/auth/organizations", headers=auth_header(chosen["token"])))
    assert [o["is_current"] for o in listed if o["id"] == both["a"]] == [True]
    assert len(listed) == 2


def test_login_without_history_opens_oldest_membership(
    client: TestClient, owner_token: str, other_org: OtherOrg
) -> None:
    _new_user(client, owner_token, "doble@example.com", "viewer")
    ok(_add_existing(client, other_org.token, "doble@example.com", "admin"), 201)
    body = ok(_login(client, "doble@example.com"))
    assert body["organization"]["id"] == _org_a(client, owner_token)
    assert body["role"] == "viewer"


def test_login_with_foreign_or_unknown_org_is_denied(
    client: TestClient, owner_token: str, other_org: OtherOrg, db: Session
) -> None:
    for org in (other_org.organization_id, uuid.uuid4()):
        res = _login(client, OWNER_A, org)
        assert res.status_code == 403, res.text
        assert res.json()["error"]["code"] == "ORGANIZATION_NOT_AVAILABLE"
    user = db.scalar(select(User).where(User.email == OWNER_A))
    assert user is not None
    db.refresh(user)
    assert user.failed_login_count == 0  # la contraseña era correcta
    failed = _events(client, owner_token, "login_failed")
    assert [e["details"]["reason"] for e in failed] == ["organization_not_available"] * 2
    assert _events(client, other_org.token, "login_failed") == []
    # Mismo trato que una contraseña mala cuando la organización es válida pero la clave no.
    bad = client.post(
        f"{V1}/auth/login",
        json={
            "email": OWNER_A,
            "password": "Otra-Clave-Segura-99",
            "organization_id": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_organizations_requires_session(client: TestClient) -> None:
    assert client.get(f"{V1}/auth/organizations").status_code == 401


# --- Cambio de organización -------------------------------------------------------------


def test_switch_issues_new_token_and_revokes_old(
    client: TestClient, owner_token: str, other_org: OtherOrg, both: dict[str, str]
) -> None:
    old = ok(_login(client, other_org.email, both["a"]))
    res = client.post(
        f"{V1}/auth/switch",
        json={"organization_id": both["b"]},
        headers=auth_header(old["token"]),
    )
    new = ok(res)
    assert new["token"] != old["token"]
    assert new["organization"]["id"] == both["b"] and new["role"] == "owner"
    assert "users.manage" in new["permissions"]
    # El cambio no alarga el vencimiento absoluto (D-139).
    assert new["expires_at"] == old["expires_at"]
    assert [o["id"] for o in new["organizations"] if o["is_current"]] == [both["b"]]

    stale = client.get(f"{V1}/auth/me", headers=auth_header(old["token"]))
    assert stale.status_code == 401
    again = client.post(
        f"{V1}/auth/switch",
        json={"organization_id": both["a"]},
        headers=auth_header(old["token"]),
    )
    assert again.status_code == 401
    me = ok(client.get(f"{V1}/auth/me", headers=auth_header(new["token"])))
    assert me["organization"]["id"] == both["b"]

    # Un evento en cada organización, sin el id de la otra.
    out_a = _events(client, owner_token, "organization_switched")
    in_b = _events(client, new["token"], "organization_switched")
    assert [e["details"] for e in out_a] == [{"direction": "out"}]
    assert [e["details"] for e in in_b] == [{"direction": "in"}]
    assert both["b"] not in json.dumps(out_a) and both["a"] not in json.dumps(in_b)


def test_switch_to_foreign_unknown_or_same_org(
    client: TestClient, owner_token: str, other_org: OtherOrg
) -> None:
    errors = []
    for org in (other_org.organization_id, uuid.uuid4()):
        res = client.post(
            f"{V1}/auth/switch",
            json={"organization_id": str(org)},
            headers=auth_header(owner_token),
        )
        assert res.status_code == 403, res.text
        errors.append(res.json()["error"])
    assert errors[0] == errors[1]  # no revela si la organización existe
    assert errors[0]["code"] == "ORGANIZATION_NOT_AVAILABLE"
    assert len(_events(client, owner_token, "organization_switch_denied")) == 2
    assert _events(client, other_org.token, "organization_switch_denied") == []
    # La sesión sigue valiendo.
    assert client.get(f"{V1}/auth/me", headers=auth_header(owner_token)).status_code == 200

    same = client.post(
        f"{V1}/auth/switch",
        json={"organization_id": _org_a(client, owner_token)},
        headers=auth_header(owner_token),
    )
    assert same.status_code == 409
    assert same.json()["error"]["code"] == "SAME_ORGANIZATION"


def test_deactivation_is_per_organization(
    client: TestClient, owner_token: str, other_org: OtherOrg, both: dict[str, str]
) -> None:
    in_a = ok(_login(client, other_org.email, both["a"]))
    in_b = ok(_login(client, other_org.email, both["b"]))
    # A desactiva a la dueña de B en A: en B sigue entera.
    res = client.patch(
        f"{V1}/users/{other_org.user_id}",
        json={"is_active": False},
        headers=auth_header(owner_token),
    )
    assert ok(res)["user"]["is_active"] is False
    assert client.get(f"{V1}/auth/me", headers=auth_header(in_a["token"])).status_code == 401
    assert client.get(f"{V1}/auth/me", headers=auth_header(in_b["token"])).status_code == 200

    denied = client.post(
        f"{V1}/auth/switch",
        json={"organization_id": both["a"]},
        headers=auth_header(in_b["token"]),
    )
    assert denied.status_code == 403
    assert _login(client, other_org.email, both["a"]).status_code == 403
    body = ok(_login(client, other_org.email))
    assert body["organization"]["id"] == both["b"]
    assert [o["id"] for o in body["organizations"]] == [both["b"]]

    # En la B la ven activa y propietaria.
    members = ok(client.get(f"{V1}/users", headers=auth_header(body["token"])))
    mine = next(m for m in members if m["user"]["email"] == other_org.email)
    assert mine["user"]["is_active"] is True and mine["role"] == "owner"


# --- Alta de organizaciones -------------------------------------------------------------


def test_owner_creates_organization(client: TestClient, owner_token: str) -> None:
    res = client.post(
        f"{V1}/organizations",
        json={
            "legal_name": "Tercera Empresa SA",
            "legal_form": "SA",
            "ruc": RUC,
            "ruc_check_digit": RUC_DV,
        },
        headers=auth_header(owner_token),
    )
    created = ok(res, 201)
    assert created["legal_form"] == "SA" and created["ruc"] == RUC
    # La sesión no cambia; la nueva aparece en la lista con rol de propietario.
    assert _org_a(client, owner_token) != created["id"]
    listed = ok(client.get(f"{V1}/auth/organizations", headers=auth_header(owner_token)))
    assert {o["id"]: o["role"] for o in listed}[created["id"]] == "owner"

    switched = ok(
        client.post(
            f"{V1}/auth/switch",
            json={"organization_id": created["id"]},
            headers=auth_header(owner_token),
        )
    )
    token = switched["token"]
    logs = ok(client.get(f"{V1}/audit/logs", headers=auth_header(token)))
    assert [entry["action"] for entry in logs] == ["organization.created"]
    assert logs[0]["after"]["legal_name"] == "Tercera Empresa SA"
    contexts = ok(client.get(f"{V1}/finance/contexts", headers=auth_header(token)))
    assert [c["kind"] for c in contexts] == ["business"]
    members = ok(client.get(f"{V1}/users", headers=auth_header(token)))
    assert [(m["user"]["email"], m["role"]) for m in members] == [(OWNER_A, "owner")]


@pytest.mark.parametrize("role", ["admin", "accountant", "viewer"])
def test_only_owners_create_organizations(client: TestClient, make_user: Any, role: str) -> None:
    _, token = make_user(role)
    res = client.post(
        f"{V1}/organizations",
        json={"legal_name": "No Corresponde SRL", "legal_form": "SRL"},
        headers=auth_header(token),
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "OWNER_ONLY"


def test_owner_elsewhere_can_create_from_any_session(
    client: TestClient, other_org: OtherOrg, both: dict[str, str]
) -> None:
    # Es contadora en A, pero propietaria de B: puede, aunque la sesión sea la de A.
    token = ok(_login(client, other_org.email, both["a"]))["token"]
    res = client.post(
        f"{V1}/organizations",
        json={"legal_name": "Cuarta Empresa EAS", "legal_form": "EAS"},
        headers=auth_header(token),
    )
    ok(res, 201)


def test_setup_still_only_with_empty_database(client: TestClient, owner_token: str) -> None:
    res = client.post(f"{V1}/system/setup", json=SETUP_BODY)
    assert res.status_code == 409


def test_setup_response_lists_its_organization(client: TestClient) -> None:
    body = ok(client.post(f"{V1}/system/setup", json=SETUP_BODY), 201)
    assert [(o["id"], o["is_current"]) for o in body["organizations"]] == [
        (body["organization"]["id"], True)
    ]


# --- Sumar a un usuario existente -------------------------------------------------------


def test_add_existing_user_keeps_password_and_other_orgs(
    client: TestClient, owner_token: str, other_org: OtherOrg, make_user: Any, db: Session
) -> None:
    user_id, _ = make_user("accountant")
    user = db.get_one(User, uuid.UUID(user_id))
    password_hash = user.password_hash

    res = _add_existing(client, other_org.token, "Accountant@Example.com", "viewer")
    added = ok(res, 201)
    assert added["user"]["id"] == user_id and added["role"] == "viewer"
    assert set(added) == {"user", "role", "member_since"}  # nada de sus otras organizaciones
    assert "Empresa de Prueba" not in res.text

    db.refresh(user)
    assert user.password_hash == password_hash
    # En A sigue de contadora; en B entra de consulta con la misma contraseña.
    a_members = ok(client.get(f"{V1}/users", headers=auth_header(owner_token)))
    assert {m["user"]["email"]: m["role"] for m in a_members}["accountant@example.com"] == (
        "accountant"
    )
    in_b = ok(_login(client, "accountant@example.com", other_org.organization_id))
    assert in_b["role"] == "viewer"

    b_logs = ok(client.get(f"{V1}/audit/logs", headers=auth_header(other_org.token)))
    assert [entry["action"] for entry in b_logs if entry["action"] == "user.added"] == [
        "user.added"
    ]
    a_logs = ok(client.get(f"{V1}/audit/logs", headers=auth_header(owner_token)))
    assert "user.added" not in {entry["action"] for entry in a_logs}

    again = _add_existing(client, other_org.token, "accountant@example.com", "admin")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_MEMBER"


def test_add_existing_user_errors(client: TestClient, other_org: OtherOrg) -> None:
    missing = _add_existing(client, other_org.token, "nadie@example.com", "viewer")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "USER_NOT_FOUND"

    # Un administrador de B no puede sumar a nadie como propietario.
    _new_user(client, other_org.token, "admin-b@example.com", "admin")
    admin_b = ok(_login(client, "admin-b@example.com"))["token"]
    res = _add_existing(client, admin_b, OWNER_A, "owner")
    assert res.status_code == 403 and res.json()["error"]["code"] == "OWNER_ONLY"
    ok(_add_existing(client, admin_b, OWNER_A, "accountant"), 201)

    # Crear con un email que ya existe sigue dando EMAIL_TAKEN (no toca al usuario).
    body = {"email": OWNER_A, "full_name": "Otra", "password": STRONG_PASSWORD, "role": "viewer"}
    taken = client.post(f"{V1}/users", json=body, headers=auth_header(other_org.token))
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "EMAIL_TAKEN"

    # Ver y administrar usuarios requiere permiso.
    _new_user(client, other_org.token, "viewer-b@example.com", "viewer")
    viewer_b = ok(_login(client, "viewer-b@example.com"))["token"]
    assert _add_existing(client, viewer_b, "admin-b@example.com", "viewer").status_code == 403


def test_other_org_cannot_deactivate_a_member_of_a(
    client: TestClient, owner_token: str, other_org: OtherOrg
) -> None:
    # La única propietaria de A no es de B: B no la ve ni la toca.
    me = ok(client.get(f"{V1}/auth/me", headers=auth_header(owner_token)))["user"]["id"]
    res = client.patch(
        f"{V1}/users/{me}", json={"is_active": False}, headers=auth_header(other_org.token)
    )
    assert res.status_code == 404
    assert client.get(f"{V1}/auth/me", headers=auth_header(owner_token)).status_code == 200


# --- RUC único --------------------------------------------------------------------------


def test_ruc_is_unique_across_organizations(
    client: TestClient, owner_token: str, other_org: OtherOrg, db: Session
) -> None:
    pair = {"ruc": RUC, "ruc_check_digit": RUC_DV}
    ok(client.patch(f"{V1}/organization", json=pair, headers=auth_header(owner_token)))
    # Repetir el propio RUC no es choque.
    same = {**pair, "legal_name": "Empresa de Prueba EAS"}
    ok(client.patch(f"{V1}/organization", json=same, headers=auth_header(owner_token)))

    patched = client.patch(f"{V1}/organization", json=pair, headers=auth_header(other_org.token))
    assert patched.status_code == 409 and patched.json()["error"]["code"] == "RUC_TAKEN"
    created = client.post(
        f"{V1}/organizations",
        json={"legal_name": "Copia SA", "legal_form": "SA", **pair},
        headers=auth_header(owner_token),
    )
    assert created.status_code == 409 and created.json()["error"]["code"] == "RUC_TAKEN"
    b = db.get_one(Organization, other_org.organization_id)
    db.refresh(b)
    assert b.ruc is None

    # Sin RUC no chocan; la base también lo exige (índice único parcial, 0008).
    ok(
        client.post(
            f"{V1}/organizations",
            json={"legal_name": "Sin RUC SA", "legal_form": "SA"},
            headers=auth_header(owner_token),
        ),
        201,
    )
    with pytest.raises(IntegrityError, match="uq_organizations_ruc"), db.begin_nested():
        db.add(Organization(legal_name="Directa", legal_form="SA", ruc=RUC, ruc_check_digit="7"))
        db.flush()


# --- Migraciones 0008 y 0009 ------------------------------------------------------------


def _version(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.scalar(text("SELECT version_num FROM alembic_version")))


def _exec(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_migrations_0008_0009(migration_db: tuple[Config, Engine]) -> None:  # noqa: F811
    cfg, engine = migration_db
    head = ScriptDirectory.from_config(cfg).get_current_head()
    command.upgrade(cfg, "head")
    command.check(cfg)
    command.downgrade(cfg, "0007")
    assert _version(engine) == "0007"

    # 0008: con RUC repetidos, la subida se niega y deja la base como estaba.
    _exec(
        engine,
        "INSERT INTO core.organizations (legal_name, legal_form, ruc, ruc_check_digit) VALUES"
        " ('Uno', 'EAS', '44444401', '7'), ('Dos', 'SA', '44444401', '7'),"
        " ('Tres', 'SA', NULL, NULL), ('Cuatro', 'SA', NULL, NULL)",
    )
    with pytest.raises(RuntimeError, match=r"RUC repetidos.*44444401 \(2 organizaciones\)"):
        command.upgrade(cfg, "0008")
    assert _version(engine) == "0007"
    _exec(
        engine,
        "UPDATE core.organizations SET ruc = NULL, ruc_check_digit = NULL WHERE legal_name = 'Dos'",
    )
    command.upgrade(cfg, "0008")

    # 0009: el desactivado de antes queda desactivado en su organización; la cuenta, activa.
    _exec(
        engine,
        "INSERT INTO core.users (email, full_name, password_hash, is_active) VALUES"
        " ('baja@example.com', 'Baja', 'x', false), ('alta@example.com', 'Alta', 'x', true)",
    )
    _exec(
        engine,
        "INSERT INTO core.organization_members (organization_id, user_id, role_code)"
        " SELECT o.id, u.id, 'viewer' FROM core.organizations o, core.users u"
        " WHERE o.legal_name IN ('Uno', 'Dos')",
    )
    command.upgrade(cfg, "head")
    assert _version(engine) == head
    command.check(cfg)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT u.email, u.is_active, bool_and(m.is_active), bool_or(m.is_active)"
                " FROM core.users u JOIN core.organization_members m ON m.user_id = u.id"
                " GROUP BY u.email, u.is_active ORDER BY u.email"
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        ("alta@example.com", True, True, True),
        ("baja@example.com", True, False, False),
    ]

    # Activa en una y desactivada en otra: la bajada de la 0009 se niega.
    _exec(
        engine,
        "UPDATE core.organization_members m SET is_active = true FROM core.organizations o"
        " WHERE o.id = m.organization_id AND o.legal_name = 'Uno'"
        " AND m.user_id = (SELECT id FROM core.users WHERE email = 'baja@example.com')",
    )
    with pytest.raises(RuntimeError, match=r"1 usuario\(s\) activos en una organización"):
        command.downgrade(cfg, "0008")
    assert _version(engine) == head
    _exec(
        engine,
        "UPDATE core.organization_members SET is_active = false"
        " WHERE user_id = (SELECT id FROM core.users WHERE email = 'baja@example.com')",
    )
    command.downgrade(cfg, "0007")
    assert _version(engine) == "0007"
    with engine.connect() as conn:
        users = dict(conn.execute(text("SELECT email, is_active FROM core.users")).all())
        index = conn.scalar(
            text("SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_organizations_ruc'")
        )
    assert users == {"baja@example.com": False, "alta@example.com": True}
    assert index == 0
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_failed_login_of_user_deactivated_everywhere_stays_in_its_org(
    client: TestClient, owner_token: str, make_user: Any, other_org: OtherOrg
) -> None:
    user_id, _ = make_user("viewer")
    res = client.patch(
        f"{V1}/users/{user_id}", json={"is_active": False}, headers=auth_header(owner_token)
    )
    ok(res)
    assert _login(client, "viewer@example.com").status_code == 401
    reasons = [e["details"]["reason"] for e in _events(client, owner_token, "login_failed")]
    assert reasons == ["no_membership"]
    assert _events(client, other_org.token, "login_failed") == []
