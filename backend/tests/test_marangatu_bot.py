"""Bot de Marangatu contra el portal simulado (BOT_MARANGATU.md §9). Nunca el portal real.

El trabajador corre como en la app: otro proceso, con un Chromium sin ventana. Cada prueba
comprueba también lo que el bot **no** hizo: presentar, reintentar el ingreso, cambiar la
clave, descargar o enviar un formulario.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.marangatu import catalog, pantallas, recon, service, supervisor
from app.modules.marangatu.protocol import EndEvent, Job, StepEvent
from app.modules.marangatu.recon import denied
from tests.conftest import auth_header
from tests.finance_utils import ok
from tests.marangatu_fake import LOGIN_POSTS, FakePortal
from tests.marangatu_utils import (
    MARANGATU,
    PASSWORD,
    RUC,
    BotEnv,
    actions,
    bot_env,  # noqa: F401 - fixture
    enable_bot,
    start_and_supervise,
)

NOT_DONE = (
    "/eset/presentar",
    "/eset/configuracion/cambiar-clave",
    "/eset/descargas/constancia.pdf",
    "/eset/descargas/estado",
    "/eset/olvide",
)
HOME_URLS = [
    "/eset/",
    "/eset/datosBasicosContribuyente.do",
    "/eset/recibirDDJJContribuyente.do",
    "/eset/mantenerAbmXsl.do",
    "/eset/buzon/marandu",
    "/eset/consultas/obligaciones",
    "/eset/consultas/novedades",
]


def _nothing_submitted(portal: FakePortal) -> None:
    for path in NOT_DONE:
        assert portal.state.count(path) == 0, path
    assert portal.state.received_forms == []
    assert all(method == "GET" or path in LOGIN_POSTS for method, path in portal.state.hits)


def test_reconnaissance_happy_path(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_bot(client, owner_token)
    with FakePortal(password=PASSWORD, user=RUC) as portal:
        detail = start_and_supervise(client, owner_token, db, portal.login_url, monkeypatch)
    assert detail["status"] == "completada", detail
    assert detail["stop_code"] is None
    steps = detail["steps"]
    names = actions(detail)
    # La captura del ingreso va ANTES de escribir la clave.
    assert names[:4] == ["abrir_ingreso", "llenar", "llenar", "clic"]
    assert steps[0]["screen_id"] == "login" and steps[0]["capture_path"]
    assert steps[1]["values"] == {"campo": "#usuario", "dato": "usuario", "valor": RUC}
    assert steps[2]["values"] == {"campo": "#clave", "dato": "clave", "valor": "[oculta]"}
    assert steps[4]["screen_id"] == "inicio"
    visited = [s for s in steps if s["action"] == "reconocer_pagina"]
    urls = [s["values"]["url"].removeprefix(portal.base_url) for s in visited]
    # Los enlaces que arma JavaScript (obligaciones, novedades) se siguen: se espera al menú.
    assert urls == HOME_URLS
    assert [s["screen_id"] for s in visited] == [
        "inicio",
        "informacion_contribuyente",
        "presentar_declaracion",
        "cuenta_corriente",
        "marandu",
        None,
        None,
    ]
    # La estructura no lleva los valores de los campos (el período precargado no aparece).
    form = visited[5]["values"]["estructura"]
    assert {"tipo": "text", "id": "periodo", "nombre": "periodo", "etiqueta": "Período"} in form[
        "campos"
    ]
    assert "11/2026" not in json.dumps(form)
    assert {b["texto"] for b in form["botones"]} == {"Presentar", "Buscar"}
    # Sale de Marangatu al final, y nada se presentó ni se envió.
    assert names[-2:] == ["salir", "reconocer"] and steps[-1]["screen_id"] == "sesion_cerrada"
    assert portal.state.logged_out
    assert portal.state.login_attempts == 1
    # El enlace de salir se usa una sola vez y al final: el recorrido nunca lo visita.
    assert portal.state.count("/eset/logout") == 1
    after = portal.state.hits[portal.state.hits.index(("GET", "/eset/logout")) + 1 :]
    assert all(path in ("/favicon.ico", "/eset/login") for _, path in after)
    _nothing_submitted(portal)
    # Borrador del catálogo para revisar a mano, con su SHA-256 en el registro.
    draft_step = next(s for s in steps if s["action"] == "borrador_catalogo")
    draft = yaml.safe_load((bot_env.data_dir / draft_step["capture_path"]).read_text("utf-8"))
    assert draft["meta"]["provisorio"] is True and draft["meta"]["corrida"] == detail["id"]
    assert [
        urlsplit(p["reconoce"]["url"].removeprefix("^https?://[^/]+")).path.split("(")[0]
        for p in draft["pantallas"]
    ] == [re.escape(u) for u in HOME_URLS]
    assert draft["pantallas"][0]["id"] == "inicio" and draft["pantallas"][0]["version"] == 3
    assert "#periodo" in draft["pantallas"][5]["reconoce"]["campos"]
    # Sin datos personales: se reconoce por URL, título y campos; nunca por textos ni encabezados.
    assert all("textos" not in p["reconoce"] for p in draft["pantallas"])
    draft_text = (bot_env.data_dir / draft_step["capture_path"]).read_text("utf-8")
    assert "9999999" not in draft_text and "example.com" not in draft_text
    assert "INFORMACIÓN DEL CONTRIBUYENTE" not in draft_text
    # Cada captura existe, con su hash; la cadena y los archivos verifican.
    for step in steps:
        if step["capture_path"]:
            assert (bot_env.data_dir / step["capture_path"]).is_file()
    verify = ok(client.get(f"{MARANGATU}/verify", headers=auth_header(owner_token)))
    assert verify["valid"] and verify["files_checked"] >= 6
    shot = client.get(
        f"{MARANGATU}/steps/{steps[0]['id']}/capture", headers=auth_header(owner_token)
    )
    assert shot.status_code == 200 and shot.headers["content-type"] == "image/png"


def test_password_never_leaks(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prueba obligatoria (spec §2): la clave exacta no está en la base, los registros ni los
    archivos de captura, después de una corrida completa."""
    caplog.set_level(logging.DEBUG)
    enable_bot(client, owner_token)
    with FakePortal(password=PASSWORD, user=RUC) as portal:
        detail = start_and_supervise(client, owner_token, db, portal.login_url, monkeypatch)
    assert detail["status"] == "completada", detail
    assert portal.state.login_attempts == 1  # la clave llegó al portal, y a nada más
    # La API no la devuelve.
    status = client.get(f"{MARANGATU}/credentials", headers=auth_header(owner_token))
    assert status.json() == {"ruc": RUC, "has_password": True, "store_available": True}
    assert PASSWORD not in json.dumps(detail)
    # También escapada como en un JSON con `ensure_ascii` (\u00d1…).
    escaped = json.dumps(PASSWORD)[1:-1]
    assert escaped != PASSWORD
    # Base: todas las tablas de todos los esquemas de la app, fila por fila.
    tables = db.execute(
        text(
            "SELECT table_schema, table_name FROM information_schema.tables"
            " WHERE table_schema IN ('core', 'audit', 'finance', 'accounting', 'tax', 'marangatu')"
            " AND table_type = 'BASE TABLE'"
        )
    ).all()
    assert len(tables) > 30
    for schema, table in tables:
        query = f'SELECT string_agg(t::text, chr(10)) FROM "{schema}"."{table}" t'  # noqa: S608
        dump = db.scalar(text(query))
        assert PASSWORD not in (dump or "") and escaped not in (dump or ""), f"{schema}.{table}"
    # Registros: el de esta prueba y el del trabajador.
    assert PASSWORD not in caplog.text and escaped not in caplog.text
    logs = list((bot_env.data_dir / "logs").glob("*.log"))
    assert logs
    # Archivos: capturas, borrador y registros, en bytes (UTF-8, UTF-16 y escapada).
    needles = [PASSWORD.encode("utf-8"), PASSWORD.encode("utf-16-le"), escaped.encode()]
    files = [p for p in bot_env.data_dir.rglob("*") if p.is_file()]
    assert len(files) >= 7
    for path in files:
        content = path.read_bytes()
        assert not any(n in content for n in needles), path


