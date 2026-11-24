import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.organizations.ruc import ruc_check_digit
from tests.conftest import auth_header


def test_ruc_check_digit_official_vector() -> None:
    # Ejemplo del Manual Técnico SIFEN v150 (mismo vector que el proyecto de facturación).
    assert ruc_check_digit("44444401") == 7
    with pytest.raises(ValueError):
        ruc_check_digit("12a4")


def test_organization_update_is_audited(client: TestClient, owner_token: str) -> None:
    res = client.patch(
        "/api/v1/organization",
        json={"trade_name": "Marca Comercial", "ruc": "44444401", "ruc_check_digit": "7"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["ruc"] == "44444401"

    logs = client.get("/api/v1/audit/logs", headers=auth_header(owner_token)).json()
    update = next(entry for entry in logs if entry["action"] == "organization.updated")
    assert update["before"] == {"trade_name": None, "ruc": None, "ruc_check_digit": None}
    assert update["after"]["ruc"] == "44444401"
    assert update["request_id"]


def test_organization_update_audits_only_changed_fields(
    client: TestClient, owner_token: str
) -> None:
    res = client.patch(
        "/api/v1/organization",
        json={"legal_name": "Empresa de Prueba EAS", "legal_form": "SA"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 200
    logs = client.get("/api/v1/audit/logs", headers=auth_header(owner_token)).json()
    update = next(entry for entry in logs if entry["action"] == "organization.updated")
    assert update["before"] == {"legal_form": "EAS"}
    assert update["after"] == {"legal_form": "SA"}

    # Sin cambios reales no se agrega nada a la auditoría.
    client.patch(
        "/api/v1/organization", json={"legal_form": "SA"}, headers=auth_header(owner_token)
    )
    again = client.get("/api/v1/audit/logs", headers=auth_header(owner_token)).json()
    assert len(again) == len(logs)


def test_organization_rejects_wrong_check_digit(client: TestClient, owner_token: str) -> None:
    res = client.patch(
        "/api/v1/organization",
        json={"ruc": "44444401", "ruc_check_digit": "3"},
        headers=auth_header(owner_token),
    )
    assert res.status_code == 422
    res = client.patch(
        "/api/v1/organization", json={"ruc": "44444401"}, headers=auth_header(owner_token)
    )
    assert res.status_code == 422


def test_audit_log_is_append_only(client: TestClient, owner_token: str, db: Session) -> None:
    for statement in (
        "UPDATE audit.audit_logs SET action = 'alterado'",
        "DELETE FROM audit.audit_logs",
        "TRUNCATE audit.audit_logs",
        "DELETE FROM audit.security_events",
    ):
        nested = db.begin_nested()
        with pytest.raises(DBAPIError, match="solo inserción"):
            db.execute(text(statement))
        nested.rollback()


def test_hash_chain_detects_tampering(client: TestClient, owner_token: str, db: Session) -> None:
    client.patch(
        "/api/v1/organization", json={"trade_name": "Uno"}, headers=auth_header(owner_token)
    )
    client.patch(
        "/api/v1/organization", json={"trade_name": "Dos"}, headers=auth_header(owner_token)
    )

    ok = client.get("/api/v1/audit/verify", headers=auth_header(owner_token)).json()
    assert ok["valid"] is True
    assert ok["checked"] >= 3

    # Simula a alguien con acceso de dueño a la base que desactiva la protección.
    db.execute(text("ALTER TABLE audit.audit_logs DISABLE TRIGGER audit_logs_immutable"))
    db.execute(
        text(
            'UPDATE audit.audit_logs SET after = \'{"trade_name": "Falso"}\' '
            "WHERE seq = (SELECT max(seq) FROM audit.audit_logs)"
        )
    )
    db.execute(text("ALTER TABLE audit.audit_logs ENABLE TRIGGER audit_logs_immutable"))
    db.commit()

    broken = client.get("/api/v1/audit/verify", headers=auth_header(owner_token)).json()
    assert broken["valid"] is False
    assert broken["first_broken_seq"] is not None


def test_security_events_listed(client: TestClient, owner_token: str) -> None:
    client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "mala"})
    events = client.get("/api/v1/audit/security-events", headers=auth_header(owner_token)).json()
    types = [e["event_type"] for e in events]
    assert "setup_completed" in types
    assert "login_failed" in types
