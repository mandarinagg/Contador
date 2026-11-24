"""Registro de comprobantes (spec fase 4 §5.5 y §5.6; D-088, D-089, D-099, BR-TAX-07/08/09)."""

import io
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.organizations.ruc import ruc_check_digit
from app.modules.tax.vouchers import included_vat
from tests.conftest import SETUP_BODY, auth_header
from tests.finance_utils import (
    audit_entries,
    business_context,
    create_account,
    create_tx,
    ok,
    personal_context,
)
from tests.tax_utils import (
    SIFEN_CDC,
    SIFEN_DV,
    SIFEN_RUC,
    TAX,
    confirm_register,
    create_voucher,
    dv,
    fix_today,
    load_rules,
    obligation,
    put_profile,
    rejected,
    set_ruc,
    setup_tax,
    voucher_body,
)
from tests.test_tax_obligations import PARALLEL, _app_client, own_engine  # noqa: F401


def _post(client: TestClient, token: str, **overrides: Any) -> Any:
    return client.post(
        f"{TAX}/vouchers", json=voucher_body(**overrides), headers=auth_header(token)
    )


def _code(res: Any) -> str:
    return str(res.json()["error"]["code"])


def cdc_for(
    *,
    doc_type: str = "01",
    ruc: str = SIFEN_RUC,
    ruc_dv: str = SIFEN_DV,
    number: str = "001-001-0014528",
    day: str = "20261015",
) -> str:
    """CDC como lo arma `buildCdc` del proyecto de facturación (MT SIFEN v150, §10.1)."""
    establishment, point, seq = number.split("-")
    body = f"{doc_type}{ruc.zfill(8)}{ruc_dv}{establishment}{point}{seq}2{day}1587326098"
    return body + str(ruc_check_digit(body))


@pytest.fixture
def tax(client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch) -> str:
    setup_tax(client, owner_token, monkeypatch)
    return owner_token


def test_sifen_cases_of_the_research(db: Session) -> None:
    assert ruc_check_digit(SIFEN_RUC) == int(SIFEN_DV)
    assert ruc_check_digit(SIFEN_CDC[:43]) == int(SIFEN_CDC[43]) == 8
    # La función de la base da lo mismo (la usan las restricciones).
    assert db.scalar(text("SELECT tax.ruc_check_digit(:d)"), {"d": SIFEN_RUC}) == 7
    assert db.scalar(text("SELECT tax.ruc_check_digit(:d)"), {"d": SIFEN_CDC[:43]}) == 8
    assert db.scalar(text("SELECT tax.ruc_check_digit('12a')")) == -1
    assert cdc_for(day="20170125") == SIFEN_CDC


