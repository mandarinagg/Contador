"""Calendario de vencimientos (spec fase 4 §5.2; D-086, D-098, BR-TAX-05).

La referencia de cada prueba se calcula aparte, en Python, con las tablas leídas del YAML de
la investigación (no con el código que se prueba).
"""

import os
from datetime import date, timedelta
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tax import rule_params
from app.modules.tax.calendar import BusinessDays, Exceptions
from app.modules.tax.common import add_months, month_end
from app.modules.tax.models import Holiday
from app.modules.tax.obligations import Planned, plan_due
from app.modules.tax.rules import RuleCache
from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import ok
from tests.tax_utils import TAX, load_rules, obligation, setup_tax

YAML_PATH = os.path.join(BACKEND_DIR, "..", "docs", "research", "tax_rules_candidatas.yaml")
CODES = {*rule_params.OBLIGATION_RULES, "CAL-PERPETUO-DJ", "CAL-PERPETUO-DJI"}


def _tables() -> dict[str, dict[str, int]]:
    with open(YAML_PATH, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return {
        r["code"]: r["parameters"]["day_by_digit"]
        for r in data["rules"]
        if r["code"] in ("CAL-PERPETUO-DJ", "CAL-PERPETUO-DJI")
    }


def _reference(day: date, holidays: set[date]) -> date:
    while day.weekday() >= 5 or day in holidays:
        day += timedelta(days=1)
    return day


def _plan(
    db: Session, code: str, period: date, digit: int, holidays: set[date] | None = None
) -> Planned:
    start = period
    end = month_end(period) if code in rule_params.MONTHLY_RULES else date(period.year, 12, 31)
    result = plan_due(
        code=code,
        period_start=start,
        period_end=end,
        digit=digit,
        rules=RuleCache(db, CODES),
        calendar=BusinessDays.from_days(holidays or set()),
        exceptions=Exceptions(db, date(2000, 1, 1), date(2100, 1, 1)),
    )
    assert isinstance(result, Planned)
    return result


def test_all_ruc_digits_for_dj_and_dji(client: TestClient, owner_token: str, db: Session) -> None:
    load_rules(client, owner_token)
    tables = _tables()
    # Febrero de 2027: el 7 cae domingo (DJ, terminación 0), el resto se corre o no según cae.
    for digit in range(10):
        vat = _plan(db, "IVA-GENERAL-LIQUIDACION", date(2027, 1, 1), digit)
        nominal = date(2027, 2, tables["CAL-PERPETUO-DJ"][str(digit)])
        assert vat.nominal_due_date == nominal
        assert vat.due_date == _reference(nominal, set())
        register = _plan(db, "REG-COMPROB-MENSUAL", date(2027, 1, 1), digit)
        nominal = date(2027, 3, tables["CAL-PERPETUO-DJI"][str(digit)])
        assert register.nominal_due_date == nominal
        assert register.due_date == _reference(nominal, set())
    # Los días de la DJ y la DJI son los del YAML (7..25 y 8..26).
    assert [tables["CAL-PERPETUO-DJ"][str(d)] for d in range(10)] == list(range(7, 26, 2))
    assert [tables["CAL-PERPETUO-DJI"][str(d)] for d in range(10)] == list(range(8, 27, 2))


def test_weekend_and_consecutive_non_business_days_shift_forward(
    client: TestClient, owner_token: str, db: Session
) -> None:
    load_rules(client, owner_token)
    # Agosto de 2027: el 7 es sábado. IVA de julio, terminación 0.
    saturday = date(2027, 8, 7)
    assert saturday.weekday() == 5
    plain = _plan(db, "IVA-GENERAL-LIQUIDACION", date(2027, 7, 1), 0)
    assert plain.nominal_due_date == saturday
    assert plain.due_date == date(2027, 8, 9)  # lunes
    # Domingo: febrero de 2027, terminación 0.
    sunday = _plan(db, "IVA-GENERAL-LIQUIDACION", date(2027, 1, 1), 0)
    assert sunday.nominal_due_date.weekday() == 6
    assert sunday.due_date == sunday.nominal_due_date + timedelta(days=1)
    # Feriado en día hábil: el 15 de agosto de 2027 es domingo; usamos el miércoles 11.
    holiday = _plan(db, "IVA-GENERAL-LIQUIDACION", date(2027, 7, 1), 2, {date(2027, 8, 11)})
    assert holiday.nominal_due_date == date(2027, 8, 11)
    assert holiday.due_date == date(2027, 8, 12)
    # Sábado, domingo, y feriados el lunes y el martes: pasa al miércoles.
    chain = _plan(
        db, "IVA-GENERAL-LIQUIDACION", date(2027, 7, 1), 0, {date(2027, 8, 9), date(2027, 8, 10)}
    )
    assert chain.due_date == date(2027, 8, 11)
    # D-098: el aviso usa la fecha fija sin correr.
    assert min(chain.nominal_due_date, chain.due_date) == saturday


def test_rg_60_2026_exception_replaces_only_what_it_names(
    client: TestClient, owner_token: str, db: Session
) -> None:
    load_rules(client, owner_token)
    with open(YAML_PATH, encoding="utf-8") as handle:
        rule = next(
            r for r in yaml.safe_load(handle)["rules"] if r["code"] == "CAL-EXCEPCION-2026-11"
        )
    new_dates = rule["parameters"]["new_date_by_digit"]
    for digit in range(10):
        # IVA de octubre (determinativa, vence en noviembre): la reemplaza.
        vat = _plan(db, "IVA-GENERAL-LIQUIDACION", date(2026, 10, 1), digit)
        assert vat.due_date == date.fromisoformat(new_dates[str(digit)])
        assert vat.exception is not None
        assert vat.exception.exception.legal_reference.startswith("RG DNIT N° 60/2026")
        # Registro de comprobantes (DJI, excluida): no la toca.
        register = _plan(db, "REG-COMPROB-MENSUAL", date(2026, 9, 1), digit)
        assert register.exception is None
        assert register.due_date == _reference(register.nominal_due_date, set())
        # IVA de septiembre (vence en octubre): tampoco.
        october = _plan(db, "IVA-GENERAL-LIQUIDACION", date(2026, 9, 1), digit)
        assert october.exception is None


def test_user_exception_for_some_digits_only(
    client: TestClient, owner_token: str, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch, ruc="80000005")  # terminación 5
    res = client.post(
        f"{TAX}/due-date-exceptions",
        json={
            "obligation_code": "REG-COMPROB-MENSUAL",
            "due_month": "2026-12-01",
            "ruc_digits": [5, 6],
            "new_due_date": "2026-12-28",
            "legal_reference": "RG de prueba",
        },
        headers=auth_header(owner_token),
    )
    ok(res, 201)
    row = obligation(client, owner_token, "REG-COMPROB-MENSUAL", "2026-10-01")
    assert row["due_date"] == "2026-12-28"
    assert row["exception"]["legal_reference"] == "RG de prueba"
    assert row["remind_by"] == "2026-12-18"  # la fija (DJI 5 = 18) es anterior
    assert "excepción" in row["shift_explanation"]
    # Otra terminación no se afecta.
    other = _plan(db, "REG-COMPROB-MENSUAL", date(2026, 10, 1), 7)
    assert other.exception is None
    # Superponer otra excepción activa para la misma terminación: 409.
    res = client.post(
        f"{TAX}/due-date-exceptions",
        json={
            "obligation_code": "REG-COMPROB-MENSUAL",
            "due_month": "2026-12-01",
            "ruc_digits": [6],
            "new_due_date": "2026-12-29",
            "legal_reference": "Otra",
        },
        headers=auth_header(owner_token),
    )
    assert res.status_code == 409


def test_annual_obligations_with_non_december_close(
    client: TestClient, owner_token: str, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(
        client,
        owner_token,
        monkeypatch,
        ruc="80000003",  # terminación 3: DJ 13, DJI 14
        obligations=(("700", "2025-01-01"), ("948", "2025-01-01")),
        valid_from="2025-01-01",
        fiscal_close_month=6,
    )
    ire = ok(
        client.get(
            f"{TAX}/obligations",
            params={"code": "IRE-GENERAL-DJ"},
            headers=auth_header(owner_token),
        )
    )
    # Ejercicios de julio a junio; el IRE vence 4 meses después del cierre (octubre).
    periods = [(r["period_start"], r["period_end"]) for r in ire]
    assert ("2025-07-01", "2026-06-30") in periods
    current = next(r for r in ire if r["period_start"] == "2025-07-01")
    assert current["nominal_due_date"] == "2026-10-13"
    assert current["due_date"] == str(_reference(date(2026, 10, 13), set()))
    eeff = ok(
        client.get(
            f"{TAX}/obligations",
            params={"code": "EEFF-PRESENTACION"},
            headers=auth_header(owner_token),
        )
    )
    assert (
        next(r for r in eeff if r["period_start"] == "2025-07-01")["nominal_due_date"]
        == "2026-10-14"
    )


def test_reference_calendar_for_a_whole_year(
    client: TestClient, owner_token: str, db: Session
) -> None:
    load_rules(client, owner_token)
    ok(client.post(f"{TAX}/holidays/load-candidates", headers=auth_header(owner_token)))
    holidays = set(db.scalars(__import__("sqlalchemy").select(Holiday.day)))
    assert date(2027, 12, 8) in holidays
    tables = _tables()
    calendar = BusinessDays(db, date(2027, 1, 1), date(2028, 3, 31))
    cache = RuleCache(db, CODES)
    exceptions = Exceptions(db, date(2027, 1, 1), date(2028, 3, 1))
    checked = 0
    for month in range(1, 13):
        period = date(2027, month, 1)
        for digit in range(10):
            for code, table, offset in (
                ("IVA-GENERAL-LIQUIDACION", "CAL-PERPETUO-DJ", 1),
                ("REG-COMPROB-MENSUAL", "CAL-PERPETUO-DJI", 2),
            ):
                result: Any = plan_due(
                    code=code,
                    period_start=period,
                    period_end=month_end(period),
                    digit=digit,
                    rules=cache,
                    calendar=calendar,
                    exceptions=exceptions,
                )
                due_month = add_months(period, offset)
                nominal = due_month.replace(day=tables[table][str(digit)])
                assert result.nominal_due_date == nominal
                assert result.due_date == _reference(nominal, holidays), (code, period, digit)
                checked += 1
    assert checked == 240
