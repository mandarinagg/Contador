"""Corridas de depreciación y generación de recurrentes concurrentes, con conexiones reales
(spec 3B §5.2 y §5.6; D-058, D-061).

Igual que `test_accounting_numbering_concurrency.py`: base propia, un pedido HTTP por hilo y
una sesión por pedido. Otra conexión retiene la fila del ejercicio (el primer candado de
D-049, que toman la corrida y la generación) hasta que todos los pedidos están bloqueados, y
recién entonces la suelta: compiten de verdad por el mismo período.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_db
from app.main import create_app
from tests.accounting_utils import ACC, ALQUILERES, BANCOS
from tests.assets_utils import new_asset, period_id, setup_books
from tests.conftest import BACKEND_DIR, SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.test_accounting_numbering_concurrency import WAIT_SECONDS, _blocked_sessions, _wait_until

PARALLEL = 6


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    base = make_url(get_settings().test_database_url)
    name = f"{base.database}_3b_conc"
    url = base.set(database=name)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config(f"{BACKEND_DIR}/alembic.ini")
    cfg.set_main_option("script_location", f"{BACKEND_DIR}/migrations")
    cfg.attributes["url"] = url.render_as_string(hide_password=False)
    engine = create_engine(url, pool_size=PARALLEL + 4)
    try:
        command.upgrade(cfg, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="module")
def books(engine: Engine) -> dict[str, Any]:
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
    client = TestClient(app)
    token = ok(client.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    books = setup_books(client, token, (2026,))
    books["app"] = app
    new_asset(client, books)
    ok(
        client.post(
            f"{ACC}/recurring",
            json={
                "description": "Alquiler",
                "day_of_month": 10,
                "start_date": "2026-01-01",
                "lines": [
                    {"account_id": books["accounts"][ALQUILERES]["id"], "debit": "100"},
                    {"account_id": books["accounts"][BANCOS]["id"], "credit": "100"},
                ],
            },
            headers=auth_header(token),
        ),
        201,
    )
    return books


def _race(
    books: dict[str, Any], engine: Engine, path: str, body: dict[str, Any]
) -> list[tuple[int, Any]]:
    blocker = engine.connect()
    try:
        blocker.execute(
            text("SELECT 1 FROM accounting.fiscal_years WHERE id = :id FOR UPDATE"),
            {"id": books["years"][2026]["id"]},
        )
        barrier = Barrier(PARALLEL + 1)

        def _call() -> tuple[int, Any]:
            client = TestClient(books["app"])
            barrier.wait(timeout=WAIT_SECONDS)
            res = client.post(f"{ACC}{path}", json=body, headers=auth_header(books["token"]))
            return res.status_code, res.json()

        pool = ThreadPoolExecutor(max_workers=PARALLEL)
        futures = [pool.submit(_call) for _ in range(PARALLEL)]
        barrier.wait(timeout=WAIT_SECONDS)
        _wait_until(
            lambda: _blocked_sessions(engine) >= PARALLEL,
            "los pedidos no llegaron a bloquearse en la fila del ejercicio",
        )
        blocker.rollback()
        return [f.result(timeout=WAIT_SECONDS) for f in futures]
    finally:
        blocker.rollback()
        blocker.close()


def test_concurrent_runs_create_one_live_run(books: dict[str, Any], engine: Engine) -> None:
    results = _race(books, engine, "/depreciation/run", {"period_id": period_id(books, 2026, 2)})
    codes = sorted((s, b.get("error", {}).get("code") if s != 201 else None) for s, b in results)
    assert codes == [(201, None)] + [(409, "DEPRECIATION_RUN_EXISTS")] * (PARALLEL - 1)
    with engine.connect() as conn:
        runs = conn.scalar(text("SELECT count(*) FROM accounting.depreciation_runs"))
        entries = conn.scalar(
            text("SELECT count(*) FROM accounting.journal_entries WHERE kind = 'depreciation'")
        )
    assert runs == entries == 1


def test_concurrent_generation_does_not_duplicate(books: dict[str, Any], engine: Engine) -> None:
    results = _race(books, engine, "/recurring/generate", {"period_id": period_id(books, 2026, 3)})
    assert [s for s, _ in results] == [200] * PARALLEL
    created = [e["id"] for _, body in results for e in body["created"]]
    existing = {e["id"] for _, body in results for e in body["existing"]}
    assert len(created) == 1 and existing == set(created)
    with engine.connect() as conn:
        count = conn.scalar(
            text("SELECT count(*) FROM accounting.journal_entries WHERE kind = 'recurring'")
        )
    assert count == 1
