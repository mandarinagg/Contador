"""Migración 0006 (D-125): la autorización de la DNIT para la vida útil fiscal de un bien.

Sin diferencias con los modelos, reversible sin datos, y la bajada no pierde una autorización
cargada (mismo criterio que la 0004 y la 0005, D-080).
"""

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.assets_utils import new_asset, setup_books
from tests.conftest import SETUP_BODY
from tests.finance_utils import ok
from tests.tax_utils import fix_today
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture
from tests.test_tax_migration import api  # noqa: F401 - fixture


def _version(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.scalar(text("SELECT version_num FROM alembic_version")))


def test_0006_is_reversible_and_keeps_authorizations(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    command.check(cfg)
    # Sin autorizaciones, baja y sube sin perder nada.
    command.downgrade(cfg, "0005")
    assert _version(engine) == "0005"
    command.upgrade(cfg, "head")
    command.check(cfg)

    fix_today(monkeypatch)
    token = ok(api.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    books = setup_books(api, token)
    new_asset(api, books, fiscal_useful_life_months=96, fiscal_life_authorization="CV 800")
    with pytest.raises(RuntimeError, match=r"1 bien\(es\) tienen una autorización"):
        command.downgrade(cfg, "0005")
    # Sigue en head: la bajada entera se revierte.
    assert _version(engine) == ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        assert conn.scalar(
            text("SELECT fiscal_life_authorization FROM accounting.fixed_assets")
        ) == ("CV 800")
