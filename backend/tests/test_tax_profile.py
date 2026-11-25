"""Perfil fiscal versionado (spec fase 4 §5.4; D-083, D-094, BR-TAX-04/12)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_header
from tests.finance_utils import audit_entries, ok
from tests.tax_utils import TAX, fix_today, load_rules, put_profile, rejected, set_ruc, setup_tax

VERIFY = {"verified_document_reference": "Constancia de RUC 2026-11-01"}


def test_no_profile_without_organization_ruc(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    fix_today(monkeypatch)
    load_rules(client, owner_token)
    body = put_profile(client, owner_token, expect=422)
    assert body["error"]["code"] == "PROFILE_REQUIRES_RUC"
    # La base también lo exige.
    rejected(
        db,
        "INSERT INTO tax.profiles (organization_id, valid_from, ire_regime, vat_taxpayer, origin,"
        " created_by) SELECT o.id, '2026-01-01', 'unknown', true, 'declared', u.id"
        " FROM core.organizations o, core.users u LIMIT 1",
        {},
        "trg_profiles_ruc_required",
    )


def test_versions_by_valid_from_and_correction(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch, profile=False)
    put_profile(client, owner_token, valid_from="2026-01-01", obligations=(("211", "2026-01-01"),))
    body = put_profile(
        client,
        owner_token,
        valid_from="2026-07-01",
        obligations=(("211", "2026-01-01"), ("955", "2026-07-01")),
    )
    assert [v["valid_from"] for v in body["history"]] == ["2026-07-01", "2026-01-01"]
    assert body["current"]["valid_from"] == "2026-07-01"
    assert body["ruc"] == "80000005"
    # Misma fecha que una declarada: la corrige (auditado antes y después).
    body = put_profile(
        client,
        owner_token,
        valid_from="2026-07-01",
        obligations=(("211", "2026-01-01"), ("955", "2026-08-01")),
    )
    assert len(body["history"]) == 2
    assert body["current"]["obligations"][1] == {
        "code": "955",
        "registered_on": "2026-08-01",
        "supported": True,
    }
    replaced = [
        e
        for e in audit_entries(client, owner_token, "tax.profile")
        if e["action"].endswith("replaced")
    ]
    assert replaced and replaced[0]["before"]["obligations"][1]["registered_on"] == "2026-07-01"


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"vat_taxpayer": False}, "211"),
        ({"ire_regime": "ire_simple", "obligations": (("700", "2026-01-01"),)}, "700"),
        ({"ire_regime": "ire_general", "obligations": (("701", "2026-01-01"),)}, "701"),
        ({"obligations": (("700", "2026-01-01"), ("701", "2026-01-01"))}, "700"),
    ],
)
def test_inconsistent_profiles_are_rejected(
    client: TestClient,
    owner_token: str,
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
    problem: str,
) -> None:
    setup_tax(client, owner_token, monkeypatch, profile=False)
    body = put_profile(client, owner_token, expect=422, **fields)
    assert body["error"]["code"] == "PROFILE_INCONSISTENT"
    assert problem in body["error"]["message"]


def test_verification_requires_license_and_is_final(
    client: TestClient,
    owner_token: str,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Any,
    db: Session,
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    pid = ok(client.get(f"{TAX}/profile", headers=auth_header(owner_token)))["current"]["id"]
    missing = {"verified_by_name": "Contadora", "verified_license": "Mat. 1"}  # ya no (D-120)
    res = client.post(f"{TAX}/profile/{pid}/verify", json=missing, headers=auth_header(owner_token))
    assert res.status_code == 422
    _, admin = make_user("admin")
    res = client.post(f"{TAX}/profile/{pid}/verify", json=VERIFY, headers=auth_header(admin))
    assert res.status_code == 403
    body = ok(
        client.post(f"{TAX}/profile/{pid}/verify", json=VERIFY, headers=auth_header(owner_token))
    )
    assert body["current"]["origin"] == "verified"
    assert body["current"]["verified_by_name"] == "CONTADOR AI"
    assert body["current"]["verified_license"] == "Constancia de RUC (DNIT)"
    assert body["current"]["verified_document_reference"] == "Constancia de RUC 2026-11-01"
    # Verificada: la misma fecha no se corrige, ni por la API ni por SQL.
    res = put_profile(client, owner_token, expect=409)
    assert res["error"]["code"] == "PROFILE_VERIFIED"
    rejected(
        db,
        "UPDATE tax.profiles SET vat_taxpayer = false WHERE id = :id",
        {"id": pid},
        "trg_profiles_verified_final",
    )
    rejected(
        db,
        "DELETE FROM tax.profile_obligations WHERE profile_id = :id",
        {"id": pid},
        "trg_profile_obligations_verified_final",
    )
    rejected(db, "DELETE FROM tax.profiles WHERE id = :id", {"id": pid}, "trg_profiles_no_delete")
    # Una versión nace declarada: por SQL tampoco nace verificada.
    rejected(
        db,
        "INSERT INTO tax.profiles (organization_id, valid_from, ire_regime, vat_taxpayer, origin,"
        " verified_by_name, verified_license, verified_document_reference, verified_at,"
        " verified_by, created_by) SELECT organization_id, '2026-12-01', ire_regime, true,"
        " 'verified', 'X', 'Mat. 1', 'X', now(), created_by, created_by"
        " FROM tax.profiles WHERE id = :id",
        {"id": pid},
        "trg_profiles_born_declared",
    )
    # Una versión nueva con otra fecha sí.
    put_profile(client, owner_token, valid_from="2026-11-01")
    set_ruc(client, owner_token, "80000005")
