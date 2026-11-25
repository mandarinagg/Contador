"""Esquemas de la API del bot de Marangatu (`/api/v1/marangatu`)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsIn(_Strict):
    bot_enabled: bool


class SettingsOut(BaseModel):
    bot_enabled: bool
    stages: dict[str, str]
    catalog_provisional: bool
    catalog_updated: str | None


class CredentialsIn(_Strict):
    # `SecretStr`: ni el repr ni un error de validación muestran la clave.
    password: Annotated[SecretStr, Field(min_length=1, max_length=200)]


class CredentialsOut(BaseModel):
    ruc: str | None
    has_password: bool
    store_available: bool


class RunOut(BaseModel):
    id: uuid.UUID
    task_type: str
    period: date | None
    stage: str
    status: str
    stop_code: str | None
    stop_text: str | None
    stop_detail: str | None
    started_by: uuid.UUID | None
    started_at: datetime
    finished_at: datetime | None


class StepOut(BaseModel):
    id: uuid.UUID
    seq: int
    occurred_at: datetime
    screen_id: str | None
    screen_version: int | None
    action: str
    values: dict[str, Any]
    result: str
    message: str | None
    capture_path: str | None
    capture_sha256: str | None


class RunDetailOut(RunOut):
    steps: list[StepOut]


class FileProblemOut(BaseModel):
    seq: int
    path: str
    problem: str


class VerifyOut(BaseModel):
    valid: bool
    checked: int
    first_broken_seq: int | None
    files_checked: int
    file_problems: list[FileProblemOut]
