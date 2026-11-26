"""Bot de Marangatu con varias organizaciones (fase M5, D-140): una sola corrida en toda la
instalación, documentos por organización y el RUC que no cambia con una clave guardada."""

import uuid
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.marangatu import service, storage, supervisor
from app.modules.marangatu.models import Run
from app.modules.marangatu.stop_codes import StopCode
from tests.conftest import OtherOrg, auth_header
from tests.finance_utils import ok
from tests.marangatu_utils import (  # noqa: F401 - fixture
    MARANGATU,
    PASSWORD,
    RUC,
    BotEnv,
    bot_env,
    enable_bot,
)
from tests.tax_utils import dv, set_ruc
from tests.test_finance_migration import migration_db  # noqa: F401 - fixture

RUC_B = "80000013"


def _start(client: TestClient, token: str) -> Any:
    return client.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(token))


# --- Una sola corrida en toda la instalación --------------------------------------------


@pytest.fixture
def two_bots(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    """A y B con el bot encendido, RUC propio y clave guardada."""
    enable_bot(client, owner_token)
    set_ruc(client, other_org.token, RUC_B)
    ok(
        client.put(
            f"{MARANGATU}/settings",
            json={"bot_enabled": True},
            headers=auth_header(other_org.token),
        )
    )
    ok(
        client.put(
            f"{MARANGATU}/credentials",
            json={"password": PASSWORD},
            headers=auth_header(other_org.token),
        )
    )


def test_other_organization_is_refused_while_a_run_is_in_progress(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    two_bots: None,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ok(_start(client, owner_token), 202)
    assert first["status"] == "en_curso"
    monkeypatch.setattr(supervisor, "alive_runs", lambda: {uuid.UUID(first["id"])})

    busy = _start(client, other_org.token)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "BOT_BUSY"
    # No dice de quién es la corrida en curso.
    owner_org = db.scalar(text("SELECT id FROM core.organizations ORDER BY created_at LIMIT 1"))
    for secret in (str(owner_org), "Empresa de Prueba", first["id"]):
        assert secret not in busy.text
    # La propia organización sigue viendo su código de siempre.
    again = _start(client, owner_token)
    assert again.status_code == 409 and again.json()["error"]["code"] == "RUN_IN_PROGRESS"
    # B no dejó ninguna corrida ni se coló en la de A.
    assert ok(client.get(f"{MARANGATU}/runs", headers=auth_header(other_org.token))) == []

    # Al terminar la de A, B puede.
    run = db.get(Run, uuid.UUID(first["id"]))
    assert run is not None
    service.finish_run(db, run, status="completada")
    second = ok(_start(client, other_org.token), 202)
    assert second["status"] == "en_curso"


def test_database_refuses_two_runs_in_progress_in_different_organizations(
    db: Session, owner_token: str, other_org: OtherOrg
) -> None:
    orgs = [r[0] for r in db.execute(text("SELECT id FROM core.organizations ORDER BY created_at"))]
    assert len(orgs) == 2
    db.add(Run(organization_id=orgs[0], task_type="general", stage="reconocimiento"))
    db.flush()
    with pytest.raises(IntegrityError, match="uq_runs_one_running"), db.begin_nested():
        db.add(Run(organization_id=orgs[1], task_type="general", stage="reconocimiento"))
        db.flush()


def test_interrupted_runs_of_any_organization_are_closed_in_their_own_chain(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    two_bots: None,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ok(_start(client, owner_token), 202)
    # La app se cerró con la de A en curso (nadie la atiende): la de B la cierra al lanzar.
    monkeypatch.setattr(supervisor, "alive_runs", set)
    second = ok(_start(client, other_org.token), 202)
    assert second["status"] == "en_curso"
    old = ok(client.get(f"{MARANGATU}/runs/{first['id']}", headers=auth_header(owner_token)))
    assert old["status"] == "detenida" and old["stop_code"] == StopCode.BROWSER_ERROR
    assert old["steps"][-1]["action"] == "interrumpida"
    # El paso quedó en la organización de A, no en la de B.
    orgs = {
        str(r.organization_id)
        for r in db.execute(
            text("SELECT organization_id FROM marangatu.steps WHERE run_id = :r"),
            {"r": first["id"]},
        )
    }
    assert orgs == {str(db.get(Run, uuid.UUID(first["id"])).organization_id)}  # type: ignore[union-attr]
    assert service.verify_chain(db, check_files=False).valid


def test_close_interrupted_is_global_and_respects_live_runs(
    db: Session, owner_token: str, other_org: OtherOrg
) -> None:
    a = db.scalar(text("SELECT id FROM core.organizations ORDER BY created_at LIMIT 1"))
    run_a = Run(organization_id=a, task_type="general", stage="reconocimiento")
    db.add(run_a)
    db.commit()
    assert service.close_interrupted(db, {run_a.id}) == []
    assert db.get(Run, run_a.id).status == "en_curso"  # type: ignore[union-attr]
    assert service.close_interrupted(db, set()) == [run_a.id]
    closed = db.get(Run, run_a.id)
    assert closed is not None and closed.status == "detenida"
    assert closed.stop_code == StopCode.BROWSER_ERROR.value


# --- Documentos por organización -------------------------------------------------------


def test_new_runs_store_documents_under_their_organization(
    db: Session,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    org, run_id = uuid.uuid4(), uuid.uuid4()
    folder = storage.run_dir(org, run_id)
    assert folder == bot_env.data_dir / "documentos" / str(org) / "marangatu" / str(run_id)
    assert folder.is_dir()
    shot = folder / "001.png"
    shot.write_bytes(b"x")
    assert storage.relative(shot) == f"documentos/{org}/marangatu/{run_id}/001.png"
    assert storage.belongs_to(storage.relative(shot), org)
    assert not storage.belongs_to(storage.relative(shot), uuid.uuid4())


def test_legacy_paths_still_resolve_and_verify(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    """Una corrida anterior a la D-140 (`documentos/marangatu/<corrida>/`) sigue valiendo."""
    org_a = db.scalar(text("SELECT id FROM core.organizations ORDER BY created_at LIMIT 1"))
    run = Run(organization_id=org_a, task_type="general", stage="reconocimiento")
    db.add(run)
    db.commit()
    legacy = bot_env.data_dir / "documentos" / "marangatu" / str(run.id)
    legacy.mkdir(parents=True)
    shot = legacy / "001-ingreso.png"
    shot.write_bytes(b"captura vieja")
    step = service.add_step(
        db,
        run,
        action="captura",
        capture_path=storage.relative(shot),
        capture_sha256=storage.sha256_file(shot),
    )
    assert step.capture_path == f"documentos/marangatu/{run.id}/001-ingreso.png"
    res = client.get(f"{MARANGATU}/steps/{step.id}/capture", headers=auth_header(owner_token))
    assert res.status_code == 200 and res.content == b"captura vieja"
    verify = ok(client.get(f"{MARANGATU}/verify", headers=auth_header(owner_token)))
    assert verify["valid"] is True and verify["files_checked"] == 1

    # Y una nueva, en la carpeta de su organización: conviven en la misma verificación.
    new = storage.run_dir(org_a, run.id) / "002.png"
    new.write_bytes(b"captura nueva")
    step2 = service.add_step(
        db,
        run,
        action="captura",
        capture_path=storage.relative(new),
        capture_sha256=storage.sha256_file(new),
    )
    res = client.get(f"{MARANGATU}/steps/{step2.id}/capture", headers=auth_header(owner_token))
    assert res.status_code == 200 and res.content == b"captura nueva"
    verify = ok(client.get(f"{MARANGATU}/verify", headers=auth_header(owner_token)))
    assert verify["valid"] is True and verify["files_checked"] == 2
    # La otra organización no las ve.
    for sid in (step.id, step2.id):
        denied = client.get(
            f"{MARANGATU}/steps/{sid}/capture", headers=auth_header(other_org.token)
        )
        assert denied.status_code == 404


def test_a_step_cannot_point_to_another_organizations_folder(
    client: TestClient,
    owner_token: str,
    other_org: OtherOrg,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    """Aunque un paso de B apuntara (por un error) a la carpeta de A, B no recibe el archivo."""
    org_a = db.scalar(text("SELECT id FROM core.organizations ORDER BY created_at LIMIT 1"))
    run_a = Run(organization_id=org_a, task_type="general", stage="reconocimiento")
    db.add(run_a)
    db.commit()
    secret = storage.run_dir(org_a, run_a.id) / "secreto.png"
    secret.write_bytes(b"de A")
    service.finish_run(db, run_a, status="completada")
    run_b = Run(
        organization_id=other_org.organization_id, task_type="general", stage="reconocimiento"
    )
    db.add(run_b)
    db.commit()
    step = service.add_step(
        db,
        run_b,
        action="captura",
        capture_path=storage.relative(secret),
        capture_sha256=storage.sha256_file(secret),
    )
    res = client.get(f"{MARANGATU}/steps/{step.id}/capture", headers=auth_header(other_org.token))
    assert res.status_code == 404 and b"de A" not in res.content


# --- Cambio de RUC con una clave guardada ----------------------------------------------


def test_ruc_change_is_refused_while_the_password_is_saved(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    headers = auth_header(owner_token)
    enable_bot(client, owner_token)
    new = {"ruc": RUC_B, "ruc_check_digit": dv(RUC_B)}
    res = client.patch("/api/v1/organization", json=new, headers=headers)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "MARANGATU_CREDENTIALS_EXIST"
    assert "borrá la clave de Marangatu" in res.json()["error"]["message"]
    assert ok(client.get("/api/v1/organization", headers=headers))["ruc"] == RUC
    # Otros cambios y el mismo RUC siguen pasando.
    ok(client.patch("/api/v1/organization", json={"trade_name": "Marca"}, headers=headers))
    ok(
        client.patch(
            "/api/v1/organization", json={"ruc": RUC, "ruc_check_digit": dv(RUC)}, headers=headers
        )
    )
    # Sacar el RUC también cambia la clave de lugar: se niega.
    res = client.patch(
        "/api/v1/organization", json={"ruc": None, "ruc_check_digit": None}, headers=headers
    )
    assert res.status_code == 409
    # Borrada la clave, se puede.
    assert client.delete(f"{MARANGATU}/credentials", headers=headers).status_code == 204
    assert ok(client.patch("/api/v1/organization", json=new, headers=headers))["ruc"] == RUC_B


def test_ruc_change_without_a_saved_password_proceeds(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    headers = auth_header(owner_token)
    set_ruc(client, owner_token, RUC)  # primera vez: no había RUC
    res = client.patch(
        "/api/v1/organization", json={"ruc": RUC_B, "ruc_check_digit": dv(RUC_B)}, headers=headers
    )
    assert ok(res)["ruc"] == RUC_B


def test_ruc_change_with_the_credential_store_down_proceeds(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_ruc(client, owner_token, RUC)
    monkeypatch.delenv("CONTADOR_TEST_KEYRING_FILE")
    res = client.patch(
        "/api/v1/organization",
        json={"ruc": RUC_B, "ruc_check_digit": dv(RUC_B)},
        headers=auth_header(owner_token),
    )
    assert ok(res)["ruc"] == RUC_B


# --- Migración 0010 --------------------------------------------------------------------


def _index_def(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(
            conn.scalar(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_runs_one_running'")
            )
        )


def test_migration_0010_one_running_run_installation_wide(
    migration_db: tuple[Config, Engine],  # noqa: F811
) -> None:
    cfg, engine = migration_db
    head = ScriptDirectory.from_config(cfg).get_current_head()
    command.upgrade(cfg, "head")
    command.check(cfg)
    assert "(status)" in _index_def(engine)
    command.downgrade(cfg, "0009")
    assert "(organization_id)" in _index_def(engine)

    # Con la 0009, dos organizaciones pueden tener una corrida en curso cada una.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO core.organizations (legal_name, legal_form) VALUES"
                " ('Uno', 'SA'), ('Dos', 'SA')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO marangatu.runs (organization_id, task_type, stage, started_at)"
                " SELECT id, 'general', 'reconocimiento',"
                " now() - CASE legal_name WHEN 'Uno' THEN interval '2 hours'"
                " ELSE interval '1 hour' END FROM core.organizations"
            )
        )
    command.upgrade(cfg, "head")
    command.check(cfg)
    assert "(status)" in _index_def(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT o.legal_name, r.status, r.stop_code, r.finished_at IS NOT NULL,"
                " (SELECT count(*) FROM marangatu.steps s WHERE s.run_id = r.id"
                "  AND s.organization_id = r.organization_id AND s.action = 'interrumpida')"
                " FROM marangatu.runs r JOIN core.organizations o ON o.id = r.organization_id"
                " ORDER BY o.legal_name"
            )
        ).all()
    # Quedó la más antigua; la otra, cerrada con su paso en la cadena.
    assert [tuple(r) for r in rows] == [
        ("Dos", "detenida", "BROWSER_ERROR", True, 1),
        ("Uno", "en_curso", None, False, 0),
    ]
    # La bajada siempre se puede.
    command.downgrade(cfg, "0009")
    assert "(organization_id)" in _index_def(engine)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert str(conn.scalar(text("SELECT version_num FROM alembic_version"))) == head
