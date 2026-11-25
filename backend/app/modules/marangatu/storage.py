"""Almacén de documentos del bot: capturas, borradores del catálogo y descargas (spec §5).

La app todavía no tiene un almacén de documentos general (fase 6): se guardan en la carpeta de
datos de la app (`<datos>/documentos/marangatu/<corrida>/`), y el registro guarda la ruta
**relativa** a esa carpeta y el SHA-256 del archivo (D-131). La verificación del registro
vuelve a calcular el SHA-256 de cada archivo.
"""

import hashlib
import uuid
from pathlib import Path

from app.core.config import app_data_dir

DOCUMENTS_DIR = "documentos"
LOGS_DIR = "logs"


def data_root() -> Path:
    return app_data_dir()


def run_dir(run_id: uuid.UUID) -> Path:
    """Carpeta de los documentos de una corrida (se crea si falta)."""
    path = data_root() / DOCUMENTS_DIR / "marangatu" / str(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def worker_log(run_id: uuid.UUID) -> Path:
    path = data_root() / LOGS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path / f"marangatu-{run_id}.log"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def relative(path: Path) -> str:
    """Ruta relativa a la carpeta de datos, con `/` (igual en Windows y en Linux)."""
    return path.resolve().relative_to(data_root().resolve()).as_posix()


def resolve(relative_path: str) -> Path:
    """La ruta absoluta de un documento; rechaza rutas que salgan de la carpeta de datos."""
    root = data_root().resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Ruta de documento fuera de la carpeta de datos")
    return path
