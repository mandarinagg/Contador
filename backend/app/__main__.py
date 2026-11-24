"""Arranque del backend como proceso propio (`python -m app` o ejecutable empaquetado).

1. Aplica las migraciones pendientes (la app de escritorio actualiza su base sola).
2. Levanta la API en el host y puerto de la configuración (por defecto 127.0.0.1:8765).

La app de escritorio (Tauri) lanza este proceso y le pasa la configuración por
variables de entorno `CONTADOR_*`.
"""

import logging
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("contador.launcher")


def migrations_dir() -> Path:
    # Empaquetado con PyInstaller, los archivos de datos quedan en sys._MEIPASS.
    bundle = getattr(sys, "_MEIPASS", None)
    base = Path(bundle) if bundle else Path(__file__).resolve().parent.parent
    return base / "migrations"


def upgrade_database(url: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir()))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    import psycopg

    logger.info("Aplicando migraciones (psycopg %s)", psycopg.pq.__impl__)
    upgrade_database(settings.database_url)

    from app.main import app  # después de migrar: la app asume el esquema al día

    logger.info("API en http://%s:%s", settings.api_host, settings.api_port)
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # se usa el logging JSON propio
        access_log=False,
    )


if __name__ == "__main__":
    main()
