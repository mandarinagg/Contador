"""Una sola corrida del bot de Marangatu en curso en toda la instalación.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-26

Plan multiempresa, fase M5 (docs/specs/MULTI_ORG_PERSONA_FISICA.md, respuesta 4; D-140). El
índice único parcial `uq_runs_one_running` pasa de «una por organización» a «una en toda la
instalación»: se indexa `status` solo cuando es `en_curso`, así que dos filas en curso (de
cualquier organización) chocan. Hay un solo navegador y una sola PC.

Subida: si por alguna razón ya hay más de una corrida en curso (p. ej. una bajada y una subida
con la app cerrada a medias), se deja la más antigua y las demás se cierran como `BROWSER_ERROR`
con un paso «interrumpida» en el registro de su organización, igual que hace la app al arrancar.
Ninguna corrida se borra ni se reescribe fuera de lo que `runs_guard` permite.

Bajada: vuelve al índice por organización, que es más permisivo: siempre se puede.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_runs_one_running"
# Las que sobran: todas las en curso menos la más antigua (la que ganó el turno).
CLOSE_EXTRA_SQL = """
WITH extra AS (
  SELECT id, organization_id FROM marangatu.runs
  WHERE status = 'en_curso'
    AND id <> (SELECT id FROM marangatu.runs WHERE status = 'en_curso'
               ORDER BY started_at, id LIMIT 1)
), stepped AS (
  INSERT INTO marangatu.steps (run_id, organization_id, action, result, message)
  SELECT id, organization_id, 'interrumpida', 'error', 'La app se cerró durante la corrida'
  FROM extra
  RETURNING run_id
)
UPDATE marangatu.runs SET status = 'detenida', stop_code = 'BROWSER_ERROR',
  stop_detail = 'Corrida interrumpida: la app se cerró antes de terminar', finished_at = now()
WHERE id IN (SELECT id FROM extra)
"""


def upgrade() -> None:
    op.execute(CLOSE_EXTRA_SQL)
    op.drop_index(
        INDEX,
        table_name="runs",
        schema="marangatu",
        postgresql_where=sa.text("status = 'en_curso'"),
    )
    op.create_index(
        INDEX,
        "runs",
        ["status"],
        unique=True,
        schema="marangatu",
        postgresql_where=sa.text("status = 'en_curso'"),
    )


def downgrade() -> None:
    op.drop_index(
        INDEX,
        table_name="runs",
        schema="marangatu",
        postgresql_where=sa.text("status = 'en_curso'"),
    )
    op.create_index(
        INDEX,
        "runs",
        ["organization_id"],
        unique=True,
        schema="marangatu",
        postgresql_where=sa.text("status = 'en_curso'"),
    )
