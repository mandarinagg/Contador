"""Tributación (núcleo): perfil fiscal, reglas versionadas, feriados y excepciones de
calendario, obligaciones, comprobantes y configuración (esquema `tax`).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-24

Especificación: docs/specs/FASE4_TRIBUTACION.md (D-082 a D-095; D-096 en adelante en
docs/DECISIONS.md). Escrita a mano sobre un borrador autogenerado. Además de las tablas:
- `tax.ruc_check_digit(text)`: el dígito verificador módulo 11 (el mismo algoritmo que
  `app/modules/organizations/ruc.py`), que usan los CHECK del RUC de la contraparte y del
  CDC de los comprobantes. Va antes de las tablas.
- Triggers en PL/pgSQL (`TAX_TRIGGERS_SQL`), la última defensa: reglas inmutables salvo el
  estado (`rule_versions_guard`), transiciones de las obligaciones y lo presentado fijo
  (`obligations_guard`), bloqueo del mes con el registro confirmado
  (`vouchers_period_lock`), comprobantes que no se borran (`vouchers_no_delete`) y, además,
  el perfil verificado fijo, los feriados que corrieron un vencimiento presentado y «nunca
  dos asientos vivos para el mismo hecho» (BR-TAX-10) en los dos sentidos, incluido un
  trigger nuevo en `accounting.journal_entries` (`journal_entries_voucher_guard`).
- Permisos `tax.read`, `tax.manage` y `tax.verify` (D-094).

La bajada se niega si hay comprobantes (aunque estén anulados) u obligaciones presentadas
o pagadas, como la de la 0004 (D-080): no se pierde nada en silencio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copia congelada de lo que agrega esta migración al catálogo (`app/core/permissions.py`,
# D-031): una migración no importa el catálogo vivo. Una prueba verifica catálogo = base.
TAX_PERMISSIONS: dict[str, str] = {
    "tax.read": "Ver la tributación: perfil fiscal, reglas, calendario, comprobantes, IVA y avisos",
    "tax.manage": "Cargar el perfil declarado, comprobantes, obligaciones, feriados, "
    "excepciones y la configuración tributaria",
    "tax.verify": "Verificar reglas tributarias y el perfil fiscal, y deprecar reglas",
}
# D-094: el administrador gestiona pero no verifica; consulta solo lee.
TAX_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": ("tax.read", "tax.manage", "tax.verify"),
    "admin": ("tax.read", "tax.manage"),
    "accountant": ("tax.read", "tax.manage", "tax.verify"),
    "viewer": ("tax.read",),
}

RUC_CHECK_DIGIT_SQL = r"""
-- Dígito verificador módulo 11 de la SET: cada dígito, de derecha a izquierda, por un peso
-- de 2 a 11 que vuelve a 2; con el resto de la suma entre 11, el dígito es 11 - resto, o 0
-- si el resto es 0 o 1. Igual que `app/modules/organizations/ruc.py`, que es el port de
-- `setCheckDigit` del proyecto de facturación (Manual Técnico SIFEN v150). Para algo que
-- no son dígitos devuelve -1, así el CHECK que lo compara falla.
CREATE FUNCTION tax.ruc_check_digit(p_digits text) RETURNS integer
  LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
  v_total integer := 0;
  v_weight integer := 2;
  v_rest integer;
BEGIN
  IF p_digits !~ '^[0-9]+$' THEN
    RETURN -1;
  END IF;
  FOR i IN REVERSE length(p_digits)..1 LOOP
    v_total := v_total + substr(p_digits, i, 1)::integer * v_weight;
    v_weight := CASE WHEN v_weight = 11 THEN 2 ELSE v_weight + 1 END;
  END LOOP;
  v_rest := v_total % 11;
  RETURN CASE WHEN v_rest > 1 THEN 11 - v_rest ELSE 0 END;
END $$;
"""

TAX_TRIGGERS_SQL = r"""
-- Todas las violaciones usan SQLSTATE 23000 (integrity_constraint_violation) y un nombre
-- estable en CONSTRAINT (`trg_*`), como en `accounting`.

-- Rechazo genérico del borrado (por fila) y del TRUNCATE.
CREATE FUNCTION tax.reject_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'En %.% no se borra nada (operación %)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'integrity_constraint_violation',
          CONSTRAINT = 'trg_' || TG_TABLE_NAME || '_no_delete';
END $$;

-- Reglas (D-084): una versión nace pendiente y no se edita; solo cambian el estado y los
-- datos de la revisión, en las transiciones pending → verified, pending → deprecated y
-- verified → deprecated (que conserva la revisión). No se borran.
CREATE FUNCTION tax.rule_versions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_state text[] := ARRAY['validation_status', 'reviewed_by_name', 'reviewed_reference',
                          'reviewed_at', 'review_note', 'deprecation_reason', 'deprecated_at',
                          'updated_at'];
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.validation_status <> 'pending' THEN
      RAISE EXCEPTION 'Una versión de regla nace pendiente de verificación'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_rule_versions_born_pending';
    END IF;
    RETURN NEW;
  END IF;
  IF (to_jsonb(NEW) - v_state) <> (to_jsonb(OLD) - v_state) THEN
    RAISE EXCEPTION 'La versión % de % no se edita: un cambio es una versión nueva',
      OLD.version, OLD.code
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_rule_versions_immutable';
  END IF;
  IF NEW.validation_status = OLD.validation_status THEN
    IF (NEW.reviewed_by_name, NEW.reviewed_reference, NEW.reviewed_at, NEW.review_note,
        NEW.deprecation_reason, NEW.deprecated_at)
       IS DISTINCT FROM (OLD.reviewed_by_name, OLD.reviewed_reference, OLD.reviewed_at,
                         OLD.review_note, OLD.deprecation_reason, OLD.deprecated_at) THEN
      RAISE EXCEPTION 'La revisión de la versión % de % no cambia sin cambiar de estado',
        OLD.version, OLD.code
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_rule_versions_invalid_transition';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT ((OLD.validation_status = 'pending' AND NEW.validation_status IN ('verified', 'deprecated'))
          OR (OLD.validation_status = 'verified' AND NEW.validation_status = 'deprecated')) THEN
    RAISE EXCEPTION 'Una regla no pasa de % a %', OLD.validation_status, NEW.validation_status
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_rule_versions_invalid_transition';
  END IF;
  IF OLD.validation_status = 'verified'
     AND (NEW.reviewed_by_name, NEW.reviewed_reference, NEW.reviewed_at, NEW.review_note)
         IS DISTINCT FROM (OLD.reviewed_by_name, OLD.reviewed_reference, OLD.reviewed_at,
                           OLD.review_note) THEN
    RAISE EXCEPTION 'Deprecar una regla verificada conserva su revisión'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_rule_versions_invalid_transition';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER rule_versions_guard BEFORE INSERT OR UPDATE ON tax.rule_versions
  FOR EACH ROW EXECUTE FUNCTION tax.rule_versions_guard();
