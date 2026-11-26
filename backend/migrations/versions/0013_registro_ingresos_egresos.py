"""Registro de INGRESOS y EGRESOS del IRP-RSP y archivo anual 956.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-26

Plan multiempresa, fase M7 (docs/specs/MULTI_ORG_PERSONA_FISICA.md; D-143). `tax.vouchers` admite
las direcciones `income` (INGRESOS, tipo de registro 3) y `expense` (EGRESOS, 4) con los tipos 201 a
211 de la Tabla 4 del formato oficial (`docs/research/formato_registro_comprobantes.yaml`), que no
tienen timbrado. Lo tributario sigue sin leer el contexto personal (`business_only`, D-035).

- `timbrado`, `number`, `counterparty_doc_type` y `vat_rule_version_id` pasan a nulos, con CHECK
  condicionales: el timbrado y la regla de tasas solo en compras y ventas; el número, salvo en los
  tipos que no lo piden (205 a 208); la contraparte, salvo en 206, 207 y 211.
- Columnas nuevas de los tipos que las usan: cuenta o tarjeta y banco (207, 211), número de
  empleador IPS (206), «especificar tipo de documento» (209, 210) y número y timbrado del
  comprobante asociado (201, 203).
- Anti duplicado de los que no tienen timbrado (D-104 ampliada): dos índices únicos parciales
  `NULLS NOT DISTINCT`, con número y sin número.
- El trigger del período confirmado (D-089) también bloquea el año del REG-COMPROB-ANUAL (956)
  presentado.

Bajada: se niega si hay algún ingreso o egreso, anulado o no (D-080): no tienen lugar en el esquema
anterior y los comprobantes no se borran (D-088).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "vouchers"
SCHEMA = "tax"

# (nombre sin el prefijo `ck_vouchers_`, condición). Las tres primeras reemplazan a las de la 0005.
NEW_CHECKS = [
    ("direction_valid", "direction IN ('purchase', 'sale', 'income', 'expense')"),
    (
        "type_valid",
        "(direction IN ('purchase', 'sale') AND voucher_type IN ('invoice', 'credit_note', 'debit_note')) OR (direction = 'income' AND voucher_type IN ('credit_sale', 'payslip', 'other_income')) OR (direction = 'expense' AND voucher_type IN ('credit_purchase', 'foreign_voucher', 'public_entity', 'e_ticketing', 'ips_statement', 'card_statement', 'payslip', 'other_expense', 'bank_transfer'))",
    ),
    (
        "number_format",
        "CASE WHEN direction IN ('purchase', 'sale') THEN number ~ '^[0-9]{3}-[0-9]{3}-[0-9]{7}$' ELSE char_length(btrim(number)) > 0 END",
    ),
    ("timbrado_when_timbrado", "(direction IN ('purchase', 'sale')) = (timbrado IS NOT NULL)"),
    (
        "number_required",
        "number IS NOT NULL OR (direction, voucher_type) IN (('income', 'payslip'), ('expense', 'e_ticketing'), ('expense', 'ips_statement'), ('expense', 'card_statement'), ('expense', 'payslip'))",
    ),
    ("register_not_electronic", "direction IN ('purchase', 'sale') OR NOT is_electronic"),
    (
        "vat_rule_when_vat",
        "(direction IN ('purchase', 'sale')) = (vat_rule_version_id IS NOT NULL)",
    ),
    (
        "register_amounts",
        "direction IN ('purchase', 'sale') OR (taxed_5 = 0 AND vat_10 = 0 AND vat_5 = 0 AND (direction = 'income' OR exempt = 0))",
    ),
    (
        "register_imputes_vat",
        "direction IN ('purchase', 'sale') OR NOT imputes_vat OR (direction = 'expense' AND voucher_type = 'card_statement')",
    ),
    (
        "period_first_day",
        "voucher_type NOT IN ('ips_statement', 'payslip') OR extract(day FROM issued_on) = 1",
    ),
    (
        "counterparty_required",
        "counterparty_doc_type IS NOT NULL OR (direction = 'expense' AND voucher_type IN ('ips_statement', 'card_statement', 'bank_transfer'))",
    ),
    (
        "counterparty_ids_with_type",
        "counterparty_doc_type IS NOT NULL OR (counterparty_ruc IS NULL AND counterparty_document IS NULL)",
    ),
    (
        "counterparty_by_type",
        "((direction, voucher_type) NOT IN (('income', 'payslip'), ('expense', 'public_entity'), ('expense', 'e_ticketing')) OR counterparty_doc_type = 'ruc') AND ((direction, voucher_type) <> ('expense', 'foreign_voucher') OR counterparty_doc_type = 'tax_id') AND ((direction, voucher_type) <> ('income', 'other_income') OR counterparty_doc_type IN ('ruc', 'identity_card', 'passport')) AND (direction IN ('purchase', 'sale') OR counterparty_doc_type IS DISTINCT FROM 'unnamed')",
    ),
    (
        "account_when_account",
        "(direction = 'expense' AND voucher_type IN ('card_statement', 'bank_transfer')) = (account_number IS NOT NULL) AND (direction = 'expense' AND voucher_type IN ('card_statement', 'bank_transfer')) = (bank_name IS NOT NULL)",
    ),
    (
        "ips_employer_when_ips",
        "(voucher_type = 'ips_statement') = (ips_employer_number IS NOT NULL)",
    ),
    (
        "description_when_other",
        "(voucher_type IN ('other_expense', 'other_income')) = (document_description IS NOT NULL)",
    ),
    (
        "related_when_credit",
        "(voucher_type IN ('credit_purchase', 'credit_sale')) = (related_number IS NOT NULL) AND (voucher_type IN ('credit_purchase', 'credit_sale')) = (related_timbrado IS NOT NULL)",
    ),
    (
        "related_format",
        "(related_number IS NULL OR related_number ~ '^[0-9]{3}-[0-9]{3}-[0-9]{7}$') AND (related_timbrado IS NULL OR related_timbrado ~ '^[0-9]{8}$')",
    ),
    (
        "register_texts_not_blank",
        "char_length(btrim(account_number)) > 0 AND char_length(btrim(bank_name)) > 0 AND char_length(btrim(ips_employer_number)) > 0 AND char_length(btrim(document_description)) > 0",
    ),
]
OLD_CHECKS = [
    ("direction_valid", "direction IN ('purchase', 'sale')"),
    ("type_valid", "voucher_type IN ('invoice', 'credit_note', 'debit_note')"),
    ("number_format", "number ~ '^[0-9]{3}-[0-9]{3}-[0-9]{7}$'"),
]
NEW_COLUMNS = [
    ("account_number", sa.String(length=30)),
    ("bank_name", sa.String(length=250)),
    ("ips_employer_number", sa.String(length=30)),
    ("document_description", sa.String(length=50)),
    ("related_number", sa.String(length=15)),
    ("related_timbrado", sa.CHAR(length=8)),
]
REGISTER = "direction IN ('income', 'expense') AND voided_at IS NULL"
INDEXES = [
    (
        "uq_vouchers_register_numbered_live",
        [
            "organization_id",
            "direction",
            "voucher_type",
            "counterparty_doc_type",
            "counterparty_ruc",
            "counterparty_document",
            "account_number",
            "number",
        ],
        f"{REGISTER} AND number IS NOT NULL",
    ),
    (
        "uq_vouchers_register_unnumbered_live",
        [
            "organization_id",
            "direction",
            "voucher_type",
            "counterparty_doc_type",
            "counterparty_ruc",
            "counterparty_document",
            "account_number",
            "ips_employer_number",
            "issued_on",
        ],
        f"{REGISTER} AND number IS NULL",
    ),
]

_LOCK_HEAD = """
CREATE OR REPLACE FUNCTION tax.vouchers_period_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_ignored text[] := ARRAY['journal_entry_id', 'updated_at'];
  v_month date;
  v_status text;
  v_days date[];