def test_formats_are_validated(client: TestClient, tax: str, db: Session) -> None:
    assert _post(client, tax, timbrado="1234567").status_code == 422
    assert _post(client, tax, number="001-001-000001").status_code == 422
    assert _post(client, tax, number="1-001-0000001").status_code == 422
    res = _post(client, tax, counterparty_ruc_dv="3")
    assert res.status_code == 422 and _code(res) == "RUC_CHECK_DIGIT_INVALID"
    # Electrónico: CDC obligatorio, con su DV y coherente con el comprobante.
    res = _post(client, tax, is_electronic=True, number="001-001-0014528")
    assert _code(res) == "CDC_REQUIRED"
    bad_dv = cdc_for()[:43] + str((int(cdc_for()[43]) + 1) % 10)
    res = _post(client, tax, is_electronic=True, cdc=bad_dv, number="001-001-0014528")
    assert _code(res) == "CDC_CHECK_DIGIT_INVALID"
    res = _post(client, tax, is_electronic=True, cdc=cdc_for(), number="001-001-0014529")
    assert _code(res) == "CDC_MISMATCH" and "el número" in res.json()["error"]["message"]
    res = _post(
        client, tax, is_electronic=True, cdc=cdc_for(doc_type="05"), number="001-001-0014528"
    )
    assert _code(res) == "CDC_MISMATCH" and "tipo" in res.json()["error"]["message"]
    res = _post(client, tax, cdc=cdc_for(), number="001-001-0014528")
    assert _code(res) == "CDC_NOT_APPLICABLE"
    good = create_voucher(client, tax, is_electronic=True, cdc=cdc_for(), number="001-001-0014528")
    assert good["cdc"] == cdc_for()
    # El CDC oficial del Manual es de 2017: no hay regla de tasas vigente («sin regla», D-082).
    res = _post(
        client,
        tax,
        is_electronic=True,
        cdc=SIFEN_CDC,
        number="001-001-0014528",
        issued_on="2017-01-25",
    )
    assert _code(res) == "RULE_MISSING"
    # La base es la última defensa.
    rejected(
        db,
        "UPDATE tax.vouchers SET cdc = :cdc WHERE id = :id",
        {"cdc": bad_dv, "id": good["id"]},
        "ck_vouchers_cdc_format",
    )
    rejected(
        db,
        "UPDATE tax.vouchers SET counterparty_ruc_dv = '3' WHERE id = :id",
        {"id": good["id"]},
        "ck_vouchers_ruc_check_digit",
    )
    rejected(
        db,
        "UPDATE tax.vouchers SET timbrado = '123' WHERE id = :id",
        {"id": good["id"]},
        "ck_vouchers_timbrado_format",
    )


def test_included_vat_by_rate_with_rounding(client: TestClient, tax: str) -> None:
    from decimal import Decimal

    assert included_vat(Decimal(110000), Decimal("0.1")) == 10000
    assert included_vat(Decimal(105000), Decimal("0.05")) == 5000
    assert included_vat(Decimal(16), Decimal("0.1")) == 1  # 1,45
    assert included_vat(Decimal(17), Decimal("0.1")) == 2  # 1,55
    assert included_vat(Decimal(31), Decimal("0.05")) == 1  # 1,48
    assert included_vat(Decimal(32), Decimal("0.05")) == 2  # 1,52
    mixed = create_voucher(client, tax, taxed_10="110000", taxed_5="105000", exempt="5000")
    assert (mixed["vat_10"], mixed["vat_5"], mixed["total"]) == ("10000", "5000", "220000")
    assert mixed["rules_applied"][0]["code"] == "IVA-GENERAL-TASAS"
    assert mixed["rule_status"] == "pending"
    # Impreso con ±1: se acepta y se guarda lo impreso.
    printed = create_voucher(
        client, tax, number="001-001-0000002", taxed_10="110000", vat_10="10001"
    )
    assert printed["vat_10"] == "10001"
    low = create_voucher(client, tax, number="001-001-0000003", taxed_5="105000", vat_5="4999")
    assert low["vat_5"] == "4999"
    # ±2: rechazado.
    res = _post(client, tax, number="001-001-0000004", taxed_10="110000", vat_10="10002")
    assert res.status_code == 422 and _code(res) == "VAT_MISMATCH"
    res = _post(client, tax, number="001-001-0000004", taxed_10="110000", vat_10=9998)
    assert res.status_code == 422  # un número JSON, nunca
    res = _post(client, tax, number="001-001-0000004", taxed_10="1100.5")
    assert res.status_code == 422