CREATE TRIGGER rule_versions_no_delete BEFORE DELETE ON tax.rule_versions
  FOR EACH ROW EXECUTE FUNCTION tax.reject_delete();
CREATE TRIGGER rule_versions_no_truncate BEFORE TRUNCATE ON tax.rule_versions
  FOR EACH STATEMENT EXECUTE FUNCTION tax.reject_delete();

-- Obligaciones (D-087, BR-TAX-06): nacen pendientes; transiciones pending → filed → paid,
-- pending → not_applicable, filed → pending (reabrir) y not_applicable → pending solo si la
-- marcó el sistema (D-098). Una presentada o pagada no cambia su vencimiento, su regla, su
-- excepción ni su estimado, y lo presentado y lo pagado no se reescriben. No se borran.
CREATE FUNCTION tax.obligations_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending' THEN
      RAISE EXCEPTION 'Una obligación nace pendiente'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_obligations_born_pending';
    END IF;
    RETURN NEW;
  END IF;
  IF (NEW.organization_id, NEW.code, NEW.dnit_code, NEW.period_start, NEW.period_end)
     IS DISTINCT FROM (OLD.organization_id, OLD.code, OLD.dnit_code, OLD.period_start,
                       OLD.period_end) THEN
    RAISE EXCEPTION 'La obligación % del período % no cambia de código ni de período',
      OLD.code, OLD.period_start
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_obligations_identity_fixed';
  END IF;
  IF NEW.status <> OLD.status AND NOT (
       (OLD.status = 'pending' AND NEW.status IN ('filed', 'not_applicable'))
    OR (OLD.status = 'filed' AND NEW.status IN ('paid', 'pending'))
    OR (OLD.status = 'not_applicable' AND NEW.status = 'pending' AND OLD.not_applicable_auto)) THEN
    RAISE EXCEPTION 'Una obligación no pasa de % a %', OLD.status, NEW.status
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_obligations_invalid_transition';
  END IF;
  IF OLD.status IN ('filed', 'paid') AND (
       (NEW.nominal_due_date, NEW.due_date, NEW.rule_version_id, NEW.calendar_rule_version_id,
        NEW.exception_id, NEW.calculated_amount, NEW.calculated_credit_balance)
       IS DISTINCT FROM (OLD.nominal_due_date, OLD.due_date, OLD.rule_version_id,
                         OLD.calendar_rule_version_id, OLD.exception_id, OLD.calculated_amount,
                         OLD.calculated_credit_balance)
    OR (NEW.status IN ('filed', 'paid')
        AND (NEW.filed_on, NEW.filing_reference, NEW.declared_amount, NEW.declared_credit_balance)
            IS DISTINCT FROM (OLD.filed_on, OLD.filing_reference, OLD.declared_amount,
                              OLD.declared_credit_balance))
    OR (OLD.status = 'paid'
        AND (NEW.paid_on, NEW.paid_amount, NEW.payment_transaction_id)
            IS DISTINCT FROM (OLD.paid_on, OLD.paid_amount, OLD.payment_transaction_id))) THEN
    RAISE EXCEPTION 'La obligación % del período % está %: no cambia su vencimiento, su regla '
      'ni lo presentado', OLD.code, OLD.period_start, OLD.status
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_obligations_filed_fixed';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER obligations_guard BEFORE INSERT OR UPDATE ON tax.obligations
  FOR EACH ROW EXECUTE FUNCTION tax.obligations_guard();
CREATE TRIGGER obligations_no_delete BEFORE DELETE ON tax.obligations
  FOR EACH ROW EXECUTE FUNCTION tax.reject_delete();
CREATE TRIGGER obligations_no_truncate BEFORE TRUNCATE ON tax.obligations
  FOR EACH STATEMENT EXECUTE FUNCTION tax.reject_delete();

-- Perfil (D-083): nace declarado y solo si la organización tiene RUC; la verificación
-- cambia solo el origen y sus datos; un perfil verificado (y sus obligaciones) no cambia.
-- No se borra.
CREATE FUNCTION tax.profiles_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_verification text[] := ARRAY['origin', 'verified_by_name', 'verified_license',
                                 'verified_document_reference', 'verified_at', 'verified_by',
                                 'updated_at'];
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.origin <> 'declared' THEN
      RAISE EXCEPTION 'Un perfil fiscal nace declarado; después lo verifica un contador'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_profiles_born_declared';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM core.organizations
                    WHERE id = NEW.organization_id AND ruc IS NOT NULL
                      AND ruc_check_digit IS NOT NULL) THEN
      RAISE EXCEPTION 'La organización no tiene RUC: sin RUC no hay perfil fiscal'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_profiles_ruc_required';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.origin = 'verified' AND (to_jsonb(NEW) - 'updated_at') <> (to_jsonb(OLD) - 'updated_at') THEN
    RAISE EXCEPTION 'El perfil fiscal desde % está verificado: no cambia (cargá una versión nueva)',
      OLD.valid_from
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_profiles_verified_final';
  END IF;
  IF NEW.origin = 'verified' AND (to_jsonb(NEW) - v_verification) <> (to_jsonb(OLD) - v_verification) THEN
    RAISE EXCEPTION 'La verificación del perfil no cambia sus datos'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_profiles_verified_final';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION tax.profile_obligations_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM tax.profiles
              WHERE origin = 'verified'
                AND id IN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.profile_id END,
                           CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE NEW.profile_id END)) THEN
    RAISE EXCEPTION 'Las obligaciones de un perfil verificado no cambian'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_profile_obligations_verified_final';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER profiles_guard BEFORE INSERT OR UPDATE ON tax.profiles
  FOR EACH ROW EXECUTE FUNCTION tax.profiles_guard();
