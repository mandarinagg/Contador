"""Confirmar importaciones en paralelo, con conexiones reales (D-034).

Las demás pruebas corren dentro de una transacción que se revierte, con una sola conexión:
no pueden ejercitar candados entre conexiones. Estas usan una base propia
(`<base de pruebas>_conc`, creada y migrada al empezar y borrada al terminar), un pedido HTTP
por hilo y una sesión de SQLAlchemy por pedido, igual que la app real.

Para no depender de la suerte, las pruebas principales **sostienen el candado de la cuenta**
desde otra conexión hasta que ambos pedidos están bloqueados dentro de `commit`, y recién
entonces lo sueltan: así los dos compiten de verdad por el mismo recurso. Las pruebas de
estrés repiten la carrera libre (sin retención) varias veces.
"""

import json
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
from tests.conftest import BACKEND_DIR, SETUP_BODY, auth_header
from tests.finance_utils import API, audit_entries, business_context, create_account, ok
from tests.test_finance_import import PY_MAPPING

CSV = "\n".join(
    [
        "Fecha;Concepto;Nro. Operación;Importe",
        "05/03/2026;Pago ANDE;1001;-150.000",
        "06/03/2026;Depósito cliente;1002;1.234.567",
        "07/03/2026;Supermercado;1003;-85.000",
    ]
).encode()
ROWS = 3
WAIT_SECONDS = 30


@pytest.fixture(scope="module")
def concurrent_engine() -> Iterator[Engine]:
    """Base propia con las migraciones aplicadas; se borra al terminar el módulo."""
    base = make_url(get_settings().test_database_url)
    name = f"{base.database}_conc"
    url = base.set(database=name)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config(f"{BACKEND_DIR}/alembic.ini")
    cfg.set_main_option("script_location", f"{BACKEND_DIR}/migrations")
    cfg.attributes["url"] = url.render_as_string(hide_password=False)
    engine = create_engine(url, pool_size=10)
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
def owner(app: FastAPI) -> tuple[str, str]:
    """(token, id del contexto empresarial) de una organización ya configurada y confirmada."""
    client = TestClient(app)
    res = client.post("/api/v1/system/setup", json=SETUP_BODY)
    assert res.status_code == 201, res.text
    token = str(res.json()["token"])
    return token, business_context(client, token)


@pytest.fixture
def world(app: FastAPI, owner: tuple[str, str]) -> dict[str, Any]:
    """Una cuenta nueva por prueba, para que los duplicados de una no afecten a la otra."""
    token, biz = owner
    client = TestClient(app)
    account = create_account(client, token, biz, f"Cuenta {time.monotonic_ns()}")["id"]
    return {"app": app, "token": token, "biz": biz, "account": account, "client": client}


def _preview(world: dict[str, Any]) -> str:
    res = world["client"].post(
        f"{API}/contexts/{world['biz']}/imports",
        files={"file": ("extracto.csv", CSV, "application/octet-stream")},
        data={"account_id": world["account"], "mapping": json.dumps(PY_MAPPING)},
        headers=auth_header(world["token"]),
    )
    return str(ok(res, 201)["id"])


def _commit_in_threads(world: dict[str, Any], batch_ids: list[str]) -> list[tuple[int, Any]]:
    """Confirma cada lote desde su propio hilo y conexión, arrancando a la vez."""
    barrier = Barrier(len(batch_ids))

    def _commit(batch_id: str) -> tuple[int, Any]:
        client = TestClient(world["app"])  # cliente propio: sin estado compartido entre hilos
        barrier.wait(timeout=WAIT_SECONDS)
        res = client.post(
            f"{API}/contexts/{world['biz']}/imports/{batch_id}/commit",
            headers=auth_header(world["token"]),
        )
        return res.status_code, res.json()

    with ThreadPoolExecutor(max_workers=len(batch_ids)) as pool:
        futures = [pool.submit(_commit, b) for b in batch_ids]
        return [f.result(timeout=WAIT_SECONDS) for f in futures]


