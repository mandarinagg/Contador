"""Registro de INGRESOS y EGRESOS del IRP-RSP y archivo anual 956 (fase M7, D-143).

El archivo esperado (`tests/golden/registro_anual_956.csv`) se arma acá desde las columnas del
YAML de la especificación (`docs/research/formato_registro_comprobantes.yaml`), no desde el
código que se prueba.
"""

import io
import os
import zipfile
from datetime import date
from typing import Any

import pytest
import yaml
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from tests.conftest import BACKEND_DIR, SETUP_BODY, STRONG_PASSWORD, auth_header
from tests.finance_utils import create_account, create_tx, ok, personal_context
from tests.register_utils import (
    CEDULA,
    EMPLOYER_RUC,
    PF,
    card_body,
    create,
    error_code,
    income_body,
    ips_body,
    payslip_body,
    person_profile,
    post_voucher,
    setup_person,
)
from tests.tax_utils import (
    SIFEN_CDC,
    SIFEN_DV,
    SIFEN_RUC,
    TAX,
    create_voucher,
    dv,
    file_obligation,
    obligation,
    org_id,
    rejected,
    setup_tax,
    user_id,
    voucher_body,
)
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture
from tests.test_tax_migration import api  # noqa: F401 - fixture

SPEC = os.path.join(BACKEND_DIR, "..", "docs", "research", "formato_registro_comprobantes.yaml")
GOLDEN = os.path.join(BACKEND_DIR, "tests", "golden", "registro_anual_956.csv")


@pytest.fixture
def person(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    return setup_person(client, monkeypatch)


def _spec() -> dict[str, Any]:
    with open(SPEC, encoding="utf-8") as handle:
        return dict(yaml.safe_load(handle))


# --- Alta, validación por tipo y perfil ----------------------------------------------------


def test_income_and_expenses_without_timbrado(client: TestClient, person: str) -> None:
    income = create(client, person, income_body())
    assert income["timbrado"] is None
    assert income["number"] == "R-15"
    assert income["total"] == "350000"
    assert (income["imputes_vat"], income["imputes_irp"]) == (False, True)  # por defecto, al IRP
    assert income["rules_applied"] == [] and income["rule_status"] is None
    # El período de la liquidación y del extracto de IPS se guarda el día 1.
    payslip = create(client, person, payslip_body(issued_on="2026-02-25"))
    assert payslip["issued_on"] == "2026-02-01" and payslip["number"] is None
    ips = create(client, person, ips_body(issued_on="2026-04-18"))
    assert ips["issued_on"] == "2026-04-01"
    assert ips["counterparty_doc_type"] is None
    assert ips["counterparty_name"] == "Instituto de Previsión Social"
    card = create(client, person, card_body())
    assert (card["account_number"], card["bank_name"]) == ("4111-XXXX-1234", "Banco Uno")
    # La 208 también va como egreso (aporte) del mismo empleador y período.
    create(client, person, payslip_body(direction="expense", taxed_10="450000"))
    listed = ok(
        client.get(
            f"{TAX}/vouchers",
            params={"year": 2026, "direction": "expense"},
            headers=auth_header(person),
        )
    )
    assert {v["voucher_type"] for v in listed} == {"ips_statement", "card_statement", "payslip"}
    by_type = ok(
        client.get(
            f"{TAX}/vouchers",
            params={"voucher_type": "payslip"},
            headers=auth_header(person),
        )
    )
    assert {v["direction"] for v in by_type} == {"income", "expense"}
    # Las compras con timbrado siguen igual, imputando al IRP.
    purchase = create_voucher(client, person, imputes_vat=False, imputes_irp=True)
    assert purchase["timbrado"] == "12345678" and purchase["rules_applied"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (income_body(voucher_type="ips_statement"), "VOUCHER_TYPE_INVALID"),
        (income_body(voucher_type="invoice"), "VOUCHER_TYPE_INVALID"),
        (income_body(timbrado="12345678"), "FIELD_NOT_APPLICABLE"),
        (income_body(is_electronic=True), "CDC_NOT_APPLICABLE"),
        (income_body(number=None), "VOUCHER_NUMBER_REQUIRED"),
        (income_body(document_description=None), "FIELD_REQUIRED"),
        (income_body(account_number="123"), "FIELD_NOT_APPLICABLE"),
        (income_body(counterparty_doc_type="foreign_id"), "COUNTERPARTY_DOC_TYPE_INVALID"),
        (income_body(counterparty_doc_type=None), "COUNTERPARTY_REQUIRED"),
        (income_body(imputes_vat=True), "IMPUTES_VAT_NOT_APPLICABLE"),
        (income_body(taxed_5="1000"), "AMOUNT_NOT_APPLICABLE"),
        (income_body(taxed_10="0", exempt="0"), "VOUCHER_TOTAL_ZERO"),
        (income_body(issued_on="2020-12-31"), "DATE_BEFORE_REGISTER"),
        (payslip_body(counterparty_doc_type="identity_card"), "COUNTERPARTY_DOC_TYPE_INVALID"),
        (ips_body(ips_employer_number=None), "FIELD_REQUIRED"),
        (ips_body(exempt="1000"), "AMOUNT_NOT_APPLICABLE"),
        (card_body(bank_name=None), "FIELD_REQUIRED"),
        (card_body(counterparty_name=None), "COUNTERPARTY_NAME_REQUIRED"),
        (
            income_body(voucher_type="credit_sale", document_description=None, related_number=None),
            "FIELD_REQUIRED",
        ),
        (
            ips_body(voucher_type="foreign_voucher", ips_employer_number=None, number="X-1"),
            "COUNTERPARTY_REQUIRED",
        ),
        (
            card_body(
                voucher_type="public_entity",
                number="1",
                account_number=None,
                bank_name=None,
                counterparty_doc_type="identity_card",
                counterparty_document="2345678",
            ),
            "COUNTERPARTY_DOC_TYPE_INVALID",
        ),
        # Una compra sigue pidiendo timbrado y número EEE-PPP-NNNNNNN, y no lleva lo nuevo.
        (voucher_body(timbrado=None), "TIMBRADO_REQUIRED"),
        (voucher_body(number="R-15"), "VOUCHER_NUMBER_INVALID"),
        (voucher_body(voucher_type="payslip"), "VOUCHER_TYPE_INVALID"),
        (voucher_body(bank_name="Banco Uno"), "FIELD_NOT_APPLICABLE"),
    ],
)
def test_validation_per_type(
    client: TestClient, person: str, body: dict[str, Any], code: str
) -> None:
    res = post_voucher(client, person, body)
    assert res.status_code == 422, res.text
    assert error_code(res) == code


