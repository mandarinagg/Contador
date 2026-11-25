"""Libros y estados en XLSX (spec 3B §5.8; D-063, D-076).

Cada reporte se abre con `openpyxl`: trae la razón social, el título, el aviso del plan sin
validar, totales iguales a los del JSON del mismo reporte, e importes numéricos (enteros con
formato `#,##0`), nunca texto.
"""

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.modules.accounting.asset_schedule import MONEY_COLUMNS
from app.modules.accounting.exports import (
    DATE_FORMAT,
    MONEY_FORMAT,
    UNVALIDATED_NOTICE,
    XLSX_MEDIA_TYPE,
)
from tests.accounting_utils import ACC, BANCOS, CAPITAL, HONORARIOS, VENTAS, posted
from tests.assets_utils import months, new_asset, run_and_post, setup_books
from tests.conftest import auth_header
from tests.finance_utils import ok

RANGE = {"from": "2026-01-01", "to": "2026-12-31"}


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    books = setup_books(client, owner_token, (2026,))
    accounts = books["accounts"]
    for day, lines in (
        ("2026-01-02", [(BANCOS, 80_000_000, 0), (CAPITAL, 0, 80_000_000)]),
        ("2026-01-15", [("1.02.04.03", 10_000_000, 0), (BANCOS, 0, 10_000_000)]),
        ("2026-02-10", [(BANCOS, 3_300_000, 0), (VENTAS, 0, 3_300_000)]),
        ("2026-03-05", [(HONORARIOS, 1_250_001, 0), (BANCOS, 0, 1_250_001)]),
    ):
        posted(client, owner_token, accounts, day, lines)
    new_asset(client, books)
    for y, m in months(date(2026, 2, 1), 3):
        run_and_post(client, books, y, m)
    return books


def _get(client: TestClient, books: dict[str, Any], path: str, **params: Any) -> Any:
    return client.get(f"{ACC}{path}", params=params, headers=auth_header(books["token"]))


def _sheet(client: TestClient, books: dict[str, Any], path: str, **params: Any) -> Worksheet:
    res = _get(client, books, path, format="xlsx", **params)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == XLSX_MEDIA_TYPE
    assert res.headers["content-disposition"].startswith("attachment; filename=")
    ws = load_workbook(io.BytesIO(res.content)).active
    assert ws is not None
    return ws


def _header(ws: Worksheet, title: str) -> list[Any]:
    first = [row[0] for row in ws.iter_rows(min_row=1, max_row=8, values_only=True)]
    assert first[0] == "Empresa de Prueba EAS"
    assert first[1] == "RUC: sin cargar"
    assert first[2] == title
    assert UNVALIDATED_NOTICE in first
    return first


def _row(ws: Worksheet, label: str, column: int = 0) -> list[Any]:
    for row in ws.iter_rows():
        if row[column].value == label:
            return list(row)
    raise AssertionError(f"Sin fila {label!r}")


def _money(cells: list[Any]) -> list[int]:
    """Importes de la fila: tienen que ser enteros con el formato de guaraníes."""
    values = []
    for cell in cells:
        if cell.value is None or isinstance(cell.value, str):
            continue
        assert isinstance(cell.value, int) and not isinstance(cell.value, bool), cell.value
        assert cell.number_format == MONEY_FORMAT
        values.append(cell.value)
    return values


def _no_text_amounts(ws: Worksheet, first_money_column: int) -> None:
    for row in ws.iter_rows(min_row=10):
        for cell in row[first_money_column:]:
            if isinstance(cell.value, str):
                assert not cell.value.replace(".", "").isdigit(), cell.value


def test_journal_xlsx(client: TestClient, books: dict[str, Any]) -> None:
    data = ok(_get(client, books, "/reports/journal", **RANGE))
    ws = _sheet(client, books, "/reports/journal", **RANGE)
    _header(ws, "Libro diario")
    totals = _money(_row(ws, "Totales"))
    assert totals == [int(data["total_debit"]), int(data["total_credit"])]
    lines = [r for r in ws.iter_rows(min_row=10) if isinstance(r[8].value, int)]
    assert len(lines) == sum(len(e["lines"]) for e in data["entries"])
    _no_text_amounts(ws, 8)
    # Escritor propio (D-117): fechas de Excel, no texto, y los totales en negrita.
    first = data["entries"][0]
    assert lines[0][0].value == datetime.fromisoformat(first["entry_date"])
    assert lines[0][0].number_format == DATE_FORMAT
    assert lines[0][1].value == first["number"]
    assert all(cell.font.b for cell in _row(ws, "Totales") if cell.value is not None)
    assert ws.title == "Libro diario"


def test_ledger_xlsx(client: TestClient, books: dict[str, Any]) -> None:
    bank = books["accounts"][BANCOS]["id"]
    data = ok(_get(client, books, f"/reports/ledger/{bank}", **RANGE))
    ws = _sheet(client, books, f"/reports/ledger/{bank}", **RANGE)
    _header(ws, f"Libro mayor: {BANCOS} {books['accounts'][BANCOS]['name']}")
    totals = _money(_row(ws, "Totales", 2))
    assert totals == [
        int(data["total_debit"]),
        int(data["total_credit"]),
        int(data["closing_balance"]),
    ]
    assert _money(_row(ws, "Saldo anterior", 2)) == [int(data["opening_balance"])]


