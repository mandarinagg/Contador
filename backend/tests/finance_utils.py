"""Ayudas para las pruebas de finanzas (no es un módulo de pruebas)."""

import json
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from tests.conftest import auth_header

API = "/api/v1/finance"


def _no_float(text: str) -> Any:
    raise AssertionError(f"La API devolvió un número con decimales en JSON: {text}")


def strict_json(res: Response) -> Any:
    """JSON de la respuesta; falla si aparece cualquier número no entero (un float)."""
    return json.loads(res.text, parse_float=_no_float)


def ok(res: Response, code: int = 200) -> Any:
    assert res.status_code == code, res.text
    return strict_json(res)


def business_context(client: TestClient, token: str) -> str:
    contexts = ok(client.get(f"{API}/contexts", headers=auth_header(token)))
    return str(next(c["id"] for c in contexts if c["kind"] == "business"))


def personal_context(client: TestClient, token: str) -> str:
    return str(ok(client.post(f"{API}/contexts/personal", headers=auth_header(token)), 201)["id"])


def create_account(
    client: TestClient, token: str, cid: str, name: str = "Banco", **fields: Any
) -> dict[str, Any]:
    body = {"name": name, "kind": "checking", "currency": "PYG", "opening_date": "2026-01-01"}
    body.update(fields)
    res = client.post(f"{API}/contexts/{cid}/accounts", json=body, headers=auth_header(token))
    return dict(ok(res, 201))


def create_tx(
    client: TestClient,
    token: str,
    cid: str,
    account_id: str,
    amount: str,
    booked_on: str = "2026-03-10",
    description: str = "Movimiento",
    **fields: Any,
) -> dict[str, Any]:
    body = {
        "account_id": account_id,
        "booked_on": booked_on,
        "amount": amount,
        "description": description,
    }
    body.update(fields)
    res = client.post(f"{API}/contexts/{cid}/transactions", json=body, headers=auth_header(token))
    return dict(ok(res, 201))


def audit_entries(client: TestClient, token: str, entity_type: str) -> list[dict[str, Any]]:
    res = client.get(
        "/api/v1/audit/logs",
        params={"entity_type": entity_type, "limit": 200},
        headers=auth_header(token),
    )
    return list(ok(res))
