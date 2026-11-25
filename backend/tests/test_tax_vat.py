"""Estimación del IVA y borrador del Formulario 120 (spec fase 4 §5.7; D-090, D-097, BR-TAX-11)."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from tests.accounting_utils import CAJA, HONORARIOS, VENTAS, create_year, load_chart, posted
from tests.conftest import auth_header
from tests.finance_utils import ok
from tests.tax_utils import TAX, create_voucher, file_obligation, obligation, setup_tax

SALE = {"direction": "sale", "counterparty_ruc": "80000011", "counterparty_ruc_dv": "0"}


@pytest.fixture
def month(client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Septiembre con una compra (saldo a favor de 30.000) y octubre con de todo."""
    from tests.tax_utils import dv

    SALE["counterparty_ruc_dv"] = dv("80000011")
    setup_tax(client, owner_token, monkeypatch)
    t = owner_token
    made: dict[str, Any] = {}
    made["sep_purchase"] = create_voucher(
        client, t, issued_on="2026-09-10", taxed_10="330000", number="001-001-0000100"
    )
    made["sale"] = create_voucher(
        client,
        t,
        **SALE,
        number="001-001-0000001",
        taxed_10="1100000",
        taxed_5="210000",
        exempt="50000",
    )
    made["sale_note"] = create_voucher(
        client,
        t,
        **SALE,
        voucher_type="credit_note",
        number="001-001-0000002",
        taxed_10="110000",
        related_voucher_id=made["sale"]["id"],
        issued_on="2026-10-20",
    )
    made["purchase"] = create_voucher(
        client, t, number="001-001-0000101", taxed_10="550000", taxed_5="105000"
    )
    made["purchase_note"] = create_voucher(
        client,
        t,
        voucher_type="credit_note",
        number="001-001-0000102",
        taxed_10="11000",
        related_voucher_id=made["purchase"]["id"],
        issued_on="2026-10-25",
    )
    made["no_vat"] = create_voucher(
        client, t, number="001-001-0000103", taxed_10="220000", imputes_vat=False, imputes_ire=True
    )
    return made


def _vat(client: TestClient, token: str, year: int = 2026, month: int = 10) -> dict[str, Any]:
    return dict(ok(client.get(f"{TAX}/vat/{year}/{month}", headers=auth_header(token))))


def _boxes(result: dict[str, Any]) -> dict[str, str | None]:
    return {b["box"]: b["value"] for b in result["form_120"]["boxes"]}


def test_estimate_by_rate_with_notes_and_estimated_previous_balance(
    client: TestClient, owner_token: str, month: dict[str, Any]
) -> None:
    result = _vat(client, owner_token)
    assert result["is_estimate"] is True
    assert result["debit"]["sales"]["rate_10"] == {
        "taxed": "1100000",
        "base": "1000000",
        "vat": "100000",
    }
    assert result["debit"]["sales"]["rate_5"]["vat"] == "10000"
    assert result["debit"]["sales"]["exempt"] == "50000"
    assert result["debit"]["credit_notes"]["vat"] == "10000"
    assert result["debit"]["total"] == "100000"
    assert result["credit"]["purchases"]["vat"] == "55000"
    assert result["credit"]["credit_notes"]["vat"] == "1000"
    assert result["credit"]["total"] == "54000"
    assert result["previous_balance"] == {
        "amount": "30000",
        "source": "estimated",
        "month": "2026-09-01",
        "obligation_id": None,
    }
    assert result["result"] == {"to_pay": "16000", "credit_balance": "0"}
    codes = {w["code"] for w in result["warnings"]}
    assert "PURCHASES_NOT_IMPUTED" in codes
    assert result["rule_status"] == "pending"
    assert {"IVA-GENERAL-TASAS", "IVA-F120-ESTRUCTURA", "IVA-PRORRATEO"} <= {
        r["code"] for r in result["rules_applied"]
    }


def test_declared_previous_balance_wins_over_estimated(
    client: TestClient, owner_token: str, month: dict[str, Any]
) -> None:
    sep = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-09-01")
    file_obligation(
        client, owner_token, sep["id"], declared_amount="0", declared_credit_balance="25000"
    )
    result = _vat(client, owner_token)
    assert result["previous_balance"]["source"] == "declared"
    assert result["previous_balance"]["amount"] == "25000"
    assert result["previous_balance"]["obligation_id"] == sep["id"]
    assert result["result"]["to_pay"] == "21000"
    # Noviembre arrastra desde la declarada de septiembre con lo estimado de octubre.
    november = _vat(client, owner_token, 2026, 11)
    assert november["previous_balance"] == {
        "amount": "0",
        "source": "estimated",
        "month": "2026-10-01",
        "obligation_id": None,
    }