BEGIN
  IF TG_OP = 'UPDATE' AND (to_jsonb(NEW) - v_ignored) = (to_jsonb(OLD) - v_ignored) THEN
    RETURN NEW;
  END IF;
  v_days := CASE WHEN TG_OP = 'UPDATE' THEN ARRAY[OLD.issued_on, NEW.issued_on]
                 ELSE ARRAY[NEW.issued_on] END;
  FOR v_month IN SELECT DISTINCT date_trunc('month', d)::date FROM unnest(v_days) AS d
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
"""
# D-143: el registro anual (956) confirmado bloquea los comprobantes de su ejercicio (enero a
# diciembre: la 715 exige el cierre en diciembre, D-142).
_LOCK_ANNUAL = """
  FOR v_month IN SELECT DISTINCT date_trunc('year', d)::date FROM unnest(v_days) AS d
  LOOP
    SELECT status INTO v_status FROM tax.obligations
     WHERE organization_id = NEW.organization_id AND code = 'REG-COMPROB-ANUAL'
       AND period_start = v_month
     FOR SHARE;
    IF v_status IN ('filed', 'paid') THEN
      RAISE EXCEPTION 'El registro anual de comprobantes de % está confirmado: reabrilo para '
        'cambiar sus comprobantes', to_char(v_month, 'YYYY')
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'trg_vouchers_period_locked';
    END IF;
  END LOOP;
