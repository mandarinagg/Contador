"""Rendimiento de la fase 3B (spec 3B §5.10): una corrida de depreciación con 2.000 bienes en
menos de 1 s y el XLSX del diario con 20.000 líneas en menos de 3 s.

Excluible con `-m "not slow"`. Los bienes y los asientos se siembran directo en la base (los
asientos con los triggers de usuario desactivados dentro de la transacción de la prueba, como
en `test_accounting_performance.py`). Cada medición de la corrida se descarta después, para
que la siguiente vuelva a generar el mismo borrador.
"""

import statistics
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.accounting_utils import ACC, BANCOS
from tests.assets_utils import INFORMATICA, MUEBLES, VEHICULOS, period_id, setup_books
from tests.conftest import auth_header
from tests.test_accounting_performance import CREDIT_CODES, DEBIT_CODES, SEED_ENTRIES, SEED_LINES

ASSETS = 2_000
RUN_LIMIT_MS = 1_000
XLSX_LIMIT_MS = 3_000
JOURNAL_LINES = 20_000
SAMPLES = 5

SEED_ASSETS = text(
    """
    INSERT INTO accounting.fixed_assets (organization_id, category_id, name, acquired_on,
        start_rule, depreciation_start, cost, residual_value, useful_life_months,
        fiscal_useful_life_months, fiscal_residual_rate, fiscal_residual_value, created_by)
    SELECT :org, (CAST(:categories AS uuid[]))[g % 3 + 1], 'Bien sembrado ' || g,
           DATE '2025-01-15', 'next_month',
           CAST(DATE '2025-02-01' + make_interval(months => g % 10) AS date),
           1000000 + g * 1000, 0, 24 + g % 37, 60, 10, (1000000 + g * 1000) / 10, :user
    FROM generate_series(1, :rows) AS g
    """
)


def _timed(call: Callable[[], Any], after: Callable[[Any], None]) -> tuple[float, float, float]:
    samples = []
    for n in range(SAMPLES + 1):
        started = time.perf_counter()
        result = call()
        elapsed = (time.perf_counter() - started) * 1000
        after(result)
        if n:  # la primera es de calentamiento
            samples.append(elapsed)
    return statistics.median(samples), min(samples), max(samples)


@pytest.mark.slow
def test_depreciation_run_with_2000_assets(
    client: TestClient, owner_token: str, db: Session
) -> None:
    books = setup_books(client, owner_token, (2025, 2026))
    headers = auth_header(owner_token)
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    org_id = db.scalar(text("SELECT id FROM core.organizations"))
    categories = [books["categories"][c]["id"] for c in (MUEBLES, INFORMATICA, VEHICULOS)]
    db.execute(
        SEED_ASSETS, {"org": org_id, "categories": categories, "user": user_id, "rows": ASSETS}
    )
    db.execute(text("ANALYZE accounting.fixed_assets"))
    # Todos los meses de 2025 ya corridos para los bienes que empiezan antes (orden: D-058):
    # se mide el primer mes en que entran los 2.000.
    for month in range(2, 13):
        res = client.post(
            f"{ACC}/depreciation/run",
            json={"period_id": period_id(books, 2025, month)},
            headers=headers,
        )
        assert res.status_code == 201, res.text
        assert (
            client.post(f"{ACC}/entries/{res.json()['entry_id']}/post", headers=headers).status_code
            == 200
        )
    target = period_id(books, 2026, 1)

    def run() -> Any:
        res = client.post(f"{ACC}/depreciation/run", json={"period_id": target}, headers=headers)
        assert res.status_code == 201, res.text
        return res.json()

    def discard(created: Any) -> None:
        assert len(created["items"]) == ASSETS
        res = client.post(
            f"{ACC}/entries/{created['entry_id']}/discard",
            json={"reason": "Medición"},
            headers=headers,
        )
        assert res.status_code == 200, res.text

    median, low, high = _timed(run, discard)
    print(
        f"\n[rendimiento] corrida de {ASSETS} bienes: mediana {median:.0f} ms"
        f" (mín {low:.0f}, máx {high:.0f})"
    )
    assert median < RUN_LIMIT_MS, f"la corrida tardó {median:.0f} ms"


@pytest.mark.slow
def test_journal_xlsx_with_20000_lines(client: TestClient, owner_token: str, db: Session) -> None:
    books = setup_books(client, owner_token, (2025, 2026))
    accounts = books["accounts"]
    headers = auth_header(owner_token)
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    org_id = db.scalar(text("SELECT id FROM core.organizations"))
    for table in ("journal_entries", "journal_lines"):
        db.execute(text(f"ALTER TABLE accounting.{table} DISABLE TRIGGER USER"))
    db.execute(
        SEED_ENTRIES,
        {
            "org": org_id,
            "y2025": books["years"][2025]["id"],
            "y2026": books["years"][2026]["id"],
            "user": user_id,
            "rows": JOURNAL_LINES,  # mitad en cada ejercicio, dos líneas por asiento
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
    for table in ("journal_entries", "journal_lines"):
        db.execute(text(f"ALTER TABLE accounting.{table} ENABLE TRIGGER USER"))
    db.execute(text("ANALYZE accounting.journal_entries"))
    db.execute(text("ANALYZE accounting.journal_lines"))
    lines = db.scalar(
        text(
            "SELECT count(*) FROM accounting.journal_lines l JOIN accounting.journal_entries e"
            " ON e.id = l.entry_id WHERE e.fiscal_year_id = :y"
        ),
        {"y": books["years"][2026]["id"]},
    )
    assert lines == JOURNAL_LINES

    def export() -> Any:
        res = client.get(
            f"{ACC}/reports/journal",
            params={"from": "2026-01-01", "to": "2026-12-31", "format": "xlsx"},
            headers=headers,
        )
        assert res.status_code == 200
        return res.content

    def check(content: Any) -> None:
        assert content[:2] == b"PK"

    median, low, high = _timed(export, check)
    print(
        f"\n[rendimiento] XLSX del diario con {JOURNAL_LINES} líneas: mediana {median:.0f} ms"
        f" (mín {low:.0f}, máx {high:.0f})"
    )
    assert median < XLSX_LIMIT_MS, f"el XLSX del diario tardó {median:.0f} ms"