CREATE TRIGGER profiles_no_delete BEFORE DELETE ON tax.profiles
  FOR EACH ROW EXECUTE FUNCTION tax.reject_delete();
CREATE TRIGGER profiles_no_truncate BEFORE TRUNCATE ON tax.profiles
  FOR EACH STATEMENT EXECUTE FUNCTION tax.reject_delete();
CREATE TRIGGER profile_obligations_guard BEFORE INSERT OR UPDATE OR DELETE
  ON tax.profile_obligations
  FOR EACH ROW EXECUTE FUNCTION tax.profile_obligations_guard();

-- Feriados (D-086): uno que corrió un vencimiento ya presentado no se borra ni cambia de día.
CREATE FUNCTION tax.holidays_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (TG_OP = 'DELETE' OR NEW.day IS DISTINCT FROM OLD.day) AND EXISTS (
       SELECT 1 FROM tax.obligations
        WHERE status IN ('filed', 'paid') AND exception_id IS NULL
          AND nominal_due_date <= OLD.day AND due_date > OLD.day) THEN
    RAISE EXCEPTION 'El feriado del % corrió un vencimiento ya presentado', OLD.day
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_holidays_in_use';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

CREATE TRIGGER holidays_guard BEFORE UPDATE OR DELETE ON tax.holidays
  FOR EACH ROW EXECUTE FUNCTION tax.holidays_guard();

-- Excepciones de calendario: no se borran (se desactivan).
CREATE TRIGGER due_date_exceptions_no_delete BEFORE DELETE ON tax.due_date_exceptions
  FOR EACH ROW EXECUTE FUNCTION tax.reject_delete();
CREATE TRIGGER due_date_exceptions_no_truncate BEFORE TRUNCATE ON tax.due_date_exceptions
  FOR EACH STATEMENT EXECUTE FUNCTION tax.reject_delete();

-- Bloqueo del período confirmado (D-089, BR-TAX-08): con el REG-COMPROB-MENSUAL del mes
-- presentado, los comprobantes del mes no se crean, modifican ni anulan. Al mover uno de
-- mes cuentan los dos meses. Lo único que se puede tocar es el vínculo con su asiento
-- (`journal_entry_id`), que no cambia lo registrado. La fila de la obligación se lee
-- `FOR SHARE`: si otra transacción la está confirmando, se espera y se ve el estado final
-- (y al revés, confirmar espera a que termine el alta del comprobante).
CREATE FUNCTION tax.vouchers_period_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_ignored text[] := ARRAY['journal_entry_id', 'updated_at'];
  v_month date;
  v_status text;
BEGIN
  IF TG_OP = 'UPDATE' AND (to_jsonb(NEW) - v_ignored) = (to_jsonb(OLD) - v_ignored) THEN
    RETURN NEW;
  END IF;
  FOR v_month IN
    SELECT DISTINCT date_trunc('month', d)::date
      FROM unnest(CASE WHEN TG_OP = 'UPDATE' THEN ARRAY[OLD.issued_on, NEW.issued_on]
                       ELSE ARRAY[NEW.issued_on] END) AS d
  LOOP
    SELECT status INTO v_status FROM tax.obligations
     WHERE organization_id = NEW.organization_id AND code = 'REG-COMPROB-MENSUAL'
       AND period_start = v_month
     FOR SHARE;
    IF v_status IN ('filed', 'paid') THEN
      RAISE EXCEPTION 'El registro de comprobantes de % está confirmado: reabrilo para cambiar '
        'sus comprobantes', to_char(v_month, 'MM/YYYY')
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_vouchers_period_locked';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

-- Comprobantes (D-088, D-091): uno anulado no cambia (salvo su asiento); una nota va con un
-- comprobante original de la misma contraparte; y si el comprobante tiene asiento vivo, su
-- movimiento vinculado no tiene otro (BR-TAX-10).
CREATE FUNCTION tax.vouchers_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_ignored text[] := ARRAY['journal_entry_id', 'updated_at'];
  v_original tax.vouchers%ROWTYPE;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.voided_at IS NOT NULL
     AND (to_jsonb(NEW) - v_ignored) <> (to_jsonb(OLD) - v_ignored) THEN
    RAISE EXCEPTION 'El comprobante % está anulado: no cambia', OLD.number
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_vouchers_voided_final';
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.organization_id, NEW.context_id, NEW.direction)
     IS DISTINCT FROM (OLD.organization_id, OLD.context_id, OLD.direction) THEN
    RAISE EXCEPTION 'Un comprobante no cambia de organización ni de dirección'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_vouchers_identity_fixed';
  END IF;
  IF NEW.related_voucher_id IS NOT NULL THEN
    SELECT * INTO v_original FROM tax.vouchers WHERE id = NEW.related_voucher_id;
    IF v_original.voucher_type <> 'invoice'
       OR (v_original.counterparty_doc_type, v_original.counterparty_ruc,
           v_original.counterparty_document)
          IS DISTINCT FROM (NEW.counterparty_doc_type, NEW.counterparty_ruc,
                            NEW.counterparty_document) THEN
      RAISE EXCEPTION 'La nota % no corresponde a una factura de la misma contraparte',
        NEW.number
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_vouchers_note_mismatch';
    END IF;
  END IF;
  IF NEW.journal_entry_id IS NOT NULL AND NEW.transaction_id IS NOT NULL
     AND EXISTS (SELECT 1 FROM accounting.journal_entries
                  WHERE id = NEW.journal_entry_id AND status IN ('draft', 'posted'))
     AND EXISTS (SELECT 1 FROM accounting.journal_entries
                  WHERE source_transaction_id = NEW.transaction_id
                    AND status IN ('draft', 'posted') AND id <> NEW.journal_entry_id) THEN
    RAISE EXCEPTION 'El movimiento vinculado ya tiene otro asiento vivo'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_vouchers_transaction_has_entry';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER vouchers_guard BEFORE INSERT OR UPDATE ON tax.vouchers
  FOR EACH ROW EXECUTE FUNCTION tax.vouchers_guard();
