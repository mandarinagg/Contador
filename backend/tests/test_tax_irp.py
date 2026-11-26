"""Borrador del IRP-RSP y del Formulario 515, y la condición 3 sin contabilidad (fase M8, D-144).

Los importes esperados salen del instructivo del Formulario 515 v1 (ejemplos 1 y 2 del Rubro 5)
y de sumar a mano los comprobantes de cada prueba, no del código que se prueba.
"""

import io
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.modules.tax import irp, rule_params
from app.modules.tax.candidate_rules import RULES
from app.modules.tax.models import Voucher
from tests.conftest import STRONG_PASSWORD, auth_header
from tests.finance_utils import ok
from tests.register_utils import (
    card_body,
    create,
    income_body,
    ips_body,
    payslip_body,
    post_voucher,
    setup_person,
)
from tests.tax_utils import TAX, create_voucher, org_id, put_profile, rules_by_code, setup_tax

M = 1_000_000


@pytest.fixture
def person(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    return setup_person(client, monkeypatch)


def _params() -> rule_params.IrpServicesParams:
    row = next(r for r in RULES if r["code"] == irp.IRP_RULE)
    params = rule_params.parse(irp.IRP_RULE, row["parameters"])
    assert isinstance(params, rule_params.IrpServicesParams)
    return params


def _irp(client: TestClient, token: str, year: int = 2026) -> dict[str, Any]:
    return dict(ok(client.get(f"{TAX}/irp/{year}", headers=auth_header(token))))


def _boxes(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {b["box"]: b for b in result["form_515"]["boxes"]}


def _values(result: dict[str, Any]) -> dict[str, str | None]:
    return {k: b["value"] for k, b in _boxes(result).items()}


def _codes(result: dict[str, Any]) -> set[str]:
    return {w["code"] for w in result["warnings"]}


# --- Escala del art. 69 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("net", "expected"),
    [
        (0, (0, 0, 0)),
        (50 * M, (4 * M, 0, 0)),
        # Un guaraní más ya es del segundo tramo: 0,09 se redondea a 0.
        (50 * M + 1, (4 * M, 0, 0)),
        # 9 % de 50 = 4,5 → 5 (la mitad hacia arriba); de 6 = 0,54 → 1.
        (50 * M + 50, (4 * M, 5, 0)),
        (50 * M + 6, (4 * M, 1, 0)),
        (60 * M, (4 * M, 900_000, 0)),  # ejemplo 2 del instructivo
        (150 * M, (4 * M, 9 * M, 0)),
        (150 * M + 5, (4 * M, 9 * M, 1)),  # 10 % de 5 = 0,5 → 1
        (210 * M, (4 * M, 9 * M, 6 * M)),  # ejemplo 1 del instructivo
    ],
)
def test_brackets(net: int, expected: tuple[int, int, int]) -> None:
    taxes = irp.bracket_taxes(Decimal(net), _params())
    assert tuple(int(t) for t in taxes) == expected


def test_amount_of_each_voucher() -> None:
    def voucher(**fields: Any) -> Voucher:
        base: dict[str, Any] = {
            "taxed_10": Decimal(0),
            "taxed_5": Decimal(0),
            "exempt": Decimal(0),
            "vat_10": Decimal(0),
            "vat_5": Decimal(0),
            "condition": "cash",
            "imputes_vat": False,
            "voucher_type": "invoice",
        }
        return Voucher(**{**base, **fields})

    # Venta: sin IVA (instructivo del 515); la nota de crédito emitida resta.
    sale = voucher(direction="sale", taxed_10=Decimal(110_000), vat_10=Decimal(10_000))
    assert irp._voucher_amounts(sale) == (100_000, 0, 0)
    note = voucher(
        direction="sale",
        voucher_type="credit_note",
        taxed_10=Decimal(11_000),
        vat_10=Decimal(1_000),
    )
    assert irp._voucher_amounts(note) == (-10_000, 0, 0)
    # Compra: con el IVA si no es crédito fiscal, sin el IVA si lo es (art. 68).
    purchase = voucher(direction="purchase", taxed_10=Decimal(110_000), vat_10=Decimal(10_000))
    assert irp._voucher_amounts(purchase) == (0, 0, 110_000)
    purchase.imputes_vat = True
    assert irp._voucher_amounts(purchase) == (0, 0, 100_000)
    # A crédito no entra: entran sus cobros (203) y pagos (201).
    assert irp._voucher_amounts(voucher(direction="purchase", condition="credit")) is None
    income = voucher(direction="income", taxed_10=Decimal(300), exempt=Decimal(50))
    assert irp._voucher_amounts(income) == (300, 50, 0)


# --- Borrador del año ----------------------------------------------------------------------


def test_zero_year_is_filed_anyway(client: TestClient, person: str) -> None:
    result = _irp(client, person)
    assert result["is_estimate"] is True
    assert result["rule_status"] == "pending"
    assert {r["code"] for r in result["rules_applied"]} == {"IRP-RSP-DJ", "REG-COMPROB-ANUAL"}
    assert {"RULE_PENDING", "BELOW_THRESHOLD"} <= _codes(result)
    values = _values(result)
    for box in ("10", "12", "14", "22", "24", "25", "26", "27", "29", "45", "46", "47", "48"):
        assert values[box] == "0", box
    assert result["threshold"] == {"amount": "80000000", "reached": False}
    boxes = _boxes(result)
    assert boxes["46"]["label"] == "Impuesto al 8 % (renta neta hasta ₲ 50.000.000)"
    assert boxes["48"]["label"] == "Impuesto al 10 % (renta neta desde ₲ 150.000.001)"
    assert any("hasta el 5 % de la renta bruta" in w for w in result["form_515"]["warnings"])
    assert result["result"] == {"net_income": "0", "tax": "0", "to_pay": "0"}
    assert result["register_control"]["matches"] is True
    assert result["register_control"]["method"] == "voucher_register"
    assert result["register_control"]["stop_code"] is None
    # La obligación del año está en el calendario.
    assert result["obligation"] is not None and result["obligation"]["status"] == "pending"


def test_missing_personal_data_stays_empty(client: TestClient, person: str) -> None:
    boxes = _boxes(_irp(client, person))
    # D-PF-16 (familiares, autovehículo, vivienda, préstamos) y D-PF-5 (retenciones).
    for box in ("11", "13", "15", "16", "17", "18", "19", "20", "21", "23", "30", "41"):
        assert boxes[box]["value"] is None, box
        assert boxes[box]["status"] == "missing_data", box
        assert boxes[box]["note"].startswith("No calculado: falta el dato."), box
    assert "D-PF-16" in boxes["18"]["doubts"] and "D-PF-16" in boxes["23"]["doubts"]
    assert "D-PF-5" in boxes["41"]["doubts"]
    # Lo que depende de esas casillas o de la DJ anterior tampoco se calcula.
    for box in ("28", "31", "32", "33-39", "40", "42", "43", "44", "49", "50", "51"):
        assert boxes[box]["value"] is None and boxes[box]["status"] == "not_calculated", box
    assert boxes["12"]["origin"] == "income" and boxes["22"]["origin"] == "expense"
    assert boxes["45"]["origin"] is None


def test_below_threshold_with_records(client: TestClient, person: str) -> None:
    create(client, person, income_body())  # 300.000 gravado y 50.000 exonerado
    create(client, person, payslip_body())  # 5.000.000
    create(client, person, ips_body())  # egreso 450.000
    create(client, person, card_body())  # egreso 800.000
    # Factura de compra con IVA: sin crédito fiscal, el egreso va con el IVA.
    create_voucher(client, person, imputes_vat=False, imputes_irp=True)  # 110.000
    # No entran: a crédito, sin imputar al IRP y anulado.
    create_voucher(client, person, number="001-001-0000002", condition="credit", imputes_irp=True)
    create_voucher(client, person, number="001-001-0000003", imputes_irp=False)
    voided = create(client, person, income_body(number="R-99", taxed_10="999"))
    ok(
        client.post(
            f"{TAX}/vouchers/{voided['id']}/void",
            json={"reason": "Prueba"},
            headers=auth_header(person),
        )
    )
    # Otro año no entra.
    create(client, person, income_body(number="R-2025", issued_on="2025-12-31"))
    result = _irp(client, person)
    values = _values(result)
    assert (values["10"], values["12"], values["14"]) == ("50000", "5300000", "5300000")
    assert values["22"] == values["24"] == values["26"] == "1360000"
    assert values["27"] == values["29"] == values["45"] == "3940000"
    assert (values["46"], values["47"], values["48"]) == ("315200", "0", "0")
    assert result["threshold"]["reached"] is False
    assert result["result"] == {"net_income": "3940000", "tax": "315200", "to_pay": "0"}
    assert "BELOW_THRESHOLD" in _codes(result) and "CREDIT_VOUCHERS_EXCLUDED" in _codes(result)
    assert result["register"]["credit_excluded"] == 1
    assert (result["register"]["income_count"], result["register"]["expense_count"]) == (2, 3)
    control = result["register_control"]
    assert control["matches"] is True and control["vouchers"] == 5
    assert {r["box"] for r in control["rows"]} == {"10", "12", "14", "22"}


@pytest.mark.parametrize(
    ("income", "reached", "to_pay"),
    [
        (80 * M, False, "0"),
        (80 * M + 1, True, str(4 * M + 2_700_000)),  # 4 M + 9 % de 30.000.001 = 2.700.000,09
        (210 * M, True, str(19 * M)),
    ],
)
def test_threshold_edges(
    client: TestClient, person: str, income: int, reached: bool, to_pay: str
) -> None:
    create(client, person, income_body(taxed_10=str(income), exempt="0"))
    result = _irp(client, person)
    assert result["threshold"]["reached"] is reached
    assert result["result"]["to_pay"] == to_pay
    assert ("BELOW_THRESHOLD" in _codes(result)) is not reached
    if income == 210 * M:
        values = _values(result)
        assert (values["46"], values["47"], values["48"]) == ("4000000", "9000000", "6000000")


def test_expenses_above_income(client: TestClient, person: str) -> None:
    create(client, person, income_body(taxed_10="1000000", exempt="0"))
    create(client, person, card_body(taxed_10="3000000"))
    result = _irp(client, person)
    values = _values(result)
    assert values["22"] == "3000000"
    assert values["26"] == "1000000"  # limitada a la 25
    assert values["27"] == values["45"] == values["46"] == "0"
    assert any("superan a los ingresos" in w for w in result["form_515"]["warnings"])


def test_first_year_warning(
    client: TestClient, person: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    put_profile(
        client,
        person,
        valid_from="2026-01-01",
        ire_regime="none",
        vat_taxpayer=False,
        obligations=(("715", "2026-03-01"), ("956", "2026-03-01")),
    )
    result = _irp(client, person)
    assert "FIRST_YEAR" in _codes(result)
    assert result["registered_on"] == "2026-03-01"


def test_without_the_rule_only_the_register(client: TestClient, person: str) -> None:
    create(client, person, income_body())
    rule = rules_by_code(client, person)["IRP-RSP-DJ"]
    ok(
        client.post(
            f"{TAX}/rules/{rule['id']}/deprecate",
            json={"reason": "Prueba"},
            headers=auth_header(person),
        )
    )
    result = _irp(client, person)
    assert result["form_515"]["available"] is False
    assert "IRP-RSP-DJ" in result["form_515"]["message"]
    assert result["result"] is None and result["threshold"] is None
    assert result["register"]["income_taxed"] == "300000"
    assert result["register_control"]["matches"] is True


def test_xlsx_opens_and_its_totals_match(client: TestClient, person: str) -> None:
    create(client, person, income_body(taxed_10=str(210 * M), exempt="0"))
    result = _irp(client, person)
    res = client.get(f"{TAX}/irp/2026", params={"format": "xlsx"}, headers=auth_header(person))
    assert res.status_code == 200
    assert "irp-2026.xlsx" in res.headers["content-disposition"]
    sheet = load_workbook(io.BytesIO(res.content), read_only=True)["IRP"]
    rows = list(sheet.iter_rows(values_only=True))
    by_label = {r[0]: r for r in rows if r and isinstance(r[0], str)}
    assert by_label["A pagar (estimado)"][2] == int(result["result"]["to_pay"])
    box_45 = next(r for r in rows if len(r) > 1 and r[1] == "45")
    assert box_45[2] == int(_values(result)["45"] or 0)


# --- Condición 3 de la D-119 sin contabilidad ----------------------------------------------


def test_register_control_to_the_guarani(client: TestClient, db: Session, person: str) -> None:
    create(client, person, income_body())
    create(client, person, card_body())
    values = {k: Decimal(v) for k, v in _values(_irp(client, person)).items() if v is not None}
    organization = org_id(db)
    ok_control = irp.register_control(db, organization, 2026, values)
    assert ok_control.matches is True and ok_control.stop_code is None
    # ₲ 1 de diferencia en una casilla ya no cuadra.
    off = irp.register_control(db, organization, 2026, {**values, "22": values["22"] + 1})
    assert off.matches is False
    assert off.stop_code == "LEDGER_MISMATCH"
    row = next(r for r in off.out()["rows"] if r["box"] == "22")
    assert (row["draft"], row["register"], row["difference"]) == ("800001", "800000", "1")
    assert off.out()["message"]
    # Una casilla sin valor tampoco.
    missing = irp.register_control(db, organization, 2026, {**values, "12": None})
    assert missing.matches is False


def test_condition_3_with_accounting_is_not_available(
    client: TestClient, db: Session, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)  # EAS con IRE General: lleva contabilidad
    cuadre = irp.condition_3(db, org_id(db), 2026, {})
    assert cuadre.method == "ledger" and cuadre.available is False
    assert cuadre.matches is None and cuadre.stop_code == "LEDGER_MISMATCH"


# --- Permisos y alcance --------------------------------------------------------------------


def test_permissions_and_scope(
    client: TestClient, person: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get(f"{TAX}/irp/2026").status_code == 401
    res = client.post(
        "/api/v1/users",
        json={
            "email": "lectora@example.com",
            "full_name": "Lectora",
            "password": STRONG_PASSWORD,
            "role": "viewer",
        },
        headers=auth_header(person),
    )
    ok(res, 201)
    login = client.post(
        "/api/v1/auth/login", json={"email": "lectora@example.com", "password": STRONG_PASSWORD}
    )
    viewer = str(ok(login)["token"])
    assert client.get(f"{TAX}/irp/2026", headers=auth_header(viewer)).status_code == 200
    res = client.get(f"{TAX}/irp/2026?format=xlsx", headers=auth_header(viewer))
    assert res.status_code == 200
    # Fuera del perfil: 2024 no tiene perfil vigente; un año imposible no existe.
    res = client.get(f"{TAX}/irp/2024", headers=auth_header(person))
    assert res.status_code == 422 and res.json()["error"]["code"] == "IRP_NOT_APPLICABLE"
    assert client.get(f"{TAX}/irp/1999", headers=auth_header(person)).status_code == 404


def test_not_applicable_without_715(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    res = client.get(f"{TAX}/irp/2026", headers=auth_header(owner_token))
    assert res.status_code == 422 and res.json()["error"]["code"] == "IRP_NOT_APPLICABLE"
    res = post_voucher(client, owner_token, income_body())
    assert res.status_code == 422  # tampoco tiene el registro anual
