"""Migración 0007 (bot de Marangatu): sin diferencias con los modelos, reversible sin corridas,
y la bajada no pierde el registro de una corrida (D-080; Res. 568/2006, art. 10)."""

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.conftest import SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.marangatu_utils import MARANGATU
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture
from tests.test_tax_migration import api  # noqa: F401 - fixture


def _version(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.scalar(text("SELECT version_num FROM alembic_version")))


def test_0007_is_reversible_and_keeps_runs(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,  # noqa: F811
) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    command.check(cfg)
    command.downgrade(cfg, "0006")
    assert _version(engine) == "0006"
    command.upgrade(cfg, "head")
    command.check(cfg)

    token = ok(api.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    # Con el bot apagado, la corrida queda detenida enseguida: igual es registro.
    run = ok(api.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(token)), 202)
    assert run["stop_code"] == "BOT_OFF"
    with pytest.raises(RuntimeError, match=r"hay 1 corrida\(s\) del bot de Marangatu"):
        command.downgrade(cfg, "0006")
    # Sigue en head: la bajada entera se revierte.
    assert _version(engine) == ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM marangatu.steps")) == 1