CREATE TRIGGER vouchers_period_lock BEFORE INSERT OR UPDATE ON tax.vouchers
  FOR EACH ROW EXECUTE FUNCTION tax.vouchers_period_lock();
CREATE TRIGGER vouchers_no_delete BEFORE DELETE ON tax.vouchers
  FOR EACH ROW EXECUTE FUNCTION tax.reject_delete();
CREATE TRIGGER vouchers_no_truncate BEFORE TRUNCATE ON tax.vouchers
  FOR EACH STATEMENT EXECUTE FUNCTION tax.reject_delete();

-- BR-TAX-10 desde la contabilidad: un asiento nuevo de un movimiento no nace si un
-- comprobante vinculado a ese movimiento ya tiene asiento vivo.
CREATE FUNCTION tax.journal_entries_voucher_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.source_transaction_id IS NOT NULL AND NEW.status IN ('draft', 'posted') AND EXISTS (
       SELECT 1 FROM tax.vouchers v
         JOIN accounting.journal_entries e ON e.id = v.journal_entry_id
        WHERE v.transaction_id = NEW.source_transaction_id
          AND e.status IN ('draft', 'posted') AND e.id <> NEW.id) THEN
    RAISE EXCEPTION 'Un comprobante vinculado al movimiento ya tiene asiento vivo'
      USING ERRCODE = 'integrity_constraint_violation',
            CONSTRAINT = 'trg_journal_entries_voucher_has_entry';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER journal_entries_voucher_guard BEFORE INSERT ON accounting.journal_entries
  FOR EACH ROW EXECUTE FUNCTION tax.journal_entries_voucher_guard();
