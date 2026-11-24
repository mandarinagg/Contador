"""Rendimiento de los reportes con 100.000 líneas contabilizadas (spec §5.12).

Excluible con `-m "not slow"`. La siembra escribe directo en la base con los triggers de
usuario **desactivados dentro de la transacción de la prueba** (que se revierte al final):
contabilizar 50.000 asientos uno por uno en una sola transacción actualizaría 50.000 veces la
misma fila del ejercicio (la numeración), y eso mide la siembra, no los reportes. Los
números se ponen correlativos por ejercicio, como los habría asignado el trigger.
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.accounting_utils import ACC, BANCOS, create_year, load_chart
from tests.conftest import auth_header
from tests.test_finance_performance import LIMIT_MS, _measure

ENTRIES = 50_000  # dos líneas cada uno: 100.000 líneas
LEDGER_LINES = 20_000
TABLES = ("journal_entries", "journal_lines")
DEBIT_CODES = ["1.01.01.02", "1.01.03.01", "11.04", "11.05", "11.06", "15.01", "1.02.04.03"]
CREDIT_CODES = ["4.01.01.01", "4.99", "2.01.01.01", "2.01.02.01", "3.01.01.01", "1.02.04.99"]

SEED_ENTRIES = text(
    """
    INSERT INTO accounting.journal_entries (organization_id, fiscal_year_id, entry_date, kind,
        description, created_by, status, number, posted_by, posted_at)
    SELECT :org,
           CASE WHEN g % 2 = 0 THEN CAST(:y2026 AS uuid) ELSE CAST(:y2025 AS uuid) END,
           CASE WHEN g % 2 = 0 THEN DATE '2026-01-01' ELSE DATE '2025-01-01' END + (g / 2) % 365,
           'manual', 'Asiento sembrado ' || g, :user, 'posted', (g + 1) / 2, :user, now()
    FROM generate_series(1, :rows) AS g
    """
)
SEED_LINES = text(
    """
    INSERT INTO accounting.journal_lines (organization_id, entry_id, line_no, account_id,
        debit, credit)
    SELECT e.organization_id, e.id, side.line_no,
           CASE WHEN side.line_no = 1 THEN
                CASE WHEN e.number % 5 < 2 THEN CAST(:bank AS uuid)
                     ELSE (CAST(:debits AS uuid[]))[e.number % :n_debits + 1] END
                ELSE (CAST(:credits AS uuid[]))[e.number % :n_credits + 1] END,
           CASE WHEN side.line_no = 1 THEN 1000 * (e.number % 900 + 1) ELSE 0 END,
           CASE WHEN side.line_no = 2 THEN 1000 * (e.number % 900 + 1) ELSE 0 END
    FROM accounting.journal_entries e CROSS JOIN (VALUES (1), (2)) AS side(line_no)
    WHERE e.organization_id = :org
    """
)


@pytest.mark.slow
def test_reports_with_100k_posted_lines(client: TestClient, owner_token: str, db: Session) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    years = {y: create_year(client, owner_token, y)["id"] for y in (2025, 2026)}
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    org_id = db.scalar(text("SELECT id FROM core.organizations"))

    started = time.perf_counter()
    for table in TABLES:
        db.execute(text(f"ALTER TABLE accounting.{table} DISABLE TRIGGER USER"))
    db.execute(
        SEED_ENTRIES,
        {
            "org": org_id,
            "y2025": years[2025],
            "y2026": years[2026],
            "user": user_id,
            "rows": ENTRIES,
        },
    )
    db.execute(
        SEED_LINES,
        {
            "org": org_id,
            "bank": accounts[BANCOS]["id"],
            "debits": [accounts[c]["id"] for c in DEBIT_CODES],
            "credits": [accounts[c]["id"] for c in CREDIT_CODES],
            "n_debits": len(DEBIT_CODES),
            "n_credits": len(CREDIT_CODES),
        },
    )
    for table in TABLES:
        db.execute(text(f"ALTER TABLE accounting.{table} ENABLE TRIGGER USER"))
    db.execute(text("ANALYZE accounting.journal_entries"))
    db.execute(text("ANALYZE accounting.journal_lines"))
    seed_s = time.perf_counter() - started
    lines, bank_lines = db.execute(
        text(
            "SELECT count(*), count(*) FILTER (WHERE account_id = :bank)"
            " FROM accounting.journal_lines"
        ),
        {"bank": accounts[BANCOS]["id"]},
    ).one()
    assert (lines, bank_lines) == (2 * ENTRIES, LEDGER_LINES)

    def trial_balance() -> None:
        res = client.get(
            f"{ACC}/reports/trial-balance",
            params={"from": "2026-01-01", "to": "2026-12-31"},
            headers=headers,
        )
        assert res.status_code == 200 and res.json()["balanced"] is True

    def ledger_first_page() -> None:
        res = client.get(
            f"{ACC}/reports/ledger/{accounts[BANCOS]['id']}",
            params={"from": "2025-01-01", "to": "2026-12-31"},
            headers=headers,
        )
        assert res.status_code == 200 and len(res.json()["movements"]) == 200

    def balance_sheet() -> None:
        res = client.get(
            f"{ACC}/reports/balance-sheet", params={"at": "2026-12-31"}, headers=headers
        )
        assert res.status_code == 200 and res.json()["balanced"] is True

    trial = _measure(trial_balance)
    ledger = _measure(ledger_first_page)
    sheet = _measure(balance_sheet)
    print(  # se ve con `pytest -s`; queda en el informe de la fase
        f"\n[rendimiento] siembra {2 * ENTRIES} líneas: {seed_s:.2f} s"
        f"\n[rendimiento] balance de comprobación anual: {trial}"
        f"\n[rendimiento] mayor de {LEDGER_LINES} líneas (primera página): {ledger}"
        f"\n[rendimiento] balance general: {sheet}"
    )
    assert trial.median < LIMIT_MS, f"balance de comprobación tardó {trial}"
    assert ledger.median < LIMIT_MS, f"libro mayor tardó {ledger}"
    assert sheet.median < LIMIT_MS, f"balance general tardó {sheet}"
