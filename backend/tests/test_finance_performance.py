"""Rendimiento con 100.000 movimientos (spec §5.11). Excluible con `-m "not slow"`."""

import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import auth_header
from tests.finance_utils import API, business_context, create_account, ok

# Requisito de la spec (§5.11). Se puede endurecer para ver el margen real:
# `CONTADOR_PERF_LIMIT_MS=120 pytest -m slow -s tests/test_finance_performance.py`.
LIMIT_MS = float(os.environ.get("CONTADOR_PERF_LIMIT_MS", "300"))
MARGIN_TARGET_MS = 120.0  # objetivo de margen para el resumen (informativo, no falla)
ROWS = 100_000
WARMUPS = 2
RUNS = 9

SEED = text(
    """
    INSERT INTO finance.transactions (context_id, account_id, currency, booked_on, amount,
        description, category_id, source, dedupe_key, created_by, reviewed_at)
    SELECT :ctx,
           CASE WHEN g % 2 = 0 THEN CAST(:a1 AS uuid) ELSE CAST(:a2 AS uuid) END,
           'PYG',
           DATE '2026-11-24' - (g % 730),
           CASE WHEN g % 3 = 0 THEN 1000 * (g % 500 + 1) ELSE -1000 * (g % 300 + 1) END,
           'Movimiento sembrado ' || g,
           CASE WHEN g % 3 <> 0 THEN CAST(:cat AS uuid) END,
           'manual',
           sha256(convert_to(g::text, 'UTF8')),
           :user_id,
           now()
    FROM generate_series(1, :rows) AS g
    """
)


@dataclass
class Timing:
    median: float
    low: float
    high: float

    def __str__(self) -> str:
        return f"mediana {self.median:.1f} ms (mín {self.low:.1f}, máx {self.high:.1f})"


def _measure(call: Callable[[], object], runs: int = RUNS) -> Timing:
    """Calentamiento (planes, caché de la conexión, importaciones) y mediana de varias corridas.

    La mediana tolera algunas corridas lentas por carga de la máquina; mín y máx se imprimen
    para ver cuánta dispersión hubo.
    """
    for _ in range(WARMUPS):
        call()
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    return Timing(statistics.median(samples), min(samples), max(samples))


@pytest.mark.slow
def test_first_page_and_yearly_summary_with_100k_transactions(
    client: TestClient, owner_token: str, db: Session
) -> None:
    headers = auth_header(owner_token)
    biz = business_context(client, owner_token)
    a1 = create_account(client, owner_token, biz, "Banco 1")["id"]
    a2 = create_account(client, owner_token, biz, "Banco 2")["id"]
    category = ok(
        client.post(
            f"{API}/contexts/{biz}/categories",
            json={"name": "Gastos varios", "kind": "expense"},
            headers=headers,
        ),
        201,
    )["id"]
    user_id = db.scalar(text("SELECT id FROM core.users WHERE email = 'owner@example.com'"))
    started = time.perf_counter()
    db.execute(
        SEED, {"ctx": biz, "a1": a1, "a2": a2, "cat": category, "user_id": user_id, "rows": ROWS}
    )
    db.execute(text("ANALYZE finance.transactions"))
    seed_s = time.perf_counter() - started
    count = db.scalar(
        text("SELECT count(*) FROM finance.transactions WHERE context_id = :c"), {"c": biz}
    )
    assert count == ROWS

    def first_page() -> None:
        res = client.get(f"{API}/contexts/{biz}/transactions", headers=headers)
        assert res.status_code == 200 and len(res.json()) == 50

    def yearly_summary() -> None:
        res = client.get(
            f"{API}/contexts/{biz}/summary",
            params={"from": "2025-12-01", "to": "2026-11-30"},
            headers=headers,
        )
        assert res.status_code == 200
        assert len(res.json()["by_month"]) == 12

    page = _measure(first_page)
    summary = _measure(yearly_summary)
    margin = "cumple" if summary.median < MARGIN_TARGET_MS else "NO cumple"
    print(  # se ve con `pytest -s`; queda en el informe de la fase
        f"\n[rendimiento] siembra {ROWS} filas: {seed_s:.2f} s"
        f"\n[rendimiento] GET /transactions (primera página): {page}"
        f"\n[rendimiento] GET /summary 12 meses: {summary}"
        f"\n[rendimiento] objetivo de margen < {MARGIN_TARGET_MS:.0f} ms: {margin}"
    )
    assert page.median < LIMIT_MS, f"GET /transactions tardó {page}"
    assert summary.median < LIMIT_MS, f"GET /summary tardó {summary}"
