"""Avisos (spec fase 4 §5.9; D-092, D-098, BR-TAX-04/05)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_header
from tests.finance_utils import business_context, create_account, create_tx, ok
from tests.tax_utils import (
    TAX,
    create_voucher,
    file_obligation,
    fix_today,
    load_rules,
    obligation,
    put_profile,
    set_ruc,
    setup_tax,
)


def _alerts(client: TestClient, token: str, as_of: str | None = None) -> dict[str, Any]:
    params = {"as_of": as_of} if as_of else {}
    body = ok(client.get(f"{TAX}/alerts", params=params, headers=auth_header(token)))
    return {a["code"]: a for a in body["alerts"]} | {"_meta": body}


def test_missing_profile_and_unverified_rules(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fix_today(monkeypatch)
    set_ruc(client, owner_token, "80000005")
    load_rules(client, owner_token)
    alerts = _alerts(client, owner_token)
    assert "PROFILE_MISSING" in alerts
    assert "OBLIGATIONS_OVERDUE" not in alerts


def test_overdue_due_soon_and_remind_by(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch, ruc="80000005")  # DJ 17, DJI 18
    alerts = _alerts(client, owner_token)
    assert alerts["_meta"]["as_of"] == "2026-11-24" and alerts["_meta"]["alert_days"] == 10
    overdue = alerts["OBLIGATIONS_OVERDUE"]
    assert overdue["severity"] == "danger"
    assert all(i["due_date"] < "2026-11-24" for i in overdue["items"])
    assert "PROFILE_UNVERIFIED" in alerts
    rules_alert = alerts["RULES_UNVERIFIED"]
    assert {"IVA-GENERAL-TASAS", "CAL-PERPETUO-DJ"} <= {r["code"] for r in rules_alert["items"]}
    assert "REGISTER_UNCONFIRMED" in alerts
    # IVA de diciembre: vence el domingo 17/01/2027, que pasa al lunes 18. El aviso usa el 17
    # (D-098): con 10 días, desde el 07/01 ya avisa aunque el vencimiento corrido quede fuera.
    january = _alerts(client, owner_token, "2027-01-07")
    soon = {(i["code"], i["period_start"]): i for i in january["OBLIGATIONS_DUE_SOON"]["items"]}
    item = soon[("IVA-GENERAL-LIQUIDACION", "2026-12-01")]
    assert (item["remind_by"], item["due_date"]) == ("2027-01-17", "2027-01-18")
    assert (
        "18/01/2027" in item["shift_explanation"] and "sin verificar" in item["shift_explanation"]
    )
    # El registro de noviembre vence el lunes 18 (sin correr): todavía no.
    assert ("REG-COMPROB-MENSUAL", "2026-11-01") not in soon
    assert ("REG-COMPROB-MENSUAL", "2026-11-01") in {
        (i["code"], i["period_start"])
        for i in _alerts(client, owner_token, "2027-01-08")["OBLIGATIONS_DUE_SOON"]["items"]
    }
    # La cantidad de días se configura.
    ok(client.put(f"{TAX}/settings", json={"alert_days": 2}, headers=auth_header(owner_token)))
    assert "OBLIGATIONS_DUE_SOON" not in _alerts(client, owner_token, "2027-01-07")
    # Presentar quita la vencida.
    sep = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-09-01")
    file_obligation(client, owner_token, sep["id"])
    ids = {i["id"] for i in _alerts(client, owner_token)["OBLIGATIONS_OVERDUE"]["items"]}
    assert sep["id"] not in ids


def test_months_with_movements_and_no_vouchers_and_legacy_ruc(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    biz = business_context(client, owner_token)
    account = create_account(client, owner_token, biz)
    create_tx(client, owner_token, biz, account["id"], "-5000", booked_on="2026-08-10")
    create_tx(client, owner_token, biz, account["id"], "-5000", booked_on="2026-10-10")
    create_voucher(
        client,
        owner_token,
        issued_on="2026-10-15",
        counterparty_ruc="1234567A",
        counterparty_ruc_dv=None,
    )
    alerts = _alerts(client, owner_token)
    assert alerts["MONTHS_WITHOUT_VOUCHERS"]["items"] == [{"month": "2026-08-01"}]
    legacy = alerts["COUNTERPARTY_RUC_UNCHECKED"]["items"]
    assert [i["ruc"] for i in legacy] == ["1234567A"]


def test_each_alert_goes_away_when_resolved(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = owner_token
    headers = auth_header(t)
    fix_today(monkeypatch)
    set_ruc(client, t, "80000005")
    load_rules(client, t)
    assert "PROFILE_MISSING" in _alerts(client, t)
    # Perfil desde octubre, para que haya poco que presentar.
    put_profile(
        client,
        t,
        valid_from="2026-10-01",
        obligations=(("211", "2026-10-01"), ("955", "2026-10-01")),
    )
    assert "PROFILE_MISSING" not in _alerts(client, t)
    pid = ok(client.get(f"{TAX}/profile", headers=headers))["current"]["id"]
    ok(
        client.post(
            f"{TAX}/profile/{pid}/verify",
            json={
                "verified_by_name": "Contadora",
                "verified_license": "Mat. 1",
                "verified_document_reference": "Constancia",
            },
            headers=headers,
        )
    )
    assert "PROFILE_UNVERIFIED" not in _alerts(client, t)
    # Vencidas y registro sin confirmar: se presentan.
    for item in _alerts(client, t)["OBLIGATIONS_OVERDUE"]["items"]:
        file_obligation(client, t, item["id"])
    alerts = _alerts(client, t)
    assert "OBLIGATIONS_OVERDUE" not in alerts
    for item in alerts.get("REGISTER_UNCONFIRMED", {"items": []})["items"]:
        file_obligation(client, t, item["id"])
    assert "REGISTER_UNCONFIRMED" not in _alerts(client, t)
    # Las que vencen pronto: al presentarlas dejan de avisar.
    for item in _alerts(client, t, "2026-12-10")["OBLIGATIONS_DUE_SOON"]["items"]:
        file_obligation(client, t, item["id"])
    assert "OBLIGATIONS_DUE_SOON" not in _alerts(client, t, "2026-12-10")
    # Reglas en uso verificadas.
    for rule in _alerts(client, t)["RULES_UNVERIFIED"]["items"]:
        ok(
            client.post(
                f"{TAX}/rules/{rule['id']}/verify",
                json={"reviewed_by_name": "Contadora", "reviewed_reference": "Mat. 1"},
                headers=headers,
            )
        )
    assert "RULES_UNVERIFIED" not in _alerts(client, t)
    # Meses sin comprobantes y RUC sin DV.
    biz = business_context(client, t)
    account = create_account(client, t, biz)
    create_tx(client, t, biz, account["id"], "-5000", booked_on="2026-11-05")
    legacy = create_voucher(
        client, t, issued_on="2026-11-05", counterparty_ruc="1234567A", counterparty_ruc_dv=None
    )
    alerts = _alerts(client, t)
    assert "MONTHS_WITHOUT_VOUCHERS" not in alerts
    assert "COUNTERPARTY_RUC_UNCHECKED" in alerts
    ok(
        client.post(
            f"{TAX}/vouchers/{legacy['id']}/void", json={"reason": "RUC mal"}, headers=headers
        )
    )
    alerts = _alerts(client, t)
    assert "COUNTERPARTY_RUC_UNCHECKED" not in alerts
    assert alerts["MONTHS_WITHOUT_VOUCHERS"]["items"] == [{"month": "2026-11-01"}]
    create_voucher(client, t, issued_on="2026-11-06")
    assert "MONTHS_WITHOUT_VOUCHERS" not in _alerts(client, t)
