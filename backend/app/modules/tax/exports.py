"""Exportación del registro de comprobantes (D-093, D-096).

`xlsx`: libro de compras y ventas con las columnas del formato oficial de la RG 90/2021
(`docs/research/formato_registro_comprobantes.yaml`), más el IVA, si es electrónico y el CDC.
Sin los anulados. Importes como números enteros (`#,##0`).

`marangatu` (D-096): el archivo de **importación** de Marangatu según la Especificación
Técnica para Importación, versión 1 (junio de 2021), transcripta en ese YAML (`pending`):
- CSV en UTF-8, sin encabezado, dentro de un ZIP con el mismo nombre
  `<RUC sin DV>_REG_<MMAAAA>_<id>` (id de hasta 5 posiciones, distinto en cada archivo), un
  ZIP por lote de hasta 5.000 filas; si hay más de un lote, un ZIP que los contiene;
- columnas de VENTAS (19) y COMPRAS (20) en el orden oficial; montos enteros con IVA
  incluido, en guaraníes (los de otra moneda ya están convertidos, D-041);
- **los electrónicos no se exportan**: Marangatu los trae solo (RG 90/2021, art. 6°). La
  vista previa dice cuántos y cuáles se excluyeron, para imputarlos en Marangatu;
- separador: la especificación dice coma y su ejemplo usa punto y coma (D-F4-1). Por
  defecto, el punto y coma del ejemplo oficial; `separator=comma` usa la coma. En los textos
  libres (nombres) se reemplaza el separador por un espacio y se avisa;
- notas de crédito según la guía de registro manual y el instructivo del Formulario 120
  (D-122, resuelve D-F4-4): la **recibida** va en VENTAS y la **emitida** en COMPRAS; las
  notas de débito, en la sección de su comprobante;
- «NO IMPUTA» (solo compras) va en `N`: la app no registra imputaciones parciales. Un
  comprobante que no imputa a ninguna obligación no se exporta (Marangatu exige al menos
  una) y se lista;
- es un **borrador**: Marangatu valida hasta en 72 horas y puede rechazar líneas. Conviene
  probar primero con uno o dos comprobantes (`limit`);
- el archivo mensual (955) lleva solo compras y ventas: los ingresos y egresos van en el anual.

`annual_plan` (D-143): el archivo del **registro anual (956)** del IRP-RSP sin IVA, con el mismo
escritor: `<RUC sin DV>_REG_<AAAA>_<id>`, las compras y ventas del año con sus 20 y 19 columnas
y además INGRESOS (15 columnas) y EGRESOS (18), mezclados en el mismo archivo como admite la
especificación. Fechas `dd/mm/aaaa`, salvo el período `mm/aaaa` de los tipos 206 y 208. Solo si
el perfil vigente al cierre del año incluye la 956.
"""

import csv
import io
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import AppError
from app.modules.accounting import fast_xlsx
from app.modules.accounting.exports import Column, Styled, workbook
from app.modules.organizations.models import Organization
from app.modules.tax import profile as profiles
from app.modules.tax import rules, vouchers
from app.modules.tax.common import ZERO, month_end
from app.modules.tax.models import DIRECTIONS, PERIOD_TYPES, TIMBRADO_DIRECTIONS, Voucher

IMPORT_RULE = "REG-COMPROB-IMPORTACION"
ANNUAL_RULE = vouchers.ANNUAL_REGISTER_RULE
MAX_ROWS = 5000
# Tabla 1 de la especificación: tipos de registro.
REGISTER_SALES, REGISTER_PURCHASES, REGISTER_INCOME, REGISTER_EXPENSE = 1, 2, 3, 4
# Tabla 4: tipos de comprobante.
VOUCHER_CODES = {
    "invoice": 109,
    "credit_note": 110,
    "debit_note": 111,
    "credit_purchase": 201,
    "foreign_voucher": 202,
    "credit_sale": 203,
    "public_entity": 204,
    "e_ticketing": 205,
    "ips_statement": 206,
    "card_statement": 207,
    "payslip": 208,
    "other_expense": 209,
    "other_income": 210,
    "bank_transfer": 211,
}
IDENTIFICATION_CODES = {
    "ruc": 11,
    "identity_card": 12,
    "passport": 13,
    "foreign_id": 14,
    "unnamed": 15,
    "diplomatic": 16,
    "tax_id": 17,
}
SEPARATORS = {"semicolon": ";", "comma": ","}
MIN_DATE = date(2021, 1, 1)
DRAFT_NOTICE = (
    "Borrador del archivo de importación de Marangatu, sin verificar contra la fuente oficial. "
    "Marangatu lo valida hasta en 72 horas y puede rechazar líneas. Probá primero con un "
    "archivo de uno o dos comprobantes (`limit`) y usá un identificador distinto en cada "
    "archivo: Marangatu no acepta dos archivos con el mismo nombre para el mismo período."
)
DOUBTS = {
    "D-F4-1": "Separador: la especificación dice coma y su ejemplo usa punto y coma.",
    "D-F4-2": "La columna «IMPUTA IRE» aplica solo al IRE SIMPLE según las guías de la DNIT.",
}