def _commit_while_account_is_locked(
    world: dict[str, Any], engine: Engine, batch_ids: list[str]
) -> list[tuple[int, Any]]:
    """Retiene el candado de la cuenta hasta que todos los pedidos esperan, y lo suelta."""
    blocker = engine.connect()
    try:
        blocker.execute(
            text("SELECT 1 FROM finance.accounts WHERE id = :id FOR UPDATE"),
            {"id": world["account"]},
        )
        barrier = Barrier(len(batch_ids) + 1)

        def _commit(batch_id: str) -> tuple[int, Any]:
            client = TestClient(world["app"])
            barrier.wait(timeout=WAIT_SECONDS)
            res = client.post(
                f"{API}/contexts/{world['biz']}/imports/{batch_id}/commit",
                headers=auth_header(world["token"]),
            )
            return res.status_code, res.json()

        with ThreadPoolExecutor(max_workers=len(batch_ids)) as pool:
            futures = [pool.submit(_commit, b) for b in batch_ids]
            barrier.wait(timeout=WAIT_SECONDS)
            _wait_until(
                lambda: _blocked_sessions(engine) >= len(batch_ids),
                f"los {len(batch_ids)} pedidos no llegaron a bloquearse en un candado",
            )
            blocker.rollback()  # suelta la cuenta: ahora compiten de verdad
            return [f.result(timeout=WAIT_SECONDS) for f in futures]
    finally:
        blocker.rollback()
        blocker.close()


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


def _transactions(engine: Engine, account_id: str) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT import_batch_id::text, description FROM finance.transactions "
                "WHERE account_id = :a ORDER BY description, import_batch_id"
            ),
            {"a": account_id},
        )
        return [(batch, description) for batch, description in rows]


def _codes(results: list[tuple[int, Any]]) -> list[tuple[int, str | None]]:
    return sorted(
        (status, body.get("error", {}).get("code") if status != 200 else None)
        for status, body in results
    )


def test_two_simultaneous_commits_of_same_batch_create_rows_once(
    world: dict[str, Any], concurrent_engine: Engine
) -> None:
    batch_id = _preview(world)
    results = _commit_while_account_is_locked(world, concurrent_engine, [batch_id, batch_id])

    assert _codes(results) == [(200, None), (409, "IMPORT_ALREADY_COMMITTED")]
    winner = next(body for status, body in results if status == 200)
    assert winner["status"] == "committed" and winner["rows_imported"] == ROWS
    stored = _transactions(concurrent_engine, world["account"])
    assert len(stored) == ROWS and {b for b, _ in stored} == {batch_id}
    committed = [
        e
        for e in audit_entries(world["client"], world["token"], "finance.import")
        if e["action"] == "finance.import.committed" and e["entity_id"] == batch_id
    ]
    assert len(committed) == 1


def test_two_simultaneous_batches_with_same_rows_do_not_duplicate(
    world: dict[str, Any], concurrent_engine: Engine
) -> None:
    first, second = _preview(world), _preview(world)
    results = _commit_while_account_is_locked(world, concurrent_engine, [first, second])

    assert _codes(results) == [(200, None), (409, "IMPORT_NEW_DUPLICATES")]
    loser_body = next(body for status, body in results if status == 409)
    assert loser_body["error"]["details"]["rows"] == [2, 3, 4]  # fila 1 es la cabecera
    stored = _transactions(concurrent_engine, world["account"])
    assert len(stored) == ROWS, "el segundo lote duplicó movimientos"
    winner = next(body for status, body in results if status == 200)
    assert {b for b, _ in stored} == {winner["id"]}

    # La señal quedó guardada: el lote perdedor sigue pendiente y con las filas marcadas.
    loser_id = first if winner["id"] == second else second
    batch = ok(
        world["client"].get(
            f"{API}/contexts/{world['biz']}/imports/{loser_id}",
            headers=auth_header(world["token"]),
        )
    )
    assert batch["status"] == "previewed" and batch["rows_duplicate"] == ROWS
    assert all(r["decision"] == "skip" and r["duplicate_of"] for r in batch["rows"])


@pytest.mark.parametrize("scenario", ["same_batch", "two_batches"])
def test_free_race_never_duplicates(
    world: dict[str, Any], concurrent_engine: Engine, scenario: str
) -> None:
    """La carrera sin retención del candado, repetida: el invariante se cumple siempre."""
    for _ in range(6):
        account = create_account(
            world["client"], world["token"], world["biz"], f"Carrera {time.monotonic_ns()}"
        )["id"]
        world["account"] = account
        first = _preview(world)
        second = first if scenario == "same_batch" else _preview(world)
        results = _commit_in_threads(world, [first, second])
        expected = (
            "IMPORT_ALREADY_COMMITTED" if scenario == "same_batch" else "IMPORT_NEW_DUPLICATES"
        )
        assert _codes(results) == [(200, None), (409, expected)]
        assert len(_transactions(concurrent_engine, account)) == ROWS
