"""Clave de Marangatu en el almacén de credenciales del sistema (spec §2, «Credenciales»).

- Entrada `ContadorAI/Marangatu/<RUC>` (usuario: el RUC sin DV). En Windows, el Administrador
  de credenciales (DPAPI, por usuario de Windows), elegido explícitamente para que el ejecutable
  empaquetado no dependa del descubrimiento de backends de `keyring` (D-128).
- El backend solo **guarda**, **borra** e informa **si hay** clave. Nunca la devuelve.
- Solo el trabajador la lee (`read_for_login`), justo antes de escribirla en el formulario.
- Ningún error de aquí lleva el texto de la excepción original: podría traer datos del almacén.
- `PYTHON_KEYRING_BACKEND` (variable de `keyring`) manda si está definida: las pruebas la usan
  para un almacén de prueba compartido entre el backend y el trabajador.
"""

import os
import sys

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, PasswordDeleteError

from app.core.errors import AppError

SERVICE_PREFIX = "ContadorAI/Marangatu"


class CredentialStoreError(AppError):
    status_code = 503

    def __init__(self) -> None:
        super().__init__(
            "CREDENTIAL_STORE_UNAVAILABLE",
            "No se pudo usar el almacén de credenciales del sistema.",
        )


def service_name(ruc: str) -> str:
    return f"{SERVICE_PREFIX}/{ruc}"


def _backend() -> KeyringBackend:
    if os.environ.get("PYTHON_KEYRING_BACKEND"):
        return keyring.get_keyring()
    if sys.platform == "win32":
        from keyring.backends.Windows import WinVaultKeyring

        return WinVaultKeyring()
    return keyring.get_keyring()


def save(ruc: str, password: str) -> None:
    try:
        _backend().set_password(service_name(ruc), ruc, password)
    except (KeyringError, OSError, RuntimeError):
        raise CredentialStoreError() from None


def delete(ruc: str) -> bool:
    """Borra la clave. `False` si no había ninguna."""
    try:
        _backend().delete_password(service_name(ruc), ruc)
    except PasswordDeleteError:
        return False
    except (KeyringError, OSError, RuntimeError):
        raise CredentialStoreError() from None
    return True


def has_password(ruc: str) -> bool:
    try:
        return _backend().get_password(service_name(ruc), ruc) is not None
    except (KeyringError, OSError, RuntimeError):
        raise CredentialStoreError() from None


def read_for_login(ruc: str) -> str | None:
    """Solo para el trabajador: la clave, para escribirla ya en el campo. No guardarla."""
    try:
        return _backend().get_password(service_name(ruc), ruc)
    except (KeyringError, OSError, RuntimeError):
        raise CredentialStoreError() from None