def test_duplicates_are_rejected(client: TestClient, tax: str, db: Session) -> None:
    first = create_voucher(client, tax)
    res = _post(client, tax)
    assert res.status_code == 409 and _code(res) == "VOUCHER_DUPLICATE"
    # Otro proveedor con el mismo timbrado y número es otro comprobante.
    create_voucher(client, tax, counterparty_ruc="80000005", counterparty_ruc_dv=dv("80000005"))
    # Anulado, se puede volver a cargar.
    ok(
        client.post(
            f"{TAX}/vouchers/{first['id']}/void",
            json={"reason": "Mal cargado"},
            headers=auth_header(tax),
        )
    )
    create_voucher(client, tax)
    # La base lo impide aunque el servicio fallara.
    rejected(
        db,
        "INSERT INTO tax.vouchers (organization_id, context_id, context_kind, direction,"
        " voucher_type, is_electronic, timbrado, number, issued_on, counterparty_doc_type,"
        " counterparty_ruc, counterparty_ruc_dv, counterparty_name, condition, currency, taxed_10,"
        " taxed_5, exempt, vat_10, vat_5, imputes_vat, imputes_ire, imputes_irp,"
        " vat_rule_version_id, created_by)"
        " SELECT organization_id, context_id, context_kind, direction, voucher_type, is_electronic,"
        " timbrado, number, issued_on, counterparty_doc_type, counterparty_ruc,"
        " counterparty_ruc_dv, counterparty_name, condition, currency, taxed_10, taxed_5, exempt,"
        " vat_10, vat_5, imputes_vat, imputes_ire, imputes_irp, vat_rule_version_id, created_by"
        " FROM tax.vouchers WHERE voided_at IS NULL AND counterparty_ruc = :ruc",
        {"ruc": SIFEN_RUC},
        "uq_vouchers_purchase_live",
    )


def test_credit_note_with_its_original(client: TestClient, tax: str, db: Session) -> None:
    invoice = create_voucher(client, tax, taxed_10="110000")
    res = _post(client, tax, voucher_type="credit_note", number="001-001-0000010")
    assert _code(res) == "RELATED_VOUCHER_REQUIRED"
    note = create_voucher(
        client,
        tax,
        voucher_type="credit_note",
        number="001-001-0000010",
        taxed_10="11000",
        related_voucher_id=invoice["id"],
        issued_on="2026-10-20",
    )
    assert note["vat_10"] == "1000"
    # Más que la factura: no.
    res = _post(
        client,
        tax,
        voucher_type="credit_note",
        number="001-001-0000011",
        taxed_10="100000",
        related_voucher_id=invoice["id"],
        issued_on="2026-10-21",
    )
    assert _code(res) == "CREDIT_NOTE_EXCEEDS_ORIGINAL"
    # Otra contraparte: no.
    res = _post(
        client,
        tax,
        voucher_type="credit_note",
        number="001-001-0000012",
        taxed_10="1100",
        related_voucher_id=invoice["id"],
        counterparty_ruc="80000005",
        counterparty_ruc_dv=dv("80000005"),
    )
    assert _code(res) == "VOUCHER_NOTE_MISMATCH"
    rejected(
        db,
        "UPDATE tax.vouchers SET counterparty_ruc = '80000005', counterparty_ruc_dv = :dv"
        " WHERE id = :id",
        {"id": note["id"], "dv": dv("80000005")},
        "trg_vouchers_note_mismatch",
    )
    # La factura con notas vivas no se anula.
    res = client.post(
        f"{TAX}/vouchers/{invoice['id']}/void", json={"reason": "Prueba"}, headers=auth_header(tax)
    )
    assert _code(res) == "VOUCHER_HAS_NOTES"


def test_foreign_currency_with_rate(client: TestClient, tax: str) -> None:
    res = _post(client, tax, currency="USD", taxed_10="730025")
    assert _code(res) == "FX_RATE_REQUIRED"
    res = _post(
        client, tax, currency="USD", fx_rate="7300.25", foreign_total="100.00", taxed_10="730000"
    )
    assert _code(res) == "FX_TOTAL_MISMATCH"
    body = create_voucher(
        client, tax, currency="USD", fx_rate="7300.25", foreign_total="100.00", taxed_10="730025"
    )
    assert (body["currency"], body["fx_rate"], body["foreign_total"]) == (
        "USD",
        "7300.25",
        "100.00",
    )
    # 33,33 USD por 7300,25 = 243317,3325: vale 243317 o 243318.
    create_voucher(
        client,
        tax,
        number="001-001-0000020",
        currency="USD",
        fx_rate="7300.25",
        foreign_total="33.33",
        taxed_10="243318",
    )
    res = _post(client, tax, number="001-001-0000021", fx_rate="7300", taxed_10="1000")
    assert _code(res) == "FX_NOT_APPLICABLE"


