"""Migración 0005 (fase 4): sin diferencias, reversible con datos, y la bajada no pierde lo que
no se puede volver a calcular (comprobantes, obligaciones presentadas)."""

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
from app.core.permissions import ROLE_PERMISSIONS, Perm
from app.main import create_app
from tests.accounting_utils import BANCOS, CAPITAL, posted
from tests.assets_utils import setup_books
from tests.conftest import SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.tax_utils import (
    TAX,
    create_voucher,
    file_obligation,
    fix_today,
    load_rules,
    obligation,
    put_profile,
    set_ruc,
)
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture


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


def _scalar(engine: Engine, sql: str) -> Any:
    with engine.connect() as conn:
        return conn.scalar(text(sql))


def _accounting_functions(engine: Engine) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p"
                " JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'accounting'"
            )
        )
        return {name: definition for name, definition in rows}


def _triggers_on_entries(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
                " AND tgrelid = 'accounting.journal_entries'::regclass"
            )
        )
        return set(rows.scalars())


def _counts(engine: Engine) -> tuple[Any, ...]:
    with engine.connect() as conn:
        return tuple(
            conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM accounting.journal_entries),"
                    " (SELECT count(*) FROM accounting.ledger_accounts),"
                    " (SELECT count(*) FROM finance.transactions),"
                    " (SELECT ruc FROM core.organizations)"
                )
            ).one()
        )


def test_downgrade_to_0004_and_upgrade_with_data(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "0004")
    functions_0004 = _accounting_functions(engine)
    triggers_0004 = _triggers_on_entries(engine)
    command.upgrade(cfg, "head")
    command.check(cfg)
    tax_perms = {p.value for p in Perm if p.value.startswith("tax.")}
    assert (
        set(
            (
                _scalar(
                    engine,
                    "SELECT string_agg(code, ',') FROM core.permissions WHERE code LIKE 'tax.%'",
                )
                or ""
            ).split(",")
        )
        == tax_perms
    )
    with engine.connect() as conn:
        loaded = {
            (str(role), str(perm))
            for role, perm in conn.execute(
                text(
                    "SELECT role_code, permission_code FROM core.role_permissions"
                    " WHERE permission_code LIKE 'tax.%'"
                )
            )
        }
    assert loaded == {
        (role.value, perm.value)
        for role, perms in ROLE_PERMISSIONS.items()
        for perm in perms
        if perm.value in tax_perms
    }

    fix_today(monkeypatch)
    token = ok(api.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    books = setup_books(api, token, (2026,))
    posted(api, token, books["accounts"], "2026-01-05", [(BANCOS, 500, 0), (CAPITAL, 0, 500)])
    set_ruc(api, token, "80000005")
    load_rules(api, token)
    ok(api.post(f"{TAX}/holidays/load-candidates", headers=auth_header(token)))
    put_profile(api, token)
    assert _scalar(engine, "SELECT count(*) FROM tax.obligations") > 0
    before = _counts(engine)

    command.downgrade(cfg, "0004")
    assert _scalar(engine, "SELECT version_num FROM alembic_version") == "0004"
    assert _scalar(engine, "SELECT count(*) FROM pg_namespace WHERE nspname = 'tax'") == 0
    assert _scalar(engine, "SELECT count(*) FROM core.permissions WHERE code LIKE 'tax.%'") == 0
    assert _accounting_functions(engine) == functions_0004
    assert _triggers_on_entries(engine) == triggers_0004
    assert _counts(engine) == before

    command.upgrade(cfg, "head")
    command.check(cfg)
    assert _counts(engine) == before
    # Vuelve a funcionar: reglas, perfil y calendario se cargan de nuevo.
    assert load_rules(api, token)["created"] == 39
    put_profile(api, token)
    assert _scalar(engine, "SELECT count(*) FROM tax.obligations") > 0


def test_downgrade_refuses_to_lose_vouchers_or_filed_obligations(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    fix_today(monkeypatch)
    token = ok(api.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    set_ruc(api, token, "80000005")
    load_rules(api, token)
    put_profile(api, token)
    row = obligation(api, token, "IVA-GENERAL-LIQUIDACION", "2026-01-01")
    file_obligation(api, token, row["id"])
    with pytest.raises(RuntimeError, match=r"hay 0 comprobantes y 1 obligaciones"):
        command.downgrade(cfg, "0004")
    voucher = create_voucher(api, token)
    ok(
        api.post(
            f"{TAX}/vouchers/{voucher['id']}/void",
            json={"reason": "Prueba"},
            headers=auth_header(token),
        )
    )
    # Anulado igual cuenta: la bajada no lo borra.
    with pytest.raises(RuntimeError, match=r"hay 1 comprobantes"):
        command.downgrade(cfg, "0004")
    assert _scalar(engine, "SELECT version_num FROM alembic_version") == "0005"
    assert _scalar(engine, "SELECT count(*) FROM tax.vouchers") == 1
