"""Configuración del backend, leída de variables de entorno (prefijo CONTADOR_)."""

from functools import lru_cache
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
