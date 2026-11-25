"""Permisos y privacidad de la tributación (spec fase 4 §5.10; D-094, BR-TAX-12)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_header
from tests.finance_utils import audit_entries, create_account, create_tx, ok, personal_context
from tests.tax_utils import TAX, create_voucher, obligation, setup_tax

ANY = str(uuid.uuid4())
WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("post", "/rules/load-candidates", None),
    ("post", f"/rules/{ANY}/verify", {}),
    ("post", "/rules/verify-verifiable", None),
    ("post", f"/rules/{ANY}/deprecate", {"reason": "Prueba"}),
    ("post", "/holidays/load-candidates", None),
    ("post", "/holidays", {"day": "2027-01-02", "name": "X", "legal_reference": "X"}),
    ("patch", f"/holidays/{ANY}", {"name": "X"}),
    ("delete", f"/holidays/{ANY}", None),
    (
        "post",
        "/due-date-exceptions",
        {
            "obligation_code": "IVA-GENERAL-LIQUIDACION",
            "due_month": "2027-01-01",
            "new_due_date": "2027-01-30",
            "legal_reference": "X",
        },
    ),
    ("patch", f"/due-date-exceptions/{ANY}", {"is_active": False}),
    (
        "put",
        "/profile",
        {
            "valid_from": "2026-01-01",
            "ire_regime": "ire_general",
            "vat_taxpayer": True,
            "obligations": [],
        },
    ),
    (
        "post",
        f"/profile/{ANY}/verify",
        {"verified_by_name": "X", "verified_license": "Mat. 1", "verified_document_reference": "X"},
    ),
    ("post", "/obligations/sync", None),
    ("post", f"/obligations/{ANY}/file", {"filed_on": "2026-02-07", "filing_reference": "X"}),
    ("post", f"/obligations/{ANY}/pay", {"paid_on": "2026-02-07", "paid_amount": "1"}),
    ("post", f"/obligations/{ANY}/not-applicable", {"reason": "Prueba"}),
    ("post", f"/obligations/{ANY}/reopen", {"reason": "Prueba"}),
    ("post", "/vouchers", {}),
    ("patch", f"/vouchers/{ANY}", {"notes": "X"}),
    ("post", f"/vouchers/{ANY}/void", {"reason": "Prueba"}),
    ("post", f"/vouchers/{ANY}/propose-entry", {"account_id": ANY}),
    ("post", "/vat/2026/10/apply", None),
    ("put", "/settings", {"alert_days": 5}),
]
READS = [
    "/rules",
    "/holidays",
    "/due-date-exceptions",
    "/profile",
    "/obligations",
    "/vouchers",
    "/vouchers/export?year=2026",
    "/vat/2026/10",
    "/alerts",
    "/settings",
]


def _call(
    client: TestClient, token: str, method: str, path: str, body: dict[str, Any] | None
) -> Any:
    kwargs: dict[str, Any] = {"headers": auth_header(token)}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(f"{TAX}{path}", **kwargs)


def test_viewer_only_reads(
    client: TestClient, owner_token: str, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    _, viewer = make_user("viewer")
    for path in READS:
        assert client.get(f"{TAX}{path}", headers=auth_header(viewer)).status_code == 200, path
    for method, path, body in WRITES:
        res = _call(client, viewer, method, path, body)
        assert res.status_code == 403, (method, path, res.text)


def test_admin_manages_but_does_not_verify(
    client: TestClient, owner_token: str, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    _, admin = make_user("admin")
    verify = [w for w in WRITES if w[1].endswith("/verify") or w[1].endswith("/deprecate")]
    for method, path, body in verify:
        assert _call(client, admin, method, path, body).status_code == 403, path
    # Gestiona: carga comprobantes y presenta obligaciones.
    assert create_voucher(client, admin)["id"]
    row = obligation(client, admin, "IVA-GENERAL-LIQUIDACION", "2026-01-01")
    res = client.post(
        f"{TAX}/obligations/{row['id']}/file",
        json={"filed_on": "2026-02-07", "filing_reference": "N° 1"},
        headers=auth_header(admin),
    )
    assert res.status_code == 200
    # Sin `tax.verify` no cambia el estado de un feriado.
    holiday = ok(
        client.post(
            f"{TAX}/holidays",
            json={"day": "2027-01-04", "name": "Feriado", "legal_reference": "Decreto"},
            headers=auth_header(admin),
        ),
        201,
    )
    res = client.patch(
        f"{TAX}/holidays/{holiday['id']}",
        json={"validation_status": "verified"},
        headers=auth_header(admin),
    )
    assert res.status_code == 403


def test_personal_context_never_shows_up(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    personal = personal_context(client, owner_token)
    account = create_account(client, owner_token, personal, "Personal")
    tx = create_tx(client, owner_token, personal, account["id"], "-5000", booked_on="2026-08-10")
    # Ni el aviso de meses sin comprobantes cuenta lo personal.
    alerts = ok(client.get(f"{TAX}/alerts", headers=auth_header(owner_token)))
    assert "MONTHS_WITHOUT_VOUCHERS" not in {a["code"] for a in alerts["alerts"]}
    # Vincular lo personal: 404, sin decir que existe.
    res = client.post(
        f"{TAX}/vouchers",
        json={
            "direction": "purchase",
            "voucher_type": "invoice",
            "timbrado": "12345678",
            "number": "001-001-0000001",
            "issued_on": "2026-08-10",
            "counterparty_doc_type": "ruc",
            "counterparty_ruc": "44444401",
            "counterparty_ruc_dv": "7",
            "counterparty_name": "X",
            "condition": "cash",
            "taxed_10": "5000",
            "transaction_id": tx["id"],
        },
        headers=auth_header(owner_token),
    )
    assert res.status_code == 404
    assert personal not in res.text and tx["id"] not in res.text


def test_every_change_is_audited(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    voucher = create_voucher(client, owner_token)
    ok(
        client.patch(
            f"{TAX}/vouchers/{voucher['id']}",
            json={"notes": "Nota"},
            headers=auth_header(owner_token),
        )
    )
    ok(client.put(f"{TAX}/settings", json={"alert_days": 7}, headers=auth_header(owner_token)))
    actions = {
        e["action"]
        for entity in ("rules", "rule_version", "profile", "obligation", "voucher", "settings")
        for e in audit_entries(client, owner_token, f"tax.{entity}")
    }
    assert {
        "tax.rules.loaded",
        "tax.rule_version.created",
        "tax.profile.created",
        "tax.obligation.created",
        "tax.voucher.created",
        "tax.voucher.updated",
        "tax.settings.updated",
    } <= actions, actions
