"""El plan de cuentas propuesto, verificado contra el modelo oficial de la RG 49/2014 (D-124).

`docs/research/rg49_2014_codigos.yaml` es el extracto de los Anexos 1 y 2 del XLS oficial de
la DNIT (con su SHA-256). Esta prueba es la verificación de CONTADOR AI (D-118, D-120): si el
plan cambia y deja de respetar el modelo, falla.

Reglas (RG 49/2014, art. 3: se usan los códigos del modelo y se pueden agregar cuentas o
subcuentas; los códigos hasta el quinto nivel no se modifican):
- cada cuenta `rg49_2014` tiene un código del modelo y el mismo nombre;
- ninguna cuenta `propuesta` reutiliza un código del modelo, y todas cuelgan de uno;
- el código de cada cuenta empieza con el de su padre, y el padre no es imputable;
- en el balance, activo deudor, pasivo y patrimonio acreedores, salvo las regularizadoras
  «(-)», que llevan la naturaleza opuesta.
"""

import os
import re
import unicodedata

import yaml
from fastapi.testclient import TestClient

from app.modules.accounting import proposed_chart, rg49_codes
from tests.accounting_utils import ACC, error_code, load_chart
from tests.conftest import auth_header
from tests.finance_utils import ok

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICIAL_PATH = os.path.join(BACKEND_DIR, "..", "docs", "research", "rg49_2014_codigos.yaml")
BALANCE = {
    "1": ("activo", "deudora"),
    "2": ("pasivo", "acreedora"),
    "3": ("patrimonio", "acreedora"),
}
OPPOSITE = {"deudora": "acreedora", "acreedora": "deudora"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).strip())


def _official() -> dict[str, str]:
    with open(OFFICIAL_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["meta"]["sha256"] == (
        "a61f008446942c990a4b1f275310d55c10b0e519a5c6661648475d8a27734c67"
    )
    return {str(code): _norm(name) for code, name in data["codigos"].items()}


def test_extract_covers_both_annexes() -> None:
    official = _official()
    assert len(official) == 305
    assert official["1"] == "ACTIVO" and official["2"] == "PASIVO"
    assert official["4"] == "INGRESOS OPERATIVOS"
    assert official["11"] == "GASTOS DE ADMINISTRACIÓN"


def test_model_accounts_match_the_official_codes_and_names() -> None:
    official = _official()
    model = [a for a in proposed_chart.CUENTAS if a["origen"] == "rg49_2014"]
    assert len(model) == 142
    wrong = {
        a["codigo"]: (a["nombre"], official.get(a["codigo"]))
        for a in model
        if official.get(a["codigo"]) != _norm(a["nombre"])
    }
    assert wrong == {}


def test_own_accounts_hang_from_the_model_without_reusing_codes() -> None:
    official = _official()
    own = [a for a in proposed_chart.CUENTAS if a["origen"] == "propuesta"]
    assert len(own) == 31
    for account in own:
        code = account["codigo"]
        assert code not in official, f"{code} reutiliza un código del modelo"
        ancestor = code
        while ancestor not in official and "." in ancestor:
            ancestor = ancestor.rsplit(".", 1)[0]
        assert ancestor in official, f"{code} no cuelga de una cuenta del modelo"


def test_hierarchy_and_nature() -> None:
    by_code = {a["codigo"]: a for a in proposed_chart.CUENTAS}
    parents = {a["padre"] for a in proposed_chart.CUENTAS if a["padre"]}
    for code, account in by_code.items():
        parent = account["padre"]
        if parent is not None:
            assert parent in by_code, code
            assert code.startswith(parent + "."), code
            assert not by_code[parent]["imputable"], code
        assert not (account["imputable"] and code in parents), code
        expected = BALANCE.get(code.split(".")[0])
        if expected is None:
            continue
        kind, nature = expected
        assert account["tipo"] == kind, code
        if _norm(account["nombre"]).startswith("(-)"):
            assert account["naturaleza"] == OPPOSITE[nature], code
        else:
            assert account["naturaleza"] == nature, code


def test_packaged_codes_are_identical_to_research_yaml() -> None:
    with open(OFFICIAL_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert {k: str(v) for k, v in data["meta"].items()} == rg49_codes.META
    assert {str(k): v for k, v in data["codigos"].items()} == rg49_codes.CODES


def test_tool_refuses_a_user_account_that_takes_a_model_code_with_another_name(
    client: TestClient, owner_token: str
) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    ok(client.post(f"{ACC}/chart/validate", headers=headers))
    # 1.01.02.02 es «INVERSIONES EN ENTIDADES VINCULADAS» en el modelo (el plan no la trae).
    created = ok(
        client.post(
            f"{ACC}/chart/accounts",
            json={
                "parent_id": accounts["1.01.02"]["id"],
                "code": "1.01.02.02",
                "name": "Plazo fijo",
                "is_postable": True,
            },
            headers=headers,
        ),
        201,
    )
    res = client.post(f"{ACC}/chart/validate", headers=headers)
    assert res.status_code == 422 and error_code(res) == "CHART_NOT_VERIFIABLE"
    assert res.json()["error"]["details"] == {
        "problems": [
            "1.01.02.02: se llama «Plazo fijo» y en el modelo es «INVERSIONES EN ENTIDADES "
            "VINCULADAS»."
        ],
        "count": 1,
    }
    # Archivada, no cuenta: el plan se vuelve a validar.
    ok(
        client.patch(
            f"{ACC}/chart/accounts/{created['id']}", json={"archived": True}, headers=headers
        )
    )
    assert ok(client.post(f"{ACC}/chart/validate", headers=headers))["chart_status"] == (
        "validated"
    )