def _yn(value: bool) -> str:
    return "S" if value else "N"


def _int(value: Decimal) -> str:
    return str(int(value))


def _section(voucher: Voucher) -> int:
    if voucher.direction == "income":
        return REGISTER_INCOME
    if voucher.direction == "expense":
        return REGISTER_EXPENSE
    is_sale = voucher.direction == "sale"
    if voucher.voucher_type == "credit_note":
        is_sale = not is_sale  # D-122 (D-F4-4 resuelta)
    return REGISTER_SALES if is_sale else REGISTER_PURCHASES


@dataclass
class MarangatuPlan:
    organization_ruc: str
    period: str  # MMAAAA (955) o AAAA (956)
    separator: str
    rows: list[list[str]] = field(default_factory=list)
    excluded_electronic: list[Voucher] = field(default_factory=list)
    excluded_not_imputed: list[Voucher] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rule: Any = None
    extra_rules: list[Any] = field(default_factory=list)
    total_rows: int = 0
    period_text: str = "ese mes"

    def batches(self) -> list[list[list[str]]]:
        return [self.rows[i : i + MAX_ROWS] for i in range(0, len(self.rows), MAX_ROWS)] or []

    def names(self, first_id: int) -> list[str]:
        return [
            f"{self.organization_ruc}_REG_{self.period}_{first_id + i:05d}"
            for i in range(len(self.batches()))
        ]


def _clean(text: str, separator: str, changed: list[str]) -> str:
    cleaned = " ".join(text.replace(separator, " ").replace('"', " ").split())
    if cleaned != " ".join(text.split()):
        changed.append(text)
    return cleaned


@dataclass
class _Counters:
    changed: list[str] = field(default_factory=list)
    unnamed_numbers: int = 0
    non_ruc_purchases: int = 0
    old_cash: int = 0
    ire_imputed: int = 0


def _organization_ruc(db: Session, organization_id: uuid.UUID) -> str:
    org = db.get(Organization, organization_id)
    assert org is not None
    if org.ruc is None:
        raise AppError(
            "ORGANIZATION_RUC_REQUIRED",
            "Cargá el RUC de la organización: el nombre del archivo lo lleva.",
            status_code=422,
        )
    return org.ruc


def _rows_of(
    db: Session, organization_id: uuid.UUID, first: date, last: date, directions: tuple[str, ...]
) -> list[Any]:
    original = aliased(Voucher)
    return list(
        db.execute(
            select(Voucher, original.number, original.timbrado)
            .outerjoin(original, original.id == Voucher.related_voucher_id)
            .where(
                Voucher.organization_id == organization_id,
                Voucher.voided_at.is_(None),
                Voucher.issued_on >= first,
                Voucher.issued_on <= last,
                Voucher.direction.in_(directions),
            )
            .order_by(Voucher.issued_on, Voucher.direction, Voucher.number, Voucher.id)
        ).all()
    )


def _date(voucher: Voucher) -> str:
    """dd/mm/aaaa; el período mm/aaaa en el extracto de IPS (206) y la liquidación (208)."""
    if voucher.direction in ("income", "expense") and voucher.voucher_type in PERIOD_TYPES:
        return f"{voucher.issued_on:%m/%Y}"
    return f"{voucher.issued_on:%d/%m/%Y}"


