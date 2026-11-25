"""Supervisor del trabajador: lo lanza, escribe sus pasos y lo mata si se cuelga (D-127).

- El trabajador es **otro proceso** (`worker.py`). Si se cae o se cuelga, la API sigue: el
  supervisor corre en un hilo del backend, espera con un límite de tiempo y, al vencer, mata
  el árbol entero (trabajador, Playwright y el navegador).
- Lo que el trabajador cuenta llega como líneas JSON; el supervisor valida cada evento, calcula
  él mismo el SHA-256 de cada captura (no confía en el trabajador) y escribe el paso en la
  base, que lo encadena.
- La salida de errores del trabajador va a `<datos>/logs/marangatu-<corrida>.log`.
"""

import contextlib
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import IO

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.marangatu import service, storage
from app.modules.marangatu.models import Run
from app.modules.marangatu.protocol import WORKER_ARG, EndEvent, Job, StepEvent, parse_event
from app.modules.marangatu.stop_codes import StopCode

logger = logging.getLogger("contador.marangatu.supervisor")

# Margen sobre el tiempo del trabajo antes de matar al trabajador (cerrar el navegador y salir
# de Marangatu también lleva su tiempo).
GRACE_SECONDS = 60

# Corridas que este proceso está atendiendo (desde que se lanzan hasta que terminan). Una
# corrida `en_curso` que no está acá quedó así por un cierre de la app.
_claimed: set[uuid.UUID] = set()
_lock = threading.Lock()


def alive_runs() -> set[uuid.UUID]:
    with _lock:
        return set(_claimed)


def _claim(run_id: uuid.UUID) -> None:
    with _lock:
        _claimed.add(run_id)


def _release(run_id: uuid.UUID) -> None:
    with _lock:
        _claimed.discard(run_id)


def worker_command() -> list[str]:
    """Cómo lanzar el trabajador: el ejecutable empaquetado se relanza a sí mismo."""
    if getattr(sys, "frozen", False):
        return [sys.executable, WORKER_ARG]
    return [sys.executable, "-m", "app.modules.marangatu.worker"]


def build_job(run: Run, ruc: str, capture_dir: Path) -> Job:
    settings = get_settings()
    headless = settings.marangatu_headless
    channel = settings.marangatu_browser_channel
    if channel is None and sys.platform == "win32":
        channel = "msedge"
    return Job(
        run_id=run.id,
        kind="reconocimiento",
        stage=run.stage,
        ruc=ruc,
        login_url=settings.marangatu_url,
        capture_dir=str(capture_dir),
        headless=bool(headless) if headless is not None else False,
        channel=channel or None,
        max_pages=settings.marangatu_max_pages,
        timeout_seconds=settings.marangatu_timeout_seconds,
    )


