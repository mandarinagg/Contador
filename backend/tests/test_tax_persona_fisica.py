"""Perfil y calendario de la persona física (fase M6, D-142).

Regímenes `resimple` y `none`, obligaciones 715 (IRP-RSP), 716 (IRP-RGC), 956 (registro anual)
y 702 (RESIMPLE). Las fechas de referencia se calculan aparte, con las tablas del YAML de la
investigación, no con el código que se prueba.
"""

import os
from datetime import date, timedelta
from typing import Any

import pytest
import yaml
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.organizations.ruc import ruc_check_digit
from app.modules.tax import rule_params
from app.modules.tax.calendar import BusinessDays, Exceptions
from app.modules.tax.obligations import Planned, plan_due
from app.modules.tax.rules import RuleCache
from tests.conftest import BACKEND_DIR, SETUP_BODY, auth_header
from tests.finance_utils import ok
from tests.tax_utils import TAX, fix_today, load_rules, put_profile, set_ruc
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture

YAML_PATH = os.path.join(BACKEND_DIR, "..", "docs", "research", "tax_rules_candidatas.yaml")
CODES = {*rule_params.OBLIGATION_RULES, "CAL-PERPETUO-DJ", "CAL-PERPETUO-DJI"}
PF = {"legal_form": "PERSONA_FISICA", "first_names": "María José", "last_names": "Benítez Duarte"}
CEDULA = "1234567"  # terminación 7