@pytest.mark.parametrize(
    ("mode", "password", "code", "attempts"),
    [
        ("normal", "otra-clave", "LOGIN_FAILED", 1),
        ("captcha", PASSWORD, "CAPTCHA", 0),
        ("login_cambiado", PASSWORD, "UNKNOWN_SCREEN", 0),
    ],
)
def test_login_stops_without_retrying(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    password: str,
    code: str,
    attempts: int,
) -> None:
    """Un solo intento: ante ingreso fallido, captcha o pantalla desconocida, se detiene."""
    enable_bot(client, owner_token, password=password)
    with FakePortal(password=PASSWORD, user=RUC, mode=mode) as portal:
        detail = start_and_supervise(client, owner_token, db, portal.login_url, monkeypatch)
    assert detail["status"] == "detenida" and detail["stop_code"] == code, detail
    assert detail["stop_text"]
    assert portal.state.login_attempts == attempts
    assert portal.state.count("/eset/") == 0
    _nothing_submitted(portal)
    first = detail["steps"][0]
    assert first["action"] == "abrir_ingreso" and first["capture_path"]
    if code != "LOGIN_FAILED":
        # Ni siquiera escribió la clave.
        assert "llenar" not in [
            s["action"] for s in detail["steps"] if s["values"].get("dato") == "clave"
        ]
    assert detail["steps"][-1]["action"] == "detener"


