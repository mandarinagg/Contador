"""Autorización de la DNIT para una vida útil fiscal distinta de la categoría (D-125).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25

Agrega `accounting.fixed_assets.fiscal_life_authorization`: el número de la autorización
particular de la DNIT (Decreto 3182, art. 31, último párrafo) que permite a un bien una vida
útil o un residual fiscal distintos de los de su categoría. El servicio la exige en ese caso.

La bajada se niega si algún bien tiene una autorización cargada (mismo criterio que la 0004,
D-080): no se pierde nada en silencio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fixed_assets",
        sa.Column("fiscal_life_authorization", sa.String(length=100), nullable=True),
        schema="accounting",
    )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(
        sa.text(
            "SELECT count(*) FROM accounting.fixed_assets"
            " WHERE fiscal_life_authorization IS NOT NULL"
        )
    ).scalar_one()
    if used:
        raise RuntimeError(
            f"{used} bien(es) tienen una autorización de la DNIT para su vida útil fiscal: "
            "la bajada la perdería. Exportalas antes."
        )
    op.drop_column("fixed_assets", "fiscal_life_authorization", schema="accounting")
