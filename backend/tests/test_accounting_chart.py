"""Plan de cuentas (D-037, D-038, BR-ACC-09, BR-ACC-10; spec §5.7)."""

import os
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.modules.accounting import proposed_chart
from tests.accounting_utils import (
    ACC,
    BANCOS,
    CAJA,
    CAPITAL,
    GRUPO_DISPONIBILIDADES,
    RESULTADO_EJERCICIO,
    VENTAS,
    chart_by_code,
    create_year,
    draft,
    error_code,
    load_chart,
    posted,
)
from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import audit_entries, ok

YAML_PATH = os.path.join(
    os.path.dirname(BACKEND_DIR), "docs", "research", "plan_de_cuentas_propuesto.yaml"
)
KINDS = {
    "activo": "asset",
    "pasivo": "liability",
    "patrimonio": "equity",
    "ingreso": "income",
    "gasto": "expense",
}


def _yaml() -> dict[str, Any]:
    with open(YAML_PATH, encoding="utf-8") as handle:
        return dict(yaml.safe_load(handle))


def test_packaged_chart_is_identical_to_research_yaml() -> None:
    """La copia empaquetada (módulo Python) es idéntica al YAML de la investigación."""
    research = _yaml()
    assert research["meta"] == proposed_chart.META
    assert research["cuentas"] == list(proposed_chart.CUENTAS)
    assert len(proposed_chart.CUENTAS) == 159


def test_load_proposed_creates_159_accounts_with_hierarchy_and_kinds(
    client: TestClient, owner_token: str
) -> None:
    headers = auth_header(owner_token)
    before = ok(client.get(f"{ACC}/chart", headers=headers))
    assert before["chart_status"] == "none" and before["accounts"] == []

    created = load_chart(client, owner_token)
    assert len(created) == 159
    by_id = {a["id"]: a for a in created.values()}
    for row in _yaml()["cuentas"]:
        account = created[row["codigo"]]
        assert account["name"] == row["nombre"]
        assert account["kind"] == KINDS[row["tipo"]]
        assert account["normal_side"] == ("debit" if row["naturaleza"] == "deudora" else "credit")
        assert account["is_postable"] is row["imputable"]
        assert account["origin"] == ("proposed" if row["origen"] == "propuesta" else "rg49_2014")
        assert account["note"] == row.get("nota")
        parent = by_id[account["parent_id"]]["code"] if account["parent_id"] else None
        assert parent == row["padre"]

    chart = ok(client.get(f"{ACC}/chart", headers=headers))
    assert chart["chart_status"] == "pending"
    roots = [a["code"] for a in chart["accounts"]]
    assert roots == ["1", "2", "3", "4", "5", "8", "10", "11", "13", "14", "15", "17", "19"]
    activo = chart["accounts"][0]
    corriente = activo["children"][0]
    assert corriente["code"] == "1.01"
    assert [c["code"] for c in corriente["children"]][:2] == ["1.01.01", "1.01.02"]
    flat = ok(client.get(f"{ACC}/chart", params={"flat": "true"}, headers=headers))
    assert len(flat["accounts"]) == 159 and all(a["children"] is None for a in flat["accounts"])

    created_audit = [
        e
        for e in audit_entries(client, owner_token, "accounting.ledger_account")
        if e["action"] == "accounting.ledger_account.created"
    ]
    assert len(created_audit) == 159
    assert audit_entries(client, owner_token, "accounting.chart")[0]["after"]["chart_status"] == (
        "pending"
    )


def test_proposed_chart_is_not_loaded_twice(client: TestClient, owner_token: str) -> None:
    load_chart(client, owner_token)
    res = client.post(f"{ACC}/chart/load-proposed", headers=auth_header(owner_token))
    assert res.status_code == 409 and error_code(res) == "CHART_NOT_EMPTY"
    assert len(chart_by_code(client, owner_token)) == 159


def test_used_account_does_not_change_code_or_nature(client: TestClient, owner_token: str) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token)
    bank = accounts[BANCOS]["id"]
    # Sin líneas, el código se puede corregir (sigue siendo hijo del mismo padre).
    res = client.patch(
        f"{ACC}/chart/accounts/{bank}", json={"code": "1.01.01.04.09"}, headers=headers
    )
    assert ok(res)["code"] == "1.01.01.04.09"
    accounts = chart_by_code(client, owner_token)
    draft(client, owner_token, accounts, "2026-02-01", [("1.01.01.04.09", 10, 0)])

    for change in (
        {"code": "1.01.01.04.01"},
        {"kind": "liability"},
        {"is_postable": False},
        {"normal_side": "credit"},
    ):
        res = client.patch(f"{ACC}/chart/accounts/{bank}", json=change, headers=headers)
        assert res.status_code == 409 and error_code(res) == "ACCOUNT_IN_USE", change
    res = client.patch(
        f"{ACC}/chart/accounts/{bank}",
        json={"name": "Banco Itaú cuenta corriente"},
        headers=headers,
    )
    assert ok(res)["name"] == "Banco Itaú cuenta corriente" and ok(res)["in_use"] is True


