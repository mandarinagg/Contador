"""Fundación: identidad, organizaciones, roles/permisos y auditoría inmutable.

Revision ID: 0001
Revises:
Create Date: 2026-11-23

Requiere PostgreSQL 18+ (uuidv7() y sha256() nativos).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.permissions import PERMISSION_DESCRIPTIONS, ROLE_INFO, ROLE_PERMISSIONS

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("CREATE SEQUENCE audit.audit_logs_seq AS bigint")
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_kind", sa.String(length=20), server_default="user", nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("prev_hash", sa.LargeBinary(length=32), nullable=True),
        sa.Column("row_hash", sa.LargeBinary(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        sa.UniqueConstraint("seq", name=op.f("uq_audit_logs_seq")),
        schema="audit",
    )
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "ix_audit_logs_org_seq",
        "audit_logs",
        ["organization_id", "seq"],
        unique=False,
        schema="audit",
    )
    op.create_table(
        "security_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("email_attempted", sa.String(length=254), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_events")),
        schema="audit",
    )
    op.create_index(
        "ix_security_events_occurred",
        "security_events",
        ["occurred_at"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "ix_security_events_user", "security_events", ["user_id"], unique=False, schema="audit"
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("trade_name", sa.String(length=200), nullable=True),
        sa.Column("legal_form", sa.String(length=20), nullable=False),
        sa.Column("ruc", sa.String(length=8), nullable=True),
        sa.Column("ruc_check_digit", sa.String(length=1), nullable=True),
        sa.Column("base_currency", sa.String(length=3), server_default="PYG", nullable=False),
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
        sa.CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$'", name=op.f("ck_organizations_base_currency_iso")
        ),
        sa.CheckConstraint(
            "legal_form IN ('EAS','SA','SRL','UNIPERSONAL','OTRA')",
            name=op.f("ck_organizations_legal_form_valid"),
        ),
        sa.CheckConstraint(
            "ruc IS NULL OR ruc ~ '^[0-9]{1,8}$'", name=op.f("ck_organizations_ruc_digits")
        ),
        sa.CheckConstraint(
            "ruc_check_digit IS NULL OR ruc_check_digit ~ '^[0-9]$'",
            name=op.f("ck_organizations_ruc_check_digit_digit"),
        ),
        sa.CheckConstraint(
            "(ruc IS NULL) = (ruc_check_digit IS NULL)", name=op.f("ck_organizations_ruc_complete")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        schema="core",
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_permissions")),
        schema="core",
    )
    op.create_table(
        "roles",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_roles")),
        schema="core",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_users_failed_login_count_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema="core",
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
        schema="core",
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_code", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_organization_members_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"], ["core.roles.code"], name=op.f("fk_organization_members_role_code_roles")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core.users.id"],
            name=op.f("fk_organization_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_members")),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name=op.f("uq_organization_members_organization_id_user_id"),
        ),
        schema="core",
    )
    op.create_index(
        op.f("ix_organization_members_user_id"),
        "organization_members",
        ["user_id"],
        unique=False,
        schema="core",
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(length=50), nullable=False),
        sa.Column("permission_code", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["core.permissions.code"],
            name=op.f("fk_role_permissions_permission_code_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["core.roles.code"],
            name=op.f("fk_role_permissions_role_code_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_code", "permission_code", name=op.f("pk_role_permissions")),
        schema="core",
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_user_sessions_expires_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_user_sessions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core.users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
        schema="core",
    )
    op.create_index(
        "ix_user_sessions_user_active",
        "user_sessions",
        ["user_id"],
        unique=False,
        schema="core",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    _create_audit_protection()
    _seed_roles_and_permissions()


AUDIT_SQL = r"""
-- Hash canónico de una fila de auditoría (lo usan el trigger y la verificación).
CREATE FUNCTION audit.log_row_hash(
    p_prev bytea, p_seq bigint, p_id uuid, p_occurred_at timestamptz,
    p_org uuid, p_actor uuid, p_actor_kind text, p_action text, p_entity_type text,
    p_entity_id text, p_before jsonb, p_after jsonb, p_request_id text
) RETURNS bytea LANGUAGE sql IMMUTABLE AS $$
  SELECT sha256(
    coalesce(p_prev, '\x'::bytea) || convert_to(concat_ws('|',
      p_seq::text, p_id::text,
      to_char(p_occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
      coalesce(p_org::text, '-'), coalesce(p_actor::text, '-'), p_actor_kind, p_action,
      p_entity_type, coalesce(p_entity_id, '-'), coalesce(p_before::text, '-'),
      coalesce(p_after::text, '-'), coalesce(p_request_id, '-')
    ), 'UTF8'))
$$;

-- Encadena cada fila nueva. El candado serializa las inserciones hasta el COMMIT,
-- así seq y la cadena siguen el mismo orden.
CREATE FUNCTION audit.chain_audit_log() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_prev bytea;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('audit.audit_logs.chain'));
  NEW.seq := nextval('audit.audit_logs_seq');
  NEW.occurred_at := coalesce(NEW.occurred_at, now());
  SELECT row_hash INTO v_prev FROM audit.audit_logs ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := v_prev;
  NEW.row_hash := audit.log_row_hash(v_prev, NEW.seq, NEW.id, NEW.occurred_at,
    NEW.organization_id, NEW.actor_user_id, NEW.actor_kind, NEW.action, NEW.entity_type,
    NEW.entity_id, NEW.before, NEW.after, NEW.request_id);
  RETURN NEW;
