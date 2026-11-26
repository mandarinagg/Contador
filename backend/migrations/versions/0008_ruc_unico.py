"""RUC único entre las organizaciones de la instalación.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25

Plan multiempresa, fase M2 (docs/specs/MULTI_ORG_PERSONA_FISICA.md): una sola organización por
RUC (respuesta 1 del propietario; la clave de Marangatu es por RUC, D-128). Índice único parcial:
las organizaciones sin RUC no chocan entre sí (D-135).

La subida se niega con un mensaje claro si ya hay RUC repetidos: hay que corregirlos a mano
antes (no se elige por la persona cuál queda). La bajada solo borra el índice.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    repeated = bind.execute(
        sa.text(
            "SELECT ruc, count(*) FROM core.organizations WHERE ruc IS NOT NULL"
            " GROUP BY ruc HAVING count(*) > 1 ORDER BY ruc"
        )
    ).all()
    if repeated:
        listed = ", ".join(f"{ruc} ({count} organizaciones)" for ruc, count in repeated)
        raise RuntimeError(
            "No se puede aplicar la 0008: hay RUC repetidos entre organizaciones: "
            f"{listed}. Corregí el RUC de las que sobran y volvé a intentar."
        )
    op.create_index(
        "uq_organizations_ruc",
        "organizations",
        ["ruc"],
        unique=True,
        schema="core",
        postgresql_where=sa.text("ruc IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_organizations_ruc", table_name="organizations", schema="core")