def test_create_account_rules(client: TestClient, owner_token: str) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    group = accounts["1.01.01.04"]["id"]

    def create(**body: Any) -> Any:
        return client.post(f"{ACC}/chart/accounts", json=body, headers=headers)

    res = create(parent_id=group, code="1.01.01.04.04", name="Banco Continental", is_postable=True)
    account = ok(res, 201)
    assert (account["kind"], account["normal_side"], account["origin"]) == (
        "asset",
        "debit",
        "user",
    )
    for code in ("1.01.01.05", "1.01.01.04.05.01", "1.01.01.04"):
        res = create(parent_id=group, code=code, name="Mal código", is_postable=True)
        assert res.status_code == 422 and error_code(res) == "ACCOUNT_CODE_INVALID", code
    res = create(parent_id=group, code="1.01.01.04.04", name="Repetida", is_postable=True)
    assert res.status_code == 409 and error_code(res) == "ACCOUNT_CODE_TAKEN"
    res = create(
        parent_id=accounts[CAJA]["id"], code="1.01.01.02.01", name="Hija", is_postable=True
    )
    assert res.status_code == 422 and error_code(res) == "PARENT_IS_POSTABLE"
    res = create(
        parent_id=group,
        code="1.01.01.04.06",
        name="Gasto mal ubicado",
        kind="expense",
        is_postable=True,
    )
    assert res.status_code == 422 and error_code(res) == "ACCOUNT_KIND_MISMATCH"
    res = create(code="6", name="Grupo nuevo", kind="expense", is_postable=False)
    assert ok(res, 201)["normal_side"] == "debit"
    res = create(code="6.01", name="Sin padre", kind="expense", is_postable=True)
    assert res.status_code == 422 and error_code(res) == "ACCOUNT_CODE_INVALID"


def test_validation_requires_accountant_and_any_structural_change_resets_it(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    headers = auth_header(owner_token)
    res = client.post(
        f"{ACC}/chart/validate",
        json={"validated_by_name": "Cdora. Ana Pérez", "validated_reference": "Mat. 1234"},
        headers=headers,
    )
    assert res.status_code == 409 and error_code(res) == "CHART_EMPTY"
    accounts = load_chart(client, owner_token)
    _, admin = make_user("admin")
    _, accountant = make_user("accountant")
    body = {"validated_by_name": "Cdora. Ana Pérez", "validated_reference": "Mat. 1234"}
    assert (
        client.post(f"{ACC}/chart/validate", json=body, headers=auth_header(admin)).status_code
        == 403
    )
    settings = ok(client.post(f"{ACC}/chart/validate", json=body, headers=auth_header(accountant)))
    assert settings["chart_status"] == "validated"
    assert settings["chart_validated_by_name"] == "Cdora. Ana Pérez"
    assert settings["chart_validated_reference"] == "Mat. 1234"
    assert settings["chart_validated_at"]
    create_year(client, owner_token)
    report = ok(
        client.get(
            f"{ACC}/reports/trial-balance",
            params={"from": "2026-01-01", "to": "2026-12-31"},
            headers=headers,
        )
    )
    assert report["chart_status"] == "validated"

    # Renombrar no cambia la estructura: sigue validado.
    client.patch(
        f"{ACC}/chart/accounts/{accounts[CAJA]['id']}", json={"name": "CAJA CHICA"}, headers=headers
    )
    assert ok(client.get(f"{ACC}/settings", headers=headers))["chart_status"] == "validated"
    # Una cuenta nueva sí: vuelve a pendiente (D-046).
    ok(
        client.post(
            f"{ACC}/chart/accounts",
            json={
                "parent_id": accounts["1.01.01.04"]["id"],
                "code": "1.01.01.04.04",
                "name": "Banco nuevo",
                "is_postable": True,
            },
            headers=headers,
        ),
        201,
    )
    settings = ok(client.get(f"{ACC}/settings", headers=headers))
    assert settings["chart_status"] == "pending" and settings["chart_validated_by_name"] is None

    ok(client.post(f"{ACC}/chart/validate", json=body, headers=headers))
    ok(client.post(f"{ACC}/chart/invalidate", headers=headers))
    res = client.post(f"{ACC}/chart/invalidate", headers=headers)
    assert res.status_code == 409 and error_code(res) == "CHART_NOT_VALIDATED"
    actions = [e["action"] for e in audit_entries(client, owner_token, "accounting.chart")]
    assert actions[:3] == [
        "accounting.chart.invalidated",
        "accounting.chart.validated",
        "accounting.chart.pending",
    ]


def test_archive_rules(client: TestClient, owner_token: str) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token)
    posted(client, owner_token, accounts, "2026-01-10", [(CAJA, 5000, 0), (CAPITAL, 0, 5000)])

    def archive(code: str) -> Any:
        return client.patch(
            f"{ACC}/chart/accounts/{accounts[code]['id']}", json={"archived": True}, headers=headers
        )

    res = archive(CAJA)
    assert res.status_code == 409 and error_code(res) == "ACCOUNT_HAS_BALANCE"
    res = archive(GRUPO_DISPONIBILIDADES)
    assert res.status_code == 409 and error_code(res) == "ACCOUNT_HAS_CHILDREN"
    draft(client, owner_token, accounts, "2026-01-11", [("1.01.01.03", 10, 0)])
    res = archive("1.01.01.03")
    assert res.status_code == 409 and error_code(res) == "ACCOUNT_IN_DRAFTS"
    ok(
        client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": accounts[RESULTADO_EJERCICIO]["id"]},
            headers=headers,
        )
    )
    res = archive(RESULTADO_EJERCICIO)
    assert res.status_code == 409 and error_code(res) == "ACCOUNT_IN_SETTINGS"

    # Saldo vuelto a cero: se archiva, y entonces no recibe líneas.
    posted(client, owner_token, accounts, "2026-01-12", [(CAPITAL, 5000, 0), (CAJA, 0, 5000)])
    assert ok(archive(CAJA))["archived_at"]
    res = client.post(
        f"{ACC}/entries",
        json={
            "entry_date": "2026-01-13",
            "description": "Con cuenta archivada",
            "lines": [{"account_id": accounts[CAJA]["id"], "debit": "10"}],
        },
        headers=headers,
    )
    assert res.status_code == 422 and error_code(res) == "ACCOUNT_NOT_POSTABLE"


