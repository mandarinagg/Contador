"""Utilidades de las pruebas del bot de Marangatu (portal simulado, nunca el real)."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.marangatu import supervisor
from tests.conftest import BACKEND_DIR, auth_header
from tests.finance_utils import ok
from tests.tax_utils import set_ruc

MARANGATU = "/api/v1/marangatu"
RUC = "80000005"
# Clave distintiva (con ñ y tilde) para buscarla tal cual en la base, los registros y los
# archivos (prueba obligatoria de la spec §2).
PASSWORD = "Ñandutí-Clave-Prueba-7391!"


@dataclass
class BotEnv:
    data_dir: Path
    keyring_file: Path
    launched: list[uuid.UUID]


@pytest.fixture
def bot_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BotEnv]:
    """Carpeta de datos y almacén de credenciales propios de la prueba; el lanzamiento en
    segundo plano se reemplaza por una lista (la prueba supervisa de forma sincrónica)."""
    settings = get_settings()
    env = BotEnv(data_dir=tmp_path / "datos", keyring_file=tmp_path / "keyring.json", launched=[])
    monkeypatch.setattr(settings, "data_dir", env.data_dir)
    monkeypatch.setattr(settings, "marangatu_headless", True)
    monkeypatch.setattr(settings, "marangatu_browser_channel", None)
    monkeypatch.setattr(settings, "marangatu_timeout_seconds", 90)
    monkeypatch.setenv("CONTADOR_TEST_KEYRING_FILE", str(env.keyring_file))
    # El trabajador (otro proceso) importa el almacén de prueba desde `tests`.
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join(filter(None, [BACKEND_DIR, os.environ.get("PYTHONPATH")]))
    )
    monkeypatch.setattr(supervisor, "launch", env.launched.append)
    yield env


def enable_bot(client: TestClient, token: str, *, password: str | None = PASSWORD) -> None:
    set_ruc(client, token, RUC)
    ok(client.put(f"{MARANGATU}/settings", json={"bot_enabled": True}, headers=auth_header(token)))
    if password is not None:
        ok(
            client.put(
                f"{MARANGATU}/credentials", json={"password": password}, headers=auth_header(token)
            )
        )


def start_and_supervise(
    client: TestClient, token: str, db: Session, login_url: str, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Lanza un reconocimiento por la API y lo supervisa acá mismo. Devuelve el detalle."""
    monkeypatch.setattr(get_settings(), "marangatu_url", login_url)
    run = ok(client.post(f"{MARANGATU}/runs/reconnaissance", headers=auth_header(token)), 202)
    if run["status"] == "en_curso":
        supervisor.supervise(db, uuid.UUID(run["id"]))
    return run_detail(client, token, run["id"])


def run_detail(client: TestClient, token: str, run_id: str) -> dict[str, Any]:
    detail: dict[str, Any] = ok(
        client.get(f"{MARANGATU}/runs/{run_id}", headers=auth_header(token))
    )
    return detail


def actions(detail: dict[str, Any]) -> list[str]:
    return [s["action"] for s in detail["steps"]]
