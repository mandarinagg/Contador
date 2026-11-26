"""Pruebas contra PostgreSQL real (sin mocks de base).

Al inicio se crea la base de pruebas si falta y se le aplican las migraciones. Cada
prueba corre dentro de una transacción que se revierte al final: los `commit()` del
código pasan a ser SAVEPOINTs, así que las pruebas no se pisan entre sí.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

os.environ["CONTADOR_ENV"] = "test"
os.environ.setdefault("CONTADOR_LOG_LEVEL", "WARNING")
# Bot de Marangatu: navegador sin ventana y almacén de credenciales de prueba (un archivo por
# prueba, `CONTADOR_TEST_KEYRING_FILE`), nunca el del sistema. Lo hereda el trabajador.
os.environ.setdefault("CONTADOR_MARANGATU_HEADLESS", "true")
os.environ["PYTHON_KEYRING_BACKEND"] = "tests.marangatu_fake.keyring_file.FileKeyring"
os.environ.pop("CONTADOR_TEST_KEYRING_FILE", None)

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.permissions import Role
from app.core.security import hash_password
from app.main import create_app
from app.modules.finance.service import create_business_context
from app.modules.identity.models import User
from app.modules.organizations.models import Organization, OrganizationMember

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRONG_PASSWORD = "Clave-Segura-2026"


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = get_settings().test_database_url
    _ensure_database(url)
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()


@pytest.fixture
def client(connection: Connection) -> Iterator[TestClient]:
    app = create_app()

    def _get_db() -> Iterator[Session]:
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c


SETUP_BODY: dict[str, Any] = {
    "organization": {"legal_name": "Empresa de Prueba EAS", "legal_form": "EAS"},
    "owner": {
        "full_name": "Dueña de Prueba",
        "email": "owner@example.com",
        "password": STRONG_PASSWORD,
    },
}


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner_token(client: TestClient) -> str:
    res = client.post("/api/v1/system/setup", json=SETUP_BODY)
    assert res.status_code == 201, res.text
    return str(res.json()["token"])


@pytest.fixture
def make_user(client: TestClient, owner_token: str) -> Any:
    """Crea un usuario con el rol indicado y devuelve (id, token)."""

    def _make(role: str, email: str | None = None) -> tuple[str, str]:
        email = email or f"{role}@example.com"
        res = client.post(
            "/api/v1/users",
            json={
                "email": email,
                "full_name": f"Usuario {role}",
                "password": STRONG_PASSWORD,
                "role": role,
            },
            headers=auth_header(owner_token),
        )
        assert res.status_code == 201, res.text
        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
        )
        assert login.status_code == 200, login.text
        return str(res.json()["user"]["id"]), str(login.json()["token"])

    return _make


@dataclass(frozen=True)
class OtherOrg:
    """Segunda organización, con su propietario, su contexto empresarial y su sesión."""

    organization_id: uuid.UUID
    user_id: uuid.UUID
    token: str
    business_context_id: str
    email: str


@pytest.fixture
def other_org(client: TestClient, db: Session, owner_token: str) -> OtherOrg:
    """Organización B, creada directo en la base (la API solo crea una, con `/system/setup`) y
    con sesión por el inicio de sesión normal. La A es la de `owner_token`."""
    org = Organization(legal_name="Otra Empresa SRL", legal_form="SRL")
    email = "duena-b@example.com"
    user = User(email=email, full_name="Dueña de B", password_hash=hash_password(STRONG_PASSWORD))
    db.add_all([org, user])
    db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role_code=Role.OWNER))
    business = create_business_context(db, org.id)
    db.commit()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert login.status_code == 200, login.text
    assert login.json()["organization"]["id"] == str(org.id)
    return OtherOrg(
        organization_id=org.id,
        user_id=user.id,
        token=str(login.json()["token"]),
        business_context_id=str(business.id),
        email=email,
    )
