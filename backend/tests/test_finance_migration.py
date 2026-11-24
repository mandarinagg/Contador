"""Migración 0002: sin diferencias con los modelos, reversible y con datos iniciales.

Corre sobre una base propia y desechable (`<base de pruebas>_mig`), no sobre la de las
demás pruebas: bajar y subir migraciones con conexiones abiertas se bloquearía.
"""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from app.core.config import get_settings
from app.core.permissions import ROLE_PERMISSIONS, Perm
from tests.conftest import BACKEND_DIR


@pytest.fixture
def migration_db() -> Iterator[tuple[Config, Engine]]:
    base = make_url(get_settings().test_database_url)
    name = f"{base.database}_mig"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    cfg.attributes["url"] = url
    engine = create_engine(url)
    try:
        yield cfg, engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _finance_permissions(engine: Engine) -> set[tuple[str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT role_code, permission_code FROM core.role_permissions"
                " WHERE permission_code LIKE 'finance.%'"
            )
        )
        return {(r, p) for r, p in rows}


def test_upgrade_check_downgrade_upgrade(migration_db: tuple[Config, Engine]) -> None:
    cfg, engine = migration_db
    expected = {
        (role.value, perm.value)
        for role, perms in ROLE_PERMISSIONS.items()
        for perm in perms
        if perm in (Perm.FINANCE_READ, Perm.FINANCE_MANAGE)
    }

    # Una organización creada antes de la fase 2 recibe su contexto empresarial.
    command.upgrade(cfg, "0001")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO core.organizations (legal_name, legal_form)"
                " VALUES ('Previa EAS', 'EAS')"
            )
        )
        # Base creada antes de la fase 2: sin los permisos de finanzas.
        conn.execute(
            text("DELETE FROM core.role_permissions WHERE permission_code LIKE 'finance.%'")
        )
        conn.execute(text("DELETE FROM core.permissions WHERE code LIKE 'finance.%'"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        contexts = conn.execute(
            text("SELECT kind, name, owner_user_id FROM finance.contexts")
        ).all()
    assert [tuple(c) for c in contexts] == [("business", "Empresa", None)]
    assert _finance_permissions(engine) == expected

    command.check(cfg)  # falla si los modelos y la base difieren

    command.downgrade(cfg, "0001")
    with engine.connect() as conn:
        schema = conn.scalar(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'finance'")
        )
        organizations = conn.scalar(text("SELECT count(*) FROM core.organizations"))
    assert schema is None
    assert organizations == 1
    assert _finance_permissions(engine) == set()

    command.upgrade(cfg, "head")
    command.check(cfg)
    assert _finance_permissions(engine) == expected
