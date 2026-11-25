"""Lo que se dicen el backend y el trabajador (D-127).

- El backend escribe **una línea JSON** con el trabajo (`Job`) en la entrada del trabajador y
  la cierra. El trabajo no lleva la clave: el trabajador la lee del almacén de credenciales.
- El trabajador contesta con **líneas JSON** en su salida: un `StepEvent` por paso y un
  `EndEvent` al final. Lo demás (registros, avisos del navegador) va a la salida de errores,
  que el backend guarda en `<datos>/logs/marangatu-<corrida>.log`.
- El trabajador no toca la base: el backend escribe los pasos (y la base los encadena).
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.modules.marangatu.stop_codes import StopCode

# Argumento con el que el ejecutable empaquetado arranca como trabajador (`app/__main__.py`).
WORKER_ARG = "marangatu-worker"

StepResult = Literal["ok", "detenido", "error"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Job(_Strict):
    run_id: uuid.UUID
    kind: Literal["reconocimiento"]
    stage: str
    ruc: str
    login_url: str
    # Carpeta absoluta de los documentos de la corrida (el trabajador solo escribe ahí).
    capture_dir: str
    headless: bool
    channel: str | None
    max_pages: int = Field(ge=1, le=500)
    timeout_seconds: int = Field(ge=1, le=3600)
    navigation_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)


class StepEvent(_Strict):
    type: Literal["paso"] = "paso"
    screen_id: str | None = None
    screen_version: int | None = None
    action: str
    values: dict[str, Any] = Field(default_factory=dict)
    result: StepResult = "ok"
    message: str | None = None
    # Ruta absoluta del archivo, dentro de `Job.capture_dir`.
    capture: str | None = None


class EndEvent(_Strict):
    type: Literal["fin"] = "fin"
    status: Literal["completada", "detenida"]
    stop_code: StopCode | None = None
    detail: str | None = None


Event = Annotated[StepEvent | EndEvent, Field(discriminator="type")]


_EVENTS: TypeAdapter[StepEvent | EndEvent] = TypeAdapter(Event)


def parse_event(line: str) -> StepEvent | EndEvent:
    return _EVENTS.validate_json(line)
