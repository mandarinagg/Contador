"""Importación de extractos CSV/XLSX (BR-FIN-03, BR-FIN-08)."""

import io
import json
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from tests.conftest import auth_header
from tests.finance_utils import (
    API,
    audit_entries,
    business_context,
    create_account,
    create_tx,
    ok,
)

PY_MAPPING: dict[str, Any] = {
    "has_header": True,
    "delimiter": ";",
    "encoding": "auto",
    "date_column": "Fecha",
    "date_format": "%d/%m/%Y",
    "description_column": "Concepto",
    "reference_column": "Nro. Operación",
    "amount": {"mode": "single", "column": "Importe"},
    "decimal_separator": ",",
    "thousands_separator": ".",
    "skip_rows": 0,
}

PY_CSV = "\n".join(
    [
        "Fecha;Concepto;Nro. Operación;Importe",
        "05/03/2026;Pago ANDE;1001;-150.000",
        "06/03/2026;Depósito cliente;1002;1.234.567",
        "31/02/2026;Fecha mala;1003;-1.000",
        "07/03/2026;Con decimales;1004;-1.234,50",
        "05/03/2026;pago  ande;1001;-150.000",
        "08/03/2026;;1005;100",
        "09/03/2026;Café;1006;abc",
        "",
        "10/03/2026;SUPERMERCADO;1007;-85.000",
    ]
)


@pytest.fixture
def ctx(client: TestClient, owner_token: str) -> dict[str, Any]:
    biz = business_context(client, owner_token)
    pyg = create_account(client, owner_token, biz, "Banco PYG")
    usd = create_account(client, owner_token, biz, "Banco USD", currency="USD")
    return {"biz": biz, "pyg": pyg["id"], "usd": usd["id"], "token": owner_token}


def upload(
    client: TestClient,
    ctx: dict[str, Any],
    content: bytes,
    mapping: dict[str, Any] | str,
    *,
    account: str = "pyg",
    filename: str = "extracto.csv",
) -> Any:
    return client.post(
        f"{API}/contexts/{ctx['biz']}/imports",
        files={"file": (filename, content, "application/octet-stream")},
        data={
            "account_id": ctx[account],
            "mapping": mapping if isinstance(mapping, str) else json.dumps(mapping),
        },
        headers=auth_header(ctx["token"]),
    )


