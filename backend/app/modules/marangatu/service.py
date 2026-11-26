"""Servicio del bot: interruptor, etapas, corridas, pasos y verificación del registro."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.modules.audit import service as audit
from app.modules.marangatu import credentials, storage
from app.modules.marangatu.models import TASK_TYPES, BotSettings, Run, Step, TaskStage
from app.modules.marangatu.stop_codes import StopCode
from app.modules.organizations.models import Organization

HIDDEN = "[oculta]"
RUNNING_INDEX = "uq_runs_one_running"


# --- Interruptor y etapas ----------------------------------------------------------------


def bot_settings(db: Session, organization_id: uuid.UUID) -> BotSettings:
    row = db.scalar(select(BotSettings).where(BotSettings.organization_id == organization_id))
    if row is None:
        row = BotSettings(organization_id=organization_id, bot_enabled=False)
        db.add(row)
        db.flush()
    return row


def stages(db: Session, organization_id: uuid.UUID) -> dict[str, str]:
    """La etapa de cada tipo de tarea; los que faltan empiezan en `reconocimiento`."""
    rows = {
        r.task_type: r
        for r in db.scalars(select(TaskStage).where(TaskStage.organization_id == organization_id))
    }
    for task_type in TASK_TYPES:
        if task_type not in rows:
            rows[task_type] = TaskStage(
                organization_id=organization_id, task_type=task_type, stage="reconocimiento"
            )
            db.add(rows[task_type])
    db.flush()
    return {t: rows[t].stage for t in TASK_TYPES}


def set_enabled(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, enabled: bool
) -> BotSettings:
    row = bot_settings(db, organization_id)
    before = row.bot_enabled
    if before != enabled:
        row.bot_enabled = enabled
        audit.record(
            db,
            action="marangatu.settings.updated",
            entity_type="marangatu.settings",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=user_id,
            before={"bot_enabled": before},
            after={"bot_enabled": enabled},
        )
    db.commit()
    return row


# --- Credenciales (solo el estado y la auditoría; la clave va directo a keyring) -----------


def organization_ruc(db: Session, organization_id: uuid.UUID) -> str | None:
    organization = db.get(Organization, organization_id)
    return organization.ruc if organization else None


def record_credentials(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, ruc: str, *, saved: bool
) -> None:
    """La auditoría solo dice que la clave se guardó o se borró (spec §2)."""
    audit.record(
        db,
        action="marangatu.credentials.saved" if saved else "marangatu.credentials.deleted",
        entity_type="marangatu.credentials",
        entity_id=ruc,
        organization_id=organization_id,
        actor_user_id=user_id,
        after={"detalle": "clave de Marangatu guardada" if saved else "clave de Marangatu borrada"},
    )
    db.commit()


# --- Corridas y pasos --------------------------------------------------------------------


def get_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.organization_id != organization_id:
        raise NotFound("RUN_NOT_FOUND", "No existe esa corrida.")
    return run


def list_runs(db: Session, organization_id: uuid.UUID, limit: int) -> list[Run]:
    query = (
        select(Run)
        .where(Run.organization_id == organization_id)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


def steps_of(db: Session, run_id: uuid.UUID) -> list[Step]:
    return list(db.scalars(select(Step).where(Step.run_id == run_id).order_by(Step.seq)))


def scrub(values: dict[str, Any]) -> dict[str, Any]:
    """Segunda defensa: lo escrito en el campo de la clave nunca llega a la base."""
    clean = dict(values)
    if clean.get("dato") == "clave":
        clean["valor"] = HIDDEN
    return clean


def add_step(
    db: Session,
    run: Run,
    *,
    action: str,
    result: str = "ok",
    screen_id: str | None = None,
    screen_version: int | None = None,
    values: dict[str, Any] | None = None,
    message: str | None = None,
    capture_path: str | None = None,
    capture_sha256: str | None = None,
) -> Step:
    step = Step(
        run_id=run.id,
        organization_id=run.organization_id,
        screen_id=screen_id,
        screen_version=screen_version,
        action=action,
        values=scrub(values or {}),
        result=result,
        message=message[:1000] if message else None,
        capture_path=capture_path,
        capture_sha256=capture_sha256,
    )
    db.add(step)
    db.commit()
    return step


def finish_run(
    db: Session,
    run: Run,
    *,
    status: str,
    stop_code: StopCode | None = None,
    detail: str | None = None,
) -> Run:
    run.status = status
    run.stop_code = stop_code.value if stop_code else None
    run.stop_detail = detail[:500] if detail else None
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run


def stop_before_browser(db: Session, run: Run, code: StopCode, detail: str) -> Run:
    """Paso 1 de la spec (§4): si falla una condición, no se abre el navegador."""
    add_step(
        db, run, action="preparar", result="detenido", values={"motivo": code.value}, message=detail
    )
    return finish_run(db, run, status="detenida", stop_code=code, detail=detail)


def close_interrupted(db: Session, alive: set[uuid.UUID]) -> list[uuid.UUID]:
    """Cierra toda corrida «en curso», de cualquier organización, que ningún trabajador atiende:
    quedó así por un cierre o una caída de la app (D-140). Cada cierre deja su paso en la cadena
    y la corrida detenida con `BROWSER_ERROR`, en su propia organización. Devuelve las cerradas."""
    closed: list[uuid.UUID] = []
    for run in list(db.scalars(select(Run).where(Run.status == "en_curso").order_by(Run.id))):
        if run.id in alive:
            continue
        add_step(
            db,
            run,
            action="interrumpida",
            result="error",
            message="La app se cerró durante la corrida",
        )
        finish_run(
            db,
            run,
            status="detenida",
            stop_code=StopCode.BROWSER_ERROR,
            detail="Corrida interrumpida: la app se cerró antes de terminar",
        )
        closed.append(run.id)
    return closed


def _busy(db: Session, organization_id: uuid.UUID) -> Conflict | None:
    """El 409 si hay una corrida en curso en la instalación. Si es de otra organización, no dice
    de cuál (D-140): solo que el bot está ocupado."""
    owner = db.scalar(select(Run.organization_id).where(Run.status == "en_curso").limit(1))
    if owner is None:
        return None
    if owner == organization_id:
        return Conflict("RUN_IN_PROGRESS", "Ya hay una corrida del bot en curso.")
    return Conflict(
        "BOT_BUSY",
        "El bot de Marangatu está ocupado con otra corrida. Esperá a que termine y volvé a "
        "lanzarla.",
    )


def start_reconnaissance(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    alive: set[uuid.UUID],
    period: date | None = None,
) -> Run:
    """Crea la corrida y revisa lo que se puede revisar sin navegador.

    Devuelve la corrida `en_curso` (lista para el trabajador) o ya `detenida` con su motivo.
    Hay una sola corrida en curso en toda la instalación (D-140): si otra organización tiene
    una, 409 `BOT_BUSY`.
    """
    close_interrupted(db, alive)
    if (busy := _busy(db, organization_id)) is not None:
        raise busy
    run = Run(
        organization_id=organization_id,
        task_type="general",
        stage="reconocimiento",
        period=period,
        status="en_curso",
        started_by=user_id,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        # Carrera: otra corrida entró entre la revisión y el alta (índice único, D-140).
        if RUNNING_INDEX not in str(exc.orig):
            raise
        db.rollback()
        raise _busy(db, organization_id) or Conflict(
            "BOT_BUSY", "El bot de Marangatu está ocupado con otra corrida."
        ) from exc
    audit.record(
        db,
        action="marangatu.run.started",
        entity_type="marangatu.run",
        entity_id=run.id,
        organization_id=organization_id,
        actor_user_id=user_id,
        after={"task_type": run.task_type, "stage": run.stage},
    )
    db.commit()

    if not bot_settings(db, organization_id).bot_enabled:
        return stop_before_browser(db, run, StopCode.BOT_OFF, "El bot está apagado")
    ruc = organization_ruc(db, organization_id)
    if ruc is None:
        return stop_before_browser(
            db, run, StopCode.DATA_INCOMPLETE, "La empresa no tiene el RUC cargado"
        )
    try:
        has = credentials.has_password(ruc)
    except credentials.CredentialStoreError:
        return stop_before_browser(
            db, run, StopCode.NO_CREDENTIALS, "El almacén de credenciales no está disponible"
        )
    if not has:
        return stop_before_browser(db, run, StopCode.NO_CREDENTIALS, "No hay clave guardada")
    return run


# --- Verificación del registro -----------------------------------------------------------


@dataclass(frozen=True)
class FileProblem:
    seq: int
    path: str
    problem: str  # "falta" o "modificado"


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    checked: int
    first_broken_seq: int | None
    files_checked: int = 0
    file_problems: list[FileProblem] = field(default_factory=list)


def verify_chain(db: Session, *, check_files: bool = True) -> ChainVerification:
    """Recalcula la cadena de todos los pasos y, además, el SHA-256 de cada archivo."""
    rows = db.execute(
        text(
            """
            SELECT seq, capture_path, capture_sha256,
                   prev_hash IS NOT DISTINCT FROM lag(row_hash) OVER (ORDER BY seq) AS link_ok,
                   row_hash = marangatu.step_row_hash(prev_hash, seq, id, run_id,
                       organization_id, occurred_at, screen_id, screen_version, action, "values",
                       result, message, capture_path, capture_sha256) AS hash_ok
            FROM marangatu.steps
            ORDER BY seq
            """
        )
    ).all()
    first_broken = next((r.seq for r in rows if not (r.link_ok and r.hash_ok)), None)
    problems: list[FileProblem] = []
    files = 0
    if check_files:
        for row in rows:
            if row.capture_path is None:
                continue
            files += 1
            try:
                path = storage.resolve(row.capture_path)
            except ValueError:
                problems.append(FileProblem(row.seq, row.capture_path, "fuera_de_la_carpeta"))
                continue
            if not path.is_file():
                problems.append(FileProblem(row.seq, row.capture_path, "falta"))
            elif storage.sha256_file(path) != row.capture_sha256:
                problems.append(FileProblem(row.seq, row.capture_path, "modificado"))
    return ChainVerification(
        valid=first_broken is None and not problems,
        checked=len(rows),
        first_broken_seq=first_broken,
        files_checked=files,
        file_problems=problems,
    )
