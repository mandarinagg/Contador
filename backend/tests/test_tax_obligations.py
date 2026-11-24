"""Obligaciones y calendario (spec fase 4 §5.3 y §5.4; D-083, D-087, D-098, BR-TAX-04/06)."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_db
from app.main import create_app
from tests.conftest import BACKEND_DIR, SETUP_BODY, auth_header
from tests.finance_utils import audit_entries, business_context, create_account, create_tx, ok
from tests.tax_utils import (
    TAX,
    file_obligation,
    fix_today,
    load_rules,
    obligation,
    put_profile,
    rejected,
    set_ruc,
    setup_tax,
)


def _all(client: TestClient, token: str, **params: Any) -> list[dict[str, Any]]:
    return list(ok(client.get(f"{TAX}/obligations", params=params, headers=auth_header(token))))


def test_no_profile_no_obligations(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch, profile=False)
    result = ok(client.post(f"{TAX}/obligations/sync", headers=auth_header(owner_token)))
    assert result["profile_missing"] is True
    assert result["created"] == 0
    assert _all(client, owner_token) == []


def test_sync_is_idempotent_and_covers_until_three_months_ahead(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch, ruc="80000005")
    rows = _all(client, owner_token)
    vat = [r for r in rows if r["code"] == "IVA-GENERAL-LIQUIDACION"]
    # Desde el alta (enero de 2026) hasta 3 meses después de hoy (24/11/2026): febrero 2027.
    assert vat[0]["period_start"] == "2026-01-01"
    assert vat[-1]["period_start"] == "2027-02-01"
    assert len(vat) == 14
    assert all(r["dnit_code"] == "211" for r in vat)
    assert all(r["rule_status"] == "pending" for r in rows)
    assert {a["code"] for a in vat[0]["rules_applied"]} == {
        "IVA-GENERAL-LIQUIDACION",
        "CAL-PERPETUO-DJ",
    }
    again = ok(client.post(f"{TAX}/obligations/sync", headers=auth_header(owner_token)))
    assert again["created"] == 0
    assert len(_all(client, owner_token)) == len(rows)
    # Lo que no calcula esta fase se informa, no se inventa.
    put_profile(
        client,
        owner_token,
        obligations=(("211", "2026-01-01"), ("955", "2026-01-01"), ("715", "2026-01-01")),
    )
    result = ok(client.post(f"{TAX}/obligations/sync", headers=auth_header(owner_token)))
    assert result["unsupported_codes"] == ["715"]


def test_overdue_is_derived(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    overdue = _all(client, owner_token, status="overdue")
    assert overdue and all(r["status"] == "pending" and r["is_overdue"] for r in overdue)
    assert all(r["due_date"] < "2026-11-24" for r in overdue)
    first = overdue[0]
    file_obligation(client, owner_token, first["id"])
    assert first["id"] not in {r["id"] for r in _all(client, owner_token, status="overdue")}


def test_profile_change_recalculates_only_what_was_not_filed(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    setup_tax(client, owner_token, monkeypatch, ruc="80000005")  # terminación 5
    filed = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-08-01")
    file_obligation(client, owner_token, filed["id"], declared_amount="150000")
    pending = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-12-01")
    assert pending["nominal_due_date"] == "2027-01-17"
    # Cambia el RUC (terminación 1): lo pendiente se recalcula al sincronizar; lo presentado no.
    set_ruc(client, owner_token, "80000011")
    ok(client.post(f"{TAX}/obligations/sync", headers=auth_header(owner_token)))
    assert (
        obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-12-01")["nominal_due_date"]
        == "2027-01-09"
    )
    after = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-08-01")
    assert after["nominal_due_date"] == filed["nominal_due_date"]
    assert after["due_date"] == filed["due_date"]
    # La base tampoco deja cambiar el vencimiento de una presentada.
    rejected(
        db,
        "UPDATE tax.obligations SET due_date = due_date + 1 WHERE id = :id",
        {"id": filed["id"]},
        "trg_obligations_filed_fixed",
    )


def test_obligation_removed_from_profile_becomes_not_applicable_and_returns(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    filed = obligation(client, owner_token, "REG-COMPROB-MENSUAL", "2026-01-01")
    file_obligation(client, owner_token, filed["id"])
    # Versión nueva desde julio sin el 955.
    put_profile(client, owner_token, valid_from="2026-07-01", obligations=(("211", "2026-01-01"),))
    rows = _all(client, owner_token, code="REG-COMPROB-MENSUAL")
    by_period = {r["period_start"]: r for r in rows}
    assert by_period["2026-01-01"]["status"] == "filed"  # presentada: no cambia
    assert by_period["2026-06-01"]["status"] == "pending"  # el perfil de junio lo tiene
    assert by_period["2026-07-01"]["status"] == "not_applicable"
    assert by_period["2026-07-01"]["not_applicable_auto"] is True
    assert "perfil" in by_period["2026-07-01"]["not_applicable_reason"]
    assert len(rows) == len(by_period)  # nada se borró
    # Si el perfil lo vuelve a incluir, la obligación vuelve a pendiente (D-098).
    put_profile(
        client,
        owner_token,
        valid_from="2026-07-01",
        obligations=(("211", "2026-01-01"), ("955", "2026-01-01")),
    )
    again = obligation(client, owner_token, "REG-COMPROB-MENSUAL", "2026-07-01")
    assert again["status"] == "pending"
    assert again["not_applicable_auto"] is False


def test_transitions_by_api_and_by_sql(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    row = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-03-01")
    oid = row["id"]
    headers = auth_header(owner_token)
    # pending → paid no.
    res = client.post(
        f"{TAX}/obligations/{oid}/pay",
        json={"paid_on": "2026-04-20", "paid_amount": "100"},
        headers=headers,
    )
    assert res.status_code == 409
    rejected(
        db,
        "UPDATE tax.obligations SET status = 'paid', paid_on = '2026-04-20', paid_amount = 1,"
        " filed_on = '2026-04-20', filing_reference = 'x' WHERE id = :id",
        {"id": oid},
        "trg_obligations_invalid_transition",
    )
    filed = file_obligation(client, owner_token, oid, declared_amount="250000")
    assert filed["status"] == "filed" and filed["declared_amount"] == "250000"
    rejected(
        db,
        "UPDATE tax.obligations SET filing_reference = 'otro' WHERE id = :id",
        {"id": oid},
        "trg_obligations_filed_fixed",
    )
    rejected(
        db,
        "UPDATE tax.obligations SET period_start = '2026-02-01' WHERE id = :id",
        {"id": oid},
        "trg_obligations_identity_fixed",
    )
    paid = ok(
        client.post(
            f"{TAX}/obligations/{oid}/pay",
            json={"paid_on": "2026-04-20", "paid_amount": "250000"},
            headers=headers,
        )
    )
    assert paid["status"] == "paid"
    # paid es final (no se reabre desde pagada).
    assert (
        client.post(
            f"{TAX}/obligations/{oid}/reopen", json={"reason": "error"}, headers=headers
        ).status_code
        == 409
    )
    rejected(
        db,
        "UPDATE tax.obligations SET status = 'pending', filed_on = NULL, filing_reference = NULL,"
        " declared_amount = NULL, paid_on = NULL, paid_amount = NULL WHERE id = :id",
        {"id": oid},
        "trg_obligations_invalid_transition",
    )
    rejected(
        db, "DELETE FROM tax.obligations WHERE id = :id", {"id": oid}, "trg_obligations_no_delete"
    )
    rejected(
        db,
        "INSERT INTO tax.obligations (organization_id, code, dnit_code, period_start, period_end,"
        " nominal_due_date, due_date, rule_version_id, calendar_rule_version_id, status,"
        " filed_on, filing_reference)"
        " SELECT organization_id, code, dnit_code, '2030-01-01', '2030-01-31', nominal_due_date,"
        " due_date, rule_version_id, calendar_rule_version_id, 'filed', '2030-02-01', 'x'"
        " FROM tax.obligations WHERE id = :id",
        {"id": oid},
        "trg_obligations_born_pending",
    )
    # filed → pending (reabrir con motivo) y not_applicable manual.
    other = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-04-01")
    file_obligation(client, owner_token, other["id"])
    assert (
        client.post(
            f"{TAX}/obligations/{other['id']}/reopen", json={"reason": "x"}, headers=headers
        ).status_code
        == 422
    )
    reopened = ok(
        client.post(
            f"{TAX}/obligations/{other['id']}/reopen",
            json={"reason": "Rectificativa"},
            headers=headers,
        )
    )
    assert reopened["status"] == "pending" and reopened["reopen_reason"] == "Rectificativa"
    third = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-05-01")
    na = ok(
        client.post(
            f"{TAX}/obligations/{third['id']}/not-applicable",
            json={"reason": "Sin actividad, consultado"},
            headers=headers,
        )
    )
    assert na["status"] == "not_applicable" and na["not_applicable_auto"] is False
    # Uno manual no vuelve solo a pendiente: ni por la API ni por SQL.
    rejected(
        db,
        "UPDATE tax.obligations SET status = 'pending', not_applicable_reason = NULL"
        " WHERE id = :id",
        {"id": third["id"]},
        "trg_obligations_invalid_transition",
    )
    actions = {e["action"] for e in audit_entries(client, owner_token, "tax.obligation")}
    assert {"tax.obligation.filed", "tax.obligation.paid", "tax.obligation.reopened"} <= actions


def test_pay_links_only_business_outflows(
    client: TestClient, owner_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_tax(client, owner_token, monkeypatch)
    row = obligation(client, owner_token, "IVA-GENERAL-LIQUIDACION", "2026-03-01")
    file_obligation(client, owner_token, row["id"])
    headers = auth_header(owner_token)
    personal = ok(client.post("/api/v1/finance/contexts/personal", headers=headers), 201)["id"]
    personal_account = create_account(client, owner_token, personal, "Personal")
    personal_tx = create_tx(client, owner_token, personal, personal_account["id"], "-100")
    res = client.post(
        f"{TAX}/obligations/{row['id']}/pay",
        json={"paid_on": "2026-04-20", "paid_amount": "100", "transaction_id": personal_tx["id"]},
        headers=headers,
    )
    assert res.status_code == 404
    cid = business_context(client, owner_token)
    account = create_account(client, owner_token, cid)
    tx = create_tx(client, owner_token, cid, account["id"], "-100", description="Pago IVA")
    paid = ok(
        client.post(
            f"{TAX}/obligations/{row['id']}/pay",
            json={"paid_on": "2026-04-20", "paid_amount": "100", "transaction_id": tx["id"]},
            headers=headers,
        )
    )
    assert paid["payment_transaction_id"] == tx["id"]


# --- Concurrencia con conexiones reales ------------------------------------------------

PARALLEL = 6


@pytest.fixture(scope="module")
def own_engine() -> Iterator[Engine]:
    base = make_url(get_settings().test_database_url)
    name = f"{base.database}_tax_conc"
    url = base.set(database=name)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config(f"{BACKEND_DIR}/alembic.ini")
    cfg.set_main_option("script_location", f"{BACKEND_DIR}/migrations")
    cfg.attributes["url"] = url.render_as_string(hide_password=False)
    engine = create_engine(url, pool_size=PARALLEL + 4)
    try:
        command.upgrade(cfg, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _app_client(engine: Engine) -> TestClient:
    app = create_app()
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db() -> Iterator[Session]:
        session = sessions()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def test_concurrent_syncs_do_not_duplicate(
    own_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _app_client(own_engine)
    fix_today(monkeypatch)
    token = ok(client.post("/api/v1/system/setup", json=SETUP_BODY), 201)["token"]
    set_ruc(client, token, "80000005")
    load_rules(client, token)
    put_profile(client, token)
    with own_engine.begin() as conn:
        before = conn.scalar(text("SELECT count(*) FROM tax.obligations"))
    # La primera sincronización ya ocurrió al cargar el perfil: agregamos el 948 (EEFF) por
    # SQL, sin sincronizar, para que haya obligaciones nuevas, y las pedimos en paralelo.
    with own_engine.begin() as conn:
        org = conn.scalar(text("SELECT id FROM core.organizations"))
        profile_id = conn.scalar(text("SELECT id FROM tax.profiles"))
        conn.execute(
            text(
                "INSERT INTO tax.profile_obligations (organization_id, profile_id, code,"
                " registered_on) VALUES (:org, :p, '948', '2020-01-01')"
            ),
            {"org": org, "p": profile_id},
        )
    barrier = Barrier(PARALLEL)

    def run(_: int) -> Any:
        barrier.wait()
        return client.post(f"{TAX}/obligations/sync", headers=auth_header(token)).json()

    with ThreadPoolExecutor(PARALLEL) as pool:
        results = list(pool.map(run, range(PARALLEL)))
    created = [r["created"] for r in results]
    assert sum(created) == max(created) > 0, results
    with own_engine.begin() as conn:
        dupes = conn.scalar(
            text(
                "SELECT count(*) FROM (SELECT 1 FROM tax.obligations GROUP BY organization_id,"
                " code, period_start HAVING count(*) > 1) d"
            )
        )
        after = conn.scalar(text("SELECT count(*) FROM tax.obligations"))
    assert dupes == 0
    assert after == before + max(created)
