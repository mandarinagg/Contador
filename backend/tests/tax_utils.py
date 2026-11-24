"""Ayudas para las pruebas de tributación (no es un módulo de pruebas)."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.organizations.ruc import ruc_check_digit
from app.modules.tax import router as tax_router
from tests.conftest import auth_header
from tests.finance_utils import ok

TAX = "/api/v1/tax"
TODAY = date(2026, 11, 24)

# Casos reales de la investigación (Manual Técnico SIFEN v150, §10.1; TRIBUTACION_FASE4 §4).
SIFEN_RUC, SIFEN_DV = "44444401", "7"
SIFEN_CDC = "01444444017001001001452822017012515873260988"


def dv(ruc: str) -> str:
    return str(ruc_check_digit(ruc))


def fix_today(monkeypatch: pytest.MonkeyPatch, day: date = TODAY) -> None:
    monkeypatch.setattr(tax_router, "today", lambda: day)


def set_ruc(client: TestClient, token: str, ruc: str) -> None:
    res = client.patch(
        "/api/v1/organization",
        json={"ruc": ruc, "ruc_check_digit": dv(ruc)},
        headers=auth_header(token),
    )
    ok(res)


def load_rules(client: TestClient, token: str) -> dict[str, Any]:
    return dict(ok(client.post(f"{TAX}/rules/load-candidates", headers=auth_header(token))))


def rules_by_code(client: TestClient, token: str) -> dict[str, dict[str, Any]]:
    rows = ok(client.get(f"{TAX}/rules", headers=auth_header(token)))
    return {r["code"]: r for r in rows}


def put_profile(
    client: TestClient,
    token: str,
    *,
    valid_from: str = "2026-01-01",
    obligations: tuple[tuple[str, str], ...] = (("211", "2026-01-01"), ("955", "2026-01-01")),
    ire_regime: str = "ire_general",
    vat_taxpayer: bool = True,
    fiscal_close_month: int = 12,
    expect: int = 200,
) -> Any:
    body = {
        "valid_from": valid_from,
        "ire_regime": ire_regime,
        "fiscal_close_month": fiscal_close_month,
        "vat_taxpayer": vat_taxpayer,
        "obligations": [{"code": c, "registered_on": d} for c, d in obligations],
    }
    res = client.put(f"{TAX}/profile", json=body, headers=auth_header(token))
    assert res.status_code == expect, res.text
    return res.json()


def setup_tax(
    client: TestClient,
    token: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    ruc: str = "80000005",
    profile: bool = True,
    **profile_fields: Any,
) -> None:
    """RUC, reglas candidatas y (si se pide) perfil con 211 y 955; hoy = 24/11/2026."""
    fix_today(monkeypatch)
    set_ruc(client, token, ruc)
    load_rules(client, token)
    if profile:
        put_profile(client, token, **profile_fields)


def voucher_body(**overrides: Any) -> dict[str, Any]:
    """Factura de compra preimpresa de 110.000 al 10 % (IVA 10.000)."""
    body: dict[str, Any] = {
        "direction": "purchase",
        "voucher_type": "invoice",
        "timbrado": "12345678",
        "number": "001-001-0000001",
        "issued_on": "2026-10-15",
        "counterparty_doc_type": "ruc",
        "counterparty_ruc": SIFEN_RUC,
        "counterparty_ruc_dv": SIFEN_DV,
        "counterparty_name": "Proveedor de Prueba S.A.",
        "condition": "cash",
        "taxed_10": "110000",
    }
    body.update(overrides)
    return body


def create_voucher(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    res = client.post(f"{TAX}/vouchers", json=voucher_body(**overrides), headers=auth_header(token))
    return dict(ok(res, 201))


def obligation(client: TestClient, token: str, code: str, period_start: str) -> dict[str, Any]:
    rows = ok(client.get(f"{TAX}/obligations", params={"code": code}, headers=auth_header(token)))
    return dict(next(r for r in rows if r["period_start"] == period_start))


def file_obligation(
    client: TestClient, token: str, obligation_id: str, **fields: Any
) -> dict[str, Any]:
    body = {"filed_on": "2026-11-10", "filing_reference": "TALON-123"}
    body.update(fields)
    res = client.post(
        f"{TAX}/obligations/{obligation_id}/file", json=body, headers=auth_header(token)
    )
    return dict(ok(res))


def confirm_register(client: TestClient, token: str, month_start: str) -> dict[str, Any]:
    row = obligation(client, token, "REG-COMPROB-MENSUAL", month_start)
    return file_obligation(client, token, row["id"])


def rejected(db: Session, sql: str, params: dict[str, Any], name: str) -> None:
    """La sentencia falla en la base con la restricción o el trigger `name`."""
    nested = db.begin_nested()
    with pytest.raises(DBAPIError) as caught:
        db.execute(text(sql), params)
    nested.rollback()
    diag = getattr(caught.value.orig, "diag", None)
    assert getattr(diag, "constraint_name", None) == name, str(caught.value)


def org_id(db: Session) -> Any:
    return db.scalar(text("SELECT id FROM core.organizations LIMIT 1"))


def user_id(db: Session) -> Any:
    return db.scalar(text("SELECT id FROM core.users ORDER BY created_at LIMIT 1"))
