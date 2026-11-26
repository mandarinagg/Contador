"""Persona física como forma jurídica de una organización, con nombres y apellidos.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-26

Plan multiempresa, fase M4 (docs/specs/MULTI_ORG_PERSONA_FISICA.md; D-141). `legal_form` admite
`PERSONA_FISICA`; `first_names` y `last_names` son obligatorios para ella y nulos para las demás.
`legal_name` se sigue guardando (la calcula el servicio como «Apellidos, Nombres»). No hay columna
de cédula: el RUC de una persona física es su cédula más el DV (RG 79/2021).

Bajada: se niega si hay alguna persona física (D-080): no hay a qué forma convertirla sin perder
sus nombres.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FORM_CK = "ck_organizations_legal_form_valid"
NAMES_CK = "ck_organizations_person_names"
OLD_FORMS = "legal_form IN ('EAS','SA','SRL','UNIPERSONAL','OTRA')"
NEW_FORMS = "legal_form IN ('EAS','SA','SRL','UNIPERSONAL','PERSONA_FISICA','OTRA')"
NAMES_RULE = (
    "(legal_form = 'PERSONA_FISICA' AND first_names IS NOT NULL AND last_names IS NOT NULL)"
    " OR (legal_form <> 'PERSONA_FISICA' AND first_names IS NULL AND last_names IS NULL)"
)


def upgrade() -> None:
    op.add_column("organizations", sa.Column("first_names", sa.String(length=100)), schema="core")
    op.add_column("organizations", sa.Column("last_names", sa.String(length=100)), schema="core")
    op.drop_constraint(op.f(FORM_CK), "organizations", schema="core", type_="check")
    op.create_check_constraint(op.f(FORM_CK), "organizations", NEW_FORMS, schema="core")
    op.create_check_constraint(op.f(NAMES_CK), "organizations", NAMES_RULE, schema="core")


def downgrade() -> None:
    persons = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM core.organizations WHERE legal_form = 'PERSONA_FISICA'")
    )
    if persons:
        raise RuntimeError(
            f"No se puede bajar la 0011: hay {persons} organización(es) que son persona física. "
            "Bajarla perdería sus nombres y apellidos; no se hace sola."
        )
    op.drop_constraint(op.f(NAMES_CK), "organizations", schema="core", type_="check")
    op.drop_constraint(op.f(FORM_CK), "organizations", schema="core", type_="check")
    op.create_check_constraint(op.f(FORM_CK), "organizations", OLD_FORMS, schema="core")
    op.drop_column("organizations", "last_names", schema="core")
    op.drop_column("organizations", "first_names", schema="core")