def test_links_only_to_business_finance(client: TestClient, tax: str) -> None:
    personal = personal_context(client, tax)
    p_account = create_account(client, tax, personal, "Personal")
    p_tx = create_tx(client, tax, personal, p_account["id"], "-110000")
    res = _post(client, tax, transaction_id=p_tx["id"])
    assert res.status_code == 404
    cid = business_context(client, tax)
    account = create_account(client, tax, cid)
    tx = create_tx(client, tax, cid, account["id"], "-110000", booked_on="2026-10-15")
    voucher = create_voucher(client, tax, transaction_id=tx["id"])
    assert voucher["transaction_id"] == tx["id"]
    # Una contraparte personal tampoco.
    p_cp = ok(
        client.post(
            f"/api/v1/finance/contexts/{personal}/counterparties",
            json={"name": "Alguien", "kind": "person"},
            headers=auth_header(tax),
        ),
        201,
    )
    res = _post(client, tax, number="001-001-0000030", finance_counterparty_id=p_cp["id"])
    assert res.status_code == 404


def test_void_without_deleting(client: TestClient, tax: str, db: Session) -> None:
    voucher = create_voucher(client, tax)
    rejected(
        db,
        "UPDATE tax.vouchers SET direction = 'sale' WHERE id = :id",
        {"id": voucher["id"]},
        "trg_vouchers_identity_fixed",
    )
    voided = ok(
        client.post(
            f"{TAX}/vouchers/{voucher['id']}/void",
            json={"reason": "Duplicado"},
            headers=auth_header(tax),
        )
    )
    assert voided["voided_at"] is not None and voided["void_reason"] == "Duplicado"
    res = client.patch(
        f"{TAX}/vouchers/{voucher['id']}", json={"notes": "x"}, headers=auth_header(tax)
    )
    assert _code(res) == "VOUCHER_VOIDED"
    rejected(
        db,
        "DELETE FROM tax.vouchers WHERE id = :id",
        {"id": voucher["id"]},
        "trg_vouchers_no_delete",
    )
    rejected(
        db,
        "UPDATE tax.vouchers SET notes = 'x' WHERE id = :id",
        {"id": voucher["id"]},
        "trg_vouchers_voided_final",
    )
    listed = ok(client.get(f"{TAX}/vouchers", params={"voided": "only"}, headers=auth_header(tax)))
    assert [v["id"] for v in listed] == [voucher["id"]]
    assert ok(client.get(f"{TAX}/vouchers", headers=auth_header(tax))) == []
    actions = {e["action"] for e in audit_entries(client, tax, "tax.voucher")}
    assert {"tax.voucher.created", "tax.voucher.voided"} <= actions