def _days() -> dict[str, dict[str, int]]:
    with open(YAML_PATH, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return {
        r["code"]: r["parameters"]["day_by_digit"]
        for r in data["rules"]
        if r["code"] in ("CAL-PERPETUO-DJ", "CAL-PERPETUO-DJI")
    }


def _next_business(day: date, holidays: set[date] | None = None) -> date:
    while day.weekday() >= 5 or day in (holidays or set()):
        day += timedelta(days=1)
    return day


def _plan(db: Session, code: str, year: int, digit: int, holidays: set[date] | None = None) -> Any:
    return plan_due(
        code=code,
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        digit=digit,
        rules=RuleCache(db, CODES),
        calendar=BusinessDays.from_days(holidays or set()),
        exceptions=Exceptions(db, date(2000, 1, 1), date(2100, 1, 1)),
    )


@pytest.fixture
def person_token(client: TestClient) -> str:
    res = client.post("/api/v1/system/setup", json={**SETUP_BODY, "organization": PF})
    assert res.status_code == 201, res.text
    return str(res.json()["token"])


def _person_with_rules(client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fix_today(monkeypatch)
    set_ruc(client, token, CEDULA)
    load_rules(client, token)


def test_new_rules_load_and_are_supported(client: TestClient, owner_token: str) -> None:
    result = load_rules(client, owner_token)
    rejected = {r["code"] for r in result["rejected"]}
    assert not rejected & {"IRP-RSP-DJ", "IRP-RGC-DJ", "REG-COMPROB-ANUAL", "IRE-RESIMPLE-DJ"}
    assert {"715", "716", "956", "702"} <= set(rule_params.RULE_BY_DNIT_CODE)


def test_irp_and_registers_for_every_ruc_digit(
    client: TestClient, owner_token: str, db: Session
) -> None:
    load_rules(client, owner_token)
    days = _days()
    for digit in range(10):
        # IRP: tercer mes después del cierre (marzo), día de la DJ (RG 38/2020, art. 2°).
        for code in ("IRP-RSP-DJ", "IRP-RGC-DJ"):
            plan = _plan(db, code, 2026, digit)
            assert isinstance(plan, Planned)
            nominal = date(2027, 3, days["CAL-PERPETUO-DJ"][str(digit)])
            assert plan.nominal_due_date == nominal
            assert plan.due_date == _next_business(nominal)
            assert plan.calendar_rule.code == "CAL-PERPETUO-DJ"
        # 956: segundo mes (febrero), día de la DJI (RG 90/2021, art. 7°).
        register = _plan(db, "REG-COMPROB-ANUAL", 2026, digit)
        assert isinstance(register, Planned)
        nominal = date(2027, 2, days["CAL-PERPETUO-DJI"][str(digit)])
        assert register.nominal_due_date == nominal
        assert register.due_date == _next_business(nominal)
        # 702: 26 de febrero para todas las terminaciones (RG 61/2020, art. 12).
        resimple = _plan(db, "IRE-RESIMPLE-DJ", 2026, digit)
        assert isinstance(resimple, Planned)
        assert resimple.nominal_due_date == resimple.due_date == date(2027, 2, 26)
        assert resimple.calendar_rule.id == resimple.rule.id
    # El 716 v2 rige desde el ejercicio 2022: antes no hay regla.
    assert _plan(db, "IRP-RGC-DJ", 2021, 0) is None


def test_resimple_fixed_day_shifts_like_any_due_date(
    client: TestClient, owner_token: str, db: Session
) -> None:
    load_rules(client, owner_token)
    # 26 de febrero de 2028: sábado → lunes 28 (D-086; que la norma lo corra es D-PF-8).
    saturday = date(2028, 2, 26)
    assert saturday.weekday() == 5
    plan = _plan(db, "IRE-RESIMPLE-DJ", 2027, 3)
    assert plan.nominal_due_date == saturday
    assert plan.due_date == date(2028, 2, 28)
    holiday = _plan(db, "IRE-RESIMPLE-DJ", 2026, 3, {date(2027, 2, 26)})
    assert holiday.due_date == date(2027, 3, 1)


def test_person_calendar_with_irp_rsp_and_annual_register(
    client: TestClient, person_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _person_with_rules(client, person_token, monkeypatch)
    put_profile(
        client,
        person_token,
        ire_regime="none",
        vat_taxpayer=False,
        obligations=(("715", "2025-03-01"), ("956", "2025-03-01")),
    )
    rows = ok(client.post(f"{TAX}/obligations/sync", headers=auth_header(person_token)))
    assert rows["unsupported_codes"] == []
    listed = ok(client.get(f"{TAX}/obligations", headers=auth_header(person_token)))
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in listed:
        by_code.setdefault(row["code"], []).append(row)
    assert set(by_code) == {"IRP-RSP-DJ", "REG-COMPROB-ANUAL"}
    days = _days()
    irp = {r["period_start"]: r for r in by_code["IRP-RSP-DJ"]}
    # El perfil rige desde el 01-01-2026: el ejercicio 2025 no tiene perfil vigente al cierre.
    assert set(irp) == {"2026-01-01", "2027-01-01"}
    nominal = date(2027, 3, days["CAL-PERPETUO-DJ"]["7"])
    assert irp["2026-01-01"]["nominal_due_date"] == nominal.isoformat()
    assert irp["2026-01-01"]["due_date"] == _next_business(nominal).isoformat()
    assert irp["2026-01-01"]["dnit_code"] == "715"
    assert irp["2026-01-01"]["rule_status"] == "pending"
    assert {a["code"] for a in irp["2026-01-01"]["rules_applied"]} == {
        "IRP-RSP-DJ",
        "CAL-PERPETUO-DJ",
    }
    register = {r["period_start"]: r for r in by_code["REG-COMPROB-ANUAL"]}
    nominal = date(2027, 2, days["CAL-PERPETUO-DJI"]["7"])
    assert register["2026-01-01"]["nominal_due_date"] == nominal.isoformat()


def test_person_calendar_with_resimple(
    client: TestClient, person_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _person_with_rules(client, person_token, monkeypatch)
    put_profile(
        client,
        person_token,
        ire_regime="resimple",
        vat_taxpayer=False,
        obligations=(("702", "2026-01-01"),),
    )
    listed = ok(client.get(f"{TAX}/obligations", headers=auth_header(person_token)))
    resimple = {r["period_start"]: r for r in listed if r["code"] == "IRE-RESIMPLE-DJ"}
    assert resimple["2026-01-01"]["due_date"] == "2027-02-26"
    assert resimple["2026-01-01"]["dnit_code"] == "702"
    # La regla hace de regla del calendario: figura una sola vez.
    assert [a["code"] for a in resimple["2026-01-01"]["rules_applied"]] == ["IRE-RESIMPLE-DJ"]


@pytest.mark.parametrize(
    "fields",
    [
        {"ire_regime": "none", "vat_taxpayer": False, "obligations": (("715", "2026-01-01"),)},
        {
            "ire_regime": "none",
            "vat_taxpayer": True,
            "obligations": (("211", "2026-01-01"), ("955", "2026-01-01"), ("715", "2026-01-01")),
        },
        {
            "ire_regime": "resimple",
            "vat_taxpayer": False,
            "obligations": (("702", "2026-01-01"), ("715", "2026-01-01"), ("956", "2026-01-01")),
        },
        {"ire_regime": "unknown", "vat_taxpayer": False, "obligations": (("716", "2026-01-01"),)},
        {"ire_regime": "ire_simple", "vat_taxpayer": True, "obligations": (("701", "2026-01-01"),)},
    ],
)
def test_consistent_person_profiles(
    client: TestClient,
    person_token: str,
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
) -> None:
    _person_with_rules(client, person_token, monkeypatch)
    put_profile(client, person_token, **fields)


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        (
            {"fiscal_close_month": 6, "obligations": (("715", "2026-01-01"),)},
            "art. 52",
        ),
        (
            {"fiscal_close_month": 6, "obligations": (("716", "2026-01-01"),)},
            "diciembre",
        ),
        ({"ire_regime": "none", "obligations": (("702", "2026-01-01"),)}, "702"),
        ({"ire_regime": "ire_general", "obligations": (("702", "2026-01-01"),)}, "702"),
        (
            {"ire_regime": "resimple", "obligations": (("211", "2026-01-01"),)},
            "art. 27, último párrafo",
        ),
        (
            {"obligations": (("211", "2026-01-01"), ("715", "2026-01-01"), ("956", "2026-01-01"))},
            "955",
        ),
        ({"vat_taxpayer": False, "obligations": (("956", "2026-01-01"),)}, "715"),
        (
            {
                "ire_regime": "resimple",
                "obligations": (("700", "2026-01-01"), ("702", "2026-01-01")),
            },
            "más de un régimen",
        ),
        ({"ire_regime": "none", "obligations": (("700", "2026-01-01"),)}, "sin IRE"),
        ({"ire_regime": "resimple", "obligations": (("701", "2026-01-01"),)}, "RESIMPLE"),
    ],
)
def test_inconsistent_person_profiles(
    client: TestClient,
    person_token: str,
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
    problem: str,
) -> None:
    _person_with_rules(client, person_token, monkeypatch)
    body = put_profile(client, person_token, expect=422, **fields)
    assert body["error"]["code"] == "PROFILE_INCONSISTENT"
    assert problem in body["error"]["message"]


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"obligations": (("715", "2026-01-01"),)}, "solo la tiene una persona física"),
        ({"obligations": (("716", "2026-01-01"),)}, "716"),
        (
            {
                "ire_regime": "resimple",
                "vat_taxpayer": False,
                "obligations": (("702", "2026-01-01"),),
            },
            "art. 27",
        ),
        ({"ire_regime": "none", "obligations": ()}, "art. 2°"),
    ],
)
def test_company_cannot_have_person_obligations(
    client: TestClient,
    owner_token: str,
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
    problem: str,
) -> None:
    fix_today(monkeypatch)
    set_ruc(client, owner_token, "80000005")
    load_rules(client, owner_token)
    body = put_profile(client, owner_token, expect=422, **fields)
    assert body["error"]["code"] == "PROFILE_INCONSISTENT"
    assert problem in body["error"]["message"]


