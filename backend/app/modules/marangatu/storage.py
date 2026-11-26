"""Almacén de documentos del bot: capturas, borradores del catálogo y descargas (spec §5).

La app todavía no tiene un almacén de documentos general (fase 6): se guardan en la carpeta de
datos de la app, y el registro guarda la ruta **relativa** a esa carpeta y el SHA-256 del
archivo (D-131). La verificación del registro vuelve a calcular el SHA-256 de cada archivo.

Desde la D-140 cada organización tiene su carpeta: `<datos>/documentos/<organización>/marangatu/
<corrida>/`. Las corridas anteriores (`<datos>/documentos/marangatu/<corrida>/`) siguen
resolviéndose por su ruta relativa guardada, sin moverlas: moverlas rompería el SHA-256 y la
cadena del registro.
"""

import hashlib
import uuid
from pathlib import Path

from app.core.config import app_data_dir

DOCUMENTS_DIR = "documentos"
LOGS_DIR = "logs"


def data_root() -> Path:
    return app_data_dir()


LEGACY_FOLDER = "marangatu"


def run_dir(organization_id: uuid.UUID, run_id: uuid.UUID) -> Path:
    """Carpeta de los documentos de una corrida, dentro de la de su organización (se crea)."""
    path = data_root() / DOCUMENTS_DIR / str(organization_id) / "marangatu" / str(run_id)
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


def belongs_to(relative_path: str, organization_id: uuid.UUID) -> bool:
    """Si el documento es de esa organización. Defensa extra: el paso ya trae su organización.

    Las rutas nuevas llevan la organización en la segunda parte; las anteriores a la D-140
    (`documentos/marangatu/...`) no la llevan y se aceptan: el paso que las apunta es el que
    dice de quién son.
    """
    parts = Path(relative_path).parts
    if len(parts) < 2 or parts[0] != DOCUMENTS_DIR:
        return False
    return parts[1] == LEGACY_FOLDER or parts[1] == str(organization_id)