def _timbrado_row(
    voucher: Voucher,
    related_number: str | None,
    related_timbrado: str | None,
    sep: str,
    counters: _Counters,
) -> list[str]:
    """VENTAS (19 columnas) o COMPRAS (20)."""
    section = _section(voucher)
    doc_type = voucher.counterparty_doc_type
    assert doc_type is not None and voucher.timbrado is not None and voucher.number is not None
    number = voucher.counterparty_ruc or voucher.counterparty_document or ""
    if doc_type == "unnamed":
        counters.unnamed_numbers += 1
    if section == REGISTER_PURCHASES and doc_type != "ruc":
        counters.non_ruc_purchases += 1
    if voucher.issued_on < MIN_DATE and voucher.condition == "cash":
        counters.old_cash += 1
    total = voucher.taxed_10 + voucher.taxed_5 + voucher.exempt
    row = [
        str(section),
        str(IDENTIFICATION_CODES[doc_type]),
        _clean(number, sep, counters.changed)[:20],
        _clean(voucher.counterparty_name, sep, counters.changed)[:250],
        str(VOUCHER_CODES[voucher.voucher_type]),
        f"{voucher.issued_on:%d/%m/%Y}",
        voucher.timbrado,
        voucher.number,
        _int(voucher.taxed_10),
        _int(voucher.taxed_5),
        _int(voucher.exempt),
        _int(total),
        "1" if voucher.condition == "cash" else "2",
        _yn(voucher.currency != "PYG"),
        _yn(voucher.imputes_vat),
        _yn(voucher.imputes_ire),
        _yn(voucher.imputes_irp),
    ]
    if section == REGISTER_PURCHASES:
        row.append("N")  # NO IMPUTA
    row.extend([related_number or "", related_timbrado or ""])
    return row


def _register_row(voucher: Voucher, sep: str, counters: _Counters) -> list[str]:
    """INGRESOS (15 columnas) o EGRESOS (18), en el orden del YAML de la especificación."""

    def text(value: str | None, size: int) -> str:
        return _clean(value, sep, counters.changed)[:size] if value else ""

    doc_type = voucher.counterparty_doc_type
    head = [
        str(_section(voucher)),
        str(VOUCHER_CODES[voucher.voucher_type]),
        _date(voucher),
        text(voucher.number, 20),
        str(IDENTIFICATION_CODES[doc_type]) if doc_type else "",
        text(voucher.counterparty_ruc or voucher.counterparty_document, 20),
        text(voucher.counterparty_name, 250),
    ]
    total = voucher.taxed_10 + voucher.exempt
    if voucher.direction == "income":
        return [
            *head,
            _int(voucher.taxed_10),  # MONTO_GRAVADO
            _int(voucher.exempt),  # MONTO_NO_GRAVADO_EXONERADO
            _int(total),
            _yn(voucher.imputes_ire),
            _yn(voucher.imputes_irp),
            text(voucher.document_description, 50),
            voucher.related_number or "",
            voucher.related_timbrado or "",
        ]
    return [
        *head,
        _int(total),
        _yn(voucher.imputes_vat),
        _yn(voucher.imputes_ire),
        _yn(voucher.imputes_irp),
        "N",  # NO IMPUTA
        text(voucher.account_number, 30),
        text(voucher.bank_name, 250),
        text(voucher.ips_employer_number, 30),
        text(voucher.document_description, 50),
        voucher.related_number or "",
        voucher.related_timbrado or "",
    ]


def _fill(plan: MarangatuPlan, rows: list[Any], limit: int | None, counters: _Counters) -> None:
    sep = SEPARATORS[plan.separator]
    for voucher, related_number, related_timbrado in rows:
        if voucher.is_electronic:
            plan.excluded_electronic.append(voucher)
            continue
        if not (voucher.imputes_vat or voucher.imputes_ire or voucher.imputes_irp):
            plan.excluded_not_imputed.append(voucher)
            continue
        if limit is not None and len(plan.rows) >= limit:
            continue
        counters.ire_imputed += voucher.imputes_ire
        if voucher.direction in TIMBRADO_DIRECTIONS:
            plan.rows.append(
                _timbrado_row(voucher, related_number, related_timbrado, sep, counters)
            )
        else:
            plan.rows.append(_register_row(voucher, sep, counters))
    plan.total_rows = len(plan.rows)


