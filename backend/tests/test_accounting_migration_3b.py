"""Migración 0004 (fase 3B): sin diferencias, reversible con datos y con la versión exacta de
los triggers de la 0003 al bajar (spec 3B §5.9; D-080).

Los datos se cargan por la API contra la base propia de la migración, así la bajada
encuentra lo que dejaría una organización real.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_db
from app.main import create_app
from tests.accounting_utils import ACC, BANCOS, CAPITAL, HONORARIOS, posted
from tests.assets_utils import new_asset, run, setup_books
from tests.conftest import SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture

GUARDS = ("journal_entries_guard", "journal_lines_guard")
TABLES_3B = {
    "asset_categories",
    "fixed_assets",
    "depreciation_runs",
    "depreciation_items",
    "asset_year_values",
    "cost_centers",
    "recurring_templates",
    "recurring_template_lines",
    "recurring_generations",
}


def _definitions(engine: Engine) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p"
                " JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'accounting'"
            )
        )
        return {name: definition for name, definition in rows}


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'accounting'"
            )
        )
        return {name for (name,) in rows}


def _version(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.scalar(text("SELECT version_num FROM alembic_version")))


@pytest.fixture
def api(migration_db: tuple[Config, Engine]) -> Iterator[TestClient]:  # noqa: F811
    _, engine = migration_db
    app = create_app()
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db() -> Iterator[Session]:
        session = sessions()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


def _counts(engine: Engine) -> tuple[Any, ...]:
    with engine.connect() as conn:
        return tuple(
            conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM accounting.journal_entries),"
                    " (SELECT count(*) FROM accounting.journal_lines),"
                    " (SELECT count(*) FROM accounting.ledger_accounts),"
                    " (SELECT last_entry_number FROM accounting.fiscal_years)"
                )
            ).one()
        )


def test_downgrade_to_0003_and_upgrade_with_data(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,
) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "0003")
    frozen = _definitions(engine)
    command.upgrade(cfg, "head")
    command.check(cfg)
    assert _tables(engine) >= TABLES_3B
    after = _definitions(engine)
    assert all(after[g] != frozen[g] for g in GUARDS)

    token = ok(api.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    books = setup_books(api, token, (2026,))
    posted(api, token, books["accounts"], "2026-01-05", [(BANCOS, 500, 0), (CAPITAL, 0, 500)])
    new_asset(api, books)
    ok(
        api.post(
            f"{ACC}/cost-centers", json={"code": "ADM", "name": "Adm."}, headers=auth_header(token)
        ),
        201,
    )
    before = _counts(engine)

    command.downgrade(cfg, "0003")
    assert _version(engine) == "0003"
    assert not (TABLES_3B & _tables(engine))
    # Los triggers vuelven exactamente a los de la 0003; las funciones nuevas se van.
    assert _definitions(engine) == frozen
    assert _counts(engine) == before
    with engine.connect() as conn:
        column = conn.scalar(
            text(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = 'accounting'"
                " AND table_name = 'journal_lines' AND column_name = 'cost_center_id'"
            )
        )
    assert column is None

    command.upgrade(cfg, "head")
    command.check(cfg)
    assert _definitions(engine) == after
    assert _counts(engine) == before
    # Después de subir de nuevo, la 3B funciona sobre los datos que quedaron.
    ok(api.post(f"{ACC}/asset-categories/load-proposed", headers=auth_header(token)), 201)


def test_downgrade_refuses_to_lose_3b_entries(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,
) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    token = ok(api.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    books = setup_books(api, token, (2026,))
    headers = auth_header(token)
    center = ok(
        api.post(f"{ACC}/cost-centers", json={"code": "A", "name": "Adm."}, headers=headers), 201
    )
    body = {
        "entry_date": "2026-02-01",
        "description": "Con centro",
        "lines": [
            {
                "account_id": books["accounts"][HONORARIOS]["id"],
                "debit": "10",
                "cost_center_id": center["id"],
            },
            {"account_id": books["accounts"][BANCOS]["id"], "credit": "10"},
        ],
    }
    entry = ok(api.post(f"{ACC}/entries", json=body, headers=headers), 201)
    with pytest.raises(RuntimeError, match=r"hay 0 asientos .* y 1 líneas"):
        command.downgrade(cfg, "0003")
    assert _version(engine) == "0004"
    ok(api.post(f"{ACC}/entries/{entry['id']}/discard", json={"reason": "Prueba"}, headers=headers))
    # Un borrador descartado igual conserva sus líneas con centro: sigue sin poder bajar.
    with pytest.raises(RuntimeError):
        command.downgrade(cfg, "0003")

    new_asset(api, books)
    ok(run(api, books, 2026, 2), 201)
    with pytest.raises(RuntimeError, match="hay 1 asientos"):
        command.downgrade(cfg, "0003")
    assert _version(engine) == "0004"
    assert _tables(engine) >= TABLES_3B