"""


def _seed_permissions() -> None:
    bind = op.get_bind()
    for code, description in TAX_PERMISSIONS.items():
        bind.execute(
            sa.text(
                "INSERT INTO core.permissions (code, description) VALUES (:code, :description)"
            ),
            {"code": code, "description": description},
        )
    for role, codes in TAX_ROLE_PERMISSIONS.items():
        for code in codes:
            bind.execute(
                sa.text(
                    "INSERT INTO core.role_permissions (role_code, permission_code)"
                    " VALUES (:role, :code)"
                ),
                {"role": role, "code": code},
            )


def upgrade() -> None:
    op.execute("CREATE SCHEMA tax")
    # El dígito verificador lo usan los CHECK de los comprobantes: va antes de las tablas.
    op.execute(RUC_CHECK_DIGIT_SQL)
    op.create_table(
        "rule_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("legal_reference", sa.String(length=500), nullable=True),
        sa.Column("consulted_at", sa.Date(), nullable=True),
        sa.Column("confidence", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "validation_status", sa.String(length=12), server_default="pending", nullable=False
        ),
        sa.Column("reviewed_by_name", sa.String(length=150), nullable=True),
        sa.Column("reviewed_reference", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("deprecation_reason", sa.String(length=300), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
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
        postgresql.ExcludeConstraint(
            (sa.column("code"), "="),
            (sa.text("daterange(valid_from, valid_to, '[]')"), "&&"),
            where=sa.text("validation_status <> 'deprecated'"),
            using="gist",
            name="ex_rule_versions_no_overlap",
        ),
        sa.CheckConstraint(
            "(reviewed_by_name IS NULL) = (reviewed_reference IS NULL) AND (reviewed_by_name IS NULL) = (reviewed_at IS NULL) AND (validation_status <> 'verified' OR reviewed_by_name IS NOT NULL)",
            name=op.f("ck_rule_versions_review_complete"),
        ),
        sa.CheckConstraint(
            "(validation_status = 'deprecated') = (deprecation_reason IS NOT NULL) AND (validation_status = 'deprecated') = (deprecated_at IS NOT NULL)",
            name=op.f("ck_rule_versions_deprecation_complete"),
        ),
        sa.CheckConstraint(
            "code ~ '^[A-Z0-9]+(-[A-Z0-9]+)*$'", name=op.f("ck_rule_versions_code_format")
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('oficial_leida', 'oficial_citada_por_terceros', 'secundaria', 'no_encontrada')",
            name=op.f("ck_rule_versions_confidence_valid"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(parameters) = 'object'", name=op.f("ck_rule_versions_parameters_object")
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'verified', 'deprecated')",
            name=op.f("ck_rule_versions_status_valid"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name=op.f("ck_rule_versions_validity_ordered"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_rule_versions_version_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_versions")),
        sa.UniqueConstraint("code", "version", name=op.f("uq_rule_versions_code_version")),
        schema="tax",
    )
    op.create_table(
        "due_date_exceptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("obligation_code", sa.String(length=60), nullable=True),
        sa.Column("obligation_group", sa.String(length=20), nullable=True),
        sa.Column("due_month", sa.Date(), nullable=False),
        sa.Column(
            "ruc_digits",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{}'::smallint[]"),
            nullable=False,
        ),
        sa.Column("new_due_date", sa.Date(), nullable=False),
        sa.Column("legal_reference", sa.String(length=300), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("rule_version_id", sa.UUID(), nullable=True),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
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
            "(origin = 'candidate') = (rule_version_id IS NOT NULL)",
            name=op.f("ck_due_date_exceptions_candidate_has_rule"),
        ),
        sa.CheckConstraint(
            "obligation_group IS NULL OR obligation_group IN ('determinative')",
            name=op.f("ck_due_date_exceptions_group_valid"),
        ),
        sa.CheckConstraint(
            "origin IN ('candidate', 'user')", name=op.f("ck_due_date_exceptions_origin_valid")
        ),
        sa.CheckConstraint(
            "(obligation_code IS NULL) <> (obligation_group IS NULL)",
            name=op.f("ck_due_date_exceptions_target_one"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(legal_reference)) > 0",
            name=op.f("ck_due_date_exceptions_legal_reference_present"),
        ),
        sa.CheckConstraint(
            "extract(day FROM due_month) = 1",
            name=op.f("ck_due_date_exceptions_due_month_first_day"),
        ),
        sa.CheckConstraint(
            "ruc_digits <@ ARRAY[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]::smallint[]",
            name=op.f("ck_due_date_exceptions_ruc_digits_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_due_date_exceptions_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["rule_version_id"],
            ["tax.rule_versions.id"],
            name=op.f("fk_due_date_exceptions_rule_version_id_rule_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_due_date_exceptions")),
        schema="tax",
    )
    op.create_index(
        "ix_due_date_exceptions_due_month",
        "due_date_exceptions",
        ["due_month"],
        unique=False,
        schema="tax",
    )
    op.create_index(
        "uq_due_date_exceptions_rule_date",
        "due_date_exceptions",
        ["rule_version_id", "new_due_date"],
        unique=True,
        schema="tax",
        postgresql_where=sa.text("rule_version_id IS NOT NULL"),
    )
    op.create_table(
        "holidays",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("legal_reference", sa.String(length=300), nullable=True),
        sa.Column(
            "validation_status", sa.String(length=12), server_default="pending", nullable=False
        ),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
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
            "origin IN ('candidate', 'user')", name=op.f("ck_holidays_origin_valid")
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'verified')", name=op.f("ck_holidays_status_valid")
        ),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name=op.f("ck_holidays_name_not_blank")),
        sa.CheckConstraint(
            "source_url IS NOT NULL OR legal_reference IS NOT NULL",
            name=op.f("ck_holidays_source_present"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_holidays_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holidays")),
        sa.UniqueConstraint("day", name=op.f("uq_holidays_day")),
        schema="tax",
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("ire_regime", sa.String(length=12), nullable=False),
        sa.Column("fiscal_close_month", sa.SmallInteger(), server_default="12", nullable=False),
        sa.Column("vat_taxpayer", sa.Boolean(), nullable=False),
        sa.Column("origin", sa.String(length=10), server_default="declared", nullable=False),
        sa.Column("verified_by_name", sa.String(length=150), nullable=True),
        sa.Column("verified_license", sa.String(length=100), nullable=True),
        sa.Column("verified_document_reference", sa.String(length=150), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.UUID(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
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
            "(origin = 'verified') = (verified_by_name IS NOT NULL) AND (origin = 'verified') = (verified_license IS NOT NULL) AND (origin = 'verified') = (verified_document_reference IS NOT NULL) AND (origin = 'verified') = (verified_at IS NOT NULL) AND (origin = 'verified') = (verified_by IS NOT NULL)",
            name=op.f("ck_profiles_verification_complete"),
        ),
        sa.CheckConstraint(
            "ire_regime IN ('ire_general', 'ire_simple', 'unknown')",
            name=op.f("ck_profiles_ire_regime_valid"),
        ),
        sa.CheckConstraint(
            "origin IN ('declared', 'verified')", name=op.f("ck_profiles_origin_valid")
        ),
        sa.CheckConstraint(
            "fiscal_close_month BETWEEN 1 AND 12", name=op.f("ck_profiles_close_month_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_profiles_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_profiles_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["core.users.id"], name=op.f("fk_profiles_verified_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
        sa.UniqueConstraint("id", "organization_id", name=op.f("uq_profiles_id_organization_id")),
        sa.UniqueConstraint(
            "organization_id", "valid_from", name=op.f("uq_profiles_organization_id_valid_from")
        ),
        schema="tax",
    )
    op.create_table(
        "profile_obligations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=4), nullable=False),
        sa.Column("registered_on", sa.Date(), nullable=False),
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
            "code ~ '^[0-9]{1,4}$'", name=op.f("ck_profile_obligations_code_digits")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_profile_obligations_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "organization_id"],
            ["tax.profiles.id", "tax.profiles.organization_id"],
            name=op.f("fk_profile_obligations_profile_id_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_obligations")),
        sa.UniqueConstraint(
            "profile_id", "code", name=op.f("uq_profile_obligations_profile_id_code")
        ),
        schema="tax",
    )
    op.create_table(
        "settings",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("vat_credit_10_account_id", sa.UUID(), nullable=True),
        sa.Column("vat_credit_5_account_id", sa.UUID(), nullable=True),
        sa.Column("vat_debit_10_account_id", sa.UUID(), nullable=True),
        sa.Column("vat_debit_5_account_id", sa.UUID(), nullable=True),
        sa.Column("suppliers_account_id", sa.UUID(), nullable=True),
        sa.Column("customers_account_id", sa.UUID(), nullable=True),
        sa.Column("alert_days", sa.SmallInteger(), server_default="10", nullable=False),
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
            "alert_days BETWEEN 1 AND 60", name=op.f("ck_settings_alert_days_range")
        ),
        sa.ForeignKeyConstraint(
            ["customers_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_customers_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_settings_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["suppliers_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_suppliers_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["vat_credit_10_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_vat_credit_10_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["vat_credit_5_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_vat_credit_5_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["vat_debit_10_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_vat_debit_10_account_id_ledger_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["vat_debit_5_account_id", "organization_id"],
            ["accounting.ledger_accounts.id", "accounting.ledger_accounts.organization_id"],
            name=op.f("fk_settings_vat_debit_5_account_id_ledger_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_settings_organization_id")),
        schema="tax",
    )
    op.create_table(
        "obligations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("dnit_code", sa.String(length=4), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("nominal_due_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "remind_by",
            sa.Date(),
            sa.Computed("LEAST(nominal_due_date, due_date)", persisted=True),
            nullable=False,
        ),
        sa.Column("rule_version_id", sa.UUID(), nullable=False),
        sa.Column("calendar_rule_version_id", sa.UUID(), nullable=False),
        sa.Column("exception_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=15), server_default="pending", nullable=False),
        sa.Column("calculated_amount", sa.Numeric(precision=18, scale=0), nullable=True),
        sa.Column("calculated_credit_balance", sa.Numeric(precision=18, scale=0), nullable=True),
        sa.Column("filed_on", sa.Date(), nullable=True),
        sa.Column("filing_reference", sa.String(length=60), nullable=True),
        sa.Column("declared_amount", sa.Numeric(precision=18, scale=0), nullable=True),
        sa.Column("declared_credit_balance", sa.Numeric(precision=18, scale=0), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("paid_amount", sa.Numeric(precision=18, scale=0), nullable=True),
        sa.Column("payment_transaction_id", sa.UUID(), nullable=True),
        sa.Column("payment_context_id", sa.UUID(), nullable=True),
        sa.Column("payment_context_kind", sa.String(length=10), nullable=True),
        sa.Column("not_applicable_reason", sa.String(length=300), nullable=True),
        sa.Column(
            "not_applicable_auto", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("reopen_reason", sa.String(length=300), nullable=True),
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
            "(status = 'not_applicable') = (not_applicable_reason IS NOT NULL)",
            name=op.f("ck_obligations_not_applicable_has_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'paid') = (paid_on IS NOT NULL) AND (status = 'paid') = (paid_amount IS NOT NULL)",
            name=op.f("ck_obligations_payment_complete"),
        ),
        sa.CheckConstraint(
            "(status IN ('filed', 'paid')) = (filed_on IS NOT NULL) AND (status IN ('filed', 'paid')) = (filing_reference IS NOT NULL)",
            name=op.f("ck_obligations_filing_complete"),
        ),
        sa.CheckConstraint(
            "NOT not_applicable_auto OR status = 'not_applicable'",
            name=op.f("ck_obligations_auto_when_not_applicable"),
        ),
        sa.CheckConstraint(
            "declared_amount IS NULL OR status IN ('filed', 'paid')",
            name=op.f("ck_obligations_declared_when_filed"),
        ),
        sa.CheckConstraint(
            "declared_credit_balance IS NULL OR status IN ('filed', 'paid')",
            name=op.f("ck_obligations_declared_balance_when_filed"),
        ),
        sa.CheckConstraint(
            "payment_context_kind IS NULL OR payment_context_kind = 'business'",
            name=op.f("ck_obligations_payment_business_only"),
        ),
        sa.CheckConstraint(
            "payment_transaction_id IS NULL OR status = 'paid'",
            name=op.f("ck_obligations_payment_tx_when_paid"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'filed', 'paid', 'not_applicable')",
            name=op.f("ck_obligations_status_valid"),
        ),
        sa.CheckConstraint(
            "(calculated_amount IS NULL OR calculated_amount >= 0) AND (calculated_credit_balance IS NULL OR calculated_credit_balance >= 0) AND (declared_amount IS NULL OR declared_amount >= 0) AND (declared_credit_balance IS NULL OR declared_credit_balance >= 0) AND (paid_amount IS NULL OR paid_amount >= 0)",
            name=op.f("ck_obligations_amounts_non_negative"),
        ),
        sa.CheckConstraint(
            "(payment_transaction_id IS NULL) = (payment_context_id IS NULL) AND (payment_transaction_id IS NULL) = (payment_context_kind IS NULL)",
            name=op.f("ck_obligations_payment_source_complete"),
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name=op.f("ck_obligations_period_ordered")
        ),
        sa.CheckConstraint(
            "reopen_reason IS NULL OR char_length(btrim(reopen_reason)) >= 3",
            name=op.f("ck_obligations_reopen_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["calendar_rule_version_id"],
            ["tax.rule_versions.id"],
            name=op.f("fk_obligations_calendar_rule_version_id_rule_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["exception_id"],
            ["tax.due_date_exceptions.id"],
            name=op.f("fk_obligations_exception_id_due_date_exceptions"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_obligations_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_obligations_payment_context_org_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["payment_context_id", "payment_context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_obligations_payment_context_kind_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["payment_transaction_id", "payment_context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
            name=op.f("fk_obligations_payment_transaction_id_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_version_id"],
            ["tax.rule_versions.id"],
            name=op.f("fk_obligations_rule_version_id_rule_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_obligations")),
        sa.UniqueConstraint(
            "organization_id",
            "code",
            "period_start",
            name=op.f("uq_obligations_organization_id_code_period_start"),
        ),
        schema="tax",
    )
    op.create_index(
        "ix_obligations_org_due",
        "obligations",
        ["organization_id", "due_date"],
        unique=False,
        schema="tax",
    )
    op.create_index(
        "ix_obligations_org_remind",
        "obligations",
        ["organization_id", "remind_by"],
        unique=False,
        schema="tax",
    )
    op.create_table(
        "vouchers",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("context_id", sa.UUID(), nullable=False),
        sa.Column("context_kind", sa.String(length=10), server_default="business", nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("voucher_type", sa.String(length=12), nullable=False),
        sa.Column("is_electronic", sa.Boolean(), nullable=False),
        sa.Column("cdc", sa.CHAR(length=44), nullable=True),
        sa.Column("timbrado", sa.CHAR(length=8), nullable=False),
        sa.Column("number", sa.String(length=15), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("counterparty_doc_type", sa.String(length=15), nullable=False),
        sa.Column("counterparty_ruc", sa.String(length=8), nullable=True),
        sa.Column("counterparty_ruc_dv", sa.CHAR(length=1), nullable=True),
        sa.Column("counterparty_document", sa.String(length=20), nullable=True),
        sa.Column("counterparty_name", sa.String(length=200), nullable=False),
        sa.Column("condition", sa.String(length=6), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="PYG", nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("foreign_total", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column(
            "taxed_10", sa.Numeric(precision=18, scale=0), server_default="0", nullable=False
        ),
        sa.Column("taxed_5", sa.Numeric(precision=18, scale=0), server_default="0", nullable=False),
        sa.Column("exempt", sa.Numeric(precision=18, scale=0), server_default="0", nullable=False),
        sa.Column("vat_10", sa.Numeric(precision=18, scale=0), server_default="0", nullable=False),
        sa.Column("vat_5", sa.Numeric(precision=18, scale=0), server_default="0", nullable=False),
        sa.Column("imputes_vat", sa.Boolean(), nullable=False),
        sa.Column("imputes_ire", sa.Boolean(), nullable=False),
        sa.Column("imputes_irp", sa.Boolean(), nullable=False),
        sa.Column("vat_rule_version_id", sa.UUID(), nullable=False),
        sa.Column("related_voucher_id", sa.UUID(), nullable=True),
        sa.Column("finance_counterparty_id", sa.UUID(), nullable=True),
        sa.Column("transaction_id", sa.UUID(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.UUID(), nullable=True),
        sa.Column("void_reason", sa.String(length=300), nullable=True),
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
            "(counterparty_doc_type = 'ruc') = (counterparty_ruc IS NOT NULL)",
            name=op.f("ck_vouchers_ruc_when_ruc"),
        ),
        sa.CheckConstraint(
            "counterparty_ruc IS NOT NULL OR counterparty_ruc_dv IS NULL",
            name=op.f("ck_vouchers_dv_with_ruc"),
        ),
        sa.CheckConstraint(
            "(counterparty_doc_type IN ('identity_card', 'passport', 'foreign_id', 'diplomatic', 'tax_id')) = (counterparty_document IS NOT NULL)",
            name=op.f("ck_vouchers_document_when_document"),
        ),
        sa.CheckConstraint(
            "(currency = 'PYG') = (fx_rate IS NULL) AND (currency = 'PYG') = (foreign_total IS NULL)",
            name=op.f("ck_vouchers_fx_complete"),
        ),
        sa.CheckConstraint(
            "(voucher_type IN ('credit_note', 'debit_note')) = (related_voucher_id IS NOT NULL)",
            name=op.f("ck_vouchers_note_has_original"),
        ),
        sa.CheckConstraint(
            "cdc IS NULL OR (cdc ~ '^[0-9]{44}$' AND tax.ruc_check_digit(left(cdc, 43)) = right(cdc, 1)::integer)",
            name=op.f("ck_vouchers_cdc_format"),
        ),
        sa.CheckConstraint(
            "condition IN ('cash', 'credit')", name=op.f("ck_vouchers_condition_valid")
        ),
        sa.CheckConstraint("context_kind = 'business'", name=op.f("ck_vouchers_business_only")),
        sa.CheckConstraint(
            "counterparty_doc_type IN ('ruc', 'identity_card', 'passport', 'foreign_id', 'unnamed', 'diplomatic', 'tax_id')",
            name=op.f("ck_vouchers_doc_type_valid"),
        ),
        sa.CheckConstraint(
            "counterparty_ruc IS NULL OR (counterparty_ruc ~ '^[0-9]{1,8}$' AND counterparty_ruc_dv ~ '^[0-9]$' AND tax.ruc_check_digit(counterparty_ruc) = counterparty_ruc_dv::integer) OR (counterparty_ruc ~ '^[0-9]{1,8}[A-Z]$' AND counterparty_ruc_dv IS NULL)",
            name=op.f("ck_vouchers_ruc_check_digit"),
        ),
        sa.CheckConstraint(
            "currency IN ('PYG', 'USD', 'BRL', 'ARS', 'EUR')",
            name=op.f("ck_vouchers_currency_valid"),
        ),
        sa.CheckConstraint(
            "direction <> 'purchase' OR counterparty_doc_type = 'ruc'",
            name=op.f("ck_vouchers_purchase_has_ruc"),
        ),
        sa.CheckConstraint(
            "direction IN ('purchase', 'sale')", name=op.f("ck_vouchers_direction_valid")
        ),
        sa.CheckConstraint(
            "number ~ '^[0-9]{3}-[0-9]{3}-[0-9]{7}$'", name=op.f("ck_vouchers_number_format")
        ),
        sa.CheckConstraint("timbrado ~ '^[0-9]{8}$'", name=op.f("ck_vouchers_timbrado_format")),
        sa.CheckConstraint(
            "voucher_type IN ('invoice', 'credit_note', 'debit_note')",
            name=op.f("ck_vouchers_type_valid"),
        ),
        sa.CheckConstraint(
            "(fx_rate IS NULL OR fx_rate > 0) AND (foreign_total IS NULL OR foreign_total > 0)",
            name=op.f("ck_vouchers_fx_positive"),
        ),
        sa.CheckConstraint(
            "(voided_at IS NULL) = (voided_by IS NULL) AND (voided_at IS NULL) = (void_reason IS NULL)",
            name=op.f("ck_vouchers_void_complete"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(counterparty_name)) > 0", name=op.f("ck_vouchers_name_not_blank")
        ),
        sa.CheckConstraint(
            "is_electronic = (cdc IS NOT NULL)", name=op.f("ck_vouchers_cdc_when_electronic")
        ),
        sa.CheckConstraint(
            "related_voucher_id IS NULL OR related_voucher_id <> id",
            name=op.f("ck_vouchers_not_self"),
        ),
        sa.CheckConstraint(
            "taxed_10 + taxed_5 + exempt > 0", name=op.f("ck_vouchers_total_positive")
        ),
        sa.CheckConstraint(
            "taxed_10 >= 0 AND taxed_5 >= 0 AND exempt >= 0 AND vat_10 >= 0 AND vat_5 >= 0",
            name=op.f("ck_vouchers_amounts_non_negative"),
        ),
        sa.CheckConstraint(
            "vat_10 <= taxed_10 AND vat_5 <= taxed_5 AND (taxed_10 > 0 OR vat_10 = 0) AND (taxed_5 > 0 OR vat_5 = 0)",
            name=op.f("ck_vouchers_vat_consistent"),
        ),
        sa.CheckConstraint(
            "void_reason IS NULL OR char_length(btrim(void_reason)) >= 3",
            name=op.f("ck_vouchers_void_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["context_id", "context_kind"],
            ["finance.contexts.id", "finance.contexts.kind"],
            name="fk_vouchers_context_kind_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["context_id", "organization_id"],
            ["finance.contexts.id", "finance.contexts.organization_id"],
            name="fk_vouchers_context_org_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["core.users.id"], name=op.f("fk_vouchers_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["finance_counterparty_id", "context_id"],
            ["finance.counterparties.id", "finance.counterparties.context_id"],
            name=op.f("fk_vouchers_finance_counterparty_id_counterparties"),
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id", "organization_id"],
            ["accounting.journal_entries.id", "accounting.journal_entries.organization_id"],
            name=op.f("fk_vouchers_journal_entry_id_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organizations.id"],
            name=op.f("fk_vouchers_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["related_voucher_id", "organization_id", "direction"],
            ["tax.vouchers.id", "tax.vouchers.organization_id", "tax.vouchers.direction"],
            name=op.f("fk_vouchers_related_voucher_id_vouchers"),
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id", "context_id"],
            ["finance.transactions.id", "finance.transactions.context_id"],
            name=op.f("fk_vouchers_transaction_id_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["vat_rule_version_id"],
            ["tax.rule_versions.id"],
            name=op.f("fk_vouchers_vat_rule_version_id_rule_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["voided_by"], ["core.users.id"], name=op.f("fk_vouchers_voided_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vouchers")),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "direction",
            name=op.f("uq_vouchers_id_organization_id_direction"),
        ),
        sa.UniqueConstraint("id", "organization_id", name=op.f("uq_vouchers_id_organization_id")),
        schema="tax",
    )
    op.create_index(
        "ix_vouchers_journal_entry", "vouchers", ["journal_entry_id"], unique=False, schema="tax"
    )
    op.create_index(
        "ix_vouchers_org_issued",
        "vouchers",
        ["organization_id", "issued_on"],
        unique=False,
        schema="tax",
    )
    op.create_index(
        "ix_vouchers_related", "vouchers", ["related_voucher_id"], unique=False, schema="tax"
    )
    op.create_index(
        "ix_vouchers_transaction", "vouchers", ["transaction_id"], unique=False, schema="tax"
    )
    op.create_index(
        "uq_vouchers_purchase_live",
        "vouchers",
        ["organization_id", "voucher_type", "counterparty_ruc", "timbrado", "number"],
        unique=True,
        schema="tax",
        postgresql_where=sa.text("direction = 'purchase' AND voided_at IS NULL"),
    )
    op.create_index(
        "uq_vouchers_sale_live",
        "vouchers",
        ["organization_id", "voucher_type", "timbrado", "number"],
        unique=True,
        schema="tax",
        postgresql_where=sa.text("direction = 'sale' AND voided_at IS NULL"),
    )
    op.execute(TAX_TRIGGERS_SQL)
    _seed_permissions()


DROP_TAX_SQL = """
DROP TRIGGER journal_entries_voucher_guard ON accounting.journal_entries;
DROP FUNCTION tax.journal_entries_voucher_guard();
"""


def downgrade() -> None:
    # Lo que no se puede perder hace fallar la bajada en lugar de borrarse en silencio (mismo
    # criterio que la 0004, D-080): los comprobantes (aunque estén anulados) y las
    # obligaciones presentadas o pagadas. El resto (reglas, feriados, perfil, obligaciones
    # pendientes) se borra con sus tablas y se vuelve a cargar o calcular al subir.
    bind = op.get_bind()
    vouchers = bind.execute(sa.text("SELECT count(*) FROM tax.vouchers")).scalar_one()
    filed = bind.execute(
        sa.text("SELECT count(*) FROM tax.obligations WHERE status IN ('filed', 'paid')")
    ).scalar_one()
    if vouchers or filed:
        raise RuntimeError(
            "No se puede volver a la 0004: hay "
            f"{vouchers} comprobantes y {filed} obligaciones presentadas o pagadas, que la"
            " 0004 no puede guardar."
        )
    op.execute(DROP_TAX_SQL)
    op.execute(
        "DELETE FROM core.role_permissions WHERE permission_code LIKE 'tax.%';"
        " DELETE FROM core.permissions WHERE code LIKE 'tax.%';"
    )
    # DROP TABLE no dispara los triggers de borrado: caen con sus tablas.
    op.drop_index("ix_vouchers_transaction", table_name="vouchers", schema="tax")
    op.drop_index("ix_vouchers_related", table_name="vouchers", schema="tax")
    op.drop_index("ix_vouchers_org_issued", table_name="vouchers", schema="tax")
    op.drop_index("ix_vouchers_journal_entry", table_name="vouchers", schema="tax")
    op.drop_index(
        "uq_vouchers_sale_live",
        table_name="vouchers",
        schema="tax",
        postgresql_where=sa.text("direction = 'sale' AND voided_at IS NULL"),
    )
    op.drop_index(
        "uq_vouchers_purchase_live",
        table_name="vouchers",
        schema="tax",
        postgresql_where=sa.text("direction = 'purchase' AND voided_at IS NULL"),
    )
    op.drop_table("vouchers", schema="tax")
    op.drop_index("ix_obligations_org_remind", table_name="obligations", schema="tax")
    op.drop_index("ix_obligations_org_due", table_name="obligations", schema="tax")
    op.drop_table("obligations", schema="tax")
    op.drop_table("settings", schema="tax")
    op.drop_table("profile_obligations", schema="tax")
    op.drop_table("profiles", schema="tax")
    op.drop_table("holidays", schema="tax")
    op.drop_index(
        "uq_due_date_exceptions_rule_date",
        table_name="due_date_exceptions",
        schema="tax",
        postgresql_where=sa.text("rule_version_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_due_date_exceptions_due_month", table_name="due_date_exceptions", schema="tax"
    )
    op.drop_table("due_date_exceptions", schema="tax")
    op.drop_table("rule_versions", schema="tax")
    op.execute(
        "DROP FUNCTION tax.vouchers_guard();"
        " DROP FUNCTION tax.vouchers_period_lock();"
        " DROP FUNCTION tax.holidays_guard();"
        " DROP FUNCTION tax.profile_obligations_guard();"
        " DROP FUNCTION tax.profiles_guard();"
        " DROP FUNCTION tax.obligations_guard();"
        " DROP FUNCTION tax.rule_versions_guard();"
        " DROP FUNCTION tax.reject_delete();"
        " DROP FUNCTION tax.ruc_check_digit(text);"
        " DROP SCHEMA tax;"
    )
