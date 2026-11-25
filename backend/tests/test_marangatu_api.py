"""API del bot de Marangatu: interruptor, clave, corridas y permisos (BOT_MARANGATU.md §2 y §7).

Sin navegador: el lanzamiento del trabajador queda anotado en `bot_env.launched`.
"""

import json
import logging
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.marangatu import service, supervisor
from app.modules.marangatu.models import Run
from tests.conftest import auth_header
from tests.finance_utils import ok
from tests.marangatu_utils import (
    MARANGATU,
    PASSWORD,
    RUC,
    BotEnv,
    bot_env,  # noqa: F401 - fixture
    enable_bot,
)
from tests.tax_utils import set_ruc

ANY = str(uuid.uuid4())


def _start(client: TestClient, token: str) -> dict[str, Any]:
    run: dict[str, Any] = ok(
        client.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(token)), 202
    )
    return run


def _audit(db: Session, action: str) -> list[Any]:
    return list(
        db.execute(
            text("SELECT before, after FROM audit.audit_logs WHERE action = :a ORDER BY seq"),
            {"a": action},
        )
    )


def test_bot_starts_off_with_every_task_in_reconnaissance(
    client: TestClient, owner_token: str
) -> None:
    settings = ok(client.get(f"{MARANGATU}/settings", headers=auth_header(owner_token)))
    assert settings["bot_enabled"] is False
    assert settings["stages"] == {
        "consulta": "reconocimiento",
        "registro_comprobantes": "reconocimiento",
        "f120": "reconocimiento",
        "constancias": "reconocimiento",
        "ire": "reconocimiento",
    }
    assert settings["catalog_provisional"] is True


def test_switch_is_audited(client: TestClient, owner_token: str, db: Session) -> None:
    for value in (True, True, False):
        res = client.put(
            f"{MARANGATU}/settings", json={"bot_enabled": value}, headers=auth_header(owner_token)
        )
        assert ok(res)["bot_enabled"] is value
    rows = _audit(db, "marangatu.settings.updated")
    assert [(r.before, r.after) for r in rows] == [
        ({"bot_enabled": False}, {"bot_enabled": True}),
        ({"bot_enabled": True}, {"bot_enabled": False}),
    ]


