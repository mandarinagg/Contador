"""Feriados y excepciones de calendario (spec fase 4 §5.2; D-086, D-098, BR-TAX-05)."""

import os
from datetime import date
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tax import candidate_holidays
from app.modules.tax.holidays import candidate_days
from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import audit_entries, ok
from tests.tax_utils import TAX, file_obligation, load_rules, obligation, rejected, setup_tax

YAML_PATH = os.path.join(BACKEND_DIR, "..", "docs", "research", "feriados_py.yaml")


def test_packaged_holidays_are_identical_to_research_yaml() -> None:
    with open(YAML_PATH, encoding="utf-8") as handle:
        assert yaml.safe_load(handle) == candidate_holidays.DATA


def test_candidate_days_follow_law_7544_and_known_decrees() -> None:
    days = {h.day: h for h in candidate_days()}
    # Nada antes de la publicación de la ley (03/09/2025).
    assert min(days) >= date(2025, 9, 3)
    # 2026: el 1° de marzo se trasladó al lunes 2 (la fecha original no se carga).
    assert date(2026, 3, 2) in days and date(2026, 3, 1) not in days
    assert "Trasladado desde el 01/03/2026" in days[date(2026, 3, 2)].notes
    assert date(2026, 6, 22) in days and date(2026, 6, 20) not in days
    # Semana Santa calculada.
    assert days[date(2026, 4, 2)].name == "Jueves Santo"
    assert days[date(2027, 3, 26)].name == "Viernes Santo"
    # Fijos de todos los años del YAML.
    assert {date(y, 12, 25) for y in (2025, 2026, 2027, 2028)} <= set(days)
    assert all(h.notes.startswith("Confianza: ") and len(h.notes) <= 500 for h in days.values())
    assert all(h.legal_reference for h in days.values())


def test_load_candidates_is_idempotent_and_pending(client: TestClient, owner_token: str) -> None:
    headers = auth_header(owner_token)
    first = ok(client.post(f"{TAX}/holidays/load-candidates", headers=headers))
    expected = len(candidate_days())
    assert first == {"created": expected, "unchanged": 0, "differing": []}
    again = ok(client.post(f"{TAX}/holidays/load-candidates", headers=headers))
    assert again == {"created": 0, "unchanged": expected, "differing": []}
    listed = ok(
        client.get(
            f"{TAX}/holidays", params={"from": "2026-01-01", "to": "2026-12-31"}, headers=headers
        )
    )
    assert len(listed) == 14
    assert all(h["validation_status"] == "pending" and h["origin"] == "candidate" for h in listed)
    # Si alguien lo cambió a mano, la carga no lo pisa: lo informa.
    christmas = next(h for h in listed if h["day"] == "2026-12-25")
    ok(
        client.patch(
            f"{TAX}/holidays/{christmas['id']}", json={"name": "Navidad (editado)"}, headers=headers
        )
    )
    third = ok(client.post(f"{TAX}/holidays/load-candidates", headers=headers))
    assert [d["day"] for d in third["differing"]] == ["2026-12-25"]
    assert (
        ok(
            client.get(
                f"{TAX}/holidays",
                params={"from": "2026-12-25", "to": "2026-12-25"},
                headers=headers,
            )
        )[0]["name"]
        == "Navidad (editado)"
    )