def test_unknown_home_is_taken_as_provisional_and_crawled(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-145: un inicio desconocido, sin campo de clave, sirve para reconocer (y se sale)."""
    enable_bot(client, owner_token)
    with FakePortal(password=PASSWORD, user=RUC, mode="inicio_cambiado") as portal:
        detail = start_and_supervise(client, owner_token, db, portal.login_url, monkeypatch)
    assert detail["status"] == "completada", detail
    steps = detail["steps"]
    names = actions(detail)
    assert "inicio_provisorio" in names
    provisional = next(s for s in steps if s["action"] == "inicio_provisorio")
    assert "inicio provisorio" in provisional["message"]
    assert provisional["values"]["url"].endswith("/eset/")
    assert not [s for s in steps if s["result"] == "detenido"], "no se anota como detenido"
    assert names.index("clic") < names.index("inicio_provisorio") < names.index("reconocer_pagina")
    draft_step = next(s for s in steps if s["action"] == "borrador_catalogo")
    draft = yaml.safe_load((bot_env.data_dir / draft_step["capture_path"]).read_text("utf-8"))
    assert [p["reconoce"]["url"] for p in draft["pantallas"]] == [recon.url_regex("/eset/")]
    assert draft["pantallas"][0]["id"] == "pantalla_001"
    assert portal.state.logged_out, "sale de Marangatu"
    assert portal.state.login_attempts == 1
    _nothing_submitted(portal)


def test_failed_login_with_unknown_message_stops_without_provisional_home(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si sigue el campo de clave, es un ingreso fallido: un solo intento y se detiene."""
    enable_bot(client, owner_token, password="otra-clave")
    with FakePortal(password=PASSWORD, user=RUC, mode="login_fallido_desconocido") as portal:
        detail = start_and_supervise(client, owner_token, db, portal.login_url, monkeypatch)
    assert detail["status"] == "detenida" and detail["stop_code"] == "UNKNOWN_SCREEN", detail
    assert portal.state.login_attempts == 1
    assert "inicio_provisorio" not in actions(detail)
    assert portal.state.count("/eset/") == 0
    assert detail["steps"][-1]["action"] == "detener"
    _nothing_submitted(portal)


def test_logout_without_known_link_does_not_hang(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_bot(client, owner_token)
    started = time.monotonic()
    with FakePortal(password=PASSWORD, user=RUC, mode="inicio_sin_salir") as portal:
        detail = start_and_supervise(client, owner_token, db, portal.login_url, monkeypatch)
    assert time.monotonic() - started < 60
    assert detail["status"] == "completada", detail
    logout = next(s for s in detail["steps"] if s["action"] == "salir")
    assert logout["result"] == "ok" and "cerrar el navegador" in logout["message"]
    assert logout["values"] == {"campo": "a[href$='/eset/logout']"}
    assert portal.state.count("/eset/logout") == 0
    assert not portal.state.logged_out
    assert detail["steps"][-1]["action"] == "salir"


@pytest.mark.parametrize("stage", ["reconocimiento", "ensayo", "habilitada"])
def test_final_click_is_never_executed(
    bot_env: BotEnv,  # noqa: F811
    stage: str,
) -> None:
    """Un catálogo cuyo clic de ingreso fuera `final`: el bot no lo hace en ninguna etapa."""
    raw = [json.loads(json.dumps(s)) for s in pantallas.PANTALLAS]
    raw[0]["acciones"][2]["clic"]["final"] = True
    final_catalog = catalog.build(pantallas.META, raw)
    events: list[StepEvent | EndEvent] = []
    folder = bot_env.data_dir / "final"
    folder.mkdir(parents=True)
    from app.modules.marangatu import credentials

    credentials.save(RUC, PASSWORD)
    with FakePortal(password=PASSWORD, user=RUC) as portal:
        job = Job(
            run_id=uuid.uuid4(),
            kind="reconocimiento",
            stage=stage,
            ruc=RUC,
            login_url=portal.login_url,
            capture_dir=str(folder),
            headless=True,
            channel=None,
            max_pages=5,
            timeout_seconds=60,
        )
        recon.run(job, events.append, final_catalog)
    end = events[-1]
    assert isinstance(end, EndEvent)
    assert end.status == "detenida" and end.stop_code == "NOT_ENABLED"
    assert portal.state.login_attempts == 0
    assert not [s for s in events if isinstance(s, StepEvent) and s.action == "clic"]


def _recon_job(folder: Path, portal: FakePortal) -> Job:
    folder.mkdir(parents=True)
    return Job(
        run_id=uuid.uuid4(),
        kind="reconocimiento",
        stage="reconocimiento",
        ruc=RUC,
        login_url=portal.login_url,
        capture_dir=str(folder),
        headless=True,
        channel=None,
        max_pages=20,
        timeout_seconds=90,
    )


def test_without_waiting_the_crawl_misses_links_loaded_by_javascript(
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin la espera, el recorrido lee el menú «Recuperando opciones…» y no sigue lo que arma JS:
    es lo que pasó en el primer reconocimiento real (D-146)."""
    from app.modules.marangatu import browser, credentials

    credentials.save(RUC, PASSWORD)
    monkeypatch.setattr(browser, "wait_for_content", lambda *a, **k: None)
    events: list[StepEvent | EndEvent] = []
    with FakePortal(password=PASSWORD, user=RUC) as portal:
        recon.run(_recon_job(bot_env.data_dir / "sin-espera", portal), events.append)
    assert isinstance(events[-1], EndEvent) and events[-1].status == "completada"
    assert portal.state.count("/eset/consultas/obligaciones") == 0
    assert portal.state.count("/eset/buzon/marandu") == 1  # los enlaces ya presentes sí


def test_waiting_is_bounded_when_the_loading_text_never_goes_away(
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un texto de «cargando» que no se va no cuelga la corrida: se lee lo que haya."""
    from app.modules.marangatu import credentials

    credentials.save(RUC, PASSWORD)
    monkeypatch.setattr(recon, "CONTENT_WAIT_MS", 800)
    raw_meta = {**pantallas.META, "cargando": ["Bienvenido al nuevo Marangatu"]}
    stuck = catalog.build(raw_meta, pantallas.PANTALLAS)
    events: list[StepEvent | EndEvent] = []
    started = time.monotonic()
    with FakePortal(password=PASSWORD, user=RUC, mode="inicio_cambiado") as portal:
        recon.run(_recon_job(bot_env.data_dir / "tope", portal), events.append, stuck)
    assert time.monotonic() - started < 40
    assert isinstance(events[-1], EndEvent) and events[-1].status == "completada"


def test_crawl_never_follows_the_logout_link_even_without_the_denylist(
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La exclusión del enlace de salir no depende de la lista negra ni de que tenga id."""
    from app.modules.marangatu import credentials

    credentials.save(RUC, PASSWORD)
    monkeypatch.setattr(recon, "DENYLIST", ())
    events: list[StepEvent | EndEvent] = []
    with FakePortal(password=PASSWORD, user=RUC) as portal:
        recon.run(_recon_job(bot_env.data_dir / "sin-lista", portal), events.append)
        hits = list(portal.state.hits)
    assert portal.state.count("/eset/logout") == 1
    after = hits[hits.index(("GET", "/eset/logout")) + 1 :]
    assert all(path in ("/favicon.ico", "/eset/login") for _, path in after)


def test_worker_crash_does_not_take_down_the_api(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_bot(client, owner_token)
    monkeypatch.setattr(
        supervisor,
        "worker_command",
        lambda: [sys.executable, "-c", "import os, sys; sys.stdin.readline(); os._exit(3)"],
    )
    detail = start_and_supervise(client, owner_token, db, "http://127.0.0.1:9/", monkeypatch)
    assert detail["status"] == "detenida" and detail["stop_code"] == "BROWSER_ERROR"
    assert "código 3" in detail["stop_detail"]
    assert detail["steps"][-1]["action"] == "trabajador"
    assert client.get("/api/v1/system/health").status_code == 200
    # Y se puede lanzar otra corrida.
    run = ok(client.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(owner_token)), 202)
    assert run["status"] == "en_curso"


def test_hung_worker_is_killed(
    client: TestClient,
    owner_token: str,
    db: Session,
    bot_env: BotEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    enable_bot(client, owner_token)
    pid_file = tmp_path / "pid"
    script = (
        "import os, sys, time;"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()));"
        "sys.stdin.readline();"
        'print(\'{"type": "paso", "action": "esperando"}\', flush=True);'
        "time.sleep(600)"
    )
    monkeypatch.setattr(supervisor, "worker_command", lambda: [sys.executable, "-c", script])
    monkeypatch.setattr(supervisor, "GRACE_SECONDS", 0)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "marangatu_timeout_seconds", 2)
    started = time.monotonic()
    detail = start_and_supervise(client, owner_token, db, "http://127.0.0.1:9/", monkeypatch)
    assert time.monotonic() - started < 20
    assert detail["stop_code"] == "BROWSER_ERROR" and "tardó demasiado" in detail["stop_detail"]
    assert actions(detail) == ["esperando", "trabajador"]
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # el trabajador colgado no quedó vivo
    assert client.get("/api/v1/system/health").status_code == 200


def test_packaged_executable_runs_the_worker_with_an_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El ejecutable de PyInstaller no tiene `python -m`: se relanza con `marangatu-worker`."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert supervisor.worker_command() == [sys.executable, "marangatu-worker"]
    monkeypatch.delattr(sys, "frozen")
    assert supervisor.worker_command()[1:] == ["-m", "app.modules.marangatu.worker"]
    # `python -m app marangatu-worker` (lo mismo que hace el ejecutable) llega al trabajador.
    done = subprocess.run(
        [sys.executable, "-m", "app", "marangatu-worker"],
        input="no es un trabajo\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 2
    end: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    assert end["type"] == "fin" and end["stop_code"] == "BROWSER_ERROR"


@pytest.mark.parametrize(
    ("label", "href", "blocked"),
    [
        ("Consultar obligaciones", "/eset/consultas/obligaciones", False),
        ("Presentar declaración", "/eset/x", True),
        ("Ver", "/eset/presentarDeclaracion", True),
        ("Confirmar envío", "/eset/x", True),
        ("Pagar", "/eset/x", True),
        ("Firmá acá", "/eset/firmar", True),
        ("ACEPTAR", "/eset/x", True),
        ("Guardar borrador", "/eset/x", True),
        ("Descargar constancia", "/eset/x", True),
        ("Cerrar sesión", "/eset/x", True),
    ],
)
def test_link_denylist(label: str, href: str, blocked: bool) -> None:
    assert denied(label, href) is blocked


def test_steps_never_store_a_typed_password(
    client: TestClient, owner_token: str, db: Session
) -> None:
    """Segunda defensa del registro: lo escrito en el campo de la clave no llega a la base."""
    org_id = db.scalar(text("SELECT id FROM core.organizations"))
    from app.modules.marangatu.models import Run

    run = Run(organization_id=org_id, task_type="general", stage="reconocimiento")
    db.add(run)
    db.commit()
    step = service.add_step(
        db, run, action="llenar", values={"campo": "#clave", "dato": "clave", "valor": PASSWORD}
    )
    assert step.values["valor"] == "[oculta]"
