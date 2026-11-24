"""Numeración correlativa con contabilizaciones concurrentes, con conexiones reales (spec §5.3).

Igual que `test_finance_import_concurrency.py` (D-034): base propia (`<base de pruebas>_conc`),
un pedido HTTP por hilo y una sesión por pedido. Para que la carrera sea real, otra conexión
**retiene la fila del ejercicio** (la que serializa la numeración) hasta que todos los pedidos
están bloqueados esperándola, y recién entonces la suelta. La prueba de estrés repite la
carrera libre, sin retención.
"""

import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_db
from app.main import create_app
from tests.accounting_utils import ACC, CAJA, CAPITAL, create_year, draft, load_chart
from tests.conftest import BACKEND_DIR, SETUP_BODY, auth_header

WAIT_SECONDS = 30
PARALLEL = 6


@pytest.fixture(scope="module")
def concurrent_engine() -> Iterator[Engine]:
    base = make_url(get_settings().test_database_url)
    name = f"{base.database}_acc_conc"
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
def app(concurrent_engine: Engine) -> FastAPI:
    app = create_app()
    sessions = sessionmaker(bind=concurrent_engine, autoflush=False, expire_on_commit=False)

    def _get_db() -> Iterator[Session]:  # igual que app.core.db.get_db, con la base propia
        session = sessions()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    return app


@pytest.fixture(scope="module")
def books(app: FastAPI) -> dict[str, Any]:
    client = TestClient(app)
    res = client.post("/api/v1/system/setup", json=SETUP_BODY)
    assert res.status_code == 201, res.text
    token = str(res.json()["token"])
    accounts = load_chart(client, token)
    years = {y: create_year(client, token, y)["id"] for y in (2026, 2027, 2028)}
    return {"app": app, "client": client, "token": token, "accounts": accounts, "years": years}


def _drafts(books: dict[str, Any], year: int, count: int) -> list[str]:
    return [
        draft(
            books["client"],
            books["token"],
            books["accounts"],
            f"{year}-0{1 + n % 9}-1{n % 9}",
            [(CAJA, 100 + n, 0), (CAPITAL, 0, 100 + n)],
            f"Concurrente {n}",
        )["id"]
        for n in range(count)
    ]


def _post_all(books: dict[str, Any], entry_ids: list[str], barrier: Barrier) -> list[Any]:
    def _post(entry_id: str) -> tuple[int, Any]:
        client = TestClient(books["app"])  # cliente propio: sin estado compartido entre hilos
        barrier.wait(timeout=WAIT_SECONDS)
        res = client.post(f"{ACC}/entries/{entry_id}/post", headers=auth_header(books["token"]))
        return res.status_code, res.json()

    pool = ThreadPoolExecutor(max_workers=len(entry_ids))
    return [pool.submit(_post, e) for e in entry_ids]


def _blocked_sessions(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'"
                )
            )
            or 0
        )


def _wait_until(condition: Callable[[], bool], message: str) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(message)


def _post_while_year_is_locked(
    books: dict[str, Any], engine: Engine, year: int, entry_ids: list[str]
) -> list[tuple[int, Any]]:
    blocker = engine.connect()
    try:
        blocker.execute(
            text("SELECT 1 FROM accounting.fiscal_years WHERE id = :id FOR UPDATE"),
            {"id": books["years"][year]},
        )
        barrier = Barrier(len(entry_ids) + 1)
        futures = _post_all(books, entry_ids, barrier)
        barrier.wait(timeout=WAIT_SECONDS)
        _wait_until(
            lambda: _blocked_sessions(engine) >= len(entry_ids),
            f"los {len(entry_ids)} pedidos no llegaron a bloquearse en la fila del ejercicio",
        )
        blocker.rollback()  # suelta el ejercicio: ahora compiten de verdad
        return [f.result(timeout=WAIT_SECONDS) for f in futures]
    finally:
        blocker.rollback()
        blocker.close()


def _numbers(engine: Engine, year_id: str) -> list[int]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT number FROM accounting.journal_entries WHERE fiscal_year_id = :y"
                " AND number IS NOT NULL ORDER BY number"
            ),
            {"y": year_id},
        )
        return [int(n) for (n,) in rows]


def test_concurrent_posts_do_not_repeat_or_skip_numbers(
    books: dict[str, Any], concurrent_engine: Engine
) -> None:
    entry_ids = _drafts(books, 2026, PARALLEL)
    results = _post_while_year_is_locked(books, concurrent_engine, 2026, entry_ids)
    assert [status for status, _ in results] == [200] * PARALLEL
    assert sorted(body["number"] for _, body in results) == list(range(1, PARALLEL + 1))
    assert _numbers(concurrent_engine, books["years"][2026]) == list(range(1, PARALLEL + 1))
    with concurrent_engine.connect() as conn:
        last = conn.scalar(
            text("SELECT last_entry_number FROM accounting.fiscal_years WHERE id = :y"),
            {"y": books["years"][2026]},
        )
    assert last == PARALLEL


def test_same_draft_posted_twice_at_once_gets_one_number(
    books: dict[str, Any], concurrent_engine: Engine
) -> None:
    (entry_id,) = _drafts(books, 2027, 1)
    results = _post_while_year_is_locked(books, concurrent_engine, 2027, [entry_id, entry_id])
    codes = sorted(
        (status, body.get("error", {}).get("code") if status != 200 else None)
        for status, body in results
    )
    assert codes == [(200, None), (409, "ENTRY_NOT_DRAFT")]
    assert _numbers(concurrent_engine, books["years"][2027]) == [1]


def test_free_race_stress(books: dict[str, Any], concurrent_engine: Engine) -> None:
    expected = 0
    for _ in range(5):
        entry_ids = _drafts(books, 2028, PARALLEL)
        futures = _post_all(books, entry_ids, Barrier(PARALLEL))
        results = [f.result(timeout=WAIT_SECONDS) for f in futures]
        assert [status for status, _ in results] == [200] * PARALLEL
        expected += PARALLEL
        assert _numbers(concurrent_engine, books["years"][2028]) == list(range(1, expected + 1))
