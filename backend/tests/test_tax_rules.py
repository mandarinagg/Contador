"""Reglas tributarias como datos (spec fase 4 §5.1; D-082, D-084, D-085, BR-TAX-02/12)."""

import os
from datetime import date
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.verification import source_reference
from app.modules.tax import candidate_rules, rules
from tests.accounting_utils import error_code
from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import audit_entries, ok
from tests.tax_utils import TAX, load_rules, org_id, rejected, rules_by_code, setup_tax, user_id

YAML_PATH = os.path.join(BACKEND_DIR, "..", "docs", "research", "tax_rules_candidatas.yaml")
CANDIDATES = 39


def test_packaged_rules_are_identical_to_research_yaml() -> None:
    with open(YAML_PATH, encoding="utf-8") as handle:
        research = yaml.safe_load(handle)
    assert research["meta"] == candidate_rules.META
    assert list(research["rules"]) == list(candidate_rules.RULES)
    assert len(candidate_rules.RULES) == CANDIDATES
    assert all(r["validation_status"] == "pending" for r in candidate_rules.RULES)


def test_load_candidates_is_idempotent(client: TestClient, owner_token: str) -> None:
    first = load_rules(client, owner_token)
    assert first["created"] == CANDIDATES
    assert first["rejected"] == []
    assert first["exceptions_created"] > 0  # la RG 60/2026 (CAL-EXCEPCION-2026-11)
    second = load_rules(client, owner_token)
    assert second["created"] == 0
    assert second["unchanged"] == CANDIDATES
    assert second["exceptions_created"] == 0
    assert second["total"] == CANDIDATES
    listed = rules_by_code(client, owner_token)
    assert len(listed) == CANDIDATES
    assert all(r["validation_status"] == "pending" for r in listed.values())
    # Los códigos que usa la fase 4 (D-085) se marcan; el resto solo se muestra.
    assert listed["IVA-GENERAL-TASAS"]["used_by_calculations"] is True
    assert listed["CAL-EXCEPCION-2026-11"]["used_by_calculations"] is True
    assert listed["IVA-PRORRATEO"]["used_by_calculations"] is False
    assert any(
        e["action"] == "tax.rules.loaded" for e in audit_entries(client, owner_token, "tax.rules")
    )


def test_invalid_parameters_are_not_loaded(
    client: TestClient, owner_token: str, db: Session
) -> None:
    ok(client.get(f"{TAX}/rules", headers=auth_header(owner_token)))
    bad: list[dict[str, Any]] = [
        {
            "code": "IVA-GENERAL-TASAS",
            "description": "Tasas mal cargadas",
            "parameters": {"general_rate": 1.5, "reduced_rate": 0.05},
            "valid_from": "2020-01-01",
            "validation_status": "pending",
        },
        {
            "code": "CAL-PERPETUO-DJ",
            "description": "Faltan terminaciones",
            "parameters": {"key": "ultimo_digito_ruc_sin_dv", "day_by_digit": {"0": 7}},
            "valid_from": "2020-01-01",
            "validation_status": "pending",
        },
        {
            "code": "IVA-GENERAL-LIQUIDACION",
            "description": "Una clave de más",
            "parameters": {"obligation_code": 211, "extra": True},
            "valid_from": "2020-01-01",
            "validation_status": "pending",
        },
        {
            "code": "IVA-GENERAL-TASAS",
            "description": "Verificada en el YAML",
            "parameters": {"general_rate": 0.1, "reduced_rate": 0.05},
            "valid_from": "2020-01-01",
            "validation_status": "verified",
        },
    ]
    result = rules.load_candidates(db, org_id(db), user_id(db), bad)
    assert result.created == []
    assert [r["code"] for r in result.rejected] == [
        "IVA-GENERAL-TASAS",
        "CAL-PERPETUO-DJ",
        "IVA-GENERAL-LIQUIDACION",
        "IVA-GENERAL-TASAS",
    ]
    assert rules.list_rules(db, code=None, status=None, at=None) == []


def _rule_id(db: Session, code: str) -> Any:
    rule = rules.list_rules(db, code=code, status=None, at=None)[0]
    return rule.id


