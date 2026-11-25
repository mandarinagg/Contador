"""Trabajador del bot de Marangatu: un proceso aparte que maneja el navegador (spec §2).

Se lanza de dos formas (D-127):
- en desarrollo y en las pruebas: `python -m app.modules.marangatu.worker`;
- en el ejecutable empaquetado (no hay `python`): `contador-backend.exe marangatu-worker`,
  que `app/__main__.py` desvía hacia `main()` de este módulo.

Lee el trabajo (`protocol.Job`) de la primera línea de su entrada y escribe los eventos en su
salida, una línea JSON por evento. Todo lo demás que se imprima (registros, avisos de
Playwright) se desvía a la salida de errores, así no se mezcla con el protocolo. Si se cuelga o
se cae, el backend lo mata y la API sigue (supervisor.py).
"""

import logging
import os
import sys
from typing import TextIO

from app.core.logging import JsonFormatter
from app.modules.marangatu import recon
from app.modules.marangatu.protocol import EndEvent, Job, StepEvent
from app.modules.marangatu.stop_codes import StopCode

logger = logging.getLogger("contador.marangatu.worker")


def _protocol_channel() -> TextIO:
    """La salida original queda solo para el protocolo; `print` y compañía van a stderr."""
    channel = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1, newline="\n")
    sys.stdout.flush()
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return channel


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def main() -> int:
    channel = _protocol_channel()
    _configure_logging()

    def emit(event: StepEvent | EndEvent) -> None:
        channel.write(event.model_dump_json() + "\n")
        channel.flush()

    try:
        job = Job.model_validate_json(sys.stdin.readline())
    except ValueError:
        logger.error("Trabajo inválido en la entrada")
        emit(
            EndEvent(status="detenida", stop_code=StopCode.BROWSER_ERROR, detail="Trabajo inválido")
        )
        return 2
    logger.info("Corrida %s: %s", job.run_id, job.kind)
    try:
        recon.run(job, emit)
    except Exception as exc:
        # Solo el tipo del error: el texto podría traer datos de la página.
        logger.error("Error inesperado del trabajador: %s", type(exc).__name__)
        emit(
            EndEvent(
                status="detenida",
                stop_code=StopCode.BROWSER_ERROR,
                detail=f"Error inesperado del trabajador ({type(exc).__name__})",
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