"""
_LOCK_TAIL = """
  RETURN NEW;
END $$;
"""
# La de la 0005, tal cual, para la bajada.
_LOCK_0005 = """
CREATE OR REPLACE FUNCTION tax.vouchers_period_lock() RETURNS trigger LANGUAGE plpgsql AS $$
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
"""


def _alter(nullable: bool, voucher_type: int, number: int) -> None:
    op.alter_column(
        TABLE,
        "voucher_type",
        type_=sa.String(length=voucher_type),
        existing_nullable=False,
        schema=SCHEMA,
    )
    op.alter_column(
        TABLE, "timbrado", existing_type=sa.CHAR(length=8), nullable=nullable, schema=SCHEMA
    )
    op.alter_column(
        TABLE, "number", type_=sa.String(length=number), nullable=nullable, schema=SCHEMA
    )
    op.alter_column(
        TABLE,
        "counterparty_doc_type",
        existing_type=sa.String(length=15),
        nullable=nullable,
        schema=SCHEMA,
    )
    op.alter_column(
        TABLE, "vat_rule_version_id", existing_type=sa.UUID(), nullable=nullable, schema=SCHEMA
    )


def _checks(rows: list[tuple[str, str]], create: bool) -> None:
    for name, condition in rows:
        if create:
            op.create_check_constraint(op.f(f"ck_vouchers_{name}"), TABLE, condition, schema=SCHEMA)
        else:
            op.drop_constraint(op.f(f"ck_vouchers_{name}"), TABLE, schema=SCHEMA, type_="check")


def upgrade() -> None:
    _alter(True, 20, 20)
    for name, type_ in NEW_COLUMNS:
        op.add_column(TABLE, sa.Column(name, type_, nullable=True), schema=SCHEMA)
    _checks(OLD_CHECKS, create=False)
    _checks(NEW_CHECKS, create=True)
    for name, columns, where in INDEXES:
        op.create_index(
            name,
            TABLE,
            columns,
            unique=True,
            schema=SCHEMA,
            postgresql_where=sa.text(where),
            postgresql_nulls_not_distinct=True,
        )
    op.execute(_LOCK_HEAD + _LOCK_ANNUAL + _LOCK_TAIL)


def downgrade() -> None:
    used = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM tax.vouchers WHERE direction IN ('income', 'expense')")
    )
    if used:
        raise RuntimeError(
            f"No se puede bajar la 0013: hay {used} comprobante(s) de ingreso o egreso del "
            "registro anual (956), contando los anulados. Los comprobantes no se borran y el "
            "esquema anterior no los admite; no se hace sola."
        )
    op.execute(_LOCK_0005)
    for name, _columns, _where in INDEXES:
        op.drop_index(name, table_name=TABLE, schema=SCHEMA)
    _checks(NEW_CHECKS, create=False)
    _checks(OLD_CHECKS, create=True)
    for name, _type in NEW_COLUMNS:
        op.drop_column(TABLE, name, schema=SCHEMA)
    _alter(False, 12, 15)
