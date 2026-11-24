"""La **base** rechaza lo prohibido de la fase 3B, con SQL directo (spec 3B §5; D-057 a D-061).

Igual que `test_accounting_db_triggers.py`: se escribe sin pasar por el servicio y el
rechazo se reconoce por el nombre estable del trigger (`diag.constraint_name`). El estado
inicial (plan, ejercicio, categorías, un bien, una corrida en borrador, un centro de costos y
una plantilla recurrente con su borrador) se arma por la API.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.accounting_utils import ACC, BANCOS, CAPITAL, HONORARIOS, VENTAS, posted
from tests.assets_utils import new_asset, period_id, run, setup_books
from tests.conftest import auth_header
from tests.finance_utils import ok
from tests.test_accounting_db_triggers import INSERT_ENTRY, POST, _rejected

INSERT_CENTER_LINE = text(
    """
    INSERT INTO accounting.journal_lines (organization_id, entry_id, line_no, account_id,
        debit, credit, cost_center_id)
    VALUES (:org, :entry, :line_no, :account, :debit, :credit, :center)
    """
)


@pytest.fixture
def w(client: TestClient, owner_token: str, db: Session) -> dict[str, Any]:
    books = setup_books(client, owner_token, (2026,))
    headers = auth_header(owner_token)
    posted_entry = posted(
        client,
        owner_token,
        books["accounts"],
        "2026-01-05",
        [(BANCOS, 1000, 0), (CAPITAL, 0, 1000)],
    )
    asset = new_asset(client, books)
    feb_run = ok(run(client, books, 2026, 2), 201)
    center = ok(
        client.post(f"{ACC}/cost-centers", json={"code": "ADM", "name": "Adm."}, headers=headers),
        201,
    )
    template = ok(
        client.post(
            f"{ACC}/recurring",
            json={
                "description": "Alquiler",
                "day_of_month": 5,
                "start_date": "2026-01-01",
                "lines": [
                    {"account_id": books["accounts"][HONORARIOS]["id"], "debit": "10"},
                    {"account_id": books["accounts"][BANCOS]["id"], "credit": "10"},
                ],
            },
            headers=headers,
        ),
        201,
    )
    generated = ok(
        client.post(
            f"{ACC}/recurring/generate",
            json={"period_id": period_id(books, 2026, 3)},
            headers=headers,
        )
    )["created"][0]
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    org_id = db.scalar(text("SELECT id FROM core.organizations"))
    return {
        "books": books,
        "accounts": {code: a["id"] for code, a in books["accounts"].items()},
        "year": books["years"][2026],
        "posted": posted_entry,
        "asset": asset,
        "run": feb_run,
        "center": center,
        "template": template,
        "generated": generated,
        "user": user_id,
        "org": org_id,
    }


def _entry(db: Session, w: dict[str, Any], kind: str = "manual", **kw: Any) -> Any:
    params = {
        "org": w["org"],
        "year": w["year"]["id"],
        "day": "2026-04-15",
        "kind": kind,
        "user": w["user"],
        "status": "draft",
        "number": None,
        "tx": None,
        "ctx": None,
        "ctx_kind": None,
        "reverses": None,
        **kw,
    }
    return db.execute(INSERT_ENTRY, params).scalar_one()


def _line(
    db: Session,
    w: dict[str, Any],
    entry: Any,
    n: int,
    code: str,
    debit: int,
    credit: int,
    center: Any = None,
) -> None:
    db.execute(
        INSERT_CENTER_LINE,
        {
            "org": w["org"],
            "entry": entry,
            "line_no": n,
            "account": w["accounts"][code],
            "debit": debit,
            "credit": credit,
            "center": center,
        },
    )


def _balanced(db: Session, w: dict[str, Any], kind: str = "manual", **kw: Any) -> Any:
    entry = _entry(db, w, kind, **kw)
    _line(db, w, entry, 1, HONORARIOS, 100, 0)
    _line(db, w, entry, 2, BANCOS, 0, 100)
    return entry


def _status(db: Session, table: str, row_id: Any) -> str:
    query = text(f"SELECT entry_status FROM accounting.{table} WHERE id = :id")  # noqa: S608
    return str(db.scalar(query, {"id": row_id}))


# --- Centros de costos (D-060) ----------------------------------------------------------


def test_center_on_asset_or_liability_line_is_rejected(db: Session, w: dict[str, Any]) -> None:
    entry = _entry(db, w)
    params = {
        "org": w["org"],
        "entry": entry,
        "line_no": 1,
        "account": w["accounts"][BANCOS],
        "debit": 100,
        "credit": 0,
        "center": w["center"]["id"],
    }
    _rejected(db, INSERT_CENTER_LINE, params, "trg_journal_lines_cost_center_account")
    _rejected(
        db,
        INSERT_CENTER_LINE,
        {**params, "account": w["accounts"]["2.01.01.01"]},
        "trg_journal_lines_cost_center_account",
    )
    # En una cuenta de ingreso sí va.
    _line(db, w, entry, 1, VENTAS, 0, 100, w["center"]["id"])
    # Y tampoco se cambia después la cuenta de la línea por una de activo.
    _rejected(
        db,
        text(
            "UPDATE accounting.journal_lines SET account_id = :acc"
            " WHERE entry_id = :entry AND line_no = 1"
        ),
        {"acc": w["accounts"][BANCOS], "entry": entry},
        "trg_journal_lines_cost_center_account",
    )


def test_archived_center_is_rejected_except_in_a_reversal(db: Session, w: dict[str, Any]) -> None:
    db.execute(
        text("UPDATE accounting.cost_centers SET archived_at = now() WHERE id = :id"),
        {"id": w["center"]["id"]},
    )
    entry = _entry(db, w)
    params = {
        "org": w["org"],
        "entry": entry,
        "line_no": 1,
        "account": w["accounts"][HONORARIOS],
        "debit": 100,
        "credit": 0,
        "center": w["center"]["id"],
    }
    _rejected(db, INSERT_CENTER_LINE, params, "trg_journal_lines_cost_center_archived")
    reversal = _entry(db, w, "reversal", reverses=w["posted"]["id"])
    db.execute(INSERT_CENTER_LINE, {**params, "entry": reversal})


def test_reversal_must_keep_the_cost_centers(db: Session, w: dict[str, Any]) -> None:
    original = _entry(db, w)
    _line(db, w, original, 1, HONORARIOS, 100, 0, w["center"]["id"])
    _line(db, w, original, 2, BANCOS, 0, 100)
    db.execute(POST, {"user": w["user"], "entry": original})
    # Mismas cuentas e importes invertidos, pero sin el centro: no es la reversión.
    wrong = _entry(db, w, "reversal", reverses=original)
    _line(db, w, wrong, 1, HONORARIOS, 0, 100)
    _line(db, w, wrong, 2, BANCOS, 100, 0)
    _rejected(
        db, POST, {"user": w["user"], "entry": wrong}, "trg_journal_entries_reversal_mismatch"
    )
    db.execute(
        text(
            "UPDATE accounting.journal_lines SET cost_center_id = :c"
            " WHERE entry_id = :e AND line_no = 1"
        ),
        {"c": w["center"]["id"], "e": wrong},
    )
    db.execute(POST, {"user": w["user"], "entry": wrong})


def test_generated_entries_can_be_reversed(db: Session, w: dict[str, Any]) -> None:
    """La 0004 amplía los tipos reversibles: depreciación, baja y recurrente."""
    entry_id = w["run"]["entry_id"]
    db.execute(POST, {"user": w["user"], "entry": entry_id})
    lines = db.execute(
        text(
            "SELECT account_id, debit, credit FROM accounting.journal_lines"
            " WHERE entry_id = :e ORDER BY line_no"
        ),
        {"e": entry_id},
    ).all()
    reversal = _entry(db, w, "reversal", reverses=entry_id, day="2026-02-28")
    for n, (account, debit, credit) in enumerate(lines, start=1):
        db.execute(
            INSERT_CENTER_LINE,
            {
                "org": w["org"],
                "entry": reversal,
                "line_no": n,
                "account": account,
                "debit": credit,
                "credit": debit,
                "center": None,
            },
        )
    db.execute(POST, {"user": w["user"], "entry": reversal})
    db.execute(
        text("UPDATE accounting.journal_entries SET status = 'reversed' WHERE id = :e"),
        {"e": entry_id},
    )
    assert _status(db, "depreciation_runs", w["run"]["id"]) == "reversed"


def test_required_center_is_checked_on_post(db: Session, w: dict[str, Any]) -> None:
    db.execute(
        text(
            "UPDATE accounting.settings SET cost_centers_required = true"
            " WHERE organization_id = :org"
        ),
        {"org": w["org"]},
    )
    entry = _balanced(db, w)
    _rejected(
        db, POST, {"user": w["user"], "entry": entry}, "trg_journal_entries_cost_center_required"
    )
    for kind in ("recurring",):  # `finance` exige movimiento de origen; mismo camino
        other = _balanced(db, w, kind)
        _rejected(
            db,
            POST,
            {"user": w["user"], "entry": other},
            "trg_journal_entries_cost_center_required",
        )
    ok_entry = _entry(db, w)
    _line(db, w, ok_entry, 1, HONORARIOS, 100, 0, w["center"]["id"])
    _line(db, w, ok_entry, 2, BANCOS, 0, 100)
    db.execute(POST, {"user": w["user"], "entry": ok_entry})


# --- Depreciación (D-057, D-058) --------------------------------------------------------


def test_depreciation_entry_must_match_its_items(db: Session, w: dict[str, Any]) -> None:
    entry_id = w["run"]["entry_id"]
    db.execute(
        text(
            "UPDATE accounting.journal_lines SET debit = debit + 1"
            " WHERE entry_id = :e AND debit > 0"
        ),
        {"e": entry_id},
    )
    db.execute(
        text(
            "UPDATE accounting.journal_lines SET credit = credit + 1"
            " WHERE entry_id = :e AND credit > 0"
        ),
        {"e": entry_id},
    )
    _rejected(
        db,
        POST,
        {"user": w["user"], "entry": entry_id},
        "trg_journal_entries_depreciation_mismatch",
    )
    # Un asiento de depreciación sin corrida tampoco se contabiliza.
    lone = _balanced(db, w, "depreciation")
    _rejected(
        db, POST, {"user": w["user"], "entry": lone}, "trg_journal_entries_depreciation_mismatch"
    )


def test_disposal_entry_needs_its_asset(db: Session, w: dict[str, Any]) -> None:
    entry = _balanced(db, w, "disposal")
    _rejected(db, POST, {"user": w["user"], "entry": entry}, "trg_journal_entries_disposal_orphan")


def test_run_status_follows_its_entry_and_cannot_be_faked(db: Session, w: dict[str, Any]) -> None:
    run_id, entry_id = w["run"]["id"], w["run"]["entry_id"]
    assert _status(db, "depreciation_runs", run_id) == "draft"
    db.execute(
        text("UPDATE accounting.depreciation_runs SET entry_status = 'discarded' WHERE id = :id"),
        {"id": run_id},
    )
    assert _status(db, "depreciation_runs", run_id) == "draft"
    db.execute(POST, {"user": w["user"], "entry": entry_id})
    assert _status(db, "depreciation_runs", run_id) == "posted"
    _rejected(
        db,
        text("UPDATE accounting.depreciation_runs SET period_id = :p WHERE id = :id"),
        {"p": period_id(w["books"], 2026, 3), "id": run_id},
        "trg_depreciation_runs_immutable",
    )
    gen_id = db.scalar(
        text("SELECT id FROM accounting.recurring_generations WHERE entry_id = :e"),
        {"e": w["generated"]["id"]},
    )
    db.execute(
        text(
            "UPDATE accounting.journal_entries SET status = 'discarded', discarded_by = :u,"
            " discarded_at = now(), discard_reason = 'SQL' WHERE id = :e"
        ),
        {"u": w["user"], "e": w["generated"]["id"]},
    )
    assert _status(db, "recurring_generations", gen_id) == "discarded"


INSERT_RUN = text(
    """
    INSERT INTO accounting.depreciation_runs (organization_id, period_id, entry_id, created_by)
    VALUES (:org, :period, :entry, :user)
    """
)
INSERT_GENERATION = text(
    """
    INSERT INTO accounting.recurring_generations (organization_id, template_id, period_id,
        entry_id, created_by)
    VALUES (:org, :template, :period, :entry, :user)
    """
)


def test_run_and_generation_need_a_fresh_draft_of_their_kind(
    db: Session, w: dict[str, Any]
) -> None:
    april = period_id(w["books"], 2026, 4)
    base = {"org": w["org"], "period": april, "user": w["user"]}
    manual = _balanced(db, w)
    _rejected(db, INSERT_RUN, {**base, "entry": manual}, "trg_depreciation_runs_entry_invalid")
    _rejected(
        db,
        INSERT_RUN,
        {**base, "entry": w["posted"]["id"]},
        "trg_depreciation_runs_entry_invalid",
    )
    dep = _balanced(db, w, "depreciation")
    _rejected(
        db,
        INSERT_RUN,
        {**base, "entry": dep, "period": period_id(w["books"], 2026, 5)},
        "trg_depreciation_runs_period_mismatch",
    )
    gen = {**base, "template": w["template"]["id"]}
    _rejected(
        db, INSERT_GENERATION, {**gen, "entry": manual}, "trg_recurring_generations_entry_invalid"
    )
    rec = _balanced(db, w, "recurring")
    _rejected(
        db,
        INSERT_GENERATION,
        {**gen, "entry": rec, "period": period_id(w["books"], 2026, 6)},
        "trg_recurring_generations_period_mismatch",
    )
    db.execute(INSERT_GENERATION, {**gen, "entry": rec})


def test_one_live_run_per_period_and_generation_per_template(
    db: Session, w: dict[str, Any]
) -> None:
    feb = period_id(w["books"], 2026, 2)
    other = _entry(db, w, "depreciation", day="2026-02-28")
    _rejected(
        db,
        INSERT_RUN,
        {"org": w["org"], "period": feb, "user": w["user"], "entry": other},
        "uq_depreciation_runs_live_period",
    )
    rec = _entry(db, w, "recurring", day="2026-03-05")
    _rejected(
        db,
        INSERT_GENERATION,
        {
            "org": w["org"],
            "template": w["template"]["id"],
            "period": period_id(w["books"], 2026, 3),
            "user": w["user"],
            "entry": rec,
        },
        "uq_recurring_generations_live",
    )


def test_items_only_while_draft_and_never_change(db: Session, w: dict[str, Any]) -> None:
    item_id = db.scalar(
        text("SELECT id FROM accounting.depreciation_items WHERE run_id = :r"),
        {"r": w["run"]["id"]},
    )
    _rejected(
        db,
        text("UPDATE accounting.depreciation_items SET amount = amount + 1 WHERE id = :id"),
        {"id": item_id},
        "trg_depreciation_items_immutable",
    )
    _rejected(
        db,
        text("DELETE FROM accounting.depreciation_items WHERE id = :id"),
        {"id": item_id},
        "trg_depreciation_items_immutable",
    )
    db.execute(POST, {"user": w["user"], "entry": w["run"]["entry_id"]})
    _rejected(
        db,
        text(
            "INSERT INTO accounting.depreciation_items (organization_id, run_id, asset_id,"
            " installment, amount) VALUES (:org, :run, :asset, 2, 1)"
        ),
        {"org": w["org"], "run": w["run"]["id"], "asset": w["asset"]["id"]},
        "trg_depreciation_items_entry_not_draft",
    )


def test_depreciated_asset_keeps_its_parameters(db: Session, w: dict[str, Any]) -> None:
    for column, value in (
        ("cost", "cost + 1"),
        ("useful_life_months", "useful_life_months + 1"),
        ("residual_value", "residual_value + 1"),
        ("depreciation_start", "depreciation_start + 31"),
        ("fiscal_residual_rate", "0"),
    ):
        _rejected(
            db,
            text(f"UPDATE accounting.fixed_assets SET {column} = {value} WHERE id = :id"),  # noqa: S608
            {"id": w["asset"]["id"]},
            "trg_fixed_assets_depreciated",
        )
    db.execute(
        text("UPDATE accounting.fixed_assets SET name = 'Otro nombre' WHERE id = :id"),
        {"id": w["asset"]["id"]},
    )
    # Descartada la corrida, se puede corregir.
    db.execute(
        text(
            "UPDATE accounting.journal_entries SET status = 'discarded', discarded_by = :u,"
            " discarded_at = now(), discard_reason = 'SQL' WHERE id = :e"
        ),
        {"u": w["user"], "e": w["run"]["entry_id"]},
    )
    db.execute(
        text("UPDATE accounting.fixed_assets SET cost = cost + 1 WHERE id = :id"),
        {"id": w["asset"]["id"]},
    )


def test_year_values_are_immutable(db: Session, w: dict[str, Any]) -> None:
    row = db.execute(
        text(
            "INSERT INTO accounting.asset_year_values (organization_id, asset_id, fiscal_year_id,"
            " fiscal_net_value, accounting_net_value, fiscal_depreciation,"
            " accounting_depreciation) VALUES (:org, :asset, :year, 1, 1, 0, 0) RETURNING id"
        ),
        {"org": w["org"], "asset": w["asset"]["id"], "year": w["year"]["id"]},
    ).scalar_one()
    _rejected(
        db,
        text("UPDATE accounting.asset_year_values SET fiscal_net_value = 2 WHERE id = :id"),
        {"id": row},
        "trg_asset_year_values_immutable",
    )
    _rejected(
        db,
        text("DELETE FROM accounting.asset_year_values WHERE id = :id"),
        {"id": row},
        "trg_asset_year_values_no_delete",
    )


NO_DELETE = (
    "asset_categories",
    "fixed_assets",
    "depreciation_runs",
    "cost_centers",
    "recurring_templates",
    "recurring_generations",
)
NO_TRUNCATE = (*NO_DELETE, "asset_year_values")


def test_new_tables_are_not_deleted_nor_truncated(db: Session, w: dict[str, Any]) -> None:
    for table in NO_DELETE:
        _rejected(db, text(f"DELETE FROM accounting.{table}"), {}, f"trg_{table}_no_delete")  # noqa: S608
    for table in NO_TRUNCATE:
        _rejected(db, text(f"TRUNCATE accounting.{table} CASCADE"), {}, f"trg_{table}_no_delete")
    _rejected(
        db,
        text("TRUNCATE accounting.depreciation_items"),
        {},
        "trg_depreciation_items_no_delete",
    )


def test_sql_post_of_valid_run_is_accepted(db: Session, w: dict[str, Any]) -> None:
    db.execute(POST, {"user": w["user"], "entry": w["run"]["entry_id"]})
    assert _status(db, "depreciation_runs", w["run"]["id"]) == "posted"
