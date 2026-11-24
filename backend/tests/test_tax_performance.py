"""Rendimiento de la fase 4 (spec §5.12): con 20.000 comprobantes en un año, la estimación de
IVA de un mes en menos de 300 ms y el XLSX del año en menos de 3 s.

Excluible con `-m "not slow"`. Los comprobantes se siembran directo en la base copiando uno
cargado por la API (pasan por las restricciones y los triggers).
"""

import statistics
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import auth_header
from tests.tax_utils import TAX, create_voucher, dv, setup_tax

VOUCHERS = 20_000
VAT_LIMIT_MS = 300
XLSX_LIMIT_MS = 3_000
SAMPLES = 5

SEED = text(
    """
    INSERT INTO tax.vouchers (organization_id, context_id, context_kind, direction,
        voucher_type, is_electronic, timbrado, number, issued_on, counterparty_doc_type,
        counterparty_ruc, counterparty_ruc_dv, counterparty_name, condition, currency,
        taxed_10, taxed_5, exempt, vat_10, vat_5, imputes_vat, imputes_ire, imputes_irp,
        vat_rule_version_id, created_by)
    SELECT organization_id, context_id, context_kind, direction, voucher_type, is_electronic,
           timbrado, '002-' || lpad((g / 1000000)::text, 3, '0') || '-'
                        || lpad((g % 10000000)::text, 7, '0'),
           DATE '2026-01-01' + (g % 365), counterparty_doc_type, counterparty_ruc,
           counterparty_ruc_dv, counterparty_name, condition, currency,
           taxed_10 + (g % 50) * 1100, taxed_5, exempt, vat_10 + (g % 50) * 100, vat_5,
           imputes_vat, imputes_ire, imputes_irp, vat_rule_version_id, created_by
    FROM tax.vouchers, generate_series(1, :rows) AS g
    WHERE id = :id
    """
)


def _timed(call: Callable[[], Any]) -> tuple[float, float, float]:
    samples = []
    for n in range(SAMPLES + 1):
        started = time.perf_counter()
        call()
        elapsed = (time.perf_counter() - started) * 1000
        if n:  # la primera es de calentamiento
            samples.append(elapsed)
    return statistics.median(samples), min(samples), max(samples)


@pytest.mark.slow
def test_vat_estimate_and_year_xlsx_with_20000_vouchers(
    client: TestClient, owner_token: str, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    purchase = create_voucher(client, owner_token)
    sale = create_voucher(
        client,
        owner_token,
        direction="sale",
        counterparty_ruc="80000011",
        counterparty_ruc_dv=dv("80000011"),
        taxed_5="21000",
    )
    half = VOUCHERS // 2 - 1
    db.execute(SEED, {"rows": half, "id": purchase["id"]})
    db.execute(SEED, {"rows": half, "id": sale["id"]})
    db.execute(text("ANALYZE tax.vouchers"))
    assert db.scalar(text("SELECT count(*) FROM tax.vouchers")) == VOUCHERS

    headers = auth_header(owner_token)

    def vat() -> None:
        res = client.get(f"{TAX}/vat/2026/10", headers=headers)
        assert res.status_code == 200, res.text

    def xlsx() -> None:
        res = client.get(f"{TAX}/vouchers/export", params={"year": 2026}, headers=headers)
        assert res.status_code == 200, res.text

    vat_ms = _timed(vat)
    xlsx_ms = _timed(xlsx)
    print(f"\nIVA de un mes: mediana {vat_ms[0]:.0f} ms (mín {vat_ms[1]:.0f}, máx {vat_ms[2]:.0f})")
    print(f"XLSX del año: mediana {xlsx_ms[0]:.0f} ms (mín {xlsx_ms[1]:.0f}, máx {xlsx_ms[2]:.0f})")
    assert vat_ms[0] < VAT_LIMIT_MS
    assert xlsx_ms[0] < XLSX_LIMIT_MS