def test_form_120_boxes(client: TestClient, owner_token: str, month: dict[str, Any]) -> None:
    sep = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-09-01")
    file_obligation(client, owner_token, sep["id"], declared_credit_balance="25000")
    result = _vat(client, owner_token)
    form = result["form_120"]
    assert form["available"] is True and form["version"] == 4
    assert form["rule"]["code"] == "IVA-F120-ESTRUCTURA"
    boxes = _boxes(result)
    expected = {
        "10": "1000000",
        "22": "100000",
        "151": "200000",
        "157": "10000",
        "12": "50000",
        "15": "10000",
        "23": "1000",
        "37": "100000",
        "34": "0",
        "42": "10000",
        "35": "500000",
        "32": "100000",
        "38": "55000",
        "43": "65000",
        "21": "10000",
        "24": "101000",
        "44": "111000",
        "45": "65000",
        "46": "25000",
        "48": "21000",
        "50": "21000",
        "55": "21000",
        "160": "1210000",
        "26": "50000",
        "27": "1260000",
    }
    assert {k: boxes[k] for k in expected} == expected
    # Sin calcular, con aviso: exportadores, retenciones, prorrateo y lo de la DJ anterior.
    for box in (
        "14",
        "29",
        "49",
        "152",
        "153",
        "162",
        "163",
        "165",
        "52",
        "164",
        "51",
        "169",
        "58",
    ):
        assert boxes[box] is None, box
    by_box = {b["box"]: b for b in form["boxes"]}
    assert by_box["52"]["doubts"] == [] and "La cargás vos" in by_box["52"]["note"]
    assert by_box["164"]["status"] == "not_calculated" and "BR-TAX-11" in by_box["164"]["note"]
    assert by_box["15"]["doubts"] == [] and by_box["22"]["doubts"] == ["D-F4-7"]
    assert by_box["46"]["status"] == "from_previous"
    # El borrador coincide con la estimación genérica.
    assert boxes["50"] == result["result"]["to_pay"]


def test_vat_is_the_rate_on_the_month_bases_not_the_sum_per_voucher(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-122: casilla 38 = tasa sobre las bases (instructivo del Formulario 120 v4)."""
    setup_tax(client, owner_token, monkeypatch)
    for n in range(3):  # IVA de cada una: 1.005 / 11 = 91,36 → 91; base 914
        create_voucher(client, owner_token, number=f"001-001-000020{n}", taxed_10="1005")
    result = _vat(client, owner_token)
    boxes = _boxes(result)
    assert boxes["35"] == "2742"
    assert boxes["38"] == "274"  # el 10 % de 2.742 = 274,2; la suma por comprobante daría 273
    assert result["credit"]["purchases"]["vat"] == "274"
    assert result["credit"]["total"] == "274"
    assert result["result"]["credit_balance"] == "274"


def test_proration_warning(client: TestClient, owner_token: str, month: dict[str, Any]) -> None:
    result = _vat(client, owner_token)
    assert result["proration_warning"] is True
    assert "PRORATION_POSSIBLE" in {w["code"] for w in result["warnings"]}
    september = _vat(client, owner_token, 2026, 9)  # solo compras: no corresponde avisar
    assert september["proration_warning"] is False


def test_ledger_control_matches_and_then_not(
    client: TestClient, owner_token: str, month: dict[str, Any]
) -> None:
    t = owner_token
    without = _vat(client, t)["ledger_control"]
    assert without["available"] is False
    accounts = load_chart(client, t)
    create_year(client, t)
    for key, account in (
        ("sale", VENTAS),
        ("sale_note", VENTAS),
        ("purchase", HONORARIOS),
        ("purchase_note", HONORARIOS),
        ("no_vat", HONORARIOS),
    ):
        entry = ok(
            client.post(
                f"{TAX}/vouchers/{month[key]['id']}/propose-entry",
                json={
                    "account_id": accounts[account]["id"],
                    "counterpart_account_id": accounts[CAJA]["id"],
                },
                headers=auth_header(t),
            ),
            201,
        )
        ok(client.post(f"/api/v1/accounting/entries/{entry['id']}/post", headers=auth_header(t)))
    control = _vat(client, t)["ledger_control"]
    assert control["available"] is True and control["matches"] is True, control
    posted(client, t, accounts, "2026-10-28", [("1.01.03.05.03.01", 500, 0), (CAJA, 0, 500)])
    control = _vat(client, t)["ledger_control"]
    assert control["matches"] is False
    row = next(r for r in control["accounts"] if r["field"] == "vat_credit_10_account_id")
    assert row["difference"] == "500"
    assert control["message"]


def test_apply_takes_the_estimate_to_the_obligation(
    client: TestClient, owner_token: str, month: dict[str, Any]
) -> None:
    res = client.post(f"{TAX}/vat/2026/10/apply", headers=auth_header(owner_token))
    body = ok(res)
    assert body["calculated_amount"] == "16000"
    assert body["calculated_credit_balance"] == "0"
    file_obligation(client, owner_token, body["id"])
    res = client.post(f"{TAX}/vat/2026/10/apply", headers=auth_header(owner_token))
    assert res.status_code == 409
    res = client.post(f"{TAX}/vat/2030/10/apply", headers=auth_header(owner_token))
    assert res.status_code == 404


def test_xlsx_opens_and_its_totals_match(
    client: TestClient, owner_token: str, month: dict[str, Any]
) -> None:
    result = _vat(client, owner_token)
    res = client.get(
        f"{TAX}/vat/2026/10", params={"format": "xlsx"}, headers=auth_header(owner_token)
    )
    assert res.status_code == 200
    assert "iva-2026-10.xlsx" in res.headers["content-disposition"]
    sheet = load_workbook(io.BytesIO(res.content), read_only=True)["IVA"]
    rows = list(sheet.iter_rows(values_only=True))
    by_label = {r[0]: r for r in rows if r and isinstance(r[0], str)}
    assert by_label["Débito fiscal"][2] == int(result["debit"]["total"])
    assert by_label["Crédito fiscal"][2] == int(result["credit"]["total"])
    assert by_label["Resultado: a ingresar"][2] == int(result["result"]["to_pay"])
    box_50 = next(r for r in rows if len(r) > 1 and r[1] == "50")
    assert box_50[2] == int(_boxes(result)["50"] or 0)