def _warn(
    plan: MarangatuPlan,
    counters: _Counters,
    db: Session,
    organization_id: uuid.UUID,
    last: date,
) -> None:
    if counters.changed:
        plan.warnings.append(
            f"{len(counters.changed)} nombre(s) o documento(s) tenían el separador, comillas o "
            "saltos de línea: se reemplazaron por espacios en el archivo."
        )
    if counters.unnamed_numbers:
        plan.warnings.append(
            f"{counters.unnamed_numbers} venta(s) «sin nombre» (identificación 15) van sin número "
            "de identificación: la especificación lo pide y no dice qué número va. Revisalo "
            "antes de importar."
        )
    if counters.non_ruc_purchases:
        plan.warnings.append(
            f"{counters.non_ruc_purchases} fila(s) en COMPRAS no son RUC (notas de crédito "
            "emitidas a clientes sin RUC): la especificación pide RUC en compras y Marangatu "
            "puede rechazarlas. Cargalas a mano."
        )
    if counters.old_cash:
        plan.warnings.append(
            f"{counters.old_cash} comprobante(s) al contado anteriores al 01/01/2021: Marangatu "
            "no los acepta."
        )
    history = profiles.versions(db, organization_id)
    current = profiles.vigente(history, last)
    if counters.ire_imputed and current is not None and current.profile.ire_regime == "ire_general":
        plan.warnings.append(
            f"{counters.ire_imputed} comprobante(s) imputan al IRE, pero el perfil es del IRE "
            "General: según las guías de la DNIT esa imputación es solo del IRE SIMPLE (D-F4-2)."
        )
    if plan.excluded_electronic:
        plan.warnings.append(
            f"{len(plan.excluded_electronic)} comprobante(s) electrónicos no van en el archivo: "
            "imputalos en Marangatu, en «Obtener Comprobantes Electrónicos y Virtuales»."
        )
    if plan.excluded_not_imputed:
        plan.warnings.append(
            f"{len(plan.excluded_not_imputed)} comprobante(s) no imputan a ninguna obligación y "
            "no van en el archivo: Marangatu exige imputar cada uno al menos a una."
        )


def marangatu_plan(
    db: Session,
    organization_id: uuid.UUID,
    year: int,
    month: int,
    *,
    separator: str = "semicolon",
    limit: int | None = None,
) -> MarangatuPlan:
    """Archivo mensual (955): compras y ventas del mes."""
    ruc = _organization_ruc(db, organization_id)
    first = date(year, month, 1)
    rule = rules.require_rule(db, IMPORT_RULE, first)
    plan = MarangatuPlan(ruc, f"{month:02d}{year}", separator, rule=rule)
    counters = _Counters()
    _fill(
        plan,
        _rows_of(db, organization_id, first, month_end(first), TIMBRADO_DIRECTIONS),
        limit,
        counters,
    )
    _warn(plan, counters, db, organization_id, month_end(first))
    register = db.scalar(
        select(func.count()).where(
            Voucher.organization_id == organization_id,
            Voucher.voided_at.is_(None),
            Voucher.issued_on >= first,
            Voucher.issued_on <= month_end(first),
            Voucher.direction.not_in(TIMBRADO_DIRECTIONS),
        )
    )
    if register:
        plan.warnings.append(
            f"{register} ingreso(s) o egreso(s) del mes no van en el registro mensual: son del "
            "registro anual (956)."
        )
    return plan


def annual_plan(
    db: Session,
    organization_id: uuid.UUID,
    year: int,
    *,
    separator: str = "semicolon",
    limit: int | None = None,
) -> MarangatuPlan:
    """Archivo del registro anual (956, D-143): compras, ventas, ingresos y egresos del año."""
    ruc = _organization_ruc(db, organization_id)
    if not vouchers.annual_register_applies(db, organization_id, year):
        raise AppError(
            "ANNUAL_REGISTER_NOT_APPLICABLE",
            f"El perfil fiscal vigente al cierre de {year} no incluye el registro anual de "
            "comprobantes (956). Con IVA, el registro es mensual (955).",
            details={"year": year},
            status_code=422,
        )
    first, last = date(year, 1, 1), date(year, 12, 31)
    rule = rules.require_rule(db, IMPORT_RULE, last)
    annual = rules.require_rule(db, ANNUAL_RULE, first)
    plan = MarangatuPlan(
        ruc, str(year), separator, rule=rule, extra_rules=[annual], period_text=f"{year}"
    )
    counters = _Counters()
    _fill(plan, _rows_of(db, organization_id, first, last, DIRECTIONS), limit, counters)
    _warn(plan, counters, db, organization_id, last)
    return plan