def test_bot_off_stops_before_opening_the_browser(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    enable_bot(client, owner_token)
    ok(
        client.put(
            f"{MARANGATU}/settings", json={"bot_enabled": False}, headers=auth_header(owner_token)
        )
    )
    run = _start(client, owner_token)
    assert run["status"] == "detenida" and run["stop_code"] == "BOT_OFF"
    assert "apagado" in run["stop_text"]
    assert bot_env.launched == []
    detail = ok(client.get(f"{MARANGATU}/runs/{run['id']}", headers=auth_header(owner_token)))
    assert [(s["action"], s["result"]) for s in detail["steps"]] == [("preparar", "detenido")]


def test_no_credentials_stops_before_opening_the_browser(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    enable_bot(client, owner_token, password=None)
    run = _start(client, owner_token)
    assert run["status"] == "detenida" and run["stop_code"] == "NO_CREDENTIALS"
    assert bot_env.launched == []


def test_without_ruc_there_is_nothing_to_log_in_with(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    ok(
        client.put(
            f"{MARANGATU}/settings", json={"bot_enabled": True}, headers=auth_header(owner_token)
        )
    )
    res = client.put(
        f"{MARANGATU}/credentials", json={"password": PASSWORD}, headers=auth_header(owner_token)
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "ORGANIZATION_WITHOUT_RUC"
    assert PASSWORD not in res.text
    run = _start(client, owner_token)
    assert run["stop_code"] == "DATA_INCOMPLETE"


def test_credentials_are_saved_deleted_and_never_returned(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    set_ruc(client, owner_token, RUC)
    url = f"{MARANGATU}/credentials"
    headers = auth_header(owner_token)
    assert ok(client.get(url, headers=headers)) == {
        "ruc": RUC,
        "has_password": False,
        "store_available": True,
    }
    saved = client.put(url, json={"password": PASSWORD}, headers=headers)
    assert ok(saved) == {"ruc": RUC, "has_password": True, "store_available": True}
    assert PASSWORD not in saved.text
    # Quedó en el almacén de credenciales, con la entrada de la spec.
    stored = json.loads(bot_env.keyring_file.read_text("utf-8"))
    assert stored == {f"ContadorAI/Marangatu/{RUC}|{RUC}": PASSWORD}
    # Un error de validación tampoco la repite.
    bad = client.put(url, json={"password": PASSWORD, "extra": PASSWORD}, headers=headers)
    assert bad.status_code == 422 and PASSWORD not in bad.text
    assert ok(client.get(url, headers=headers))["has_password"] is True
    assert client.delete(url, headers=headers).status_code == 204
    assert ok(client.get(url, headers=headers))["has_password"] is False
    missing = client.delete(url, headers=headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NO_CREDENTIALS"
    # La auditoría solo dice «guardada» o «borrada».
    assert [r.after for r in _audit(db, "marangatu.credentials.saved")] == [
        {"detalle": "clave de Marangatu guardada"}
    ]
    assert [r.after for r in _audit(db, "marangatu.credentials.deleted")] == [
        {"detalle": "clave de Marangatu borrada"}
    ]
    dump = db.scalar(text("SELECT string_agg(t::text, chr(10)) FROM audit.audit_logs t"))
    assert PASSWORD not in (dump or "")
    assert PASSWORD not in caplog.text


def test_store_unavailable_is_reported_without_details(
    client: TestClient,
    owner_token: str,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_ruc(client, owner_token, RUC)
    monkeypatch.delenv("CONTADOR_TEST_KEYRING_FILE")
    status = ok(client.get(f"{MARANGATU}/credentials", headers=auth_header(owner_token)))
    assert status == {"ruc": RUC, "has_password": False, "store_available": False}
    res = client.put(
        f"{MARANGATU}/credentials", json={"password": PASSWORD}, headers=auth_header(owner_token)
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "CREDENTIAL_STORE_UNAVAILABLE"


def test_one_run_at_a_time_and_interrupted_runs_are_closed(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_bot(client, owner_token)
    first = _start(client, owner_token)
    assert first["status"] == "en_curso"
    assert bot_env.launched == [uuid.UUID(first["id"])]
    # Mientras el supervisor la atiende, no se lanza otra.
    monkeypatch.setattr(supervisor, "alive_runs", lambda: {uuid.UUID(first["id"])})
    busy = client.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(owner_token))
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "RUN_IN_PROGRESS"
    # Si la app se cerró en el medio (nadie la atiende), queda detenida y se puede seguir.
    monkeypatch.setattr(supervisor, "alive_runs", set)
    second = _start(client, owner_token)
    assert second["status"] == "en_curso"
    old = ok(client.get(f"{MARANGATU}/runs/{first['id']}", headers=auth_header(owner_token)))
    assert old["status"] == "detenida" and old["stop_code"] == "BROWSER_ERROR"
    assert old["steps"][-1]["action"] == "interrumpida"
    runs = ok(client.get(f"{MARANGATU}/runs", headers=auth_header(owner_token)))
    assert [r["id"] for r in runs] == [second["id"], first["id"]]
    assert service.verify_chain(db, check_files=False).valid


def test_runs_of_another_organization_are_not_found(
    client: TestClient, owner_token: str, db: Session
) -> None:
    res = client.get(f"{MARANGATU}/runs/{ANY}", headers=auth_header(owner_token))
    assert res.status_code == 404
    other = db.scalar(
        text(
            "INSERT INTO core.organizations (legal_name, legal_form) VALUES ('Otra', 'SA')"
            " RETURNING id"
        )
    )
    run = Run(organization_id=other, task_type="general", stage="reconocimiento")
    db.add(run)
    db.commit()
    res = client.get(f"{MARANGATU}/runs/{run.id}", headers=auth_header(owner_token))
    assert res.status_code == 404


WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("put", "/settings", {"bot_enabled": True}),
    ("put", "/credentials", {"password": PASSWORD}),
    ("delete", "/credentials", None),
    ("post", "/runs/reconnaissance", None),
]
READS = ["/settings", "/credentials", "/runs", "/verify"]


def _call(
    client: TestClient, token: str, method: str, path: str, body: dict[str, Any] | None
) -> Any:
    kwargs: dict[str, Any] = {"headers": auth_header(token)}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(f"{MARANGATU}{path}", **kwargs)


def test_viewer_only_reads(
    client: TestClient,
    owner_token: str,
    make_user: Any,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    set_ruc(client, owner_token, RUC)
    _, viewer = make_user("viewer")
    for path in READS:
        assert client.get(f"{MARANGATU}{path}", headers=auth_header(viewer)).status_code == 200
    for method, path, body in [*WRITES, ("put", "/settings", {"bot_enabled": False})]:
        res = _call(client, viewer, method, path, body)
        assert res.status_code == 403, (method, path, res.text)


def test_admin_turns_off_but_does_not_turn_on_or_use_the_password(
    client: TestClient,
    owner_token: str,
    make_user: Any,
    bot_env: BotEnv,  # noqa: F811
) -> None:
    """Como en tributación (D-094): entrar a Marangatu con la clave pide `tax.verify`."""
    enable_bot(client, owner_token)
    _, admin = make_user("admin")
    for method, path, body in WRITES:
        res = _call(client, admin, method, path, body)
        assert res.status_code == 403, (method, path, res.text)
    off = client.put(
        f"{MARANGATU}/settings", json={"bot_enabled": False}, headers=auth_header(admin)
    )
    assert ok(off)["bot_enabled"] is False
    # El contador (`tax.verify`) sí puede.
    _, accountant = make_user("accountant")
    on = client.put(
        f"{MARANGATU}/settings", json={"bot_enabled": True}, headers=auth_header(accountant)
    )
    assert ok(on)["bot_enabled"] is True
    assert _start(client, accountant)["status"] == "en_curso"
