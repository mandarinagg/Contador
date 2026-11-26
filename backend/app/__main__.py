"""Arranque del backend como proceso propio (`python -m app` o ejecutable empaquetado).

1. Aplica las migraciones pendientes (la app de escritorio actualiza su base sola).
2. Levanta la API en el host y puerto de la configuración (por defecto 127.0.0.1:8765).

La app de escritorio (Tauri) lanza este proceso y le pasa la configuración por
variables de entorno `CONTADOR_*`.

Con el argumento `marangatu-worker` arranca, en cambio, el trabajador del bot de Marangatu
(D-127): el ejecutable empaquetado no tiene `python -m`, así que el backend se relanza a sí
mismo con ese argumento.
"""

import logging
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.marangatu.protocol import WORKER_ARG

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
    if len(sys.argv) > 1 and sys.argv[1] == WORKER_ARG:
        from app.modules.marangatu.worker import main as worker_main

        sys.exit(worker_main())
    settings = get_settings()
    configure_logging(settings.log_level)
    import psycopg

    logger.info("Aplicando migraciones (psycopg %s)", psycopg.pq.__impl__)
    upgrade_database(settings.database_url)

    from app.main import app  # después de migrar: la app asume el esquema al día
    from app.modules.marangatu import supervisor

    # Las corridas del bot que quedaron «en curso» por un cierre o una caída (D-140).
    closed = supervisor.close_interrupted_at_startup()
    if closed:
        logger.warning("Corridas del bot interrumpidas y cerradas: %d", closed)

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
