"""Activo o desactivado por organización, no en toda la cuenta.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25

Plan multiempresa, fase M2 (D-137). Con un usuario en varias organizaciones, desactivarlo en una
no puede dejarlo afuera de las demás (ni dejar a otra sin propietario activo). Se agrega
`organization_members.is_active`; el valor de cada usuario pasa a sus membresías y
`users.is_active` vuelve a `true` (queda como interruptor de toda la cuenta, sin API).

La bajada se niega si algún usuario está activo en una organización y desactivado en otra:
volver a un solo valor lo activaría donde lo desactivaron. Si no, el usuario queda desactivado
cuando no tiene ninguna membresía activa.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_members",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema="core",
    )
    op.execute(
        "UPDATE core.organization_members m SET is_active = u.is_active"
        " FROM core.users u WHERE u.id = m.user_id AND NOT u.is_active"
    )
    op.execute("UPDATE core.users SET is_active = true WHERE NOT is_active")


def downgrade() -> None:
    bind = op.get_bind()
    mixed = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT user_id FROM core.organization_members"
            " GROUP BY user_id HAVING bool_or(is_active) AND NOT bool_and(is_active)) s"
        )
    ).scalar_one()
    if mixed:
        raise RuntimeError(
            f"No se puede volver a la 0008: hay {mixed} usuario(s) activos en una organización y "
            "desactivados en otra; con un solo valor quedarían activos donde los desactivaron."
        )
    op.execute(
        "UPDATE core.users u SET is_active = false WHERE NOT EXISTS ("
        "SELECT 1 FROM core.organization_members m WHERE m.user_id = u.id AND m.is_active)"
        " AND EXISTS (SELECT 1 FROM core.organization_members m WHERE m.user_id = u.id)"
    )
    op.drop_column("organization_members", "is_active", schema="core")