def test_trigger_blocks_edits_transitions_and_deletes(
    client: TestClient, owner_token: str, db: Session
) -> None:
    load_rules(client, owner_token)
    rid = _rule_id(db, "IVA-GENERAL-TASAS")
    rejected(
        db,
        "UPDATE tax.rule_versions SET description = 'otra' WHERE id = :id",
        {"id": rid},
        "trg_rule_versions_immutable",
    )
    rejected(
        db,
        "UPDATE tax.rule_versions SET parameters = '{}'::jsonb WHERE id = :id",
        {"id": rid},
        "trg_rule_versions_immutable",
    )
    rejected(
        db,
        "UPDATE tax.rule_versions SET reviewed_by_name = 'X' WHERE id = :id",
        {"id": rid},
        "trg_rule_versions_invalid_transition",
    )
    rejected(
        db,
        "DELETE FROM tax.rule_versions WHERE id = :id",
        {"id": rid},
        "trg_rule_versions_no_delete",
    )
    rejected(
        db,
        "INSERT INTO tax.rule_versions (code, version, description, parameters, validation_status)"
        " VALUES ('X-1', 1, 'x', '{}'::jsonb, 'verified')",
        {},
        "trg_rule_versions_born_pending",
    )
    # pending → verified (por la API), y verified → pending no.
    res = client.post(
        f"{TAX}/rules/{rid}/verify",
        json={},
        headers=auth_header(owner_token),
    )
    assert ok(res)["validation_status"] == "verified"
    rejected(
        db,
        "UPDATE tax.rule_versions SET validation_status = 'pending' WHERE id = :id",
        {"id": rid},
        "trg_rule_versions_invalid_transition",
    )
    # deprecated es final.
    res = client.post(
        f"{TAX}/rules/{rid}/deprecate",
        json={"reason": "Cambió la ley"},
        headers=auth_header(owner_token),
    )
    assert ok(res)["validation_status"] == "deprecated"
    rejected(
        db,
        "UPDATE tax.rule_versions SET validation_status = 'verified' WHERE id = :id",
        {"id": rid},
        "trg_rule_versions_invalid_transition",
    )
    res = client.post(
        f"{TAX}/rules/{rid}/deprecate",
        json={"reason": "Otra vez"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 409


def test_validity_ranges_do_not_overlap(client: TestClient, owner_token: str, db: Session) -> None:
    load_rules(client, owner_token)
    rejected(
        db,
        "INSERT INTO tax.rule_versions (code, version, description, parameters, valid_from)"
        " VALUES ('IVA-GENERAL-TASAS', 2, 'x', '{}'::jsonb, '2026-01-01')",
        {},
        "ex_rule_versions_no_overlap",
    )
    # Cerrar la vigencia no se puede (la versión no se edita): la nueva versión va con una
    # vigencia que no se pisa, o la anterior se depreca.
    rid = _rule_id(db, "IVA-GENERAL-TASAS")
    client.post(
        f"{TAX}/rules/{rid}/deprecate",
        json={"reason": "Reemplazada"},
        headers=auth_header(owner_token),
    )
    db.execute(
        __import__("sqlalchemy").text(
            "INSERT INTO tax.rule_versions (code, version, description, parameters, valid_from)"
            " VALUES ('IVA-GENERAL-TASAS', 2, 'nueva', "
            "'{\"general_rate\": 0.1, \"reduced_rate\": 0.05}'::jsonb, '2026-01-01')"
        )
    )
    assert rules.rule_for(db, "IVA-GENERAL-TASAS", date(2026, 6, 1)).version == 2  # type: ignore[union-attr]
    assert rules.rule_for(db, "IVA-GENERAL-TASAS", date(2025, 6, 1)) is None  # la v1 está deprecada


def test_rule_in_force_at_a_date(client: TestClient, owner_token: str) -> None:
    load_rules(client, owner_token)
    at = ok(
        client.get(f"{TAX}/rules", params={"at": "2026-11-15"}, headers=auth_header(owner_token))
    )
    codes = {r["code"] for r in at}
    assert "CAL-EXCEPCION-2026-11" in codes
    assert "REG-COMPROB-MENSUAL" in codes
    # Sin `valid_from` nunca rige (D-082: «sin regla»).
    assert "PATENTE-MUNICIPAL" not in codes
    before = ok(
        client.get(f"{TAX}/rules", params={"at": "2021-12-31"}, headers=auth_header(owner_token))
    )
    assert "REG-COMPROB-MENSUAL" not in {r["code"] for r in before}
    assert "CAL-EXCEPCION-2026-11" not in {r["code"] for r in before}


def test_tool_verifies_against_the_official_source_with_permission(
    client: TestClient, owner_token: str, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-120: verifica CONTADOR AI, sin nombre ni matrícula, y con `tax.verify`."""
    setup_tax(client, owner_token, monkeypatch, profile=False)
    rule = rules_by_code(client, owner_token)["IVA-GENERAL-TASAS"]
    rid = rule["id"]
    assert rule["verifiable"] is True and rule["unverifiable_reason"] is None
    # Ya no se aceptan nombre ni matrícula.
    res = client.post(
        f"{TAX}/rules/{rid}/verify",
        json={"reviewed_by_name": "Alguien", "reviewed_reference": "Mat. 1"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 422 and error_code(res) == "VALIDATION_ERROR"
    _, admin = make_user("admin")
    res = client.post(f"{TAX}/rules/{rid}/verify", json={}, headers=auth_header(admin))
    assert res.status_code == 403
    _, accountant = make_user("accountant")
    res = client.post(
        f"{TAX}/rules/{rid}/verify", json={"review_note": "OK"}, headers=auth_header(accountant)
    )
    body = ok(res)
    assert body["reviewed_by_name"] == "CONTADOR AI"
    assert body["reviewed_reference"] == source_reference(rule["legal_reference"])
    assert body["review_note"] == "OK"
    assert body["verifiable"] is False  # ya no está pendiente
    entries = audit_entries(client, owner_token, "tax.rule_version")
    assert any(e["action"] == "tax.rule_version.verified" for e in entries)


def test_rule_without_official_source_read_is_not_verifiable(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una regla sin la fuente oficial leída sigue `pending` (D-120, prompt maestro §8)."""
    setup_tax(client, owner_token, monkeypatch, profile=False)
    weak = [r for r in rules_by_code(client, owner_token).values() if not r["verifiable"]]
    assert weak and all(r["confidence"] != "oficial_leida" for r in weak)
    res = client.post(
        f"{TAX}/rules/{weak[0]['id']}/verify", json={}, headers=auth_header(owner_token)
    )
    assert res.status_code == 422 and error_code(res) == "RULE_NOT_VERIFIABLE"
    assert res.json()["error"]["details"]["code"] == weak[0]["code"]


def test_bulk_verify_verifies_only_the_verifiable(
    client: TestClient, owner_token: str, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El clic único (D-120): verifica las pendientes con fuente leída e informa las demás."""
    setup_tax(client, owner_token, monkeypatch, profile=False)
    _, admin = make_user("admin")
    url = f"{TAX}/rules/verify-verifiable"
    assert client.post(url, headers=auth_header(admin)).status_code == 403

    def listed() -> dict[str, dict[str, Any]]:
        rows = ok(client.get(f"{TAX}/rules", headers=auth_header(owner_token)))
        return {f"{r['code']} v{r['version']}": r for r in rows}

    before = listed()
    verifiable = {key for key, r in before.items() if r["verifiable"]}
    pending = {key for key, r in before.items() if r["validation_status"] == "pending"}
    assert verifiable and pending - verifiable
    body = ok(client.post(url, headers=auth_header(owner_token)))
    assert set(body["verified"]) == verifiable
    assert {f"{r['code']} v{r['version']}" for r in body["left_pending"]} == pending - verifiable
    assert all(r["reason"] for r in body["left_pending"])
    for key, r in listed().items():
        expected = "verified" if key in verifiable else before[key]["validation_status"]
        assert r["validation_status"] == expected, key
    # Repetir no cambia nada.
    again = ok(client.post(url, headers=auth_header(owner_token)))
    assert again["verified"] == [] and len(again["left_pending"]) == len(body["left_pending"])


@pytest.mark.parametrize(
    "table", ["rule_versions", "obligations", "profiles", "vouchers", "due_date_exceptions"]
)
def test_tax_tables_cannot_be_truncated(db: Session, table: str) -> None:
    # CASCADE para pasar las FK: el trigger de la tabla nombrada salta primero.
    rejected(db, f"TRUNCATE tax.{table} CASCADE", {}, f"trg_{table}_no_delete")
