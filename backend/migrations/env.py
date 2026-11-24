"""Entorno de Alembic. La URL viene de la configuración del backend o de -x url=..."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.models import Base

config = context.config
target_metadata = Base.metadata
SCHEMAS = {"core", "audit"}


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    return True


def run_migrations_online() -> None:
    # Prioridad: URL pasada por código (arranque empaquetado, pruebas) > `-x url=...` > config.
    url = (
        config.attributes.get("url")
        or context.get_x_argument(as_dictionary=True).get("url")
        or get_settings().database_url
    )
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            version_table_schema="public",
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Modo offline no soportado: ejecutar contra una base.")
run_migrations_online()
