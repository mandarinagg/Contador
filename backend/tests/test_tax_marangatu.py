"""Archivo de importación del registro de comprobantes para Marangatu (D-096, D-099).

Las columnas se comparan con `docs/research/formato_registro_comprobantes.yaml` (la
especificación técnica de la DNIT, RG 90/2021), no con el código que las arma.
"""

import io
import os
import zipfile
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import ok
from tests.tax_utils import SIFEN_RUC, TAX, create_voucher, dv, setup_tax
from tests.test_tax_vouchers import cdc_for

FORMAT = os.path.join(BACKEND_DIR, "..", "docs", "research", "formato_registro_comprobantes.yaml")
ORG_RUC = "80000005"
CLIENT_RUC = "80000011"


def _spec() -> dict[str, Any]:
    with open(FORMAT, encoding="utf-8") as handle:
        return dict(yaml.safe_load(handle))


def _download(client: TestClient, token: str, **params: Any) -> Any:
    query = {"year": 2026, "month": 10, "format": "marangatu", **params}
    return client.get(f"{TAX}/vouchers/export", params=query, headers=auth_header(token))


def _rows(content: bytes) -> tuple[str, list[list[str]], bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        (name,) = archive.namelist()
        raw = archive.read(name)
    lines = raw.decode("utf-8").split("\r\n")
    assert lines[-1] == ""  # cada fila termina en CRLF
    return name, [line.split(";") for line in lines[:-1]], raw


@pytest.fixture
def token(client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch) -> str:
    setup_tax(client, owner_token, monkeypatch, ruc=ORG_RUC)
    return owner_token


def _sale(**overrides: Any) -> dict[str, Any]:
    return {
        "direction": "sale",
        "counterparty_ruc": CLIENT_RUC,
        "counterparty_ruc_dv": dv(CLIENT_RUC),
        "counterparty_name": "Cliente; S.A.",
        **overrides,
    }


def test_columns_follow_the_official_order(client: TestClient, token: str) -> None:
    spec = _spec()
    purchase = create_voucher(
        client, token, condition="credit", taxed_10="110000", taxed_5="21000", exempt="5000"
    )
    sale = create_voucher(client, token, **_sale(), number="001-001-0000007", taxed_10="330000")
    res = _download(client, token)
    assert res.status_code == 200
    filename = res.headers["content-disposition"]
    assert f"{ORG_RUC}_REG_102026_00001.zip" in filename
    name, rows, raw = _rows(res.content)
    assert name == f"{ORG_RUC}_REG_102026_00001.csv"
    assert not raw.startswith(b"\xef\xbb\xbf")  # UTF-8 sin BOM, sin encabezado
    by_section = {r[0]: r for r in rows}
    sales_cols = [c["campo"] for c in spec["registros"]["VENTAS"]]
    purchase_cols = [c["campo"] for c in spec["registros"]["COMPRAS"]]
    assert len(by_section["1"]) == len(sales_cols) == 19
    assert len(by_section["2"]) == len(purchase_cols) == 20
    p = dict(zip(purchase_cols, by_section["2"], strict=True))
    assert p == {
        "CODIGO_TIPO_REGISTRO": "2",
        "CODIGO_TIPO_IDENTIFICACION_PROVEEDOR": "11",
        "NUMERO_IDENTIFICACION_PROVEEDOR": SIFEN_RUC,  # sin DV
        "NOMBRE_RAZON_SOCIAL_PROVEEDOR": "Proveedor de Prueba S.A.",
        "CODIGO_TIPO_COMPROBANTE": "109",
        "FECHA_EMISION": "15/10/2026",
        "NUMERO_TIMBRADO": "12345678",
        "NUMERO_COMPROBANTE": "001-001-0000001",
        "MONTO_GRAVADO_10_IVA_INCLUIDO": "110000",
        "MONTO_GRAVADO_5_IVA_INCLUIDO": "21000",
        "MONTO_NO_GRAVADO_O_EXENTO": "5000",
        "MONTO_TOTAL": "136000",
        "CODIGO_CONDICION_COMPRA": "2",
        "OPERACION_EN_MONEDA_EXTRANJERA": "N",
        "IMPUTA_IVA": "S",
        "IMPUTA_IRE": "N",
        "IMPUTA_IRP_RSP": "N",
        "NO_IMPUTA": "N",
        "NUMERO_COMPROBANTE_VENTA_ASOCIADO": "",
        "TIMBRADO_COMPROBANTE_VENTA_ASOCIADO": "",
    }
    s = dict(zip(sales_cols, by_section["1"], strict=True))
    assert s["NUMERO_IDENTIFICACION_COMPRADOR"] == CLIENT_RUC
    assert s["NOMBRE_RAZON_SOCIAL_COMPRADOR"] == "Cliente S.A."  # sin el separador
    assert s["MONTO_TOTAL"] == "330000" and s["CODIGO_CONDICION_VENTA"] == "1"
    assert "NO_IMPUTA" not in sales_cols
    # Los códigos usados existen en las tablas oficiales.
    assert int(p["CODIGO_TIPO_IDENTIFICACION_PROVEEDOR"]) in spec["tipos_de_identificacion"]
    assert int(p["CODIGO_TIPO_COMPROBANTE"]) in spec["tipos_de_comprobante"]
    assert purchase["id"] and sale["id"]
    # Con coma.
    res = _download(client, token, separator="comma")
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        line = archive.read(archive.namelist()[0]).decode("utf-8").split("\r\n")[0]
    assert line.count(",") in (18, 19) and ";" not in line


def test_identification_codes_are_the_official_ones() -> None:
    from app.modules.tax.exports import IDENTIFICATION_CODES, VOUCHER_CODES

    spec = _spec()
    names = {
        "ruc": "RUC",
        "identity_card": "CEDULA DE IDENTIDAD",
        "passport": "PASAPORTE",
        "foreign_id": "CEDULA EXTRANJERO",
        "unnamed": "SIN NOMBRE",
        "diplomatic": "DIPLOMATICO",
        "tax_id": "IDENTIFICACION TRIBUTARIA",
    }
    assert {
        spec["tipos_de_identificacion"][code]: key for key, code in IDENTIFICATION_CODES.items()
    } == {v: k for k, v in names.items()}
    assert spec["tipos_de_comprobante"][VOUCHER_CODES["invoice"]]["nombre"] == "FACTURA"
    assert spec["tipos_de_comprobante"][VOUCHER_CODES["credit_note"]]["nombre"] == "NOTA DE CRÉDITO"


def test_credit_notes_change_section_and_electronic_are_excluded(
    client: TestClient, token: str
) -> None:
    invoice = create_voucher(client, token, **_sale(), number="001-001-0000010", taxed_10="110000")
    create_voucher(
        client,
        token,
        **_sale(),
        voucher_type="credit_note",
        number="001-001-0000011",
        taxed_10="11000",
        related_voucher_id=invoice["id"],
        issued_on="2026-10-20",
    )
    purchase = create_voucher(client, token, number="001-001-0000020")
    create_voucher(
        client,
        token,
        voucher_type="credit_note",
        number="001-001-0000021",
        taxed_10="11000",
        related_voucher_id=purchase["id"],
        issued_on="2026-10-21",
    )
    electronic = create_voucher(
        client, token, is_electronic=True, cdc=cdc_for(), number="001-001-0014528"
    )
    create_voucher(client, token, number="001-001-0000030", imputes_vat=False)
    preview = ok(
        client.get(
            f"{TAX}/vouchers/export/marangatu-preview",
            params={"year": 2026, "month": 10},
            headers=auth_header(token),
        )
    )
    assert preview["is_draft"] is True and "uno o dos comprobantes" in preview["notice"]
    assert preview["header"] is False and preview["encoding"] == "UTF-8"
    assert preview["rows"] == 4
    assert preview["excluded_electronic"]["count"] == 1
    assert preview["excluded_electronic"]["vouchers"][0]["id"] == electronic["id"]
    assert preview["excluded_not_imputed"]["count"] == 1
    assert {d["code"] for d in preview["doubts"]} == {"D-F4-1", "D-F4-2"}  # D-F4-4 resuelta
    assert preview["rules_applied"][0]["code"] == "REG-COMPROB-IMPORTACION"
    _, rows, _ = _rows(_download(client, token).content)
    by_number = {r[7]: r for r in rows}
    # D-122: la nota de crédito emitida va en COMPRAS y la recibida en VENTAS.
    assert by_number["001-001-0000011"][0] == "2"
    assert by_number["001-001-0000011"][-2:] == ["001-001-0000010", "12345678"]
    assert by_number["001-001-0000021"][0] == "1"
    assert by_number["001-001-0000021"][-2:] == ["001-001-0000020", "12345678"]
    assert "001-001-0014528" not in by_number
    # Con un límite, para probar primero con uno o dos.
    assert (
        ok(
            client.get(
                f"{TAX}/vouchers/export/marangatu-preview",
                params={"year": 2026, "month": 10, "limit": 2},
                headers=auth_header(token),
            )
        )["rows"]
        == 2
    )


def test_nothing_to_export_and_identifier_length(client: TestClient, token: str) -> None:
    res = _download(client, token)
    assert res.status_code == 422 and res.json()["error"]["code"] == "NOTHING_TO_EXPORT"
    create_voucher(client, token)
    assert _download(client, token, first_id=99999).status_code == 200
    assert _download(client, token, first_id=100000).status_code == 422
    assert (
        client.get(
            f"{TAX}/vouchers/export",
            params={"year": 2026, "format": "marangatu"},
            headers=auth_header(token),
        ).status_code
        == 422
    )


def test_more_than_5000_rows_go_in_batches(client: TestClient, token: str, db: Session) -> None:
    first = create_voucher(client, token, number="001-001-0000001")
    db.execute(
        text(
            "INSERT INTO tax.vouchers (organization_id, context_id, context_kind, direction,"
            " voucher_type, is_electronic, timbrado, number, issued_on, counterparty_doc_type,"
            " counterparty_ruc, counterparty_ruc_dv, counterparty_name, condition, currency,"
            " taxed_10, taxed_5, exempt, vat_10, vat_5, imputes_vat, imputes_ire, imputes_irp,"
            " vat_rule_version_id, created_by)"
            " SELECT organization_id, context_id, context_kind, direction, voucher_type,"
            " is_electronic, timbrado, '001-001-' || lpad(g::text, 7, '0'), issued_on,"
            " counterparty_doc_type, counterparty_ruc, counterparty_ruc_dv, counterparty_name,"
            " condition, currency, taxed_10, taxed_5, exempt, vat_10, vat_5, imputes_vat,"
            " imputes_ire, imputes_irp, vat_rule_version_id, created_by"
            " FROM tax.vouchers, generate_series(2, 5001) g WHERE id = :id"
        ),
        {"id": first["id"]},
    )
    preview = ok(
        client.get(
            f"{TAX}/vouchers/export/marangatu-preview",
            params={"year": 2026, "month": 10, "first_id": 7},
            headers=auth_header(token),
        )
    )
    assert preview["batches"] == [
        {"name": f"{ORG_RUC}_REG_102026_00007.zip", "rows": 5000},
        {"name": f"{ORG_RUC}_REG_102026_00008.zip", "rows": 1},
    ]
    res = _download(client, token, first_id=7)
    assert f"{ORG_RUC}_REG_102026_lotes.zip" in res.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(res.content)) as outer:
        assert outer.namelist() == [
            f"{ORG_RUC}_REG_102026_00007.zip",
            f"{ORG_RUC}_REG_102026_00008.zip",
        ]
        sizes = []
        for inner_name in outer.namelist():
            _, rows, _ = _rows(outer.read(inner_name))
            sizes.append(len(rows))
    assert sizes == [5000, 1]