def test_counterparty_identification_types(client: TestClient, tax: str, db: Session) -> None:
    # RUC antiguo con letra (D-F4-10): se acepta sin DV y queda marcado para revisar.
    legacy = create_voucher(client, tax, counterparty_ruc="1234567a", counterparty_ruc_dv=None)
    assert legacy["counterparty_ruc"] == "1234567A"
    assert legacy["counterparty_ruc_dv"] is None
    assert legacy["counterparty_review_required"] is True
    # En una compra va RUC.
    res = _post(
        client,
        tax,
        number="001-001-0000040",
        counterparty_doc_type="identity_card",
        counterparty_document="1234567",
    )
    assert _code(res) == "COUNTERPARTY_RUC_REQUIRED"
    # Ventas: pasaporte, sin nombre (nombre por defecto) y cédula.
    sale = {"direction": "sale", "counterparty_ruc": None, "counterparty_ruc_dv": None}
    passport = create_voucher(
        client,
        tax,
        **sale,
        number="001-001-0000041",
        counterparty_doc_type="passport",
        counterparty_document="AB123456",
        counterparty_name="Visitante",
    )
    assert passport["counterparty_document"] == "AB123456"
    unnamed = create_voucher(
        client,
        tax,
        **sale,
        number="001-001-0000042",
        counterparty_doc_type="unnamed",
        counterparty_name=None,
    )
    assert unnamed["counterparty_name"] == "Sin nombre"
    res = _post(
        client, tax, **sale, number="001-001-0000043", counterparty_doc_type="identity_card"
    )
    assert _code(res) == "COUNTERPARTY_DOCUMENT_REQUIRED"
    rejected(
        db,
        "UPDATE tax.vouchers SET counterparty_ruc_dv = '1' WHERE id = :id",
        {"id": legacy["id"]},
        "ck_vouchers_ruc_check_digit",
    )


