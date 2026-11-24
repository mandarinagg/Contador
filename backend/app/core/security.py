"""Primitivas de seguridad: hash de contraseñas (Argon2id) y tokens de sesión opacos."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Parámetros por defecto de argon2-cffi (RFC 9106, perfil de bajo consumo de memoria).
_hasher = PasswordHasher()

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256

# Hash válido para comparar cuando el usuario no existe: iguala el tiempo de respuesta
# y no revela qué emails están registrados.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_session_token() -> str:
    """Token opaco de 256 bits. Solo su hash se guarda en la base."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()
