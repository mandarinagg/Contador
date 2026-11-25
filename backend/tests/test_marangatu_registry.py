"""Registro del bot (BOT_MARANGATU.md §5): solo agregar, cadena de hashes y archivos con SHA-256.

Las pruebas escriben con SQL directo: ni un error de código podría modificar o borrar un paso.
Para la cadena se salta el disparador como superusuario (`session_replication_role`), dentro
de la transacción de la prueba, y la verificación tiene que detectarlo.
"""

import itertools
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.marangatu import service, storage
from app.modules.marangatu.models import Run
from app.modules.marangatu.stop_codes import StopCode
from tests.conftest import auth_header
from tests.finance_utils import ok
from tests.marangatu_utils import MARANGATU, BotEnv, bot_env  # noqa: F401 - fixture


@pytest.fixture
def run(client: TestClient, owner_token: str, db: Session) -> Run:
    org_id = db.scalar(text("SELECT id FROM core.organizations"))
    row = Run(organization_id=org_id, task_type="general", stage="reconocimiento")
    db.add(row)
    db.commit()
    for n in range(3):
        service.add_step(db, row, action=f"paso_{n}", values={"n": n})
    return row


def _rejected(db: Session, sql: str, params: dict[str, Any], name: str) -> None:
    nested = db.begin_nested()
    with pytest.raises(DBAPIError) as caught:
        db.execute(text(sql), params)
    nested.rollback()
    assert caught.value.orig is not None
    assert caught.value.orig.diag.constraint_name == name  # type: ignore[attr-defined]


def test_steps_are_append_only(db: Session, run: Run) -> None:
    _rejected(
        db,
        "UPDATE marangatu.steps SET message = 'cambiado' WHERE run_id = :r",
        {"r": run.id},
        "trg_steps_append_only",
    )
    _rejected(
        db, "DELETE FROM marangatu.steps WHERE run_id = :r", {"r": run.id}, "trg_steps_append_only"
    )
    _rejected(db, "TRUNCATE marangatu.steps CASCADE", {}, "trg_steps_append_only")


def test_runs_are_not_deleted_and_finished_runs_are_fixed(db: Session, run: Run) -> None:
    _rejected(db, "DELETE FROM marangatu.runs WHERE id = :r", {"r": run.id}, "trg_runs_no_delete")
    _rejected(
        db,
        "UPDATE marangatu.runs SET task_type = 'f120' WHERE id = :r",
        {"r": run.id},
        "trg_runs_identity_fixed",
    )
    service.finish_run(db, run, status="detenida", stop_code=StopCode.BOT_OFF, detail="x")
    _rejected(
        db,
        "UPDATE marangatu.runs SET status = 'completada', stop_code = NULL WHERE id = :r",
        {"r": run.id},
        "trg_runs_finished_fixed",
    )


def test_chain_links_each_step_to_the_previous(db: Session, run: Run) -> None:
    rows = db.execute(
        text("SELECT seq, prev_hash, row_hash FROM marangatu.steps ORDER BY seq")
    ).all()
    assert len(rows) >= 3
    for before, after in itertools.pairwise(rows):
        assert after.prev_hash == before.row_hash
    result = service.verify_chain(db)
    assert result.valid and result.first_broken_seq is None


def test_tampering_bypassing_the_trigger_is_detected(db: Session, run: Run) -> None:
    middle = db.scalar(
        text("SELECT seq FROM marangatu.steps WHERE run_id = :r ORDER BY seq OFFSET 1 LIMIT 1"),
        {"r": run.id},
    )
    # Como superusuario y sin disparadores: la base ya no lo impide, la verificación sí lo ve.
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(
        text('UPDATE marangatu.steps SET "values" = \'{"n": 99}\' WHERE seq = :s'), {"s": middle}
    )
    db.execute(text("SET LOCAL session_replication_role = origin"))
    result = service.verify_chain(db)
    assert not result.valid
    assert result.first_broken_seq == middle


def test_deleting_a_step_bypassing_the_trigger_is_detected(db: Session, run: Run) -> None:
    middle = db.scalar(
        text("SELECT seq FROM marangatu.steps WHERE run_id = :r ORDER BY seq OFFSET 1 LIMIT 1"),
        {"r": run.id},
    )
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(text("DELETE FROM marangatu.steps WHERE seq = :s"), {"s": middle})
    db.execute(text("SET LOCAL session_replication_role = origin"))
    result = service.verify_chain(db)
    assert not result.valid
    assert result.first_broken_seq is not None and result.first_broken_seq > middle


def test_modified_or_missing_capture_is_detected(
    client: TestClient,
    owner_token: str,
    db: Session,
    run: Run,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    folder = storage.run_dir(run.id)
    shot = folder / "001-ingreso.png"
    shot.write_bytes(b"captura original")
    gone = folder / "002-otra.png"
    gone.write_bytes(b"otra")
    for path in (shot, gone):
        service.add_step(
            db,
            run,
            action="captura",
            capture_path=storage.relative(path),
            capture_sha256=storage.sha256_file(path),
        )
    assert service.verify_chain(db).valid
    shot.write_bytes(b"captura cambiada")
    gone.unlink()
    result = service.verify_chain(db)
    assert not result.valid and result.first_broken_seq is None
    assert {(p.path.rsplit("/", 1)[-1], p.problem) for p in result.file_problems} == {
        ("001-ingreso.png", "modificado"),
        ("002-otra.png", "falta"),
    }
    # La API tampoco entrega una captura modificada.
    step_id = db.scalar(
        text("SELECT id FROM marangatu.steps WHERE capture_path LIKE '%001-ingreso.png'")
    )
    res = client.get(f"{MARANGATU}/steps/{step_id}/capture", headers=auth_header(owner_token))
    assert res.status_code == 409 and res.json()["error"]["code"] == "CAPTURE_MODIFIED"
    verify = ok(client.get(f"{MARANGATU}/verify", headers=auth_header(owner_token)))
    assert verify["valid"] is False and len(verify["file_problems"]) == 2


def test_capture_outside_the_data_folder_is_refused(bot_env: BotEnv) -> None:  # noqa: F811
    with pytest.raises(ValueError, match="fuera de la carpeta"):
        storage.resolve("../../etc/passwd")
    assert storage.run_dir(uuid.uuid4()).is_relative_to(bot_env.data_dir)