def test_sales_need_the_organization_ruc(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fix_today(monkeypatch)
    load_rules(client, owner_token)
    res = _post(client, owner_token, direction="sale")
    assert _code(res) == "ORGANIZATION_RUC_REQUIRED"


def test_edit_recalculates_vat_and_keeps_audit(client: TestClient, tax: str) -> None:
    voucher = create_voucher(client, tax)
    res = client.patch(
        f"{TAX}/vouchers/{voucher['id']}", json={"taxed_10": "220000"}, headers=auth_header(tax)
    )
    body = ok(res)
    assert body["vat_10"] == "20000"
    res = client.patch(
        f"{TAX}/vouchers/{voucher['id']}", json={"direction": "sale"}, headers=auth_header(tax)
    )
    assert res.status_code == 422
    updated = [
        e for e in audit_entries(client, tax, "tax.voucher") if e["action"] == "tax.voucher.updated"
    ]
    assert updated[0]["before"]["taxed_10"] == "110000"


# --- Bloqueo del período confirmado (D-089) ------------------------------------------


def test_confirmed_register_locks_the_month(client: TestClient, tax: str, db: Session) -> None:
    september = create_voucher(client, tax, issued_on="2026-09-20", number="001-001-0000050")
    october = create_voucher(client, tax, issued_on="2026-10-05", number="001-001-0000051")
    confirm_register(client, tax, "2026-10-01")
    res = _post(client, tax, issued_on="2026-10-30", number="001-001-0000052")
    assert res.status_code == 409 and _code(res) == "PERIOD_CONFIRMED"
    res = client.patch(
        f"{TAX}/vouchers/{october['id']}", json={"notes": "x"}, headers=auth_header(tax)
    )
    assert _code(res) == "PERIOD_CONFIRMED"
    res = client.post(
        f"{TAX}/vouchers/{october['id']}/void", json={"reason": "x" * 3}, headers=auth_header(tax)
    )
    assert _code(res) == "PERIOD_CONFIRMED"
    # Mover uno de septiembre a octubre tampoco.
    res = client.patch(
        f"{TAX}/vouchers/{september['id']}",
        json={"issued_on": "2026-10-10"},
        headers=auth_header(tax),
    )
    assert _code(res) == "PERIOD_CONFIRMED"
    assert (
        ok(client.get(f"{TAX}/vouchers/{october['id']}", headers=auth_header(tax)))[
            "period_confirmed"
        ]
        is True
    )
    # Por SQL directo, tampoco.
    rejected(
        db,
        "UPDATE tax.vouchers SET notes = 'x' WHERE id = :id",
        {"id": october["id"]},
        "trg_vouchers_period_locked",
    )
    rejected(
        db,
        "UPDATE tax.vouchers SET issued_on = '2026-10-11' WHERE id = :id",
        {"id": september["id"]},
        "trg_vouchers_period_locked",
    )
    # Reabrir (con motivo, auditado) lo desbloquea.
    reg = obligation(client, tax, "REG-COMPROB-MENSUAL", "2026-10-01")
    ok(
        client.post(
            f"{TAX}/obligations/{reg['id']}/reopen",
            json={"reason": "Faltó una factura"},
            headers=auth_header(tax),
        )
    )
    create_voucher(client, tax, issued_on="2026-10-30", number="001-001-0000052")
    reopened = [
        e
        for e in audit_entries(client, tax, "tax.obligation")
        if e["action"] == "tax.obligation.reopened"
    ]
    assert reopened and reopened[0]["after"]["reopen_reason"] == "Faltó una factura"


# --- Duplicados concurrentes con conexiones reales -------------------------------------


def test_concurrent_duplicates(own_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    client = _app_client(own_engine)
    fix_today(monkeypatch)
    res = client.post("/api/v1/system/setup", json=SETUP_BODY)
    if res.status_code == 201:
        token = res.json()["token"]
    else:  # la base del módulo ya tiene la organización de otra prueba
        token = client.post(
            "/api/v1/auth/login",
            json={
                "email": SETUP_BODY["owner"]["email"],
                "password": SETUP_BODY["owner"]["password"],
            },
        ).json()["token"]
    set_ruc(client, token, "80000005")
    load_rules(client, token)
    put_profile(client, token)
    barrier = Barrier(PARALLEL)
    body = voucher_body(number="009-009-0000999")

    def run(_: int) -> int:
        barrier.wait()
        return client.post(f"{TAX}/vouchers", json=body, headers=auth_header(token)).status_code

    with ThreadPoolExecutor(PARALLEL) as pool:
        codes = sorted(pool.map(run, range(PARALLEL)))
    assert codes == [201] + [409] * (PARALLEL - 1)
    with own_engine.begin() as conn:
        count = conn.scalar(
            text("SELECT count(*) FROM tax.vouchers WHERE number = '009-009-0000999'")
        )
    assert count == 1


def test_register_xlsx_opens_with_totals(client: TestClient, tax: str) -> None:
    create_voucher(
        client, tax, taxed_10="110000", taxed_5="21000", counterparty_name="A & B <S.A.>"
    )
    create_voucher(client, tax, number="001-001-0000099", taxed_10="220000", issued_on="2026-11-02")
    create_voucher(
        client,
        tax,
        number="001-001-0000098",
        issued_on="2026-11-03",
        counterparty_ruc="1234567A",
        counterparty_ruc_dv=None,
    )
    res = client.get(f"{TAX}/vouchers/export", params={"year": 2026}, headers=auth_header(tax))
    assert res.status_code == 200
    assert "registro-comprobantes-2026.xlsx" in res.headers["content-disposition"]
    sheet = load_workbook(io.BytesIO(res.content))["Comprobantes"]
    rows = list(sheet.iter_rows(values_only=True))
    assert sheet["A1"].font.b is True
    header = next(i for i, r in enumerate(rows) if r and r[0] == "Registro")
    data = rows[header + 1 : -1]
    assert len(data) == 3
    assert data[0][4] == "A & B <S.A.>"
    assert data[0][9] == 110000 and isinstance(data[0][9], int)
    assert sheet.cell(row=header + 2, column=10).number_format == "#,##0"
    assert data[2][2] == "1234567A" and data[2][3] is None
    total = rows[-1]
    assert total[0] == "Total" and total[12] == 110000 + 21000 + 220000 + 110000
    month = client.get(
        f"{TAX}/vouchers/export",
        params={"year": 2026, "month": 11, "direction": "purchase"},
        headers=auth_header(tax),
    )
    assert "registro-compras-2026-11.xlsx" in month.headers["content-disposition"]
    month_rows = list(load_workbook(io.BytesIO(month.content))["Comprobantes"].iter_rows())
    assert len(month_rows) == header + 1 + 2 + 1
