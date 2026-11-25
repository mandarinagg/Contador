"""API del bot de Marangatu (`/api/v1/marangatu`, BOT_MARANGATU.md §7).

Permisos de tributación (D-130):
- leer (interruptor, estado de la clave, corridas, pasos, capturas, verificación): `tax.read`;
- **apagar** el bot: `tax.manage` (frenar siempre es seguro);
- **encender** el bot, guardar o borrar la clave y lanzar un reconocimiento: `tax.verify`
  (entra a Marangatu con la clave del contribuyente).

La clave viaja una sola vez, en el cuerpo de `PUT /credentials`, y va directo al almacén de
credenciales. El registro de pedidos solo anota método, ruta y estado (nunca el cuerpo), y la
auditoría solo «clave de Marangatu guardada» o «borrada».
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import AuthContext, DbSession, require
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.permissions import Perm
from app.modules.marangatu import catalog, credentials, service, storage, supervisor
from app.modules.marangatu.models import Run, Step
from app.modules.marangatu.schemas import (
    CredentialsIn,
    CredentialsOut,
    FileProblemOut,
    RunDetailOut,
    RunOut,
    SettingsIn,
    SettingsOut,
    StepOut,
    VerifyOut,
)
from app.modules.marangatu.stop_codes import stop_text

router = APIRouter(prefix="/marangatu", tags=["marangatu"])

Reader = Annotated[AuthContext, Depends(require(Perm.TAX_READ))]
Manager = Annotated[AuthContext, Depends(require(Perm.TAX_MANAGE))]
Verifier = Annotated[AuthContext, Depends(require(Perm.TAX_VERIFY))]
Limit = Annotated[int, Query(ge=1, le=200)]

MEDIA_TYPES = {".png": "image/png", ".yaml": "application/yaml", ".json": "application/json"}


def _settings_out(db: DbSession, auth: AuthContext) -> SettingsOut:
    meta = catalog.packaged().meta
    return SettingsOut(
        bot_enabled=service.bot_settings(db, auth.organization_id).bot_enabled,
        stages=service.stages(db, auth.organization_id),
        catalog_provisional=bool(meta.get("provisorio")),
        catalog_updated=meta.get("actualizado"),
    )


def _run_out(run: Run) -> RunOut:
    return RunOut(
        id=run.id,
        task_type=run.task_type,
        period=run.period,
        stage=run.stage,
        status=run.status,
        stop_code=run.stop_code,
        stop_text=stop_text(run.stop_code),
        stop_detail=run.stop_detail,
        started_by=run.started_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _step_out(step: Step) -> StepOut:
    return StepOut.model_validate({name: getattr(step, name) for name in StepOut.model_fields})


def _ruc(db: DbSession, auth: AuthContext) -> str:
    ruc = service.organization_ruc(db, auth.organization_id)
    if ruc is None:
        raise Conflict(
            "ORGANIZATION_WITHOUT_RUC",
            "Cargá el RUC de la empresa antes de guardar la clave de Marangatu.",
        )
    return ruc


# --- Interruptor -------------------------------------------------------------------------


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: DbSession, auth: Reader) -> SettingsOut:
    out = _settings_out(db, auth)
    db.commit()
    return out


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, db: DbSession, auth: Manager) -> SettingsOut:
    if body.bot_enabled and Perm.TAX_VERIFY.value not in auth.permissions:
        raise Forbidden(
            "FORBIDDEN",
            "No tenés permiso para encender el bot.",
            details={"missing": [Perm.TAX_VERIFY.value]},
        )
    service.set_enabled(db, auth.organization_id, auth.user_id, body.bot_enabled)
    return get_settings(db, auth)


# --- Clave -------------------------------------------------------------------------------


@router.get("/credentials", response_model=CredentialsOut)
def get_credentials(db: DbSession, auth: Reader) -> CredentialsOut:
    ruc = service.organization_ruc(db, auth.organization_id)
    if ruc is None:
        return CredentialsOut(ruc=None, has_password=False, store_available=True)
    try:
        return CredentialsOut(
            ruc=ruc, has_password=credentials.has_password(ruc), store_available=True
        )
    except credentials.CredentialStoreError:
        return CredentialsOut(ruc=ruc, has_password=False, store_available=False)


@router.put("/credentials", response_model=CredentialsOut)
def put_credentials(body: CredentialsIn, db: DbSession, auth: Verifier) -> CredentialsOut:
    ruc = _ruc(db, auth)
    credentials.save(ruc, body.password.get_secret_value())
    service.record_credentials(db, auth.organization_id, auth.user_id, ruc, saved=True)
    return CredentialsOut(ruc=ruc, has_password=True, store_available=True)


@router.delete("/credentials", status_code=status.HTTP_204_NO_CONTENT)
def delete_credentials(db: DbSession, auth: Verifier) -> Response:
    ruc = _ruc(db, auth)
    if not credentials.delete(ruc):
        raise NotFound("NO_CREDENTIALS", "No hay clave de Marangatu guardada.")
    service.record_credentials(db, auth.organization_id, auth.user_id, ruc, saved=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Corridas ----------------------------------------------------------------------------


@router.post("/runs/reconnaissance", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def start_reconnaissance(db: DbSession, auth: Verifier) -> RunOut:
    """Lanza un reconocimiento. Si falla una condición previa, la corrida ya vuelve detenida."""
    run = service.start_reconnaissance(
        db, auth.organization_id, auth.user_id, alive=supervisor.alive_runs()
    )
    if run.status == "en_curso":
        supervisor.launch(run.id)
    return _run_out(run)


@router.get("/runs", response_model=list[RunOut])
def list_runs(db: DbSession, auth: Reader, limit: Limit = 50) -> list[RunOut]:
    return [_run_out(r) for r in service.list_runs(db, auth.organization_id, limit)]


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(run_id: uuid.UUID, db: DbSession, auth: Reader) -> RunDetailOut:
    run = service.get_run(db, auth.organization_id, run_id)
    return RunDetailOut(
        **_run_out(run).model_dump(), steps=[_step_out(s) for s in service.steps_of(db, run.id)]
    )


@router.get("/steps/{step_id}/capture")
def get_capture(step_id: uuid.UUID, db: DbSession, auth: Reader) -> Response:
    """El archivo de un paso, solo si su SHA-256 sigue siendo el registrado."""
    step = db.get(Step, step_id)
    if step is None or step.organization_id != auth.organization_id or not step.capture_path:
        raise NotFound("CAPTURE_NOT_FOUND", "Ese paso no tiene captura.")
    path = storage.resolve(step.capture_path)
    if not path.is_file():
        raise NotFound("CAPTURE_NOT_FOUND", "El archivo de la captura no está.")
    content = path.read_bytes()
    if storage.sha256_bytes(content) != step.capture_sha256:
        raise AppError(
            "CAPTURE_MODIFIED", "El archivo de la captura fue modificado.", status_code=409
        )
    return Response(
        content=content,
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


@router.get("/verify", response_model=VerifyOut)
def verify(db: DbSession, auth: Reader) -> VerifyOut:
    result = service.verify_chain(db)
    return VerifyOut(
        valid=result.valid,
        checked=result.checked,
        first_broken_seq=result.first_broken_seq,
        files_checked=result.files_checked,
        file_problems=[
            FileProblemOut(seq=p.seq, path=p.path, problem=p.problem) for p in result.file_problems
        ],
    )
