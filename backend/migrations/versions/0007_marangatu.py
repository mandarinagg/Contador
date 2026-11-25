"""Bot de Marangatu, B1 (esquema `marangatu`): interruptor, etapas, corridas y registro de pasos.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-25

Especificación: docs/specs/BOT_MARANGATU.md §4, §5 y §10 (B1); D-127 en adelante.
- `settings`: el interruptor general por organización (por defecto, bot apagado).
- `task_stages`: la etapa de cada tipo de tarea.
- `runs`: las corridas. Ninguna se borra; una terminada no cambia más (`runs_guard`).
- `steps`: el registro de pasos, **solo agregar** (`steps_immutable`, también contra TRUNCATE)
  y en **cadena de hashes**: el trigger `steps_chain` toma un candado, asigna `seq`, guarda el
  hash del paso anterior y calcula el propio con `marangatu.step_row_hash` (que también usa la
  verificación). Res. 568/2006, art. 10: se conserva sin modificar durante la prescripción.

Sin permisos nuevos: usa los de tributación (D-130).

La bajada se niega si hay corridas (D-080): el registro no se pierde en silencio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copias congeladas (una migración no importa el código vivo).
STAGES = ("reconocimiento", "ensayo", "habilitada")
TASK_TYPES = ("consulta", "registro_comprobantes", "f120", "constancias", "ire")
RUN_TASK_TYPES = ("general", *TASK_TYPES)
RUN_STATUSES = ("en_curso", "completada", "detenida", "incierta")
STEP_RESULTS = ("ok", "detenido", "error")
STOP_CODES = (
    "RULE_PENDING",
    "PROFILE_MISMATCH",
    "LEDGER_MISMATCH",
    "DATA_INCOMPLETE",
    "ALREADY_FILED",
    "READBACK_MISMATCH",
    "UNKNOWN_SCREEN",
    "LOGIN_FAILED",
    "CAPTCHA",
    "NO_RECEIPT",
    "RECEIPT_MISMATCH",
    "TOO_LATE",
    "BOT_OFF",
    "NOT_ENABLED",
    "NO_CREDENTIALS",
    "BROWSER_ERROR",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


MARANGATU_SQL = r"""
-- Hash canónico de un paso (lo usan el trigger y la verificación).
CREATE FUNCTION marangatu.step_row_hash(
    p_prev bytea, p_seq bigint, p_id uuid, p_run uuid, p_org uuid, p_occurred_at timestamptz,
    p_screen_id text, p_screen_version integer, p_action text, p_values jsonb, p_result text,
    p_message text, p_capture_path text, p_capture_sha256 text
) RETURNS bytea LANGUAGE sql IMMUTABLE AS $$
  SELECT sha256(
    coalesce(p_prev, '\x'::bytea) || convert_to(concat_ws('|',
      p_seq::text, p_id::text, p_run::text, p_org::text,
      to_char(p_occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
      coalesce(p_screen_id, '-'), coalesce(p_screen_version::text, '-'), p_action,
      p_values::text, p_result, coalesce(p_message, '-'), coalesce(p_capture_path, '-'),
      coalesce(p_capture_sha256, '-')
    ), 'UTF8'))
$$;

-- Encadena cada paso nuevo. El candado serializa las inserciones hasta el COMMIT, así `seq`
-- y la cadena siguen el mismo orden.
CREATE FUNCTION marangatu.chain_step() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_prev bytea;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('marangatu.steps.chain'));
  NEW.seq := nextval('marangatu.steps_seq');
  NEW.occurred_at := coalesce(NEW.occurred_at, now());
  SELECT row_hash INTO v_prev FROM marangatu.steps ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := v_prev;
  NEW.row_hash := marangatu.step_row_hash(v_prev, NEW.seq, NEW.id, NEW.run_id,
    NEW.organization_id, NEW.occurred_at, NEW.screen_id, NEW.screen_version, NEW.action,
    NEW.values, NEW.result, NEW.message, NEW.capture_path, NEW.capture_sha256);
  RETURN NEW;
END $$;

