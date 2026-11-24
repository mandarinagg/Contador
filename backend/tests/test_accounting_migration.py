"""Migración 0003: sin diferencias con los modelos, reversible y con permisos (spec §5.11).

`TRIGGERS` son los de la 0003; con la 0004 se suman los de `TRIGGERS_0004` y con la 0005
(`head`) el de `TRIGGERS_0005` (de la tributación, sobre `journal_entries`). La
reversibilidad propia de la 0004 está en `test_accounting_migration_3b.py` y la de la 0005 en
`test_tax_migration.py`.

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
TRIGGERS_0004 = {
    "journal_entries_sync_links",
    "depreciation_runs_guard",
    "recurring_generations_guard",
    "depreciation_items_guard",
    "fixed_assets_guard",
    "asset_year_values_immutable",
    "asset_categories_no_delete",
    "fixed_assets_no_delete",
    "depreciation_runs_no_delete",
    "asset_year_values_no_delete",
    "cost_centers_no_delete",
    "recurring_templates_no_delete",
    "recurring_generations_no_delete",
    "asset_categories_no_truncate",
    "fixed_assets_no_truncate",
    "depreciation_runs_no_truncate",
    "depreciation_items_no_truncate",
    "asset_year_values_no_truncate",
    "cost_centers_no_truncate",
    "recurring_templates_no_truncate",
    "recurring_generations_no_truncate",
}

# BR-TAX-10: un asiento de un movimiento no nace si un comprobante del movimiento ya tiene uno.
TRIGGERS_0005 = {"journal_entries_voucher_guard"}


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
    assert _accounting_triggers(engine) == TRIGGERS | TRIGGERS_0004 | TRIGGERS_0005
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
    assert _accounting_triggers(engine) == TRIGGERS | TRIGGERS_0004 | TRIGGERS_0005
