"""Modelos del esquema `marangatu` (migración 0007). Especificación: BOT_MARANGATU.md §4 y §5.

- `settings`: el interruptor general por organización. Por defecto, **bot apagado**.
- `task_stages`: la etapa de cada tipo de tarea (`reconocimiento`, `ensayo`, `habilitada`).
- `runs`: cada corrida (tipo, período, etapa, resultado y motivo de detención). Una corrida
  terminada no cambia más y ninguna se borra (trigger `runs_guard`).
- `steps`: el registro de pasos. **Solo agregar** (trigger) y en **cadena de hashes**: cada
  paso guarda el hash del anterior; la base lo calcula al insertar (como `audit.audit_logs`).
  Nunca guarda la clave: los valores escritos en el campo de la clave quedan como «[oculta]».
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.modules.marangatu.stop_codes import StopCode

SCHEMA = "marangatu"
STAGES = ("reconocimiento", "ensayo", "habilitada")
# Tipos de tarea (spec §4). `general` es el reconocimiento de todo el portal, que no es de un
# tipo en particular: solo existe en la etapa `reconocimiento`.
TASK_TYPES = ("consulta", "registro_comprobantes", "f120", "constancias", "ire")
RUN_TASK_TYPES = ("general", *TASK_TYPES)
RUN_STATUSES = ("en_curso", "completada", "detenida", "incierta")
STEP_RESULTS = ("ok", "detenido", "error")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))


def _organization() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("core.organizations.id", ondelete="RESTRICT"), nullable=False)


class BotSettings(TimestampMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("organization_id"), {"schema": SCHEMA})

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    bot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class TaskStage(TimestampMixin, Base):
    __tablename__ = "task_stages"
    __table_args__ = (
        UniqueConstraint("organization_id", "task_type"),
        CheckConstraint(_in("task_type", TASK_TYPES), name="task_type_valid"),
        CheckConstraint(_in("stage", STAGES), name="stage_valid"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False, server_default="reconocimiento")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(_in("task_type", RUN_TASK_TYPES), name="task_type_valid"),
        CheckConstraint(_in("stage", STAGES), name="stage_valid"),
        CheckConstraint(_in("status", RUN_STATUSES), name="status_valid"),
        CheckConstraint(
            f"stop_code IS NULL OR {_in('stop_code', tuple(c.value for c in StopCode))}",
            name="stop_code_valid",
        ),
        CheckConstraint("task_type <> 'general' OR stage = 'reconocimiento'", name="general_recon"),
        CheckConstraint("period IS NULL OR extract(day FROM period) = 1", name="period_month"),
        CheckConstraint("(status = 'en_curso') = (finished_at IS NULL)", name="finished"),
        CheckConstraint("(status = 'detenida') = (stop_code IS NOT NULL)", name="stop_reason"),
        # Una sola corrida en curso en toda la instalación: un solo navegador a la vez (D-140).
        # Se indexa `status` solo cuando es `en_curso`: dos filas en curso chocan, sea cual sea
        # la organización.
        Index(
            "uq_runs_one_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'en_curso'"),
        ),
        Index("ix_runs_org_started", "organization_id", "started_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization()
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    period: Mapped[date | None] = mapped_column(Date)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="en_curso")
    stop_code: Mapped[str | None] = mapped_column(String(30))
    # Detalle técnico del motivo (nunca la clave).
    stop_detail: Mapped[str | None] = mapped_column(String(500))
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.users.id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = (
        CheckConstraint(_in("result", STEP_RESULTS), name="result_valid"),
        CheckConstraint(
            "(capture_path IS NULL) = (capture_sha256 IS NULL)", name="capture_with_hash"
        ),
        CheckConstraint(
            "capture_sha256 IS NULL OR capture_sha256 ~ '^[0-9a-f]{64}$'", name="capture_sha256_hex"
        ),
        Index("ix_steps_run_seq", "run_id", "seq"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # La asigna el trigger con el candado de la cadena tomado: el orden de `seq` es el de la
    # cadena aunque haya transacciones concurrentes.
    seq: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, server_default=FetchedValue()
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("marangatu.runs.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = _organization()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    screen_id: Mapped[str | None] = mapped_column(String(80))
    screen_version: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result: Mapped[str] = mapped_column(String(12), nullable=False)
    message: Mapped[str | None] = mapped_column(String(1000))
    # Ruta relativa a la carpeta de datos de la app (almacén de documentos) y su SHA-256.
    capture_path: Mapped[str | None] = mapped_column(String(500))
    capture_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), server_default=FetchedValue())
    row_hash: Mapped[bytes] = mapped_column(
        LargeBinary(32), nullable=False, server_default=FetchedValue()
    )