CREATE TRIGGER steps_chain BEFORE INSERT ON marangatu.steps
  FOR EACH ROW EXECUTE FUNCTION marangatu.chain_step();

-- Solo agregar, como `audit.audit_logs` y los asientos contabilizados.
CREATE FUNCTION marangatu.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La tabla %.% es de solo inserción (operación %)',
    TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
    USING ERRCODE = '23000', CONSTRAINT = 'trg_steps_append_only';
END $$;

CREATE TRIGGER steps_immutable BEFORE UPDATE OR DELETE ON marangatu.steps
  FOR EACH ROW EXECUTE FUNCTION marangatu.reject_change();
CREATE TRIGGER steps_no_truncate BEFORE TRUNCATE ON marangatu.steps
  FOR EACH STATEMENT EXECUTE FUNCTION marangatu.reject_change();

-- Una corrida no se borra; mientras está en curso solo cambia su resultado, y una vez
-- terminada no cambia más.
CREATE FUNCTION marangatu.runs_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Las corridas del bot no se borran'
      USING ERRCODE = '23000', CONSTRAINT = 'trg_runs_no_delete';
  END IF;
  IF OLD.status <> 'en_curso' THEN
    RAISE EXCEPTION 'La corrida % ya terminó y no se modifica', OLD.id
      USING ERRCODE = '23000', CONSTRAINT = 'trg_runs_finished_fixed';
  END IF;
  IF NEW.id <> OLD.id OR NEW.organization_id <> OLD.organization_id
     OR NEW.task_type <> OLD.task_type OR NEW.stage <> OLD.stage
     OR NEW.period IS DISTINCT FROM OLD.period OR NEW.started_at <> OLD.started_at
     OR NEW.started_by IS DISTINCT FROM OLD.started_by THEN
    RAISE EXCEPTION 'Solo cambia el resultado de una corrida en curso'
      USING ERRCODE = '23000', CONSTRAINT = 'trg_runs_identity_fixed';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER runs_guard BEFORE UPDATE OR DELETE ON marangatu.runs
  FOR EACH ROW EXECUTE FUNCTION marangatu.runs_guard();
CREATE TRIGGER runs_no_truncate BEFORE TRUNCATE ON marangatu.runs
  FOR EACH STATEMENT EXECUTE FUNCTION marangatu.reject_change();
