"""Ayudas para las pruebas de contabilidad (no es un módulo de pruebas)."""

from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from tests.conftest import auth_header
from tests.finance_utils import ok

ACC = "/api/v1/accounting"

# Cuentas imputables del plan propuesto que usan las pruebas.
CAJA = "1.01.01.02"
BANCOS = "1.01.01.04.01"
BANCO_USD = "1.01.01.04.03"
DEUDORES = "1.01.03.01"
PROVEEDORES = "2.01.01.01"
CAPITAL = "3.01.01.01"
RESULTADO_EJERCICIO = "3.03.02"
VENTAS = "4.01.01.01"
HONORARIOS = "11.04"
ALQUILERES = "11.05"
GRUPO_DISPONIBILIDADES = "1.01.01"


def load_chart(client: TestClient, token: str) -> dict[str, dict[str, Any]]:
    """Carga el plan propuesto y devuelve las cuentas por código."""
    accounts = ok(client.post(f"{ACC}/chart/load-proposed", headers=auth_header(token)), 201)
    return {a["code"]: a for a in accounts}


def chart_by_code(client: TestClient, token: str) -> dict[str, dict[str, Any]]:
    chart = ok(client.get(f"{ACC}/chart", params={"flat": "true"}, headers=auth_header(token)))
    return {a["code"]: a for a in chart["accounts"]}


def create_year(client: TestClient, token: str, year: int = 2026) -> dict[str, Any]:
    res = client.post(f"{ACC}/fiscal-years", json={"year": year}, headers=auth_header(token))
    return dict(ok(res, 201))


def entry_body(
    accounts: dict[str, dict[str, Any]],
    day: str,
    lines: list[tuple[str, int | str, int | str]],
    description: str = "Asiento de prueba",
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "entry_date": day,
        "description": description,
        "lines": [
            {"account_id": accounts[code]["id"], "debit": str(debit), "credit": str(credit)}
            for code, debit, credit in lines
        ],
    }
    body.update(extra)
    return body


def draft(
    client: TestClient,
    token: str,
    accounts: dict[str, dict[str, Any]],
    day: str,
    lines: list[tuple[str, int | str, int | str]],
    description: str = "Asiento de prueba",
) -> dict[str, Any]:
    res = client.post(
        f"{ACC}/entries",
        json=entry_body(accounts, day, lines, description),
        headers=auth_header(token),
    )
    return dict(ok(res, 201))


def post(client: TestClient, token: str, entry_id: str) -> Response:
    return client.post(f"{ACC}/entries/{entry_id}/post", headers=auth_header(token))


def posted(
    client: TestClient,
    token: str,
    accounts: dict[str, dict[str, Any]],
    day: str,
    lines: list[tuple[str, int | str, int | str]],
    description: str = "Asiento de prueba",
) -> dict[str, Any]:
    entry = draft(client, token, accounts, day, lines, description)
    return dict(ok(post(client, token, entry["id"])))


def period_for(year: dict[str, Any], month: int) -> dict[str, Any]:
    return dict(year["periods"][month - 1])


def close_period(client: TestClient, token: str, period_id: str) -> Response:
    return client.post(f"{ACC}/periods/{period_id}/close", headers=auth_header(token))


def error_code(res: Response) -> str:
    return str(res.json()["error"]["code"])
