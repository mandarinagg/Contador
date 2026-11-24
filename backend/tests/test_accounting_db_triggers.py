"""BR-ACC-01/02/03 y D-035: la **base** rechaza lo prohibido (spec §5.1 y §5.2).

Estas pruebas escriben con SQL directo, sin pasar por el servicio: demuestran que ni un
error de código podría modificar un asiento contabilizado, contabilizar uno desbalanceado o
en un período cerrado, usar una cuenta agrupadora o de otra organización, ni originar un
asiento desde un movimiento personal. Los rechazos de los triggers se reconocen por el
nombre estable que informan (`diag.constraint_name`).
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.accounting_utils import (
    BANCOS,
    CAJA,
    CAPITAL,
    GRUPO_DISPONIBILIDADES,
    VENTAS,
    create_year,
    load_chart,
    posted,
)
from tests.finance_utils import (
    business_context,
    create_account,
    create_tx,
    personal_context,
)

INSERT_ENTRY = text(
    """
    INSERT INTO accounting.journal_entries (organization_id, fiscal_year_id, entry_date, kind,
        description, created_by, status, number, source_transaction_id, source_context_id,
        source_context_kind, reverses_entry_id)
    VALUES (:org, :year, :day, :kind, 'SQL directo', :user, :status, :number, :tx, :ctx,
        :ctx_kind, :reverses)
    RETURNING id
    """
)
INSERT_LINE = text(
    """
    INSERT INTO accounting.journal_lines (organization_id, entry_id, line_no, account_id,
        debit, credit)
    VALUES (:org, :entry, :line_no, :account, :debit, :credit)
    """
)
POST = text(
    "UPDATE accounting.journal_entries SET status = 'posted', posted_by = :user,"
    " posted_at = now() WHERE id = :entry"
)


@pytest.fixture
def world(client: TestClient, owner_token: str, db: Session) -> dict[str, Any]:
    accounts = load_chart(client, owner_token)
    year = create_year(client, owner_token, 2026)
    entry = posted(
        client, owner_token, accounts, "2026-03-10", [(BANCOS, 1000, 0), (CAPITAL, 0, 1000)]
    )
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    org_id = db.scalar(text("SELECT id FROM core.organizations"))
    return {
        "accounts": {code: a["id"] for code, a in accounts.items()},
        "year": year,
        "posted": entry,
        "user": user_id,
        "org": org_id,
    }


def _rejected(db: Session, statement: Any, params: dict[str, Any], name: str) -> None:
    """La sentencia falla en la base con la restricción o el trigger `name`."""
    nested = db.begin_nested()
    with pytest.raises(DBAPIError) as caught:
        db.execute(statement, params)
    nested.rollback()
    diag = getattr(caught.value.orig, "diag", None)
    assert getattr(diag, "constraint_name", None) == name, str(caught.value)


def _entry_params(w: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    params = {
        "org": w["org"],
        "year": w["year"]["id"],
        "day": "2026-04-15",
        "kind": "manual",
        "user": w["user"],
        "status": "draft",
        "number": None,
        "tx": None,
        "ctx": None,
        "ctx_kind": None,
        "reverses": None,
    }
    params.update(overrides)
    return params


def _draft(db: Session, w: dict[str, Any], lines: list[tuple[str, int, int]], **kw: Any) -> Any:
    entry_id = db.execute(INSERT_ENTRY, _entry_params(w, **kw)).scalar_one()
    for n, (code, debit, credit) in enumerate(lines, start=1):
        db.execute(
            INSERT_LINE,
            {
                "org": w["org"],
                "entry": entry_id,
                "line_no": n,
                "account": w["accounts"][code],
                "debit": debit,
                "credit": credit,
            },
        )
    return entry_id


@pytest.fixture
def other_org_account(db: Session) -> Iterator[Any]:
    org = db.execute(
        text(
            "INSERT INTO core.organizations (legal_name, legal_form) VALUES ('Otra EAS', 'EAS')"
            " RETURNING id"
        )
    ).scalar_one()
    account = db.execute(
        text(
            "INSERT INTO accounting.ledger_accounts (organization_id, code, name, kind,"
            " normal_side, is_postable, origin) VALUES (:org, '9', 'Ajena', 'asset', 'debit',"
            " true, 'user') RETURNING id"
        ),
        {"org": org},
    ).scalar_one()
    yield account


# --- §5.1: lo contabilizado es inmutable ---------------------------------------------------


def test_valid_draft_and_post_by_sql_are_accepted(db: Session, world: dict[str, Any]) -> None:
    entry_id = _draft(db, world, [(CAJA, 500, 0), (CAPITAL, 0, 500)])
    db.execute(POST, {"user": world["user"], "entry": entry_id})
    number = db.scalar(
        text("SELECT number FROM accounting.journal_entries WHERE id = :e"), {"e": entry_id}
    )
    assert number == world["posted"]["number"] + 1  # el número lo asigna la base


def test_update_and_delete_of_posted_entry_fail(db: Session, world: dict[str, Any]) -> None:
    params = {"id": world["posted"]["id"]}
    _rejected(
        db,
        text("UPDATE accounting.journal_entries SET description = 'otra' WHERE id = :id"),
        params,
        "trg_journal_entries_posted_immutable",
    )
    _rejected(
        db,
        text("UPDATE accounting.journal_entries SET entry_date = '2026-03-11' WHERE id = :id"),
        params,
        "trg_journal_entries_posted_immutable",
    )
    _rejected(
        db,
        text(
            "UPDATE accounting.journal_entries SET status = 'draft', number = NULL,"
            " posted_at = NULL, posted_by = NULL WHERE id = :id"
        ),
        params,
        "trg_journal_entries_posted_immutable",
    )
    # A revertido solo con su reversión contabilizada.
    _rejected(
        db,
        text("UPDATE accounting.journal_entries SET status = 'reversed' WHERE id = :id"),
        params,
        "trg_journal_entries_reversal_missing",
    )
    _rejected(
        db,
        text("DELETE FROM accounting.journal_entries WHERE id = :id"),
        params,
        "trg_journal_entries_no_delete",
    )


def test_drafts_are_not_deleted_and_are_born_as_drafts(db: Session, world: dict[str, Any]) -> None:
    entry_id = _draft(db, world, [(CAJA, 500, 0)])
    _rejected(
        db,
        text("DELETE FROM accounting.journal_entries WHERE id = :id"),
        {"id": entry_id},
        "trg_journal_entries_no_delete",
    )
    _rejected(
        db,
        INSERT_ENTRY,
        _entry_params(world, status="posted", number=99),
        "trg_journal_entries_insert_draft",
    )
    # Un número puesto a mano al contabilizar no se acepta: lo asigna la base.
    db.execute(
        INSERT_LINE,
        {
            "org": world["org"],
            "entry": entry_id,
            "line_no": 2,
            "account": world["accounts"][CAPITAL],
            "debit": 0,
            "credit": 500,
        },
    )
    _rejected(
        db,
        text(
            "UPDATE accounting.journal_entries SET status = 'posted', number = 77,"
            " posted_by = :user, posted_at = now() WHERE id = :entry"
        ),
        {"user": world["user"], "entry": entry_id},
        "trg_journal_entries_number_assigned",
    )


def test_lines_of_posted_entry_cannot_change(db: Session, world: dict[str, Any]) -> None:
    entry = world["posted"]["id"]
    _rejected(
        db,
        INSERT_LINE,
        {
            "org": world["org"],
            "entry": entry,
            "line_no": 3,
            "account": world["accounts"][CAJA],
            "debit": 10,
            "credit": 0,
        },
        "trg_journal_lines_entry_not_draft",
    )
    _rejected(
        db,
        text("UPDATE accounting.journal_lines SET debit = 2000 WHERE entry_id = :e"),
        {"e": entry},
        "trg_journal_lines_entry_not_draft",
    )
    _rejected(
        db,
        text("DELETE FROM accounting.journal_lines WHERE entry_id = :e"),
        {"e": entry},
        "trg_journal_lines_entry_not_draft",
    )


def test_posting_unbalanced_single_line_or_in_closed_period_fails(
    db: Session, world: dict[str, Any]
) -> None:
    unbalanced = _draft(db, world, [(CAJA, 500, 0), (CAPITAL, 0, 400)])
    _rejected(
        db, POST, {"user": world["user"], "entry": unbalanced}, "trg_journal_entries_unbalanced"
    )
    single = _draft(db, world, [(CAJA, 500, 0)])
    _rejected(db, POST, {"user": world["user"], "entry": single}, "trg_journal_entries_min_lines")

    in_april = _draft(db, world, [(CAJA, 500, 0), (CAPITAL, 0, 500)])
    db.execute(
        text(
            "UPDATE accounting.periods SET status = 'closed', closed_at = now(), closed_by = :u"
            " WHERE fiscal_year_id = :y AND start_date = '2026-04-01'"
        ),
        {"u": world["user"], "y": world["year"]["id"]},
    )
    _rejected(
        db, POST, {"user": world["user"], "entry": in_april}, "trg_journal_entries_period_closed"
    )


def test_entry_date_must_be_inside_its_fiscal_year(db: Session, world: dict[str, Any]) -> None:
    _rejected(
        db,
        INSERT_ENTRY,
        _entry_params(world, day="2027-01-05"),
        "trg_journal_entries_date_outside_year",
    )


def test_line_with_grouping_or_archived_account_fails(db: Session, world: dict[str, Any]) -> None:
    entry_id = _draft(db, world, [])
    line = {
        "org": world["org"],
        "entry": entry_id,
        "line_no": 1,
        "account": world["accounts"][GRUPO_DISPONIBILIDADES],
        "debit": 100,
        "credit": 0,
    }
    _rejected(db, INSERT_LINE, line, "trg_journal_lines_account_not_postable")
    db.execute(
        text("UPDATE accounting.ledger_accounts SET archived_at = now() WHERE id = :a"),
        {"a": world["accounts"][CAJA]},
    )
    _rejected(
        db,
        INSERT_LINE,
        {**line, "account": world["accounts"][CAJA]},
        "trg_journal_lines_account_not_postable",
    )


def test_posting_with_an_account_archived_after_the_draft_fails(
    db: Session, world: dict[str, Any]
) -> None:
    entry_id = _draft(db, world, [(CAJA, 500, 0), (CAPITAL, 0, 500)])
    db.execute(
        text("UPDATE accounting.ledger_accounts SET archived_at = now() WHERE id = :a"),
        {"a": world["accounts"][CAJA]},
    )
    _rejected(
        db,
        POST,
        {"user": world["user"], "entry": entry_id},
        "trg_journal_entries_account_not_postable",
    )


def test_line_with_account_of_another_organization_fails(
    db: Session, world: dict[str, Any], other_org_account: Any
) -> None:
    entry_id = _draft(db, world, [])
    _rejected(
        db,
        INSERT_LINE,
        {
            "org": world["org"],
            "entry": entry_id,
            "line_no": 1,
            "account": other_org_account,
            "debit": 100,
            "credit": 0,
        },
        "fk_journal_lines_account_id_ledger_accounts",
    )


def test_line_checks_in_database(db: Session, world: dict[str, Any]) -> None:
    entry_id = _draft(db, world, [])
    base = {
        "org": world["org"],
        "entry": entry_id,
        "line_no": 1,
        "account": world["accounts"][CAJA],
    }
    _rejected(
        db, INSERT_LINE, {**base, "debit": 100, "credit": 100}, "ck_journal_lines_debit_xor_credit"
    )
    _rejected(
        db, INSERT_LINE, {**base, "debit": 0, "credit": 0}, "ck_journal_lines_debit_xor_credit"
    )
    _rejected(
        db, INSERT_LINE, {**base, "debit": "100.5", "credit": 0}, "ck_journal_lines_pyg_integer"
    )
    _rejected(
        db,
        INSERT_LINE,
        {**base, "debit": -100, "credit": 0},
        "ck_journal_lines_amounts_non_negative",
    )


# --- Reversión, cierre y ejercicios --------------------------------------------------------


def test_reversal_lines_must_mirror_the_original(db: Session, world: dict[str, Any]) -> None:
    wrong = _draft(
        db,
        world,
        [(CAPITAL, 900, 0), (BANCOS, 0, 900)],
        kind="reversal",
        reverses=world["posted"]["id"],
        day="2026-03-10",
    )
    _rejected(
        db, POST, {"user": world["user"], "entry": wrong}, "trg_journal_entries_reversal_mismatch"
    )


def test_closing_entry_only_with_all_periods_closed(db: Session, world: dict[str, Any]) -> None:
    closing = _draft(
        db, world, [(VENTAS, 100, 0), (CAPITAL, 0, 100)], kind="closing", day="2026-12-31"
    )
    _rejected(
        db, POST, {"user": world["user"], "entry": closing}, "trg_journal_entries_closing_invalid"
    )


def test_fiscal_years_do_not_overlap_and_closed_is_final(
    db: Session, world: dict[str, Any]
) -> None:
    _rejected(
        db,
        text(
            "INSERT INTO accounting.fiscal_years (organization_id, start_date, end_date)"
            " VALUES (:org, '2026-07-01', '2027-06-30')"
        ),
        {"org": world["org"]},
        "ex_fiscal_years_no_overlap",
    )
    year = {"y": world["year"]["id"], "u": world["user"]}
    _rejected(
        db,
        text("UPDATE accounting.fiscal_years SET end_date = '2026-11-30' WHERE id = :y"),
        year,
        "trg_fiscal_years_dates_fixed",
    )
    _rejected(
        db,
        text("UPDATE accounting.fiscal_years SET last_entry_number = 0 WHERE id = :y"),
        year,
        "trg_fiscal_years_numbering",
    )
    db.execute(
        text(
            "UPDATE accounting.fiscal_years SET status = 'closed', closed_at = now(),"
            " closed_by = :u WHERE id = :y"
        ),
        year,
    )
    _rejected(
        db,
        text(
            "UPDATE accounting.fiscal_years SET status = 'open', closed_at = NULL,"
            " closed_by = NULL WHERE id = :y"
        ),
        year,
        "trg_fiscal_years_closed_final",
    )
    _rejected(
        db,
        text(
            "UPDATE accounting.periods SET status = 'closed', closed_at = now(), closed_by = :u"
            " WHERE fiscal_year_id = :y"
        ),
        year,
        "trg_periods_year_closed",
    )
    _rejected(
        db,
        text("DELETE FROM accounting.fiscal_years WHERE id = :y"),
        year,
        "trg_fiscal_years_no_delete",
    )


def test_used_ledger_account_keeps_code_and_nature(db: Session, world: dict[str, Any]) -> None:
    account = {"a": world["accounts"][BANCOS]}
    for change in (
        "code = '1.01.01.04.40'",
        "kind = 'liability'",
        "normal_side = 'credit'",
        "is_postable = false",
    ):
        _rejected(
            db,
            text(f"UPDATE accounting.ledger_accounts SET {change} WHERE id = :a"),  # noqa: S608 - texto fijo de la prueba
            account,
            "trg_ledger_accounts_in_use",
        )
    db.execute(
        text("UPDATE accounting.ledger_accounts SET name = 'BANCOS (cambiado)' WHERE id = :a"),
        account,
    )


def test_child_code_extends_the_parent_code(db: Session, world: dict[str, Any]) -> None:
    _rejected(
        db,
        text(
            "INSERT INTO accounting.ledger_accounts (organization_id, code, name, kind,"
            " normal_side, is_postable, origin, parent_id)"
            " VALUES (:org, '1.02.01', 'Mal ubicada', 'asset', 'debit', true, 'user', :parent)"
        ),
        {"org": world["org"], "parent": world["accounts"][GRUPO_DISPONIBILIDADES]},
        "trg_ledger_accounts_parent_prefix",
    )


# --- §5.2: D-035, un movimiento personal no origina asientos -------------------------------


@pytest.fixture
def finance_world(client: TestClient, owner_token: str, world: dict[str, Any]) -> dict[str, Any]:
    biz = business_context(client, owner_token)
    per = personal_context(client, owner_token)
    biz_account = create_account(client, owner_token, biz, "Banco empresa")["id"]
    per_account = create_account(client, owner_token, per, "Banco personal")["id"]
    biz_tx = create_tx(client, owner_token, biz, biz_account, "150000")["id"]
    per_tx = create_tx(client, owner_token, per, per_account, "-50000")["id"]
    return {**world, "biz": biz, "per": per, "biz_tx": biz_tx, "per_tx": per_tx}


def test_entry_from_personal_context_is_rejected_by_database(
    db: Session, finance_world: dict[str, Any]
) -> None:
    w = finance_world
    base = {"kind": "finance", "day": "2026-03-10"}
    _rejected(
        db,
        INSERT_ENTRY,
        _entry_params(w, **base, tx=w["per_tx"], ctx=w["per"], ctx_kind="personal"),
        "ck_journal_entries_source_business_only",
    )
    # Aunque se declare 'business', el contexto personal no lo es: la FK lo rechaza.
    _rejected(
        db,
        INSERT_ENTRY,
        _entry_params(w, **base, tx=w["per_tx"], ctx=w["per"], ctx_kind="business"),
        "fk_journal_entries_source_context_kind_contexts",
    )
    # Y un movimiento personal no se puede atribuir al contexto empresarial.
    _rejected(
        db,
        INSERT_ENTRY,
        _entry_params(w, **base, tx=w["per_tx"], ctx=w["biz"], ctx_kind="business"),
        "fk_journal_entries_source_transaction_id_transactions",
    )
    # El movimiento empresarial sí.
    db.execute(
        INSERT_ENTRY, _entry_params(w, **base, tx=w["biz_tx"], ctx=w["biz"], ctx_kind="business")
    )


def test_source_context_must_belong_to_the_same_organization(
    db: Session, finance_world: dict[str, Any], other_org_account: Any
) -> None:
    w = finance_world
    other_org = db.scalar(
        text("SELECT organization_id FROM accounting.ledger_accounts WHERE id = :a"),
        {"a": other_org_account},
    )
    other_year = db.execute(
        text(
            "INSERT INTO accounting.fiscal_years (organization_id, start_date, end_date)"
            " VALUES (:org, '2026-01-01', '2026-12-31') RETURNING id"
        ),
        {"org": other_org},
    ).scalar_one()
    _rejected(
        db,
        INSERT_ENTRY,
        _entry_params(
            w,
            org=other_org,
            year=other_year,
            kind="finance",
            tx=w["biz_tx"],
            ctx=w["biz"],
            ctx_kind="business",
        ),
        "fk_journal_entries_source_context_org_contexts",
    )


def test_one_live_entry_per_transaction_and_voided_source_cannot_post(
    db: Session, finance_world: dict[str, Any]
) -> None:
    w = finance_world
    source = {"kind": "finance", "tx": w["biz_tx"], "ctx": w["biz"], "ctx_kind": "business"}
    entry_id = _draft(db, w, [(BANCOS, 150000, 0), (VENTAS, 0, 150000)], **source)
    _rejected(db, INSERT_ENTRY, _entry_params(w, **source), "uq_journal_entries_live_source")
    db.execute(
        text(
            "UPDATE finance.transactions SET voided_at = now(), voided_by = :u,"
            " void_reason = 'prueba' WHERE id = :t"
        ),
        {"u": w["user"], "t": w["biz_tx"]},
    )
    _rejected(db, POST, {"user": w["user"], "entry": entry_id}, "trg_journal_entries_source_voided")


def test_periods_are_not_deleted_and_tables_are_not_truncated(
    db: Session, world: dict[str, Any]
) -> None:
    _rejected(
        db,
        text("DELETE FROM accounting.periods WHERE fiscal_year_id = :y"),
        {"y": world["year"]["id"]},
        "trg_periods_no_delete",
    )
    for table in ("journal_lines", "journal_entries", "periods", "fiscal_years"):
        _rejected(db, text(f"TRUNCATE accounting.{table} CASCADE"), {}, f"trg_{table}_no_delete")