"""

DROP_MARANGATU_SQL = """
DROP TRIGGER runs_no_truncate ON marangatu.runs;
DROP TRIGGER runs_guard ON marangatu.runs;
DROP TRIGGER steps_no_truncate ON marangatu.steps;
DROP TRIGGER steps_immutable ON marangatu.steps;
DROP TRIGGER steps_chain ON marangatu.steps;
"""


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA marangatu")
    op.create_table(
        "settings",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("bot_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_settings_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_settings_organization_id")),
        schema="marangatu",
    )
    op.create_table(
        "task_stages",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=20), server_default="reconocimiento", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(_in("stage", STAGES), name=op.f("ck_task_stages_stage_valid")),
        sa.CheckConstraint(
            _in("task_type", TASK_TYPES), name=op.f("ck_task_stages_task_type_valid")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_task_stages_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_stages")),
        sa.UniqueConstraint(
            "organization_id", "task_type", name=op.f("uq_task_stages_organization_id_task_type")
        ),
        schema="marangatu",
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=30), nullable=False),
        sa.Column("period", sa.Date(), nullable=True),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="en_curso", nullable=False),
        sa.Column("stop_code", sa.String(length=30), nullable=True),
        sa.Column("stop_detail", sa.String(length=500), nullable=True),
        sa.Column("started_by", sa.UUID(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'detenida') = (stop_code IS NOT NULL)", name=op.f("ck_runs_stop_reason")
        ),
        sa.CheckConstraint(
            "(status = 'en_curso') = (finished_at IS NULL)", name=op.f("ck_runs_finished")
        ),
        sa.CheckConstraint(
            "period IS NULL OR extract(day FROM period) = 1", name=op.f("ck_runs_period_month")
        ),
        sa.CheckConstraint(
            "task_type <> 'general' OR stage = 'reconocimiento'", name=op.f("ck_runs_general_recon")
        ),
        sa.CheckConstraint(_in("stage", STAGES), name=op.f("ck_runs_stage_valid")),
        sa.CheckConstraint(_in("status", RUN_STATUSES), name=op.f("ck_runs_status_valid")),
        sa.CheckConstraint(
            f"stop_code IS NULL OR {_in('stop_code', STOP_CODES)}",
            name=op.f("ck_runs_stop_code_valid"),
        ),
        sa.CheckConstraint(_in("task_type", RUN_TASK_TYPES), name=op.f("ck_runs_task_type_valid")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_runs_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["core.users.id"],
            name=op.f("fk_runs_started_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        schema="marangatu",
    )
    op.create_index(
        "ix_runs_org_started", "runs", ["organization_id", "started_at"], schema="marangatu"
    )
    op.create_index(
        "uq_runs_one_running",
        "runs",
        ["organization_id"],
        unique=True,
        schema="marangatu",
        postgresql_where=sa.text("status = 'en_curso'"),
    )
    op.execute("CREATE SEQUENCE marangatu.steps_seq")
    op.create_table(
        "steps",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("screen_id", sa.String(length=80), nullable=True),
        sa.Column("screen_version", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column(
            "values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=12), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column("capture_path", sa.String(length=500), nullable=True),
        sa.Column("capture_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("prev_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("row_hash", sa.LargeBinary(length=32), nullable=False),
        sa.CheckConstraint(
            "(capture_path IS NULL) = (capture_sha256 IS NULL)",
            name=op.f("ck_steps_capture_with_hash"),
        ),
        sa.CheckConstraint(
            "capture_sha256 IS NULL OR capture_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_steps_capture_sha256_hex"),
        ),
        sa.CheckConstraint(_in("result", STEP_RESULTS), name=op.f("ck_steps_result_valid")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_steps_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["marangatu.runs.id"],
            name=op.f("fk_steps_run_id_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_steps")),
        sa.UniqueConstraint("seq", name=op.f("uq_steps_seq")),
        schema="marangatu",
    )
    op.create_index("ix_steps_run_seq", "steps", ["run_id", "seq"], schema="marangatu")
    op.execute(MARANGATU_SQL)


def downgrade() -> None:
    # El registro de las corridas se conserva durante la prescripción (Res. 568/2006,
    # art. 10): la bajada se niega si hay alguna (D-080). Sin corridas, el interruptor y las
    # etapas se pierden (se vuelven a configurar al subir).
    bind = op.get_bind()
    runs = bind.execute(sa.text("SELECT count(*) FROM marangatu.runs")).scalar_one()
    if runs:
        raise RuntimeError(
            f"No se puede volver a la 0006: hay {runs} corrida(s) del bot de Marangatu, y su "
            "registro se conserva sin modificar durante la prescripción."
        )
    op.execute(DROP_MARANGATU_SQL)
    op.drop_index("ix_steps_run_seq", table_name="steps", schema="marangatu")
    op.drop_table("steps", schema="marangatu")
    op.execute("DROP SEQUENCE marangatu.steps_seq")
    op.drop_index(
        "uq_runs_one_running",
        table_name="runs",
        schema="marangatu",
        postgresql_where=sa.text("status = 'en_curso'"),
    )
    op.drop_index("ix_runs_org_started", table_name="runs", schema="marangatu")
    op.drop_table("runs", schema="marangatu")
    op.drop_table("task_stages", schema="marangatu")
    op.drop_table("settings", schema="marangatu")
    op.execute(
        "DROP FUNCTION marangatu.runs_guard();"
        " DROP FUNCTION marangatu.reject_change();"
        " DROP FUNCTION marangatu.chain_step();"
        " DROP FUNCTION marangatu.step_row_hash(bytea, bigint, uuid, uuid, uuid, timestamptz,"
        " text, integer, text, jsonb, text, text, text, text);"
    )
    op.execute("DROP SCHEMA marangatu")
