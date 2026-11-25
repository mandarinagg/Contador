"""Categorías de activo fijo y alta de bienes (spec 3B §5.4 y §6; D-056, D-057, D-064, D-065)."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.verification import source_reference
from app.modules.accounting import proposed_asset_categories
from tests.accounting_utils import ACC, error_code
from tests.assets_utils import (
    INFORMATICA,
    MUEBLES,
    TERRENOS,
    VEHICULOS,
    get_asset,
    new_asset,
    setup_books,
)
from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import ok

YAML_PATH = Path(BACKEND_DIR).parent / "docs/research/categorias_activo_fijo_candidatas.yaml"


@pytest.fixture
def books(client: TestClient, owner_token: str) -> dict[str, Any]:
    return setup_books(client, owner_token, (2026, 2027))


def test_packaged_categories_are_identical_to_research_yaml() -> None:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    assert data["meta"] == proposed_asset_categories.META
    assert list(proposed_asset_categories.CATEGORIAS) == data["categorias"]
    assert len(proposed_asset_categories.CATEGORIAS) == 34


def test_load_proposed_maps_accounts_and_stays_pending(
    client: TestClient, books: dict[str, Any]
) -> None:
    categories = books["categories"]
    accounts = books["accounts"]
    assert len(categories) == 34
    assert all(c["validation_status"] == "pending" for c in categories.values())
    muebles = categories[MUEBLES]
    assert muebles["useful_life_months"] == 60 and muebles["residual_rate"] == "10"
    assert muebles["asset_account_id"] == accounts["1.02.04.03"]["id"]
    assert muebles["accumulated_account_id"] == accounts["1.02.04.99.03"]["id"]
    assert muebles["expense_account_id"] == accounts["15.01"]["id"]
    assert muebles["complete"] is True and muebles["missing"] == []
    # Terrenos no se deprecia: sin vida útil ni acumulada, no se puede usar.
    assert categories[TERRENOS]["complete"] is False
    assert "vida útil" in categories[TERRENOS]["missing"]
    # Intangibles: la norma no fija residual, queda para completar.
    assert "porcentaje de valor residual" in categories["software_licencias"]["missing"]
    again = client.post(
        f"{ACC}/asset-categories/load-proposed", headers=auth_header(books["token"])
    )
    assert again.status_code == 409 and error_code(again) == "ASSET_CATEGORIES_NOT_EMPTY"


def test_load_proposed_without_chart_leaves_accounts_empty(
    client: TestClient, owner_token: str
) -> None:
    res = client.post(f"{ACC}/asset-categories/load-proposed", headers=auth_header(owner_token))
    rows = ok(res, 201)
    assert len(rows) == 34
    assert all(r["asset_account_id"] is None and not r["complete"] for r in rows)


def test_incomplete_category_cannot_be_used(client: TestClient, books: dict[str, Any]) -> None:
    res = new_asset(client, books, category=TERRENOS, expect=422)
    assert error_code(res) == "ASSET_CATEGORY_INCOMPLETE"
    assert "Terrenos" in res.json()["error"]["message"]


def test_category_accounts_of_wrong_kind_are_rejected(
    client: TestClient, books: dict[str, Any]
) -> None:
    accounts = books["accounts"]
    headers = auth_header(books["token"])
    base = {"name": "Categoría propia", "useful_life_months": 12, "residual_rate": "5"}
    cases = [
        {"asset_account_id": accounts["15.01"]["id"]},  # gasto como activo
        {"accumulated_account_id": accounts["1.02.04.03"]["id"]},  # activo deudor como acumulada
        {"expense_account_id": accounts["4.01.01.01"]["id"]},  # ingreso como gasto
        {"asset_account_id": accounts["1.02.04"]["id"]},  # agrupadora
    ]
    for case in cases:
        res = client.post(f"{ACC}/asset-categories", json={**base, **case}, headers=headers)
        assert res.status_code == 422, (case, res.text)
        assert error_code(res) == "INVALID_CATEGORY_ACCOUNT"
        cid = books["categories"][MUEBLES]["id"]
        res = client.patch(f"{ACC}/asset-categories/{cid}", json=case, headers=headers)
        assert res.status_code == 422 and error_code(res) == "INVALID_CATEGORY_ACCOUNT"


def test_residual_rate_above_20_percent_is_rejected(
    client: TestClient, books: dict[str, Any]
) -> None:
    headers = auth_header(books["token"])
    res = client.post(
        f"{ACC}/asset-categories",
        json={"name": "Demasiado residual", "useful_life_months": 12, "residual_rate": "20.5"},
        headers=headers,
    )
    assert res.status_code == 422 and error_code(res) == "RESIDUAL_RATE_INVALID"
    # En el bien, el residual fiscal también tiene el tope del 20 % (Ley 6380, art. 11).
    res = new_asset(
        client, books, fiscal_residual_rate="25", fiscal_life_authorization="CV 1", expect=422
    )
    assert error_code(res) == "RESIDUAL_RATE_INVALID"
    asset = new_asset(client, books, fiscal_residual_rate="20", fiscal_life_authorization="CV 1")
    assert asset["fiscal_residual_value"] == "2000000"


def test_fiscal_life_off_the_table_needs_the_dnit_authorization(
    client: TestClient, books: dict[str, Any]
) -> None:
    """D-125: solo la DNIT cambia la vida útil o el residual fiscal (Decreto 3182, art. 31)."""
    headers = auth_header(books["token"])
    res = new_asset(client, books, fiscal_useful_life_months=96, expect=422)
    assert error_code(res) == "FISCAL_LIFE_NEEDS_AUTHORIZATION"
    assert res.json()["error"]["details"] == {
        "category_useful_life_months": 60,
        "category_residual_rate": "10.00",
    }
    res = new_asset(client, books, fiscal_residual_rate="5", expect=422)
    assert error_code(res) == "FISCAL_LIFE_NEEDS_AUTHORIZATION"
    # Con la de la tabla no hace falta, y una autorización sobrante no se guarda.
    asset = new_asset(client, books, fiscal_life_authorization="CV 99")
    assert asset["fiscal_life_authorization"] is None
    # Con el número de la autorización, sí.
    authorized = new_asset(
        client,
        books,
        fiscal_useful_life_months=96,
        fiscal_life_authorization="  Consulta  N° 7340000519 ",
    )
    assert authorized["fiscal_useful_life_months"] == 96
    assert authorized["fiscal_life_authorization"] == "Consulta N° 7340000519"
    url = f"{ACC}/fixed-assets/{authorized['id']}"
    # Se corrige el número, pero no se quita mientras el bien salga de la tabla.
    fixed = ok(client.patch(url, json={"fiscal_life_authorization": "CV 800"}, headers=headers))
    assert fixed["fiscal_life_authorization"] == "CV 800"
    res = client.patch(url, json={"fiscal_life_authorization": None}, headers=headers)
    assert res.status_code == 422 and error_code(res) == "FISCAL_LIFE_NEEDS_AUTHORIZATION"
    # Otra categoría: los parámetros fiscales vuelven a los suyos y la autorización se va.
    moved = ok(
        client.patch(
            url, json={"category_id": books["categories"][INFORMATICA]["id"]}, headers=headers
        )
    )
    assert moved["fiscal_useful_life_months"] == 24
    assert moved["fiscal_life_authorization"] is None


def test_validation_requires_post_and_resets_on_structural_change(
    client: TestClient, books: dict[str, Any], make_user: Any
) -> None:
    _, admin = make_user("admin")  # gestiona, pero no contabiliza ni valida (D-043)
    cid = books["categories"][MUEBLES]["id"]
    denied = client.post(f"{ACC}/asset-categories/{cid}/validate", headers=auth_header(admin))
    assert denied.status_code == 403
    validated = ok(
        client.post(
            f"{ACC}/asset-categories/{cid}/validate",
            headers=auth_header(books["token"]),
        )
    )
    assert validated["validation_status"] == "validated"
    assert validated["validated_by_name"] == "CONTADOR AI"
    assert validated["validated_reference"] == source_reference(validated["legal_reference"])
    # Un cambio de nota no la invalida; uno de vida útil, sí.
    noted = ok(
        client.patch(
            f"{ACC}/asset-categories/{cid}", json={"note": "Ok"}, headers=auth_header(admin)
        )
    )
    assert noted["validation_status"] == "validated"
    changed = ok(
        client.patch(
            f"{ACC}/asset-categories/{cid}",
            json={"useful_life_months": 48},
            headers=auth_header(admin),
        )
    )
    assert changed["validation_status"] == "pending" and changed["validated_by_name"] is None
    # Una incompleta no se valida.
    terrenos = books["categories"][TERRENOS]["id"]
    res = client.post(
        f"{ACC}/asset-categories/{terrenos}/validate",
        headers=auth_header(books["token"]),
    )
    assert res.status_code == 422 and error_code(res) == "ASSET_CATEGORY_INCOMPLETE"


def test_own_category_without_official_source_is_not_validated(
    client: TestClient, books: dict[str, Any]
) -> None:
    """D-120: CONTADOR AI no valida una categoría sin fuente oficial; queda `pending`."""
    headers = auth_header(books["token"])
    muebles = books["categories"][MUEBLES]
    own = ok(
        client.post(
            f"{ACC}/asset-categories",
            json={
                "name": "Categoría propia completa",
                "useful_life_months": 36,
                "residual_rate": "5",
                "asset_account_id": muebles["asset_account_id"],
                "accumulated_account_id": muebles["accumulated_account_id"],
                "expense_account_id": muebles["expense_account_id"],
            },
            headers=headers,
        ),
        201,
    )
    assert own["complete"] is True
    res = client.post(f"{ACC}/asset-categories/{own['id']}/validate", headers=headers)
    assert res.status_code == 422 and error_code(res) == "CATEGORY_NOT_VERIFIABLE"
    assert "fuente oficial" in res.json()["error"]["message"]
    category = ok(client.get(f"{ACC}/asset-categories/{own['id']}", headers=headers))
    assert category["validation_status"] == "pending"


def test_asset_defaults_come_from_category_and_settings(
    client: TestClient, books: dict[str, Any]
) -> None:
    asset = new_asset(client, books, category=VEHICULOS, cost=50_000_001)
    assert asset["useful_life_months"] == asset["fiscal_useful_life_months"] == 60
    assert asset["fiscal_residual_rate"] == "20"
    # Residual fiscal: costo por porcentaje, en guaraníes enteros hacia abajo (RG 77, col. 6).
    assert asset["fiscal_residual_value"] == "10000000"
    assert asset["residual_value"] == "10000000"
    assert asset["start_rule"] == "next_month"
    assert asset["depreciation_start"] == "2026-02-01"
    assert asset["warnings"] == []
    assert len(asset["installments"]) == 60
    assert all(i["status"] == "pending" for i in asset["installments"])
    total = sum(int(i["amount"]) for i in asset["installments"])
    assert total == 50_000_001 - 10_000_000


def test_start_rule_next_fiscal_year(client: TestClient, books: dict[str, Any]) -> None:
    asset = new_asset(client, books, acquired_on="2026-03-20", start_rule="next_fiscal_year")
    assert asset["depreciation_start"] == "2027-01-01"
    assert asset["installments"][0]["month"] == "2027-01-01"
    # Valor por defecto configurable (D-064).
    ok(
        client.put(
            f"{ACC}/settings",
            json={"default_asset_start_rule": "next_fiscal_year"},
            headers=auth_header(books["token"]),
        )
    )
    other = new_asset(client, books, acquired_on="2026-12-31")
    assert other["start_rule"] == "next_fiscal_year"
    assert other["depreciation_start"] == "2027-01-01"


def test_asset_parameters_are_validated(client: TestClient, books: dict[str, Any]) -> None:
    res = new_asset(client, books, residual_value="10000000", expect=422)
    assert error_code(res) == "RESIDUAL_INVALID"
    res = new_asset(client, books, cost="50", expect=422)  # depreciable 45 < 60 meses
    assert error_code(res) == "DEPRECIABLE_TOO_SMALL"
    res = new_asset(client, books, cost="10.5", expect=422)
    assert error_code(res) in ("INVALID_AMOUNT", "VALIDATION_ERROR")
    res = new_asset(client, books, acquired_on="2024-05-01", expect=422)
    assert error_code(res) == "DEPRECIATION_START_BEFORE_BOOKS"


def test_asset_acquired_before_norm_shows_warning(client: TestClient, owner_token: str) -> None:
    books = setup_books(client, owner_token, (2021,))
    asset = new_asset(client, books, acquired_on="2021-03-01")
    assert len(asset["warnings"]) == 1 and "14/10/2021" in asset["warnings"][0]
    later = new_asset(client, books, acquired_on="2021-10-14")
    assert later["warnings"] == []


def test_list_and_filter_assets(client: TestClient, books: dict[str, Any]) -> None:
    new_asset(client, books, name="Notebook Lenovo", category=INFORMATICA, cost=8_000_000)
    new_asset(client, books, name="Escritorio", category=MUEBLES)
    headers = auth_header(books["token"])
    rows = ok(client.get(f"{ACC}/fixed-assets", params={"q": "lenovo"}, headers=headers))
    assert [r["name"] for r in rows] == ["Notebook Lenovo"]
    cid = books["categories"][MUEBLES]["id"]
    rows = ok(client.get(f"{ACC}/fixed-assets", params={"category_id": cid}, headers=headers))
    assert [r["name"] for r in rows] == ["Escritorio"]
    rows = ok(client.get(f"{ACC}/fixed-assets", params={"status": "disposed"}, headers=headers))
    assert rows == []


def test_update_asset_recomputes_until_depreciated(
    client: TestClient, books: dict[str, Any]
) -> None:
    asset = new_asset(client, books)
    headers = auth_header(books["token"])
    changed = ok(
        client.patch(
            f"{ACC}/fixed-assets/{asset['id']}",
            json={"cost": "12000000", "acquired_on": "2026-02-10"},
            headers=headers,
        )
    )
    assert changed["fiscal_residual_value"] == "1200000"
    assert changed["depreciation_start"] == "2026-03-01"
    detail = get_asset(client, books, asset["id"])
    assert detail["cost"] == "12000000"
