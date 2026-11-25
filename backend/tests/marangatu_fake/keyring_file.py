"""Almacén de credenciales de prueba para `keyring` (spec §2: las pruebas no usan el real).

Guarda en un JSON cuya ruta da `CONTADOR_TEST_KEYRING_FILE`. Lo comparten el proceso de las
pruebas y el trabajador (otro proceso) porque los dos lo eligen con `PYTHON_KEYRING_BACKEND`
(ver `tests/conftest.py`).
"""

import json
import os
from pathlib import Path

from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, PasswordDeleteError


class FileKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    @staticmethod
    def _path() -> Path:
        path = os.environ.get("CONTADOR_TEST_KEYRING_FILE")
        if not path:
            raise KeyringError("Almacén de prueba sin archivo")
        return Path(path)

    def _load(self) -> dict[str, str]:
        path = self._path()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _store(self, data: dict[str, str]) -> None:
        self._path().write_text(json.dumps(data), encoding="utf-8")

    def get_password(self, service: str, username: str) -> str | None:
        return self._load().get(f"{service}|{username}")

    def set_password(self, service: str, username: str, password: str) -> None:
        data = self._load()
        data[f"{service}|{username}"] = password
        self._store(data)

    def delete_password(self, service: str, username: str) -> None:
        data = self._load()
        if data.pop(f"{service}|{username}", None) is None:
            raise PasswordDeleteError("No hay clave")
        self._store(data)