def _spawn(command: list[str], log: IO[bytes]) -> subprocess.Popen[str]:
    if sys.platform == "win32":
        return subprocess.Popen(  # noqa: S603 - el propio ejecutable, sin datos de afuera
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    # Grupo propio: al matarlo caen también Playwright y el navegador.
    return subprocess.Popen(  # noqa: S603 - el propio ejecutable, sin datos de afuera
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
        encoding="utf-8",
        start_new_session=True,
    )


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        taskkill = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run(  # noqa: S603 - ruta fija del sistema y un pid propio
            [str(taskkill), "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _reader(stream: IO[str], lines: "queue.Queue[str | None]") -> None:
    try:
        for line in stream:
            lines.put(line)
    finally:
        lines.put(None)


def _record_step(db: Session, run: Run, event: StepEvent, capture_dir: Path) -> None:
    capture_path: str | None = None
    capture_sha: str | None = None
    message = event.message
    if event.capture:
        path = Path(event.capture).resolve()
        if path.is_relative_to(capture_dir.resolve()) and path.is_file():
            capture_path = storage.relative(path)
            capture_sha = storage.sha256_file(path)
        else:
            message = f"{message or ''} (captura no encontrada)".strip()
    service.add_step(
        db,
        run,
        action=event.action,
        result=event.result,
        screen_id=event.screen_id,
        screen_version=event.screen_version,
        values=event.values,
        message=message,
        capture_path=capture_path,
        capture_sha256=capture_sha,
    )


def supervise(db: Session, run_id: uuid.UUID) -> Run:
    """Corre el trabajador para una corrida `en_curso` y la deja terminada. Sincrónico."""
    _claim(run_id)
    try:
        return _supervise(db, run_id)
    finally:
        _release(run_id)


def _supervise(db: Session, run_id: uuid.UUID) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.status != "en_curso":
        raise ValueError(f"La corrida {run_id} no está en curso")
    ruc = service.organization_ruc(db, run.organization_id)
    if ruc is None:
        return service.stop_before_browser(
            db, run, StopCode.DATA_INCOMPLETE, "La empresa no tiene el RUC cargado"
        )
    capture_dir = storage.run_dir(run.id)
    job = build_job(run, ruc, capture_dir)
    end: EndEvent | None = None
    failure: str | None = None
    with storage.worker_log(run.id).open("wb") as log:
        try:
            proc = _spawn(worker_command(), log)
        except OSError as exc:
            service.add_step(db, run, action="trabajador", result="error", message=str(exc)[:300])
            return service.finish_run(
                db,
                run,
                status="detenida",
                stop_code=StopCode.BROWSER_ERROR,
                detail="No se pudo iniciar el trabajador",
            )
        try:
            assert proc.stdin is not None and proc.stdout is not None
            try:
                proc.stdin.write(job.model_dump_json() + "\n")
                proc.stdin.close()
            except OSError:
                pass  # se cayó al arrancar: lo dice el código de salida
            lines: queue.Queue[str | None] = queue.Queue()
            threading.Thread(
                target=_reader, args=(proc.stdout, lines), daemon=True, name="marangatu-reader"
            ).start()
            deadline = time.monotonic() + job.timeout_seconds + GRACE_SECONDS
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = "El trabajador tardó demasiado y se cerró"
                    _kill_tree(proc)
                    break
                try:
                    line = lines.get(timeout=min(remaining, 1.0))
                except queue.Empty:
                    continue
                if line is None:
                    break
                if not line.strip():
                    continue
                try:
                    event = parse_event(line)
                except ValidationError:
                    logger.warning("Línea inválida del trabajador (corrida %s)", run.id)
                    continue
                if isinstance(event, StepEvent):
                    _record_step(db, run, event, capture_dir)
                else:
                    end = event
            if failure is None:
                try:
                    code = proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    _kill_tree(proc)
                    code = proc.returncode
                if end is None:
                    failure = f"El trabajador se cerró sin terminar (código {code})"
        finally:
            if proc.poll() is None:
                _kill_tree(proc)
    if failure is not None or end is None:
        detail = failure or "El trabajador no informó el final"
        service.add_step(db, run, action="trabajador", result="error", message=detail)
        return service.finish_run(
            db, run, status="detenida", stop_code=StopCode.BROWSER_ERROR, detail=detail
        )
    return service.finish_run(
        db, run, status=end.status, stop_code=end.stop_code, detail=end.detail
    )


def _supervise_in_thread(run_id: uuid.UUID) -> None:
    session = get_sessionmaker()()
    try:
        supervise(session, run_id)
    except Exception:
        logger.exception("Falló la supervisión de la corrida %s", run_id)
        session.rollback()
        try:
            run = session.get(Run, run_id)
            if run is not None and run.status == "en_curso":
                service.finish_run(
                    session,
                    run,
                    status="detenida",
                    stop_code=StopCode.BROWSER_ERROR,
                    detail="Falló la supervisión de la corrida",
                )
        except Exception:
            logger.exception("No se pudo cerrar la corrida %s", run_id)
    finally:
        session.close()
        _release(run_id)


def launch(run_id: uuid.UUID) -> None:
    """Lanza la supervisión en segundo plano (el pedido HTTP vuelve enseguida)."""
    _claim(run_id)
    threading.Thread(
        target=_supervise_in_thread, args=(run_id,), daemon=True, name=f"marangatu-{run_id}"
    ).start()
