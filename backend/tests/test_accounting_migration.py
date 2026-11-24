"""Migración 0003: sin diferencias con los modelos, reversible y con permisos (spec §5.11).

Corre sobre una base propia y desechable (`<base de pruebas>_mig`), como la de la 0002.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.permissions import PERMISSION_DESCRIPTIONS, ROLE_PERMISSIONS, Perm
from tests.test_finance_migration import migration_db

__all__ = ["migration_db"]

ACCOUNTING = (Perm.ACCOUNTING_READ, Perm.ACCOUNTING_MANAGE, Perm.ACCOUNTING_POST)
TRIGGERS = {
    "ledger_accounts_guard",
    "fiscal_years_guard",
    "fiscal_years_no_delete",
    "fiscal_years_no_truncate",
    "periods_guard",
    "periods_no_delete",
    "periods_no_truncate",
    "journal_entries_guard",
    "journal_entries_no_truncate",
    "journal_lines_guard",
    "journal_lines_no_truncate",
}


def _role_permissions(engine: Engine) -> set[tuple[str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT role_code, permission_code FROM core.role_permissions"
                " WHERE permission_code LIKE 'accounting.%'"
            )
        )
        return {(r, p) for r, p in rows}


def _catalog(engine: Engine) -> dict[str, str]:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT code, description FROM core.permissions")).all())


def _accounting_triggers(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT t.tgname FROM pg_trigger t"
                " JOIN pg_class c ON c.oid = t.tgrelid"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'accounting' AND NOT t.tgisinternal"
            )
        )
        return {name for (name,) in rows}


def _finance_columns(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns"
                " WHERE table_schema = 'finance' AND column_name = 'ledger_account_id'"
            )
        )
        return {name for (name,) in rows}


def test_upgrade_check_downgrade_upgrade(migration_db: tuple[Config, Engine]) -> None:
    cfg, engine = migration_db
    expected = {
        (role.value, perm.value)
        for role, perms in ROLE_PERMISSIONS.items()
        for perm in perms
        if perm in ACCOUNTING
    }

    command.upgrade(cfg, "head")
    command.check(cfg)  # falla si los modelos y la base difieren
    assert _role_permissions(engine) == expected
    # El catálogo de la base coincide con el del código (todas las fases).
    assert _catalog(engine) == {p.value: d for p, d in PERMISSION_DESCRIPTIONS.items()}
    assert _accounting_triggers(engine) == TRIGGERS
    assert _finance_columns(engine) == {
        "accounts.ledger_account_id",
        "categories.ledger_account_id",
    }

    # Con datos contables (y triggers que prohíben borrar), la bajada igual funciona.
    with engine.begin() as conn:
        org = conn.scalar(
            text(
                "INSERT INTO core.organizations (legal_name, legal_form)"
                " VALUES ('Con datos EAS', 'EAS') RETURNING id"
            )
        )
        conn.execute(
            text(
                "INSERT INTO accounting.ledger_accounts (organization_id, code, name, kind,"
                " normal_side, is_postable, origin) VALUES (:org, '1', 'ACTIVO', 'asset',"
                " 'debit', true, 'user')"
            ),
            {"org": org},
        )
        conn.execute(
            text(
                "INSERT INTO accounting.fiscal_years (organization_id, start_date, end_date)"
                " VALUES (:org, '2026-01-01', '2026-12-31')"
            ),
            {"org": org},
        )
    command.downgrade(cfg, "0002")
    with engine.connect() as conn:
        schema = conn.scalar(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'accounting'")
        )
        functions = conn.scalar(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                " WHERE n.nspname = 'accounting'"
            )
        )
    assert schema is None and functions == 0
    assert _role_permissions(engine) == set()
    assert _finance_columns(engine) == set()

    command.upgrade(cfg, "head")
    command.check(cfg)
    assert _role_permissions(engine) == expected
    assert _accounting_triggers(engine) == TRIGGERS
