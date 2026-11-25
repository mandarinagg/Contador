"""Configuración del backend, leída de variables de entorno (prefijo CONTADOR_)."""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONTADOR_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://contador:contador_dev@127.0.0.1:55433/contador"
    test_database_url: str = (
        "postgresql+psycopg://contador:contador_dev@127.0.0.1:55433/contador_test"
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8765
    cors_origins: Annotated[list[str], NoDecode] = Field(
        # Frontend de desarrollo y webview de Tauri (Linux/macOS: tauri://localhost; Windows:
        # http://tauri.localhost).
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "http://tauri.localhost",
        ]
    )

    session_ttl_hours: int = Field(default=12, ge=1, le=72)
    session_idle_minutes: int = Field(default=60, ge=5, le=24 * 60)
    login_max_attempts: int = Field(default=5, ge=3, le=20)
    login_lockout_minutes: int = Field(default=15, ge=1, le=24 * 60)

    # Carpeta de datos de la app (la misma que usa el lanzador: `%LOCALAPPDATA%\ContadorAI` en
    # Windows). Ahí van los documentos (capturas del bot de Marangatu) y los registros. Vacía:
    # se calcula con `app_data_dir()`.
    data_dir: Path | None = None

    # Bot de Marangatu (docs/specs/BOT_MARANGATU.md). La URL de ingreso es PROVISORIA hasta el
    # reconocimiento real. `marangatu_headless` vacío: con ventana (la persona ve lo que hace).
    # `marangatu_browser_channel` vacío: Edge del sistema en Windows, Chromium de Playwright en
    # Linux.
    marangatu_url: str = "https://marangatu.set.gov.py/eset/login"
    marangatu_headless: bool | None = None
    marangatu_browser_channel: str | None = None
    marangatu_max_pages: int = Field(default=40, ge=1, le=500)
    marangatu_timeout_seconds: int = Field(default=600, ge=10, le=3600)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


DATA_DIR_NAME = "ContadorAI"  # igual que `DATA_DIR_NAME` del lanzador (desktop/src-tauri)


def app_data_dir(settings: Settings | None = None) -> Path:
    """Carpeta de datos: la configurada o la misma que calcula el lanzador por defecto."""
    settings = settings or get_settings()
    if settings.data_dir is not None:
        return settings.data_dir
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / DATA_DIR_NAME
