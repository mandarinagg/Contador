"""Ayudas para las pruebas del registro de INGRESOS y EGRESOS (fase M7, D-143).

Persona física con IRP-RSP (715) y el registro anual (956), sin IVA, desde el 01-01-2025.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.tax_utils import TAX, dv, fix_today, load_rules, put_profile, set_ruc

PF = {"legal_form": "PERSONA_FISICA", "first_names": "María José", "last_names": "Benítez Duarte"}
CEDULA = "1234567"
EMPLOYER_RUC = "80000005"
REGISTER_OBLIGATIONS = (("715", "2025-01-01"), ("956", "2025-01-01"))


def setup_person(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, *, register: bool = True
) -> str:
    """Persona física con RUC, reglas y perfil «sin IRE», sin IVA, con la 715 y (si se pide) la
    956. Devuelve el token de su propietaria."""
    res = client.post("/api/v1/system/setup", json={**SETUP_BODY, "organization": PF})
    assert res.status_code == 201, res.text
    token = str(res.json()["token"])
    person_profile(client, token, monkeypatch, register=register)
    return token


def person_profile(
    client: TestClient,
    token: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    register: bool = True,
    ruc: str = CEDULA,
) -> None:
    fix_today(monkeypatch)
    set_ruc(client, token, ruc)
    load_rules(client, token)
    put_profile(
        client,
        token,
        valid_from="2025-01-01",
        ire_regime="none",
        vat_taxpayer=False,
        obligations=REGISTER_OBLIGATIONS if register else (("715", "2025-01-01"),),
    )


def income_body(**overrides: Any) -> dict[str, Any]:
    """Otro comprobante de ingreso (210): honorarios cobrados a una persona con cédula."""
    body: dict[str, Any] = {
        "direction": "income",
        "voucher_type": "other_income",
        "issued_on": "2026-03-10",
        "number": "R-15",
        "counterparty_doc_type": "identity_card",
        "counterparty_document": "2345678",
        "counterparty_name": "Juan Pérez",
        "taxed_10": "300000",
        "exempt": "50000",
        "document_description": "Recibo de honorarios",
    }
    body.update(overrides)
    return body


def payslip_body(**overrides: Any) -> dict[str, Any]:
    """Liquidación de salario (208) como ingreso: período, sin número, RUC del empleador."""
    body: dict[str, Any] = {
        "direction": "income",
        "voucher_type": "payslip",
        "issued_on": "2026-02-01",
        "counterparty_doc_type": "ruc",
        "counterparty_ruc": EMPLOYER_RUC,
        "counterparty_ruc_dv": dv(EMPLOYER_RUC),
        "counterparty_name": "Empleador SA",
        "taxed_10": "5000000",
    }
    body.update(overrides)
    return body


def ips_body(**overrides: Any) -> dict[str, Any]:
    """Extracto de cuenta de IPS (206): sin número ni contraparte, con el número de empleador."""
    body: dict[str, Any] = {
        "direction": "expense",
        "voucher_type": "ips_statement",
        "issued_on": "2026-04-01",
        "counterparty_doc_type": None,
        "ips_employer_number": "0012345",
        "taxed_10": "450000",
    }
    body.update(overrides)
    return body


def card_body(**overrides: Any) -> dict[str, Any]:
    """Extracto de tarjeta (207): sin número ni contraparte, con la tarjeta y el banco."""
    body: dict[str, Any] = {
        "direction": "expense",
        "voucher_type": "card_statement",
        "issued_on": "2026-05-20",
        "counterparty_doc_type": None,
        "counterparty_name": "Gastos médicos",
        "account_number": "4111-XXXX-1234",
        "bank_name": "Banco Uno",
        "taxed_10": "800000",
    }
    body.update(overrides)
    return body


def post_voucher(client: TestClient, token: str, body: dict[str, Any]) -> Any:
    return client.post(f"{TAX}/vouchers", json=body, headers=auth_header(token))


def create(client: TestClient, token: str, body: dict[str, Any]) -> dict[str, Any]:
    return dict(ok(post_voucher(client, token, body), 201))


def error_code(res: Any) -> str:
    return str(res.json()["error"]["code"])