def test_register_only_with_956(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Una empresa con IVA (211 y 955): el registro es el mensual.
    setup_tax(client, owner_token, monkeypatch)
    res = post_voucher(client, owner_token, income_body())
    assert res.status_code == 422 and error_code(res) == "REGISTER_NOT_AVAILABLE"
    res = client.get(
        f"{TAX}/vouchers/export/annual-preview",
        params={"year": 2026},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 422 and error_code(res) == "ANNUAL_REGISTER_NOT_APPLICABLE"


def test_register_follows_the_profile_at_year_end(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = setup_person(client, monkeypatch, register=False)
    res = post_voucher(client, token, income_body())
    assert error_code(res) == "REGISTER_NOT_AVAILABLE"
    person_profile(client, token, monkeypatch)
    create(client, token, income_body())
    # 2024: ningún perfil vigente al cierre.
    assert error_code(post_voucher(client, token, income_body(issued_on="2024-05-02"))) == (
        "REGISTER_NOT_AVAILABLE"
    )


def test_update_void_and_no_entry(client: TestClient, person: str) -> None:
    card = create(client, person, card_body())
    headers = auth_header(person)
    # Cambiar de tipo exige vaciar lo que el tipo nuevo no usa.
    res = client.patch(
        f"{TAX}/vouchers/{card['id']}",
        json={"voucher_type": "bank_transfer", "number": "TRX-9"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["voucher_type"] == "bank_transfer"
    res = client.patch(
        f"{TAX}/vouchers/{card['id']}",
        json={"voucher_type": "ips_statement", "ips_employer_number": "1"},
        headers=headers,
    )
    assert res.status_code == 422 and error_code(res) == "FIELD_NOT_APPLICABLE"
    res = client.post(
        f"{TAX}/vouchers/{card['id']}/propose-entry",
        json={"account_id": card["id"]},
        headers=headers,
    )
    assert res.status_code == 422 and error_code(res) == "VOUCHER_ENTRY_NOT_SUPPORTED"
    voided = ok(
        client.post(f"{TAX}/vouchers/{card['id']}/void", json={"reason": "Prueba"}, headers=headers)
    )
    assert voided["voided_at"] is not None


def test_personal_context_is_never_read(client: TestClient, person: str) -> None:
    """D-035: un ingreso no se vincula con un movimiento personal (no existe para lo tributario)."""
    personal = personal_context(client, person)
    account = create_account(client, person, personal, "Personal")
    tx = create_tx(client, person, personal, account["id"], "350000", booked_on="2026-03-10")
    res = post_voucher(client, person, income_body(transaction_id=tx["id"]))
    assert res.status_code == 404, res.text


def test_viewer_reads_but_does_not_write(client: TestClient, person: str) -> None:
    res = client.post(
        "/api/v1/users",
        json={
            "email": "lectora@example.com",
            "full_name": "Lectora",
            "password": STRONG_PASSWORD,
            "role": "viewer",
        },
        headers=auth_header(person),
    )
    ok(res, 201)
    login = client.post(
        "/api/v1/auth/login", json={"email": "lectora@example.com", "password": STRONG_PASSWORD}
    )
    viewer = str(ok(login)["token"])
    create(client, person, income_body())
    assert post_voucher(client, viewer, income_body(number="R-16")).status_code == 403
    for path in ("/vouchers/export/annual-preview", "/vouchers/export/annual"):
        res = client.get(f"{TAX}{path}", params={"year": 2026}, headers=auth_header(viewer))
        assert res.status_code == 200, (path, res.text)


# --- Anti duplicado ------------------------------------------------------------------------


def test_duplicates_with_and_without_number(client: TestClient, person: str) -> None:
    first = create(client, person, income_body())
    res = post_voucher(client, person, income_body(issued_on="2026-04-01"))
    assert res.status_code == 409 and error_code(res) == "VOUCHER_DUPLICATE"
    assert res.json()["error"]["details"]["voucher_id"] == first["id"]
    # Otro emisor con el mismo número no es el mismo comprobante.
    create(client, person, income_body(counterparty_document="3456789"))
    # Sin número: el período (y el empleador en el extracto de IPS).
    create(client, person, ips_body())
    res = post_voucher(client, person, ips_body(issued_on="2026-04-30", taxed_10="1"))
    assert res.status_code == 409 and error_code(res) == "VOUCHER_DUPLICATE"
    create(client, person, ips_body(issued_on="2026-05-01"))
    create(client, person, ips_body(ips_employer_number="0099999"))
    # Con número, el mismo extracto ya no choca con el que no lo tiene.
    create(client, person, ips_body(number="E-1"))
    # Ingreso y egreso de la misma liquidación: registros distintos.
    create(client, person, payslip_body())
    create(client, person, payslip_body(direction="expense"))
    assert error_code(post_voucher(client, person, payslip_body())) == "VOUCHER_DUPLICATE"
    # Anulado, se vuelve a cargar; y editar uno para que choque también se rechaza.
    headers = auth_header(person)
    ok(client.post(f"{TAX}/vouchers/{first['id']}/void", json={"reason": "Mal"}, headers=headers))
    again = create(client, person, income_body())
    other = create(client, person, income_body(number="R-99"))
    res = client.patch(f"{TAX}/vouchers/{other['id']}", json={"number": "R-15"}, headers=headers)
    assert res.status_code == 409 and res.json()["error"]["details"]["voucher_id"] == again["id"]


# --- CHECK y unicidad en la base, sin la API --------------------------------------------------

BASE: dict[str, Any] = {
    "direction": "income",
    "voucher_type": "other_income",
    "is_electronic": False,
    "cdc": None,
    "timbrado": None,
    "number": "R-1",
    "issued_on": date(2026, 3, 10),
    "counterparty_doc_type": "identity_card",
    "counterparty_ruc": None,
    "counterparty_ruc_dv": None,
    "counterparty_document": "2345678",
    "counterparty_name": "Juan Pérez",
    "condition": "cash",
    "taxed_10": 100,
    "taxed_5": 0,
    "exempt": 0,
    "vat_10": 0,
    "vat_5": 0,
    "imputes_vat": False,
    "imputes_ire": False,
    "imputes_irp": True,
    "vat_rule_version_id": None,
    "context_kind": "business",
    "account_number": None,
    "bank_name": None,
    "ips_employer_number": None,
    "document_description": "Recibo",
    "related_number": None,
    "related_timbrado": None,
}
IPS = {
    "direction": "expense",
    "voucher_type": "ips_statement",
    "number": None,
    "issued_on": date(2026, 4, 1),
    "counterparty_doc_type": None,
    "counterparty_document": None,
    "counterparty_name": "IPS",
    "document_description": None,
    "ips_employer_number": "0012345",
}
CARD = {
    **IPS,
    "voucher_type": "card_statement",
    "issued_on": date(2026, 5, 20),
    "ips_employer_number": None,
    "account_number": "4111",
    "bank_name": "Banco Uno",
}
CREDIT_SALE = {
    "voucher_type": "credit_sale",
    "document_description": None,
    "related_number": "001-001-0000010",
    "related_timbrado": "11111111",
}
PURCHASE = {
    "direction": "purchase",
    "voucher_type": "invoice",
    "timbrado": "12345678",
    "number": "001-001-0000001",
    "counterparty_doc_type": "ruc",
    "counterparty_ruc": SIFEN_RUC,
    "counterparty_ruc_dv": SIFEN_DV,
    "counterparty_document": None,
    "document_description": None,
    "taxed_10": 110,
    "vat_10": 10,
    "vat_rule_version_id": "RULE",
}

# (cambios sobre BASE, restricción que lo rechaza; None = válido).
MATRIX: list[tuple[str, dict[str, Any], str | None]] = [
    ("ingreso válido", {}, None),
    ("extracto de IPS válido", IPS, None),
    ("extracto de tarjeta válido", CARD, None),
    ("tarjeta que imputa IVA (207)", {**CARD, "imputes_vat": True}, None),
    ("cobro de venta a crédito válido", CREDIT_SALE, None),
    ("compra válida", PURCHASE, None),
    # Cada caso rompe una sola restricción (la base las revisa en orden alfabético).
    ("tipo de otro registro", {"voucher_type": "other_expense"}, "ck_vouchers_type_valid"),
    (
        "factura como ingreso",
        {"voucher_type": "invoice", "document_description": None},
        "ck_vouchers_type_valid",
    ),
    ("dirección desconocida", {"direction": "loan"}, "ck_vouchers_direction_valid"),
    ("ingreso con timbrado", {"timbrado": "12345678"}, "ck_vouchers_timbrado_when_timbrado"),
    ("compra sin timbrado", {**PURCHASE, "timbrado": None}, "ck_vouchers_timbrado_when_timbrado"),
    ("compra sin número", {**PURCHASE, "number": None}, "ck_vouchers_number_required"),
    ("compra con número libre", {**PURCHASE, "number": "R-1"}, "ck_vouchers_number_format"),
    ("ingreso sin número", {"number": None}, "ck_vouchers_number_required"),
    ("número en blanco", {"number": "  "}, "ck_vouchers_number_format"),
    (
        "ingreso electrónico",
        {"is_electronic": True, "cdc": SIFEN_CDC},
        "ck_vouchers_register_not_electronic",
    ),
    ("ingreso con regla de IVA", {"vat_rule_version_id": "RULE"}, "ck_vouchers_vat_rule_when_vat"),
    (
        "compra sin regla de IVA",
        {**PURCHASE, "vat_rule_version_id": None},
        "ck_vouchers_vat_rule_when_vat",
    ),
    ("ingreso con gravado al 5 %", {"taxed_5": 10}, "ck_vouchers_register_amounts"),
    ("ingreso con IVA", {"vat_10": 1}, "ck_vouchers_register_amounts"),
    ("egreso con no gravado", {**IPS, "exempt": 5}, "ck_vouchers_register_amounts"),
    ("ingreso que imputa IVA", {"imputes_vat": True}, "ck_vouchers_register_imputes_vat"),
    ("IPS a mitad de mes", {**IPS, "issued_on": date(2026, 4, 15)}, "ck_vouchers_period_first_day"),
    (
        "ingreso sin contraparte",
        {"counterparty_doc_type": None, "counterparty_document": None},
        "ck_vouchers_counterparty_required",
    ),
    (
        "documento sin tipo",
        {**IPS, "counterparty_document": "2345678"},
        "ck_vouchers_counterparty_ids_with_type",
    ),
    (
        "liquidación con cédula",
        {
            "voucher_type": "payslip",
            "number": None,
            "document_description": None,
            "issued_on": date(2026, 3, 1),
        },
        "ck_vouchers_counterparty_by_type",
    ),
    (
        "comprobante del exterior con cédula",
        {"direction": "expense", "voucher_type": "foreign_voucher", "document_description": None},
        "ck_vouchers_counterparty_by_type",
    ),
    (
        "ingreso «sin nombre»",
        {"counterparty_doc_type": "unnamed", "counterparty_document": None},
        "ck_vouchers_counterparty_by_type",
    ),
    ("tarjeta sin cuenta", {**CARD, "account_number": None}, "ck_vouchers_account_when_account"),
    ("IPS con banco", {**IPS, "bank_name": "Banco"}, "ck_vouchers_account_when_account"),
    (
        "IPS sin empleador",
        {**IPS, "ips_employer_number": None},
        "ck_vouchers_ips_employer_when_ips",
    ),
    (
        "ingreso sin descripción",
        {"document_description": None},
        "ck_vouchers_description_when_other",
    ),
    (
        "IPS con descripción",
        {**IPS, "document_description": "X"},
        "ck_vouchers_description_when_other",
    ),
    (
        "cobro sin comprobante asociado",
        {**CREDIT_SALE, "related_timbrado": None},
        "ck_vouchers_related_when_credit",
    ),
    (
        "comprobante asociado en otro tipo",
        {"related_number": "001-001-0000010", "related_timbrado": "11111111"},
        "ck_vouchers_related_when_credit",
    ),
    (
        "comprobante asociado mal escrito",
        {**CREDIT_SALE, "related_number": "1-1-10"},
        "ck_vouchers_related_format",
    ),
    ("banco en blanco", {**CARD, "bank_name": "  "}, "ck_vouchers_register_texts_not_blank"),
    ("contexto personal (D-035)", {"context_kind": "personal"}, "ck_vouchers_business_only"),
]


def _insert(db: Session, values: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    params = {**BASE, **values}
    if params["vat_rule_version_id"] == "RULE":
        params["vat_rule_version_id"] = db.scalar(
            text("SELECT id FROM tax.rule_versions WHERE code = 'IVA-GENERAL-TASAS' LIMIT 1")
        )
    org = org_id(db)
    params |= {
        "organization_id": org,
        "context_id": db.scalar(
            text(
                "SELECT id FROM finance.contexts WHERE organization_id = :o AND kind = 'business'"
            ),
            {"o": org},
        ),
        "created_by": user_id(db),
    }
    columns = ", ".join(params)
    marks = ", ".join(f":{c}" for c in params)
    return f"INSERT INTO tax.vouchers ({columns}) VALUES ({marks})", params  # noqa: S608


def test_check_matrix_in_the_database(client: TestClient, person: str, db: Session) -> None:
    for label, values, constraint in MATRIX:
        sql, params = _insert(db, values)
        if constraint is None:
            nested = db.begin_nested()
            db.execute(text(sql), params)
            nested.rollback()
        else:
            try:
                rejected(db, sql, params, constraint)
            except AssertionError as exc:  # pragma: no cover - mensaje de diagnóstico
                raise AssertionError(f"{label}: {exc}") from exc


def test_unique_indexes_in_the_database(client: TestClient, person: str, db: Session) -> None:
    for values, index in (
        ({}, "uq_vouchers_register_numbered_live"),
        (IPS, "uq_vouchers_register_unnumbered_live"),
        (CARD, "uq_vouchers_register_unnumbered_live"),
    ):
        sql, params = _insert(db, values)
        db.execute(text(sql), params)
        rejected(db, sql, {**params, "taxed_10": 1}, index)
    # Anulado deja lugar a otro igual (índices parciales sobre los vivos).
    db.execute(
        text(
            "UPDATE tax.vouchers SET voided_at = now(), voided_by = created_by,"
            " void_reason = 'Prueba' WHERE voucher_type = 'ips_statement'"
        )
    )
    sql, params = _insert(db, IPS)
    db.execute(text(sql), params)


# --- Registro anual confirmado -------------------------------------------------------------


def test_filed_annual_register_locks_the_year(client: TestClient, person: str, db: Session) -> None:
    income = create(client, person, income_body())
    ok(client.post(f"{TAX}/obligations/sync", headers=auth_header(person)))
    row = obligation(client, person, "REG-COMPROB-ANUAL", "2026-01-01")
    file_obligation(client, person, row["id"], filed_on="2026-11-20")
    res = post_voucher(client, person, ips_body())
    assert res.status_code == 409 and error_code(res) == "PERIOD_CONFIRMED"
    assert res.json()["error"]["details"]["year"] == 2026
    res = client.post(
        f"{TAX}/vouchers/{income['id']}/void",
        json={"reason": "Prueba"},
        headers=auth_header(person),
    )
    assert error_code(res) == "PERIOD_CONFIRMED"
    listed = ok(client.get(f"{TAX}/vouchers", params={"year": 2026}, headers=auth_header(person)))
    assert listed[0]["period_confirmed"] is True
    # La base también lo impide (trigger del período confirmado).
    rejected(
        db,
        "UPDATE tax.vouchers SET notes = 'x' WHERE id = :id",
        {"id": income["id"]},
        "trg_vouchers_period_locked",
    )
    # Otro año sigue abierto.
    create(client, person, income_body(number="R-30", issued_on="2025-06-01"))


# --- Archivo anual 956: archivo de referencia desde el YAML --------------------------------


def _expected_rows() -> list[dict[str, str]]:
    """Las filas del archivo de referencia por nombre de columna del YAML (registro, campos)."""
    employer = {"ruc": EMPLOYER_RUC, "name": "Empleador SA"}
    return [
        {
            "_": "COMPRAS",
            "CODIGO_TIPO_REGISTRO": "2",
            "CODIGO_TIPO_IDENTIFICACION_PROVEEDOR": "11",
            "NUMERO_IDENTIFICACION_PROVEEDOR": SIFEN_RUC,
            "NOMBRE_RAZON_SOCIAL_PROVEEDOR": "Proveedor de Prueba S.A.",
            "CODIGO_TIPO_COMPROBANTE": "109",
            "FECHA_EMISION": "15/01/2026",
            "NUMERO_TIMBRADO": "12345678",
            "NUMERO_COMPROBANTE": "001-001-0000001",
            "MONTO_GRAVADO_10_IVA_INCLUIDO": "110000",
            "MONTO_GRAVADO_5_IVA_INCLUIDO": "0",
            "MONTO_NO_GRAVADO_O_EXENTO": "0",
            "MONTO_TOTAL": "110000",
            "CODIGO_CONDICION_COMPRA": "1",
            "OPERACION_EN_MONEDA_EXTRANJERA": "N",
            "IMPUTA_IVA": "N",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
            "NO_IMPUTA": "N",
        },
        {
            "_": "INGRESOS",
            "CODIGO_TIPO_REGISTRO": "3",
            "CODIGO_TIPO_COMPROBANTE": "208",
            "FECHA_EMISION_O_PERIODO": "02/2026",
            "CODIGO_TIPO_IDENTIFICACION_PAGADOR": "11",
            "NUMERO_IDENTIFICACION_PAGADOR": employer["ruc"],
            "NOMBRE_RAZON_SOCIAL_PAGADOR": employer["name"],
            "MONTO_GRAVADO": "5000000",
            "MONTO_NO_GRAVADO_EXONERADO": "0",
            "MONTO_TOTAL": "5000000",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
        },
        {
            "_": "INGRESOS",
            "CODIGO_TIPO_REGISTRO": "3",
            "CODIGO_TIPO_COMPROBANTE": "210",
            "FECHA_EMISION_O_PERIODO": "10/03/2026",
            "NUMERO_COMPROBANTE": "R-15",
            "CODIGO_TIPO_IDENTIFICACION_PAGADOR": "12",
            "NUMERO_IDENTIFICACION_PAGADOR": "2345678",
            "NOMBRE_RAZON_SOCIAL_PAGADOR": "Juan Pérez",
            "MONTO_GRAVADO": "300000",
            "MONTO_NO_GRAVADO_EXONERADO": "50000",
            "MONTO_TOTAL": "350000",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
            "ESPECIFICAR_TIPO_DOCUMENTO": "Recibo de honorarios",
        },
        {
            "_": "EGRESOS",
            "CODIGO_TIPO_REGISTRO": "4",
            "CODIGO_TIPO_COMPROBANTE": "206",
            "FECHA_EMISION_O_PERIODO": "04/2026",
            "NOMBRE_O_DESCRIPCION": "Instituto de Previsión Social",
            "MONTO_TOTAL": "450000",
            "IMPUTA_IVA": "N",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
            "NO_IMPUTA": "N",
            "NUMERO_EMPLEADOR_IPS": "0012345",
        },
        {
            "_": "EGRESOS",
            "CODIGO_TIPO_REGISTRO": "4",
            "CODIGO_TIPO_COMPROBANTE": "207",
            "FECHA_EMISION_O_PERIODO": "20/05/2026",
            "NOMBRE_O_DESCRIPCION": "Gastos médicos",
            "MONTO_TOTAL": "800000",
            "IMPUTA_IVA": "N",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
            "NO_IMPUTA": "N",
            "NUMERO_CUENTA_O_TARJETA": "4111-XXXX-1234",
            "BANCO_FINANCIERA_COOPERATIVA": "Banco Uno",
        },
        {
            "_": "EGRESOS",
            "CODIGO_TIPO_REGISTRO": "4",
            "CODIGO_TIPO_COMPROBANTE": "201",
            "FECHA_EMISION_O_PERIODO": "05/06/2026",
            "NUMERO_COMPROBANTE_O_TRANSACCION": "REC-77",
            "CODIGO_TIPO_IDENTIFICACION_CONTRAPARTE": "11",
            "NUMERO_IDENTIFICACION_CONTRAPARTE": SIFEN_RUC,
            "NOMBRE_O_DESCRIPCION": "Proveedor de Prueba S.A.",
            "MONTO_TOTAL": "200000",
            "IMPUTA_IVA": "N",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
            "NO_IMPUTA": "N",
            "NUMERO_COMPROBANTE_COMPRA_ASOCIADO": "001-002-0000050",
            "TIMBRADO_COMPROBANTE_COMPRA_ASOCIADO": "87654321",
        },
        {
            "_": "VENTAS",
            "CODIGO_TIPO_REGISTRO": "1",
            "CODIGO_TIPO_IDENTIFICACION_COMPRADOR": "11",
            "NUMERO_IDENTIFICACION_COMPRADOR": employer["ruc"],
            "NOMBRE_RAZON_SOCIAL_COMPRADOR": employer["name"],
            "CODIGO_TIPO_COMPROBANTE": "109",
            "FECHA_EMISION": "01/07/2026",
            "NUMERO_TIMBRADO": "11111111",
            "NUMERO_COMPROBANTE": "001-001-0000010",
            "MONTO_GRAVADO_10_IVA_INCLUIDO": "0",
            "MONTO_GRAVADO_5_IVA_INCLUIDO": "0",
            "MONTO_NO_GRAVADO_O_EXENTO": "1000000",
            "MONTO_TOTAL": "1000000",
            "CODIGO_CONDICION_VENTA": "1",
            "OPERACION_EN_MONEDA_EXTRANJERA": "N",
            "IMPUTA_IVA": "N",
            "IMPUTA_IRE": "N",
            "IMPUTA_IRP_RSP": "S",
        },
    ]


def _render(spec: dict[str, Any], record: dict[str, str]) -> str:
    """Una línea en el orden de columnas del YAML; las condicionales vacías, y las `requerido:
    true` siempre con valor."""
    fields = spec["registros"][record["_"]]
    names = [f["campo"] for f in fields]
    unknown = set(record) - {"_", *names}
    assert not unknown, f"columnas que el YAML no tiene en {record['_']}: {unknown}"
    for f in fields:
        if f["requerido"] is True:
            assert record.get(f["campo"]), f"{record['_']}: falta {f['campo']}"
        if "valores" in f:
            assert int(record[f["campo"]]) in f["valores"]
    assert int(record["CODIGO_TIPO_REGISTRO"]) == next(
        k for k, v in spec["tipos_de_registro"].items() if v == record["_"]
    )
    code = int(record["CODIGO_TIPO_COMPROBANTE"])
    assert record["_"] in spec["tipos_de_comprobante"][code]["registros"]
    return ";".join(record.get(name, "") for name in names)


def _load_year(client: TestClient, token: str) -> None:
    headers = auth_header(token)
    create_voucher(client, token, issued_on="2026-01-15", imputes_vat=False, imputes_irp=True)
    create(client, token, payslip_body())
    create(client, token, income_body())
    create(client, token, ips_body())
    create(client, token, card_body())
    create(
        client,
        token,
        card_body(
            voucher_type="credit_purchase",
            issued_on="2026-06-05",
            number="REC-77",
            counterparty_doc_type="ruc",
            counterparty_ruc=SIFEN_RUC,
            counterparty_ruc_dv=SIFEN_DV,
            counterparty_name="Proveedor de Prueba S.A.",
            account_number=None,
            bank_name=None,
            related_number="001-002-0000050",
            related_timbrado="87654321",
            taxed_10="200000",
        ),
    )
    create_voucher(
        client,
        token,
        direction="sale",
        issued_on="2026-07-01",
        timbrado="11111111",
        number="001-001-0000010",
        counterparty_ruc=EMPLOYER_RUC,
        counterparty_ruc_dv=dv(EMPLOYER_RUC),
        counterparty_name="Empleador SA",
        taxed_10="0",
        exempt="1000000",
        imputes_vat=False,
        imputes_irp=True,
    )
    # Fuera del archivo: anulado, sin imputación y de otro año.
    voided = create(client, token, income_body(number="R-20", issued_on="2026-08-01"))
    ok(client.post(f"{TAX}/vouchers/{voided['id']}/void", json={"reason": "Mal"}, headers=headers))
    create(client, token, income_body(number="R-21", issued_on="2026-09-01", imputes_irp=False))
    create(client, token, income_body(number="R-22", issued_on="2025-12-31"))


def test_golden_file_matches_the_spec() -> None:
    spec = _spec()
    assert len(spec["registros"]["INGRESOS"]) == 15
    assert len(spec["registros"]["EGRESOS"]) == 18
    with open(GOLDEN, "rb") as handle:
        golden = handle.read()
    expected = "".join(f"{_render(spec, r)}\r\n" for r in _expected_rows())
    assert golden.decode("utf-8") == expected
    for line in golden.decode("utf-8").split("\r\n")[:-1]:
        name = spec["tipos_de_registro"][int(line.split(";")[0])]
        assert len(line.split(";")) == len(spec["registros"][name])


def test_annual_file(client: TestClient, person: str) -> None:
    _load_year(client, person)
    headers = auth_header(person)
    preview = ok(
        client.get(f"{TAX}/vouchers/export/annual-preview", params={"year": 2026}, headers=headers)
    )
    assert preview["rows"] == 7
    assert preview["batches"] == [{"name": f"{CEDULA}_REG_2026_00001.zip", "rows": 7}]
    assert preview["excluded_not_imputed"]["count"] == 1
    assert {r["code"] for r in preview["rules_applied"]} == {
        "REG-COMPROB-IMPORTACION",
        "REG-COMPROB-ANUAL",
    }
    assert preview["rule_status"] == "pending" and preview["is_draft"] is True
    res = client.get(f"{TAX}/vouchers/export/annual", params={"year": 2026}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    # Nombre oficial del 956: <RUC sin DV>_REG_<AAAA>_<id de hasta 5>.
    name = f"{CEDULA}_REG_2026_00001"
    assert f'filename="{name}.zip"' in res.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        assert archive.namelist() == [f"{name}.csv"]
        content = archive.read(f"{name}.csv")
    with open(GOLDEN, "rb") as handle:
        assert content == handle.read()
    # Separador coma, identificador elegido y `limit` para probar con uno.
    res = client.get(
        f"{TAX}/vouchers/export/annual",
        params={"year": 2026, "separator": "comma", "first_id": 7, "limit": 1},
        headers=headers,
    )
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        lines = archive.read(f"{CEDULA}_REG_2026_00007.csv").decode("utf-8").split("\r\n")
    assert lines[1:] == [""] and lines[0].startswith("2,11,")
    # Un año sin nada.
    res = client.get(f"{TAX}/vouchers/export/annual", params={"year": 2027}, headers=headers)
    assert res.status_code == 422 and error_code(res) == "NOTHING_TO_EXPORT"


def test_monthly_file_and_vat_leave_the_register_out(client: TestClient, person: str) -> None:
    """La 955 no cambia: los ingresos y egresos no van en el archivo mensual ni en el IVA."""
    create(client, person, income_body())
    create_voucher(client, person, issued_on="2026-03-05", imputes_vat=False, imputes_irp=True)
    headers = auth_header(person)
    preview = ok(
        client.get(
            f"{TAX}/vouchers/export/marangatu-preview",
            params={"year": 2026, "month": 3},
            headers=headers,
        )
    )
    assert preview["rows"] == 1
    assert any("registro anual (956)" in w for w in preview["warnings"])
    vat = ok(client.get(f"{TAX}/vat/2026/3", headers=headers))
    assert vat["credit"]["purchases"]["rate_10"]["vat"] == "0"  # la compra no imputa IVA
    res = client.get(
        f"{TAX}/vouchers/export", params={"year": 2026, "format": "xlsx"}, headers=headers
    )
    assert res.status_code == 200


# --- Migración 0013 ------------------------------------------------------------------------


def _scalar(engine: Engine, sql: str) -> Any:
    with engine.connect() as conn:
        return conn.scalar(text(sql))


def test_migration_0013(
    migration_db: tuple[Config, Engine],  # noqa: F811
    api: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, engine = migration_db
    head = ScriptDirectory.from_config(cfg).get_current_head()
    command.upgrade(cfg, "head")
    command.check(cfg)
    # Con compras y ventas solamente, baja y sube sin perder nada.
    token = ok(api.post("/api/v1/system/setup", json={**SETUP_BODY, "organization": PF}), 201)[
        "token"
    ]
    person_profile(api, token, monkeypatch)
    purchase = create_voucher(api, token, imputes_vat=False, imputes_irp=True)
    command.downgrade(cfg, "0012")
    assert _scalar(engine, "SELECT count(*) FROM tax.vouchers") == 1
    # Antes de la 0013 la base no admite un ingreso.
    with pytest.raises(Exception, match="direction_valid"), engine.begin() as conn:
        conn.execute(text("CREATE TEMP TABLE copy ON COMMIT DROP AS SELECT * FROM tax.vouchers"))
        conn.execute(text("UPDATE copy SET id = uuidv7(), direction = 'income'"))
        conn.execute(text("INSERT INTO tax.vouchers SELECT * FROM copy"))
    command.upgrade(cfg, "head")
    command.check(cfg)
    # Un egreso, aunque esté anulado, impide bajar (D-080).
    expense = create(api, token, ips_body())
    ok(
        api.post(
            f"{TAX}/vouchers/{expense['id']}/void",
            json={"reason": "Prueba"},
            headers=auth_header(token),
        )
    )
    with pytest.raises(RuntimeError, match=r"hay 1 comprobante\(s\) de ingreso o egreso"):
        command.downgrade(cfg, "0012")
    assert _scalar(engine, "SELECT version_num FROM alembic_version") == head
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tax.vouchers DISABLE TRIGGER vouchers_no_delete"))
        conn.execute(text("DELETE FROM tax.vouchers WHERE direction = 'expense'"))
        conn.execute(text("ALTER TABLE tax.vouchers ENABLE TRIGGER vouchers_no_delete"))
    command.downgrade(cfg, "0012")
    assert _scalar(engine, "SELECT id::text FROM tax.vouchers") == purchase["id"]
    command.upgrade(cfg, "head")
    command.check(cfg)