def test_user_holiday_needs_source_and_verification_needs_permission(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    headers = auth_header(owner_token)
    res = client.post(
        f"{TAX}/holidays", json={"day": "2027-05-03", "name": "Asueto"}, headers=headers
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "HOLIDAY_SOURCE_REQUIRED"
    created = ok(
        client.post(
            f"{TAX}/holidays",
            json={
                "day": "2027-05-03",
                "name": "Feriado adicional",
                "legal_reference": "Decreto de prueba",
            },
            headers=headers,
        ),
        201,
    )
    assert created["validation_status"] == "pending" and created["origin"] == "user"
    res = client.post(
        f"{TAX}/holidays",
        json={"day": "2027-05-03", "name": "Otro", "legal_reference": "x"},
        headers=headers,
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "HOLIDAY_EXISTS"
    _, admin = make_user("admin")
    res = client.patch(
        f"{TAX}/holidays/{created['id']}",
        json={"validation_status": "verified"},
        headers=auth_header(admin),
    )
    assert res.status_code == 403
    verified = ok(
        client.patch(
            f"{TAX}/holidays/{created['id']}",
            json={"validation_status": "verified"},
            headers=headers,
        )
    )
    assert verified["validation_status"] == "verified"
    assert any(
        e["action"] == "tax.holiday.updated"
        for e in audit_entries(client, owner_token, "tax.holiday")
    )


def test_holiday_that_shifted_a_filed_due_date_is_kept(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    setup_tax(client, owner_token, monkeypatch, ruc="80000005")  # DJ terminación 5: día 17
    headers = auth_header(owner_token)
    # IVA de marzo de 2026 vence el viernes 17/04. Un feriado ese día lo pasa al lunes 20.
    holiday = ok(
        client.post(
            f"{TAX}/holidays",
            json={"day": "2026-04-17", "name": "Feriado de prueba", "legal_reference": "Decreto X"},
            headers=headers,
        ),
        201,
    )
    row = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-03-01")
    assert (row["nominal_due_date"], row["due_date"]) == ("2026-04-17", "2026-04-20")
    assert row["remind_by"] == "2026-04-17"
    assert "2026-04-20" not in row["shift_explanation"]  # la explicación va en dd/mm/aaaa
    assert "20/04/2026" in row["shift_explanation"]
    assert "sin verificar" in row["shift_explanation"]
    file_obligation(client, owner_token, row["id"])
    res = client.delete(f"{TAX}/holidays/{holiday['id']}", headers=headers)
    assert res.status_code == 409 and res.json()["error"]["code"] == "HOLIDAY_IN_USE"
    res = client.patch(
        f"{TAX}/holidays/{holiday['id']}", json={"day": "2026-04-16"}, headers=headers
    )
    assert res.status_code == 409
    rejected(
        db, "DELETE FROM tax.holidays WHERE id = :id", {"id": holiday["id"]}, "trg_holidays_in_use"
    )
    rejected(
        db,
        "UPDATE tax.holidays SET day = '2026-04-16' WHERE id = :id",
        {"id": holiday["id"]},
        "trg_holidays_in_use",
    )
    # El nombre sí se puede corregir.
    ok(client.patch(f"{TAX}/holidays/{holiday['id']}", json={"name": "Corregido"}, headers=headers))
    # Uno que no corrió nada presentado se borra.
    free = ok(
        client.post(
            f"{TAX}/holidays",
            json={"day": "2027-06-03", "name": "Libre", "legal_reference": "Decreto Y"},
            headers=headers,
        ),
        201,
    )
    assert client.delete(f"{TAX}/holidays/{free['id']}", headers=headers).status_code == 204


def test_exceptions_crud_overlap_and_in_use(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    setup_tax(client, owner_token, monkeypatch, ruc="80000005")
    headers = auth_header(owner_token)
    base = {
        "obligation_code": "IVA-GENERAL-LIQUIDACION",
        "due_month": "2026-07-01",
        "ruc_digits": [5],
        "new_due_date": "2026-07-31",
        "legal_reference": "RG de prueba",
    }
    res = client.post(
        f"{TAX}/due-date-exceptions",
        json={**base, "obligation_group": "determinative"},
        headers=headers,
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "EXCEPTION_TARGET_INVALID"
    created = ok(client.post(f"{TAX}/due-date-exceptions", json=base, headers=headers), 201)
    assert created["origin"] == "user" and created["is_active"] is True
    row = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-06-01")
    assert row["due_date"] == "2026-07-31"
    # Otra para la misma obligación y mes que cubre la terminación 5 se superpone.
    res = client.post(
        f"{TAX}/due-date-exceptions", json={**base, "ruc_digits": []}, headers=headers
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "EXCEPTION_OVERLAP"
    # Una de grupo no: la que nombra la obligación gana sobre la del grupo (D-086).
    group = ok(
        client.post(
            f"{TAX}/due-date-exceptions",
            json={
                **base,
                "obligation_code": None,
                "obligation_group": "determinative",
                "new_due_date": "2026-07-29",
            },
            headers=headers,
        ),
        201,
    )
    assert (
        obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-06-01")["due_date"]
        == "2026-07-31"
    )
    ok(
        client.patch(
            f"{TAX}/due-date-exceptions/{group['id']}", json={"is_active": False}, headers=headers
        )
    )
    file_obligation(client, owner_token, row["id"])
    res = client.patch(
        f"{TAX}/due-date-exceptions/{created['id']}",
        json={"new_due_date": "2026-07-30"},
        headers=headers,
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "EXCEPTION_IN_USE"
    rejected(
        db,
        "DELETE FROM tax.due_date_exceptions WHERE id = :id",
        {"id": created["id"]},
        "trg_due_date_exceptions_no_delete",
    )
    # La de la RG 60/2026 (cargada con las reglas) solo se activa o desactiva.
    load_rules(client, owner_token)
    rg60 = next(
        e
        for e in ok(client.get(f"{TAX}/due-date-exceptions", headers=headers))
        if e["origin"] == "candidate"
    )
    res = client.patch(
        f"{TAX}/due-date-exceptions/{rg60['id']}",
        json={"new_due_date": "2026-11-30"},
        headers=headers,
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "EXCEPTION_FROM_RULE"
    off = ok(
        client.patch(
            f"{TAX}/due-date-exceptions/{rg60['id']}", json={"is_active": False}, headers=headers
        )
    )
    assert off["is_active"] is False
    assert any(
        e["action"] == "tax.due_date_exception.updated"
        for e in audit_entries(client, owner_token, "tax.due_date_exception")
    )