def _csv(rows: list[list[str]], separator: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(
        buffer, delimiter=SEPARATORS[separator], quoting=csv.QUOTE_NONE, lineterminator="\r\n"
    )
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def marangatu_file(plan: MarangatuPlan, first_id: int) -> tuple[str, bytes]:
    """(nombre del archivo, contenido) del ZIP a descargar."""
    batches = plan.batches()
    if not batches:
        raise AppError(
            "NOTHING_TO_EXPORT",
            f"No hay comprobantes para el archivo de importación en {plan.period_text} (los "
            "electrónicos y los que no imputan no van).",
            status_code=422,
        )
    names = plan.names(first_id)
    if len(names[-1].rsplit("_", 1)[1]) > 5:
        raise AppError(
            "FILE_ID_TOO_LONG",
            "El identificador del archivo tiene hasta 5 posiciones: usá un `first_id` menor.",
            status_code=422,
        )
    inner = [
        (f"{name}.zip", _zip([(f"{name}.csv", _csv(rows, plan.separator))]))
        for name, rows in zip(names, batches, strict=True)
    ]
    if len(inner) == 1:
        return inner[0]
    return f"{plan.organization_ruc}_REG_{plan.period}_lotes.zip", _zip(inner)


def excluded_out(voucher: Voucher) -> dict[str, Any]:
    return {
        "id": str(voucher.id),
        "direction": voucher.direction,
        "voucher_type": voucher.voucher_type,
        "issued_on": voucher.issued_on.isoformat(),
        "number": voucher.number,
        "cdc": voucher.cdc,
        "counterparty_name": voucher.counterparty_name,
    }


def marangatu_preview(plan: MarangatuPlan, first_id: int) -> dict[str, Any]:
    names = plan.names(first_id)
    return {
        "is_draft": True,
        "notice": DRAFT_NOTICE,
        "format": "csv",
        "encoding": "UTF-8",
        "header": False,
        "separator": plan.separator,
        "rows": plan.total_rows,
        "batches": [
            {"name": f"{n}.zip", "rows": len(b)} for n, b in zip(names, plan.batches(), strict=True)
        ],
        "excluded_electronic": {
            "count": len(plan.excluded_electronic),
            "vouchers": [excluded_out(v) for v in plan.excluded_electronic],
        },
        "excluded_not_imputed": {
            "count": len(plan.excluded_not_imputed),
            "vouchers": [excluded_out(v) for v in plan.excluded_not_imputed],
        },
        "warnings": plan.warnings,
        "doubts": [{"code": code, "text": text} for code, text in DOUBTS.items()],
        "rules_applied": [rules.applied(r) for r in (plan.rule, *plan.extra_rules)],
        "rule_status": (
            "pending"
            if any(r.validation_status != "verified" for r in (plan.rule, *plan.extra_rules))
            else "verified"
        ),
    }


# ------------------------------------------------------------------ XLSX

_TYPE_TEXT = {
    "invoice": "Factura",
    "credit_note": "Nota de crédito",
    "debit_note": "Nota de débito",
}
_DOC_TEXT = {
    "ruc": "RUC",
    "identity_card": "Cédula de identidad",
    "passport": "Pasaporte",
    "foreign_id": "Cédula extranjera",
    "unnamed": "Sin nombre",
    "diplomatic": "Diplomático",
    "tax_id": "Identificación tributaria",
}


def vouchers_xlsx(
    db: Session,
    organization_id: uuid.UUID,
    *,
    year: int,
    month: int | None,
    direction: str | None,
) -> bytes:
    first = date(year, month or 1, 1)
    last = month_end(first) if month else date(year, 12, 31)
    original = aliased(Voucher)
    query = (
        select(Voucher, original.number, original.timbrado)
        .outerjoin(original, original.id == Voucher.related_voucher_id)
        .where(
            Voucher.organization_id == organization_id,
            Voucher.voided_at.is_(None),
            Voucher.issued_on >= first,
            Voucher.issued_on <= last,
            # El libro es de compras y ventas; los ingresos y egresos van en el archivo 956.
            Voucher.direction.in_(TIMBRADO_DIRECTIONS),
        )
        .order_by(Voucher.direction, Voucher.issued_on, Voucher.number, Voucher.id)
    )
    if direction:
        query = query.where(Voucher.direction == direction)
    columns = [
        Column("Registro", width=10),
        Column("Tipo de identificación", width=18),
        Column("Número de identificación", width=16),
        Column("DV", width=4),
        Column("Nombre o razón social", width=34),
        Column("Tipo de comprobante", width=16),
        Column("Fecha de emisión", width=12),
        Column("Timbrado", width=10),
        Column("Número de comprobante", width=17),
        Column("Gravado 10 % (IVA incluido)", money=True),
        Column("Gravado 5 % (IVA incluido)", money=True),
        Column("No gravado o exento", money=True),
        Column("Total", money=True),
        Column("IVA 10 %", money=True),
        Column("IVA 5 %", money=True),
        Column("Condición", width=9),
        Column("Moneda", width=7),
        Column("Imputa IVA", width=8),
        Column("Imputa IRE", width=8),
        Column("Imputa IRP-RSP", width=8),
        Column("Comprobante asociado", width=17),
        Column("Timbrado asociado", width=10),
        Column("Electrónico", width=9),
        Column("CDC", width=48),
    ]
    totals = {key: ZERO for key in ("t10", "t5", "ex", "tot", "v10", "v5")}

    def data() -> Any:
        for voucher, related_number, related_timbrado in db.execute(query):
            total = voucher.taxed_10 + voucher.taxed_5 + voucher.exempt
            for key, value in (
                ("t10", voucher.taxed_10),
                ("t5", voucher.taxed_5),
                ("ex", voucher.exempt),
                ("tot", total),
                ("v10", voucher.vat_10),
                ("v5", voucher.vat_5),
            ):
                totals[key] += value
            yield [
                "Venta" if voucher.direction == "sale" else "Compra",
                _DOC_TEXT.get(voucher.counterparty_doc_type or "", ""),
                voucher.counterparty_ruc or voucher.counterparty_document or "",
                voucher.counterparty_ruc_dv or "",
                voucher.counterparty_name,
                _TYPE_TEXT[voucher.voucher_type],
                voucher.issued_on.strftime("%d/%m/%Y"),
                voucher.timbrado,
                voucher.number,
                voucher.taxed_10,
                voucher.taxed_5,
                voucher.exempt,
                total,
                voucher.vat_10,
                voucher.vat_5,
                "Contado" if voucher.condition == "cash" else "Crédito",
                voucher.currency,
                _yn(voucher.imputes_vat),
                _yn(voucher.imputes_ire),
                _yn(voucher.imputes_irp),
                related_number or "",
                related_timbrado or "",
                _yn(voucher.is_electronic),
                voucher.cdc or "",
            ]
        yield Styled(
            [
                "Total",
                *[None] * 8,
                totals["t10"],
                totals["t5"],
                totals["ex"],
                totals["tot"],
                totals["v10"],
                totals["v5"],
            ]
        )

    which = {"purchase": "compras", "sale": "ventas"}.get(direction or "", "compras y ventas")
    period = f"{month:02d}/{year}" if month else str(year)
    return fast_xlsx.workbook(
        db,
        organization_id,
        title=f"Registro de comprobantes de {which}",
        subtitle=f"Período {period}",
        chart_status="validated",
        columns=columns,
        rows=data(),
        notes=[
            "Importes en guaraníes con IVA incluido, como en el comprobante (RG 90/2021). "
            "Sin los comprobantes anulados.",
            "Para copiar o importar en Marangatu: no reemplaza la carga ni la confirmación "
            "del registro.",
        ],
        sheet="Comprobantes",
    )


def vat_xlsx(db: Session, organization_id: uuid.UUID, estimate: dict[str, Any]) -> bytes:
    """Estimación del IVA y borrador del Formulario 120, con los mismos totales del JSON."""

    def amount(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    rows: list[Any] = [Styled(["Estimación (rubros genéricos)", None, None])]
    for label, block in (
        ("Ventas", estimate["debit"]["sales"]),
        ("Notas de crédito emitidas", estimate["debit"]["credit_notes"]),
        ("Compras", estimate["credit"]["purchases"]),
        ("Notas de crédito recibidas", estimate["credit"]["credit_notes"]),
    ):
        for rate, key in (("10 %", "rate_10"), ("5 %", "rate_5")):
            rows.append([f"{label}: IVA {rate}", None, amount(block[key]["vat"])])
        rows.append([f"{label}: exento", None, amount(block["exempt"])])
    previous = estimate["previous_balance"]
    rows.extend(
        [
            Styled(["Débito fiscal", None, amount(estimate["debit"]["total"])]),
            Styled(["Crédito fiscal", None, amount(estimate["credit"]["total"])]),
            [
                f"Saldo a favor del mes anterior ({previous['source']})",
                None,
                amount(previous["amount"]),
            ],
            Styled(["Resultado: a ingresar", None, amount(estimate["result"]["to_pay"])]),
            Styled(
                ["Resultado: saldo a favor", None, amount(estimate["result"]["credit_balance"])]
            ),
            [],
        ]
    )
    form = estimate["form_120"]
    if form["available"]:
        rows.append(Styled(["Borrador del Formulario 120 v4 (sin IVA y sin céntimos)", None, None]))
        for box in form["boxes"]:
            doubt = f" [{', '.join(box['doubts'])}]" if box["doubts"] else ""
            label = f"Rubro {box['rubro']}: {box['label']}{doubt}"
            rows.append([label, box["box"], amount(box["value"]), box["note"] or ""])
    else:
        rows.append([form["message"]])
    notes = [
        "Estimación, no declaración: copiá los valores a mano en Marangatu y revisalos.",
        "Reglas aplicadas: "
        + ", ".join(
            f"{r['code']} v{r['version']} ({r['validation_status']})"
            for r in estimate["rules_applied"]
        ),
        *[w["message"] for w in estimate["warnings"]],
    ]
    return workbook(
        db,
        organization_id,
        title="Estimación del IVA y borrador del Formulario 120",
        subtitle=f"Período {estimate['month']:02d}/{estimate['year']}",
        chart_status="validated",
        columns=[
            Column("Concepto", width=70),
            Column("Casilla", width=10),
            Column("Importe", money=True, width=16),
            Column("Nota", width=60),
        ],
        rows=rows,
        notes=notes,
        sheet="IVA",
    )


def irp_xlsx(db: Session, organization_id: uuid.UUID, estimate: dict[str, Any]) -> bytes:
    """Borrador del IRP-RSP y del Formulario 515 (D-144), con los mismos importes del JSON."""

    def amount(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    register = estimate["register"]
    rows: list[Any] = [
        Styled(["Registro de comprobantes del año", None, None]),
        [f"Ingresos gravados ({register['income_count']})", None, amount(register["income_taxed"])],
        ["Ingresos no gravados o exonerados", None, amount(register["income_exempt"])],
        [f"Egresos ({register['expense_count']})", None, amount(register["expenses"])],
    ]
    result = estimate["result"]
    if result is not None:
        rows.extend(
            [
                Styled(["Renta neta imponible", None, amount(result["net_income"])]),
                Styled(["Impuesto por la escala", None, amount(result["tax"])]),
                Styled(["A pagar (estimado)", None, amount(result["to_pay"])]),
            ]
        )
    rows.append([])
    form = estimate["form_515"]
    if form["available"]:
        rows.append(Styled(["Borrador del Formulario 515 v1 (sin céntimos)", None, None]))
        for box in form["boxes"]:
            doubt = f" [{', '.join(box['doubts'])}]" if box["doubts"] else ""
            label = f"Rubro {box['rubro']}: {box['label']}{doubt}"
            rows.append([label, box["box"], amount(box["value"]), box["note"] or ""])
    else:
        rows.append([form["message"]])
    notes = [
        "Estimación, no declaración: copiá los valores a mano en Marangatu y revisalos.",
        "Reglas aplicadas: "
        + ", ".join(
            f"{r['code']} v{r['version']} ({r['validation_status']})"
            for r in estimate["rules_applied"]
        ),
        *[w["message"] for w in estimate["warnings"]],
        *form["warnings"],
    ]
    return workbook(
        db,
        organization_id,
        title="Borrador del IRP y del Formulario 515",
        subtitle=f"Ejercicio {estimate['year']}",
        chart_status="validated",
        columns=[
            Column("Concepto", width=70),
            Column("Casilla", width=10),
            Column("Importe", money=True, width=16),
            Column("Nota", width=60),
        ],
        rows=rows,
        notes=notes,
        sheet="IRP",
    )