END $$;

CREATE TRIGGER audit_logs_chain BEFORE INSERT ON audit.audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit.chain_audit_log();

-- Solo inserción: ni la aplicación ni un usuario ordinario pueden alterar la auditoría.
CREATE FUNCTION audit.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La tabla %.% es de solo inserción (operación %)',
    TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER audit_logs_immutable BEFORE UPDATE OR DELETE ON audit.audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit.reject_change();
CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit.audit_logs
  FOR EACH STATEMENT EXECUTE FUNCTION audit.reject_change();
CREATE TRIGGER security_events_immutable BEFORE UPDATE OR DELETE ON audit.security_events
  FOR EACH ROW EXECUTE FUNCTION audit.reject_change();
CREATE TRIGGER security_events_no_truncate BEFORE TRUNCATE ON audit.security_events
  FOR EACH STATEMENT EXECUTE FUNCTION audit.reject_change();
"""


def _create_audit_protection() -> None:
    op.execute(AUDIT_SQL)


def _seed_roles_and_permissions() -> None:
    roles = sa.table(
        "roles", sa.column("code"), sa.column("name"), sa.column("description"), schema="core"
    )
    perms = sa.table("permissions", sa.column("code"), sa.column("description"), schema="core")
    links = sa.table(
        "role_permissions", sa.column("role_code"), sa.column("permission_code"), schema="core"
    )
    op.bulk_insert(
        perms, [{"code": p.value, "description": d} for p, d in PERMISSION_DESCRIPTIONS.items()]
    )
    op.bulk_insert(
        roles, [{"code": r.value, "name": n, "description": d} for r, (n, d) in ROLE_INFO.items()]
    )
    op.bulk_insert(
        links,
        [
            {"role_code": r.value, "permission_code": p.value}
            for r, ps in ROLE_PERMISSIONS.items()
            for p in sorted(ps)
        ],
    )


def downgrade() -> None:
    # Destructivo: elimina toda la auditoría. Solo para desarrollo (ver docs/DECISIONS.md).
    op.drop_index(
        "ix_user_sessions_user_active",
        table_name="user_sessions",
        schema="core",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_table("user_sessions", schema="core")
    op.drop_table("role_permissions", schema="core")
    op.drop_index(
        op.f("ix_organization_members_user_id"), table_name="organization_members", schema="core"
    )
    op.drop_table("organization_members", schema="core")
    op.drop_index("uq_users_email_lower", table_name="users", schema="core")
    op.drop_table("users", schema="core")
    op.drop_table("roles", schema="core")
    op.drop_table("permissions", schema="core")
    op.drop_table("organizations", schema="core")
    op.drop_index("ix_security_events_user", table_name="security_events", schema="audit")
    op.drop_index("ix_security_events_occurred", table_name="security_events", schema="audit")
    op.drop_table("security_events", schema="audit")
    op.drop_index("ix_audit_logs_org_seq", table_name="audit_logs", schema="audit")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs", schema="audit")
    op.drop_table("audit_logs", schema="audit")
    op.execute(
        "DROP FUNCTION audit.reject_change(); DROP FUNCTION audit.chain_audit_log();"
        " DROP FUNCTION audit.log_row_hash(bytea, bigint, uuid, timestamptz, uuid, uuid, text,"
        " text, text, text, jsonb, jsonb, text); DROP SEQUENCE audit.audit_logs_seq;"
    )
    op.execute("DROP SCHEMA audit; DROP SCHEMA core;")