def _exec(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def test_migration_0012(migration_db: tuple[Config, Engine]) -> None:  # noqa: F811
    cfg, engine = migration_db
    head = ScriptDirectory.from_config(cfg).get_current_head()
    command.upgrade(cfg, "head")
    command.check(cfg)
    command.downgrade(cfg, "0011")
    _exec(engine, "INSERT INTO core.users (email, full_name, password_hash) VALUES ('a', 'A', 'x')")
    _exec(
        engine,
        "INSERT INTO core.organizations (legal_name, legal_form, ruc, ruc_check_digit)"
        " VALUES ('Empresa', 'EAS', '80000005', :dv)",
        {"dv": str(ruc_check_digit("80000005"))},
    )
    # Antes de la 0012 la base no acepta los regímenes nuevos.
    with pytest.raises(Exception, match="ire_regime_valid"):
        _exec(
            engine,
            "INSERT INTO tax.profiles (organization_id, valid_from, ire_regime, vat_taxpayer,"
            " created_by) SELECT o.id, '2026-01-01', 'resimple', false, u.id"
            " FROM core.organizations o, core.users u",
        )
    command.upgrade(cfg, "head")
    for regime, day in (("resimple", "2026-01-01"), ("none", "2026-02-01")):
        _exec(
            engine,
            "INSERT INTO tax.profiles (organization_id, valid_from, ire_regime, vat_taxpayer,"
            " created_by) SELECT o.id, CAST(:day AS date), :regime, false, u.id"
            " FROM core.organizations o, core.users u",
            {"day": day, "regime": regime},
        )
    with pytest.raises(RuntimeError, match=r"2 versión\(es\) del perfil fiscal"):
        command.downgrade(cfg, "0011")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == head
    _exec(engine, "UPDATE tax.profiles SET ire_regime = 'unknown'")
    command.downgrade(cfg, "0011")
    command.upgrade(cfg, "head")
    command.check(cfg)
