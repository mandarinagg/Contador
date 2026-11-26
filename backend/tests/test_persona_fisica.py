"""Persona física (fase M4, D-141): nombres y apellidos, razón social calculada, migración 0011."""

from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.conftest import SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture

PF = {"legal_form": "PERSONA_FISICA", "first_names": "María José", "last_names": "Benítez Duarte"}


def _setup(client: TestClient, organization: dict[str, Any]) -> Any:
    body = {**SETUP_BODY, "organization": organization}
    return client.post("/api/v1/system/setup", json=body)


def test_setup_persona_fisica_computes_legal_name(client: TestClient) -> None:
    res = ok(_setup(client, PF), 201)
    token = res["token"]
    org = ok(client.get("/api/v1/organization", headers=auth_header(token)))
    assert org["legal_name"] == "Benítez Duarte, María José"
    assert org["legal_form"] == "PERSONA_FISICA"
    assert (org["first_names"], org["last_names"]) == ("María José", "Benítez Duarte")
    assert res["organization"]["legal_name"] == "Benítez Duarte, María José"


@pytest.mark.parametrize(
    "organization",
    [
        {"legal_form": "PERSONA_FISICA", "last_names": "Benítez"},
        {"legal_form": "PERSONA_FISICA", "first_names": "María"},
        {**PF, "legal_name": "Otro nombre"},
        {"legal_form": "EAS", "legal_name": "Empresa SA", "first_names": "A", "last_names": "B"},
        {"legal_form": "EAS"},
    ],
)
def test_setup_identity_rules(client: TestClient, organization: dict[str, Any]) -> None:
    assert _setup(client, organization).status_code == 422


def test_create_persona_fisica_and_patch_names(client: TestClient, owner_token: str) -> None:
    h = auth_header(owner_token)
    body = {**PF, "trade_name": "Estudio MJ", "ruc": "4444440", "ruc_check_digit": "3"}
    res = client.post("/api/v1/organizations", json=body, headers=h)
    if res.status_code == 422:  # DV de prueba: calcularlo con el mismo algoritmo
        from app.modules.organizations.ruc import ruc_check_digit

        body["ruc_check_digit"] = str(ruc_check_digit("4444440"))
        res = client.post("/api/v1/organizations", json=body, headers=h)
    org = ok(res, 201)
    assert org["legal_name"] == "Benítez Duarte, María José"
    assert org["trade_name"] == "Estudio MJ"
    sw = ok(client.post("/api/v1/auth/switch", json={"organization_id": org["id"]}, headers=h))
    h2 = auth_header(sw["token"])
    patched = ok(client.patch("/api/v1/organization", json={"first_names": "Ana"}, headers=h2))
    assert patched["legal_name"] == "Benítez Duarte, Ana"
    patched = ok(client.patch("/api/v1/organization", json={"last_names": "Gómez"}, headers=h2))
    assert patched["legal_name"] == "Gómez, Ana"
    # La razón social no se toca a mano ni se cambia de forma jurídica.
    assert (
        client.patch("/api/v1/organization", json={"legal_name": "X Y"}, headers=h2).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/organization", json={"legal_form": "SA"}, headers=h2).status_code
        == 422
    )
    # Y en la lista de organizaciones aparece con su nombre calculado.
    names = [o["legal_name"] for o in ok(client.get("/api/v1/auth/organizations", headers=h2))]
    assert "Gómez, Ana" in names


def test_create_rejects_names_on_company_and_missing_names(
    client: TestClient, owner_token: str
) -> None:
    h = auth_header(owner_token)
    bad = [
        {"legal_name": "Empresa X", "legal_form": "SRL", "first_names": "A", "last_names": "B"},
        {"legal_form": "PERSONA_FISICA", "first_names": "A"},
        {"legal_form": "PERSONA_FISICA", "last_names": "B"},
    ]
    for body in bad:
        assert client.post("/api/v1/organizations", json=body, headers=h).status_code == 422


def test_patch_names_on_company_is_422(client: TestClient, owner_token: str) -> None:
    res = client.patch(
        "/api/v1/organization", json={"first_names": "Ana"}, headers=auth_header(owner_token)
    )
    assert res.status_code == 422


def _exec(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_migration_0011(migration_db: tuple[Config, Engine]) -> None:  # noqa: F811
    cfg, engine = migration_db
    head = ScriptDirectory.from_config(cfg).get_current_head()
    command.upgrade(cfg, "head")
    command.check(cfg)
    command.downgrade(cfg, "0010")
    command.upgrade(cfg, "head")
    # La base rechaza una persona física sin nombres y una empresa con ellos.
    with pytest.raises(Exception, match="person_names"):
        _exec(
            engine,
            "INSERT INTO core.organizations (legal_name, legal_form)"
            " VALUES ('X, Y', 'PERSONA_FISICA')",
        )
    with pytest.raises(Exception, match="person_names"):
        _exec(
            engine,
            "INSERT INTO core.organizations (legal_name, legal_form, first_names, last_names)"
            " VALUES ('Z', 'SA', 'A', 'B')",
        )
    _exec(
        engine,
        "INSERT INTO core.organizations (legal_name, legal_form, first_names, last_names)"
        " VALUES ('B, A', 'PERSONA_FISICA', 'A', 'B')",
    )
    with pytest.raises(RuntimeError, match=r"1 organización\(es\) que son persona física"):
        command.downgrade(cfg, "0010")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == head
    _exec(engine, "DELETE FROM core.organizations")
    command.downgrade(cfg, "0010")
    command.upgrade(cfg, "head")
    command.check(cfg)
