"""Perfil fiscal de la persona física: régimen RESIMPLE y «sin IRE».

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-26

Plan multiempresa, fase M6 (docs/specs/MULTI_ORG_PERSONA_FISICA.md; D-142). `tax.profiles.ire_regime`
admite `resimple` (IRE RESIMPLE, obligación 702) y `none` (la persona física sin IRE, con IRP o
IVA). Las reglas 715, 716, 956 y 702 son datos (D-084): no cambian el esquema.

Bajada: se niega si alguna versión del perfil usa `resimple` o `none` (D-080): no hay régimen
anterior al que pasarlas sin cambiar lo que declaró el contribuyente.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REGIME_CK = "ck_profiles_ire_regime_valid"
OLD_REGIMES = "ire_regime IN ('ire_general', 'ire_simple', 'unknown')"
NEW_REGIMES = "ire_regime IN ('ire_general', 'ire_simple', 'resimple', 'none', 'unknown')"


def upgrade() -> None:
    op.drop_constraint(op.f(REGIME_CK), "profiles", schema="tax", type_="check")
    op.create_check_constraint(op.f(REGIME_CK), "profiles", NEW_REGIMES, schema="tax")


def downgrade() -> None:
    used = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM tax.profiles WHERE ire_regime IN ('resimple', 'none')")
    )
    if used:
        raise RuntimeError(
            f"No se puede bajar la 0012: hay {used} versión(es) del perfil fiscal con el régimen "
            "RESIMPLE o «sin IRE». Bajarla cambiaría lo declarado; no se hace sola."
        )
    op.drop_constraint(op.f(REGIME_CK), "profiles", schema="tax", type_="check")
    op.create_check_constraint(op.f(REGIME_CK), "profiles", OLD_REGIMES, schema="tax")