def test_retained_earnings_account_must_be_postable_equity(
    client: TestClient, owner_token: str, make_user: Any
) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    for code in (VENTAS, "3.03"):
        res = client.put(
            f"{ACC}/settings",
            json={"retained_earnings_account_id": accounts[code]["id"]},
            headers=headers,
        )
        assert res.status_code == 422 and error_code(res) == "INVALID_RETAINED_EARNINGS_ACCOUNT"
    _, admin = make_user("admin")
    body = {"retained_earnings_account_id": accounts[RESULTADO_EJERCICIO]["id"]}
    assert client.put(f"{ACC}/settings", json=body, headers=auth_header(admin)).status_code == 403
    settings = ok(client.put(f"{ACC}/settings", json=body, headers=headers))
    assert settings["retained_earnings_account_id"] == accounts[RESULTADO_EJERCICIO]["id"]
    audit = audit_entries(client, owner_token, "accounting.settings")
    assert audit[0]["after"] == body


def test_chart_balances_sum_their_subtree(client: TestClient, owner_token: str) -> None:
    headers = auth_header(owner_token)
    accounts = load_chart(client, owner_token)
    create_year(client, owner_token)
    posted(client, owner_token, accounts, "2026-01-10", [(CAJA, 7000, 0), (CAPITAL, 0, 7000)])
    posted(client, owner_token, accounts, "2026-02-10", [(BANCOS, 3000, 0), (CAJA, 0, 3000)])
    # Regularizadora: la depreciación acumulada (naturaleza acreedora) resta en el activo.
    posted(
        client,
        owner_token,
        accounts,
        "2026-02-11",
        [("15.01", 500, 0), ("1.02.04.99", 0, 500)],
    )
    chart = ok(
        client.get(
            f"{ACC}/chart", params={"flat": "true", "balance_at": "2026-01-31"}, headers=headers
        )
    )
    balances = {a["code"]: a["balance"] for a in chart["accounts"]}
    assert balances[CAJA] == "7000" and balances[BANCOS] == "0"
    chart = ok(
        client.get(
            f"{ACC}/chart", params={"flat": "true", "balance_at": "2026-12-31"}, headers=headers
        )
    )
    balances = {a["code"]: a["balance"] for a in chart["accounts"]}
    assert balances[CAJA] == "4000" and balances[BANCOS] == "3000"
    assert balances[GRUPO_DISPONIBILIDADES] == "7000"
    assert balances["1.02.04.99"] == "-500" and balances["1"] == "6500"
    assert balances["3"] == "7000" and balances["15"] == "500"
    in_use = {a["code"] for a in chart["accounts"] if a["in_use"]}
    assert in_use == {CAJA, BANCOS, CAPITAL, "15.01", "1.02.04.99"}