def _rows(batch: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {r["row_number"]: r for r in batch["rows"]}


def test_csv_utf8_semicolon_errors_and_duplicates(client: TestClient, ctx: dict[str, Any]) -> None:
    existing = create_tx(
        client,
        ctx["token"],
        ctx["biz"],
        ctx["pyg"],
        "-85000",
        "2026-03-10",
        "Supermercado",
        reference="1007",
    )
    batch = ok(upload(client, ctx, ("﻿" + PY_CSV).encode("utf-8"), PY_MAPPING), 201)
    assert batch["status"] == "previewed" and batch["file_format"] == "csv"
    assert batch["currency"] == "PYG"
    assert (batch["rows_total"], batch["rows_error"], batch["rows_duplicate"]) == (8, 4, 2)
    rows = _rows(batch)
    assert rows[2]["amount"] == "-150000" and rows[2]["booked_on"] == "2026-03-05"
    assert rows[2]["reference"] == "1001" and rows[2]["decision"] == "import"
    assert rows[3]["amount"] == "1234567" and rows[3]["description"] == "Depósito cliente"
    assert rows[4]["error"] == "Fecha inválida: 31/02/2026"
    assert "PYG" in rows[5]["error"] and "decimales" in rows[5]["error"]
    assert rows[6]["duplicate_in_file"] == 2 and rows[6]["decision"] == "skip"
    assert rows[7]["error"] == "Falta la descripción"
    assert rows[8]["error"] == "Importe inválido: abc"
    assert rows[10]["duplicate_of"] == existing["id"] and rows[10]["decision"] == "skip"
    assert rows[2]["raw"] == {
        "Fecha": "05/03/2026",
        "Concepto": "Pago ANDE",
        "Nro. Operación": "1001",
        "Importe": "-150.000",
    }
    assert all(r["decision"] == "skip" for r in rows.values() if r["error"])
    # Analizar no crea movimientos.
    listed = ok(
        client.get(f"{API}/contexts/{ctx['biz']}/transactions", headers=auth_header(ctx["token"]))
    )
    assert [t["id"] for t in listed] == [existing["id"]]


def test_commit_is_idempotent_and_audited_once(client: TestClient, ctx: dict[str, Any]) -> None:
    batch = ok(upload(client, ctx, PY_CSV.encode("utf-8"), PY_MAPPING), 201)
    base = f"{API}/contexts/{ctx['biz']}/imports/{batch['id']}"
    headers = auth_header(ctx["token"])
    # Una fila con error no se puede importar; un duplicado sí, si la persona decide.
    res = client.patch(f"{base}/rows/4", json={"decision": "import"}, headers=headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "IMPORT_ROW_HAS_ERROR"
    assert (
        ok(client.patch(f"{base}/rows/6", json={"decision": "import"}, headers=headers))["decision"]
        == "import"
    )
    assert (
        client.patch(f"{base}/rows/99", json={"decision": "skip"}, headers=headers).status_code
        == 404
    )

    committed = ok(client.post(f"{base}/commit", headers=headers))
    assert committed["status"] == "committed" and committed["rows_imported"] == 4
    assert committed["committed_at"] is not None
    again = client.post(f"{base}/commit", headers=headers)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "IMPORT_ALREADY_COMMITTED"
    assert client.post(f"{base}/cancel", headers=headers).status_code == 409
    assert (
        client.patch(f"{base}/rows/2", json={"decision": "skip"}, headers=headers).status_code
        == 409
    )

    txs = ok(
        client.get(
            f"{API}/contexts/{ctx['biz']}/transactions",
            params={"unreviewed": True},
            headers=headers,
        )
    )
    assert len(txs) == 4
    assert {t["source"] for t in txs} == {"import"}
    assert {t["import_batch_id"] for t in txs} == {batch["id"]}
    assert sorted(t["amount"] for t in txs) == ["-150000", "-150000", "-85000", "1234567"]

    # Auditoría por lote: un evento al analizar y otro al confirmar; ninguno por fila.
    events = audit_entries(client, ctx["token"], "finance.import")
    assert sorted(e["action"] for e in events) == [
        "finance.import.committed",
        "finance.import.previewed",
    ]
    commit_event = next(e for e in events if e["action"] == "finance.import.committed")
    assert commit_event["entity_id"] == batch["id"]
    assert commit_event["after"]["rows_imported"] == 4
    assert audit_entries(client, ctx["token"], "finance.transaction") == []

    # Volver a subir el mismo archivo: todo lo importado aparece como duplicado.
    second = ok(upload(client, ctx, PY_CSV.encode("utf-8"), PY_MAPPING), 201)
    dup_rows = [r for r in second["rows"] if r["error"] is None]
    assert all(r["duplicate_of"] is not None for r in dup_rows)
    assert all(r["decision"] == "skip" for r in second["rows"])

    # El último lote de la cuenta (para reutilizar el mapeo).
    latest = ok(
        client.get(
            f"{API}/contexts/{ctx['biz']}/imports",
            params={"account_id": ctx["pyg"], "limit": 1},
            headers=headers,
        )
    )
    assert [b["id"] for b in latest] == [second["id"]]
    assert latest[0]["mapping"]["date_column"] == "Fecha" and latest[0]["rows"] is None


def test_duplicates_appearing_after_preview_block_commit(
    client: TestClient, ctx: dict[str, Any]
) -> None:
    headers = auth_header(ctx["token"])
    first = ok(upload(client, ctx, PY_CSV.encode("utf-8"), PY_MAPPING), 201)
    second = ok(upload(client, ctx, PY_CSV.encode("utf-8"), PY_MAPPING), 201)
    ok(client.post(f"{API}/contexts/{ctx['biz']}/imports/{first['id']}/commit", headers=headers))
    path = f"{API}/contexts/{ctx['biz']}/imports/{second['id']}/commit"
    res = client.post(path, headers=headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "IMPORT_NEW_DUPLICATES"
    assert sorted(res.json()["error"]["details"]["rows"]) == [2, 3, 10]
    # Quedaron señalados y descartados; confirmar de nuevo no duplica nada.
    done = ok(client.post(path, headers=headers))
    assert done["rows_imported"] == 0
    txs = ok(client.get(f"{API}/contexts/{ctx['biz']}/transactions", headers=headers))
    assert len(txs) == 3


def test_cancel(client: TestClient, ctx: dict[str, Any]) -> None:
    headers = auth_header(ctx["token"])
    batch = ok(upload(client, ctx, PY_CSV.encode("utf-8"), PY_MAPPING), 201)
    base = f"{API}/contexts/{ctx['biz']}/imports/{batch['id']}"
    cancelled = ok(client.post(f"{base}/cancel", headers=headers))
    assert cancelled["status"] == "cancelled"
    res = client.post(f"{base}/commit", headers=headers)
    assert res.status_code == 409 and res.json()["error"]["code"] == "IMPORT_CANCELLED"
    assert ok(client.get(f"{API}/contexts/{ctx['biz']}/transactions", headers=headers)) == []
    fetched = ok(client.get(base, params={"rows_limit": 3, "rows_after": 2}, headers=headers))
    assert [r["row_number"] for r in fetched["rows"]] == [3, 4, 5]
    actions = sorted(e["action"] for e in audit_entries(client, ctx["token"], "finance.import"))
    assert actions == ["finance.import.cancelled", "finance.import.previewed"]


def test_csv_cp1252_comma_split(client: TestClient, ctx: dict[str, Any]) -> None:
    content = "\r\n".join(
        [
            "Fecha,Descripción,Débito,Crédito",
            '02/03/2026,Transferencia recibida,,"1,234.56"',
            "03/03/2026,Comisión bancaria,12.30,",
            "04/03/2026,Ambos,1.00,2.00",
            "05/03/2026,Ninguno,,",
            "06/03/2026,Muchos decimales,1.005,",
        ]
    ).encode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        content.decode("utf-8")
    mapping = {
        **PY_MAPPING,
        "delimiter": ",",
        "description_column": "Descripción",
        "reference_column": None,
        "amount": {"mode": "split", "debit_column": "Débito", "credit_column": "Crédito"},
        "decimal_separator": ".",
        "thousands_separator": ",",
    }
    batch = ok(upload(client, ctx, content, mapping, account="usd"), 201)
    rows = _rows(batch)
    assert rows[2]["amount"] == "1234.56" and rows[2]["description"] == "Transferencia recibida"
    assert rows[3]["amount"] == "-12.30" and rows[3]["description"] == "Comisión bancaria"
    assert rows[4]["error"] == "La fila tiene débito y crédito a la vez"
    assert rows[5]["error"].startswith("Falta el importe")
    assert "como máximo 2 decimales" in rows[6]["error"]
    assert batch["rows_error"] == 3


def _xlsx(rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_xlsx_single_and_split(client: TestClient, ctx: dict[str, Any]) -> None:
    single = _xlsx(
        [
            ["Extracto del Banco", None, None, None],
            ["Fecha", "Concepto", "Nro. Operación", "Importe"],
            [datetime(2026, 4, 1), "Cobro factura 001-001-0000123", 555, 2500000],
            [datetime(2026, 4, 2), "Pago proveedor", "556", "-1.500.000"],
            ["03/04/2026", "Fecha como texto", None, -10000],
            [datetime(2026, 4, 4), "Decimales en PYG", None, 1500.5],
            [None, None, None, None],
            [datetime(2026, 4, 5), "Fórmula", None, "=1+1"],
        ]
    )
    batch = ok(
        upload(client, ctx, single, {**PY_MAPPING, "skip_rows": 1}, filename="banco.xlsx"), 201
    )
    assert batch["file_format"] == "xlsx" and batch["filename"] == "banco.xlsx"
    rows = _rows(batch)
    assert rows[3]["booked_on"] == "2026-04-01" and rows[3]["amount"] == "2500000"
    assert rows[3]["reference"] == "555"
    assert rows[4]["amount"] == "-1500000"
    assert rows[5]["booked_on"] == "2026-04-03" and rows[5]["amount"] == "-10000"
    assert "PYG" in rows[6]["error"]
    # La fórmula no se evalúa: sin valor guardado en el archivo, la fila queda sin importe.
    assert rows[8]["error"] == "Falta el importe"
    assert batch["rows_total"] == 5

    split = _xlsx(
        [
            ["Fecha", "Concepto", "Débito", "Crédito"],
            [datetime(2026, 4, 1), "Depósito", None, 100.25],
            [datetime(2026, 4, 2), "Débito automático", "0,10", None],
        ]
    )
    mapping = {
        **PY_MAPPING,
        "reference_column": None,
        "amount": {"mode": "split", "debit_column": "Débito", "credit_column": "Crédito"},
    }
    batch = ok(upload(client, ctx, split, mapping, account="usd", filename="usd.xlsx"), 201)
    rows = _rows(batch)
    assert rows[2]["amount"] == "100.25" and rows[3]["amount"] == "-0.10"
    committed = ok(
        client.post(
            f"{API}/contexts/{ctx['biz']}/imports/{batch['id']}/commit",
            headers=auth_header(ctx["token"]),
        )
    )
    assert committed["rows_imported"] == 2
    accounts = ok(
        client.get(f"{API}/contexts/{ctx['biz']}/accounts", headers=auth_header(ctx["token"]))
    )
    assert next(a for a in accounts if a["id"] == ctx["usd"])["balance"] == "100.15"


def test_realistic_bank_statements(client: TestClient, ctx: dict[str, Any]) -> None:
    """Extractos reales: cabecera del banco, hora, moneda escrita y totales al pie."""
    statement = (
        "BANCO EJEMPLO S.A.;;;;;\n"
        "Cuenta: 1234567 - GUARANIES;;;;;\n"
        ";;;;;\n"
        "Fecha;Concepto;Nro. Operación;Débito;Crédito;Saldo\n"
        "02/01/2026 08:15;Transferencia recibida de CLIENTE SA;000123;;Gs. 1.500.000;11.500.000\n"
        "03/01/2026 17:40;Pago ANDE NIS 12345;000124;Gs. 245.300;;11.254.700\n"
        "04/01/2026;Compra en dólares;000125;US$ 20,00;;11.254.700\n"
        ";Totales;;245.300;1.500.000;\n"
        ";Saldo final;;;;11.254.700\n"
    )
    mapping = {
        "skip_rows": 3,
        "date_column": "Fecha",
        "description_column": "Concepto",
        "reference_column": "Nro. Operación",
        "amount": {"mode": "split", "debit_column": "Débito", "credit_column": "Crédito"},
    }
    batch = ok(upload(client, ctx, statement.encode("cp1252"), mapping), 201)
    rows = _rows(batch)
    assert rows[5]["booked_on"] == "2026-01-02" and rows[5]["amount"] == "1500000"
    assert rows[6]["booked_on"] == "2026-01-03" and rows[6]["amount"] == "-245300"
    assert rows[5]["error"] is None and rows[6]["error"] is None
    # Otra moneda que la de la cuenta: error legible, nunca una conversión.
    assert rows[7]["error"] == "El importe está en USD y la cuenta en PYG: US$ 20,00"
    # Totales y saldo final del pie quedan como filas con error, fuera de la importación.
    assert rows[8]["error"] and rows[9]["error"]
    assert (batch["rows_total"], batch["rows_error"]) == (5, 3)

    # XLSX: fecha guardada como número y un importe calculado con decimales fantasma.
    workbook = _xlsx(
        [
            ["Fecha", "Concepto", "Importe"],
            [46034, "Fecha sin formato de fecha", -1000],
            [datetime(2026, 1, 13), "Interés calculado", 1234.5600000000001],
        ]
    )
    usd_mapping = {
        "date_column": "Fecha",
        "description_column": "Concepto",
        "amount": {"mode": "single", "column": "Importe"},
    }
    batch = ok(
        upload(client, ctx, workbook, usd_mapping, account="usd", filename="extracto.xlsx"), 201
    )
    rows = _rows(batch)
    assert rows[2]["booked_on"] == "2026-01-12" and rows[2]["amount"] == "-1000.00"
    assert rows[3]["amount"] == "1234.56" and rows[3]["raw"]["Importe"] == "1234.56"
    assert batch["rows_error"] == 0


def test_headerless_csv_uses_column_positions(client: TestClient, ctx: dict[str, Any]) -> None:
    content = b"01/05/2026;Venta;150.000\n02/05/2026;Compra;-20.000\n"
    mapping = {
        **PY_MAPPING,
        "has_header": False,
        "date_column": "1",
        "description_column": "2",
        "reference_column": None,
        "amount": {"mode": "single", "column": "3"},
    }
    batch = ok(upload(client, ctx, content, mapping), 201)
    assert [r["amount"] for r in batch["rows"]] == ["150000", "-20000"]
    assert batch["rows"][0]["row_number"] == 1


def test_file_level_rejections(client: TestClient, ctx: dict[str, Any]) -> None:
    def code(res: Any) -> str:
        return str(res.json()["error"]["code"])

    xls = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
    res = upload(client, ctx, xls, PY_MAPPING, filename="viejo.xls")
    assert res.status_code == 422 and code(res) == "IMPORT_UNSUPPORTED_FORMAT"
    assert "CSV o XLSX" in res.json()["error"]["message"]

    res = upload(client, ctx, b"x" * (10 * 1024 * 1024 + 1), PY_MAPPING)
    assert res.status_code == 413 and code(res) == "IMPORT_FILE_TOO_LARGE"

    many = "Fecha;Concepto;Nro. Operación;Importe\n" + "01/01/2026;X;1;100\n" * 20_001
    res = upload(client, ctx, many.encode(), PY_MAPPING)
    assert res.status_code == 422 and code(res) == "IMPORT_TOO_MANY_ROWS"

    res = upload(client, ctx, PY_CSV.encode(), {**PY_MAPPING, "date_column": "Día"})
    assert res.status_code == 422 and code(res) == "IMPORT_COLUMN_NOT_FOUND"
    assert "Fecha" in res.json()["error"]["details"]["available"]

    res = upload(client, ctx, PY_CSV.encode(), "{no es json")
    assert res.status_code == 422 and code(res) == "VALIDATION_ERROR"
    res = upload(client, ctx, PY_CSV.encode(), {**PY_MAPPING, "decimal_separator": "."})
    assert res.status_code == 422  # mismo separador decimal y de miles

    res = upload(client, ctx, b"PK\x03\x04basura", PY_MAPPING, filename="roto.xlsx")
    assert res.status_code == 422 and code(res) == "IMPORT_UNREADABLE"

    res = upload(client, ctx, b"", PY_MAPPING)
    assert res.status_code == 422 and code(res) == "IMPORT_EMPTY"

    # Nada de eso dejó lotes ni auditoría.
    assert audit_entries(client, ctx["token"], "finance.import") == []


def test_import_requires_manage_permission(
    client: TestClient, ctx: dict[str, Any], make_user: Any
) -> None:
    _, viewer_token = make_user("viewer")
    res = client.post(
        f"{API}/contexts/{ctx['biz']}/imports",
        files={"file": ("e.csv", PY_CSV.encode(), "text/csv")},
        data={"account_id": ctx["pyg"], "mapping": json.dumps(PY_MAPPING)},
        headers=auth_header(viewer_token),
    )
    assert res.status_code == 403
