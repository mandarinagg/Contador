"""Ayudas para las pruebas de la fase 3B (no es un módulo de pruebas)."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from tests.accounting_utils import ACC, create_year, load_chart, post
from tests.conftest import auth_header
from tests.finance_utils import ok

MUEBLES = "muebles_y_equipos_en_general"  # 60 meses, residual 10 %
INFORMATICA = "equipos_de_informatica"  # 24 meses, residual 10 %
VEHICULOS = "vehiculos_automotores"  # 60 meses, residual 20 %
TERRENOS = "terrenos"  # sin vida útil: incompleta


def setup_books(client: TestClient, token: str, years: tuple[int, ...] = (2026,)) -> dict[str, Any]:
    """Plan propuesto, ejercicios y las 34 categorías candidatas."""
    accounts = load_chart(client, token)
    created = {y: create_year(client, token, y) for y in years}
    categories = ok(
        client.post(f"{ACC}/asset-categories/load-proposed", headers=auth_header(token)), 201
    )
    return {
        "token": token,
        "accounts": accounts,
        "years": created,
        "categories": {c["code"]: c for c in categories},
    }


def period_id(books: dict[str, Any], year: int, month: int) -> str:
    return str(books["years"][year]["periods"][month - 1]["id"])


def new_asset(
    client: TestClient,
    books: dict[str, Any],
    *,
    category: str = MUEBLES,
    name: str = "Bien de prueba",
    acquired_on: str = "2026-01-15",
    cost: int | str = 10_000_000,
    expect: int = 201,
    **extra: Any,
) -> Any:
    body = {
        "category_id": books["categories"][category]["id"],
        "name": name,
        "acquired_on": acquired_on,
        "cost": str(cost),
        **extra,  # importes y porcentajes van como texto
    }
    res = client.post(f"{ACC}/fixed-assets", json=body, headers=auth_header(books["token"]))
    if expect != 201:
        assert res.status_code == expect, res.text
        return res
    return ok(res, 201)


def run(client: TestClient, books: dict[str, Any], year: int, month: int) -> Response:
    return client.post(
        f"{ACC}/depreciation/run",
        json={"period_id": period_id(books, year, month)},
        headers=auth_header(books["token"]),
    )


def run_and_post(client: TestClient, books: dict[str, Any], year: int, month: int) -> Any:
    created = ok(run(client, books, year, month), 201)
    ok(post(client, books["token"], created["entry_id"]))
    return created


def get_asset(client: TestClient, books: dict[str, Any], asset_id: str) -> Any:
    return ok(client.get(f"{ACC}/fixed-assets/{asset_id}", headers=auth_header(books["token"])))


def balance(client: TestClient, books: dict[str, Any], code: str, at: str) -> Decimal:
    """Saldo de una cuenta al cierre de `at`, en el sentido de su tipo."""
    chart = ok(
        client.get(
            f"{ACC}/chart",
            params={"flat": "true", "balance_at": at},
            headers=auth_header(books["token"]),
        )
    )
    return Decimal(next(a["balance"] for a in chart["accounts"] if a["code"] == code))


def months(start: date, count: int) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    for _ in range(count):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out