def test_trial_balance_xlsx(client: TestClient, books: dict[str, Any]) -> None:
    params = {"from": "2026-02-01", "to": "2026-03-31"}
    data = ok(_get(client, books, "/reports/trial-balance", **params))
    ws = _sheet(client, books, "/reports/trial-balance", **params)
    _header(ws, "Balance de comprobación de sumas y saldos")
    totals = _money(_row(ws, "Totales"))
    assert totals == [
        int(data[key])
        for key in (
            "total_opening_debit",
            "total_opening_credit",
            "total_debit",
            "total_credit",
            "total_debit_balance",
            "total_credit_balance",
            "total_closing_debit",
            "total_closing_credit",
        )
    ]
    bank_row = _row(ws, BANCOS)
    json_row = next(r for r in data["rows"] if r["code"] == BANCOS)
    assert _money(bank_row) == [
        int(json_row[k])
        for k in (
            "opening_debit",
            "opening_credit",
            "debit",
            "credit",
            "debit_balance",
            "credit_balance",
            "closing_debit",
            "closing_credit",
        )
    ]


def test_balance_sheet_xlsx(client: TestClient, books: dict[str, Any]) -> None:
    data = ok(_get(client, books, "/reports/balance-sheet", at="2026-12-31"))
    ws = _sheet(client, books, "/reports/balance-sheet", at="2026-12-31")
    _header(ws, "Balance general")
    assert _money(_row(ws, "Total activo", 1)) == [int(data["total_assets"])]
    assert _money(_row(ws, "Resultado no refundido", 1)) == [int(data["result"])]
    assert _money(_row(ws, "Total pasivo, patrimonio neto y resultado", 1)) == [
        int(data["total_liabilities_and_equity"])
    ]


def test_income_statement_xlsx_with_and_without_centers(
    client: TestClient, books: dict[str, Any]
) -> None:
    data = ok(_get(client, books, "/reports/income-statement", **RANGE))
    ws = _sheet(client, books, "/reports/income-statement", **RANGE)
    _header(ws, "Estado de resultados")
    assert _money(_row(ws, "Total ingresos", 1)) == [int(data["total_income"])]
    assert _money(_row(ws, "Resultado del período", 1)) == [int(data["result"])]
    by_center = ok(_get(client, books, "/reports/income-statement", by_cost_center="true", **RANGE))
    ws = _sheet(client, books, "/reports/income-statement", by_cost_center="true", **RANGE)
    _header(ws, "Estado de resultados por centro de costos")
    result = _money(_row(ws, "Resultado del período", 1))
    assert result == [int(c["result"]) for c in by_center["cost_center_columns"]] + [
        int(by_center["result"])
    ]


def test_depreciation_schedule_xlsx(client: TestClient, books: dict[str, Any]) -> None:
    year_id = books["years"][2026]["id"]
    data = ok(_get(client, books, "/reports/depreciation-schedule", fiscal_year_id=year_id))
    ws = _sheet(client, books, "/reports/depreciation-schedule", fiscal_year_id=year_id)
    _header(ws, "Cuadro de depreciación de los bienes del activo fijo (RG 77/2020, sin revalúo)")
    totals = _money(_row(ws, "TOTALES"))
    assert totals == [int(data["totals"][key]) for key in MONEY_COLUMNS]
    assert Decimal(data["totals"]["accounting_net_value"]) == Decimal(
        data["reconciliation"]["schedule_total"]
    )
    # La conciliación también sale en el archivo.
    assert _money(_row(ws, "Total")) == [
        int(data["reconciliation"]["ledger_total"]),
        int(data["reconciliation"]["schedule_total"]),
    ]


def test_validated_chart_has_no_notice(client: TestClient, books: dict[str, Any]) -> None:
    ok(
        client.post(
            f"{ACC}/chart/validate",
            json={"validated_by_name": "Cdor. Juan Benítez", "validated_reference": "Mat. 99"},
            headers=auth_header(books["token"]),
        )
    )
    ws = _sheet(client, books, "/reports/journal", **RANGE)
    first = [row[0] for row in ws.iter_rows(min_row=1, max_row=8, values_only=True)]
    assert UNVALIDATED_NOTICE not in first


def test_depreciation_schedule_xlsx_name_carries_the_fiscal_year(
    client: TestClient, books: dict[str, Any]
) -> None:
    """Dos ejercicios no se pisan al descargar: el nombre lleva las fechas del ejercicio."""
    year_id = books["years"][2026]["id"]
    res = _get(
        client, books, "/reports/depreciation-schedule", format="xlsx", fiscal_year_id=year_id
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-disposition"] == (
        'attachment; filename="cuadro-de-depreciacion-2026-01-01-2026-12-31.xlsx"'
    )


def test_cors_exposes_content_disposition(client: TestClient) -> None:
    """Sin este encabezado expuesto, el navegador no deja leer el nombre del archivo."""
    res = client.get("/api/v1/health", headers={"Origin": "http://tauri.localhost"})
    assert res.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "content-disposition" in res.headers["access-control-expose-headers"].lower()
