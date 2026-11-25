"""Libros y estados exportables a XLSX (D-063), con `openpyxl` en modo de escritura.

Cada archivo trae:
- encabezado con la razón social, el RUC con su dígito verificador, el título, el rango o
  la fecha, la fecha de emisión y, si el plan no está validado, el aviso "Plan de cuentas
  sin verificar contra la fuente oficial" (D-038, D-120), más las notas propias del reporte;
- importes como **números** (guaraníes enteros, `int`: nunca `float` ni texto) con el
  formato `#,##0`. Es el código de formato de Excel: en una configuración regional de
  Paraguay se muestra con punto de miles, `#.##0` (D-076);
- totales iguales a los del JSON del mismo reporte.

El diario y el mayor salen completos, sin paginar. El diario usa el escritor propio de
`fast_xlsx` (D-117).
"""

import io
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounting import asset_schedule, chart, reports
from app.modules.accounting.balances import ZERO
from app.modules.organizations.models import Organization

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MONEY_FORMAT = "#,##0"
DATE_FORMAT = "yyyy-mm-dd"  # el que pone openpyxl a las fechas; `fast_xlsx` usa el mismo
UNVALIDATED_NOTICE = "Plan de cuentas sin verificar contra la fuente oficial"


@dataclass(frozen=True)
class Column:
    title: str
    money: bool = False
    width: int = 16


@dataclass(frozen=True)
class Styled:
    """Fila destacada (títulos de sección y totales)."""

    values: Sequence[Any]
    bold: bool = True


Row = Sequence[Any] | Styled


def range_text(date_from: date, date_to: date) -> str:
    return f"Del {date_from:%d/%m/%Y} al {date_to:%d/%m/%Y}"


def at_text(at: date) -> str:
    return f"Al {at:%d/%m/%Y}"


def _organization_lines(db: Session, organization_id: uuid.UUID) -> list[str]:
    org = db.scalar(select(Organization).where(Organization.id == organization_id))
    if org is None:  # pragma: no cover - la organización activa existe
        return []
    ruc = f"RUC: {org.ruc}-{org.ruc_check_digit}" if org.ruc else "RUC: sin cargar"
    return [org.legal_name, ruc]


def workbook(
    db: Session,
    organization_id: uuid.UUID,
    *,
    title: str,
    subtitle: str,
    chart_status: str,
    columns: Sequence[Column],
    rows: Iterable[Row],
    notes: Sequence[str] = (),
    sheet: str = "Reporte",
) -> bytes:
    # Importación diferida, como en finanzas: openpyxl solo se carga si se exporta.
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    book = Workbook(write_only=True)
    ws = book.create_sheet(sheet[:31])
    for index, column in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(index)].width = column.width
    bold = Font(bold=True)

    def text(value: str, *, strong: bool = False) -> Any:
        cell = WriteOnlyCell(ws, value=value)
        if strong:
            cell.font = bold
        return cell

    header = _organization_lines(db, organization_id)
    for i, line in enumerate(header):
        ws.append([text(line, strong=i == 0)])
    ws.append([text(title, strong=True)])
    ws.append([subtitle])
    ws.append([f"Emitido el {datetime.now():%d/%m/%Y %H:%M}"])
    if chart_status != "validated":
        ws.append([text(UNVALIDATED_NOTICE, strong=True)])
    for note in notes:
        ws.append([note])
    ws.append([])
    ws.append([text(c.title, strong=True) for c in columns])

    money = [c.money for c in columns]
    for row in rows:
        strong = isinstance(row, Styled)
        values = row.values if isinstance(row, Styled) else row
        cells: list[Any] = []
        for index, value in enumerate(values):
            if index < len(money) and money[index] and isinstance(value, Decimal):
                cell = WriteOnlyCell(ws, value=int(value))
                cell.number_format = MONEY_FORMAT
                if strong:
                    cell.font = bold
                cells.append(cell)
            elif strong and isinstance(value, str):
                cells.append(text(value, strong=True))
            elif isinstance(value, Decimal):
                # Números que no son importes (porcentajes, años): openpyxl escribe el
                # Decimal como número, sin pasar por float.
                cells.append(int(value) if value == value.to_integral_value() else value)
            else:
                cells.append(value)
        ws.append(cells)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# --- Reportes -----------------------------------------------------------------------------


def _blank(width: int, *values: Any) -> list[Any]:
    return [*values, *([None] * (width - len(values)))]


def journal_xlsx(
    db: Session, organization_id: uuid.UUID, date_from: date, date_to: date, chart_status: str
) -> bytes:
    """Libro diario completo: una fila por línea, en orden de fecha, número y línea.

    Con el escritor propio (D-117): el diario de un año puede tener decenas de miles de líneas.
    """
    # Diferida: `fast_xlsx` importa piezas de este módulo.
    from app.modules.accounting import fast_xlsx

    page = reports.journal(db, organization_id, date_from, date_to, limit=1, after=None)
    columns = [
        Column("Fecha", width=11),
        Column("N°", width=7),
        Column("Asiento", width=40),
        Column("Comprobante", width=16),
        Column("Cuenta", width=14),
        Column("Nombre de la cuenta", width=36),
        Column("Centro", width=10),
        Column("Detalle", width=30),
        Column("Debe", money=True),
        Column("Haber", money=True),
    ]

    def rows() -> Iterable[Row]:
        for line in reports.journal_lines(db, organization_id, date_from, date_to):
            yield [
                line.entry_date,
                line.number,
                line.entry_description,
                line.document_reference,
                line.account_code,
                line.account_name,
                line.cost_center_code,
                line.line_description,
                line.debit,
                line.credit,
            ]
        yield Styled([*_blank(8, "Totales"), page.total_debit, page.total_credit])

    return fast_xlsx.workbook(
        db,
        organization_id,
        title="Libro diario",
        subtitle=range_text(date_from, date_to),
        chart_status=chart_status,
        columns=columns,
        rows=rows(),
        sheet="Libro diario",
    )


def ledger_xlsx(
    db: Session,
    organization_id: uuid.UUID,
    account_id: uuid.UUID,
    date_from: date,
    date_to: date,
    chart_status: str,
) -> bytes:
    report = reports.ledger(
        db, organization_id, account_id, date_from, date_to, limit=2**31 - 1, after=None
    )
    columns = [
        Column("Fecha", width=11),
        Column("N°", width=7),
        Column("Asiento", width=40),
        Column("Detalle", width=30),
        Column("Comprobante", width=16),
        Column("Debe", money=True),
        Column("Haber", money=True),
        Column("Saldo", money=True),
    ]

    def rows() -> Iterable[Row]:
        yield Styled([*_blank(7, None, None, "Saldo anterior"), report.opening_balance])
        for m in report.movements:
            yield [
                m.entry_date,
                m.number,
                m.entry_description,
                m.line_description,
                m.document_reference,
                m.debit,
                m.credit,
                m.balance,
            ]
        yield Styled(
            [
                *_blank(5, None, None, "Totales"),
                report.total_debit,
                report.total_credit,
                report.closing_balance,
            ]
        )

    side = "deudora" if report.account.normal_side == "debit" else "acreedora"
    return workbook(
        db,
        organization_id,
        title=f"Libro mayor: {report.account.code} {report.account.name}",
        subtitle=range_text(date_from, date_to),
        chart_status=chart_status,
        columns=columns,
        rows=rows(),
        notes=[f"Saldo en el sentido de la naturaleza de la cuenta ({side})."],
        sheet="Libro mayor",
    )


TRIAL_FIELDS = (
    "opening_debit",
    "opening_credit",
    "debit",
    "credit",
    "debit_balance",
    "credit_balance",
    "closing_debit",
    "closing_credit",
)


def trial_balance_xlsx(
    db: Session, organization_id: uuid.UUID, date_from: date, date_to: date, chart_status: str
) -> bytes:
    trial = reports.trial_balance(db, organization_id, date_from, date_to)
    columns = [
        Column("Código", width=14),
        Column("Cuenta", width=40),
        Column("Saldo inicial deudor", money=True),
        Column("Saldo inicial acreedor", money=True),
        Column("Debe", money=True),
        Column("Haber", money=True),
        Column("Saldo deudor del rango", money=True),
        Column("Saldo acreedor del rango", money=True),
        Column("Saldo final deudor", money=True),
        Column("Saldo final acreedor", money=True),
    ]

    def rows() -> Iterable[Row]:
        for r in trial:
            yield [r.account.code, r.account.name, *(getattr(r, f) for f in TRIAL_FIELDS)]
        yield Styled(
            ["Totales", None, *(sum((getattr(r, f) for r in trial), ZERO) for f in TRIAL_FIELDS)]
        )

    return workbook(
        db,
        organization_id,
        title="Balance de comprobación de sumas y saldos",
        subtitle=range_text(date_from, date_to),
        chart_status=chart_status,
        columns=columns,
        rows=rows(),
        sheet="Balance de comprobación",
    )


def _tree_rows(nodes: Sequence[chart.Node], depth: int = 0) -> Iterable[Row]:
    for node in nodes:
        values = ["  " * depth + node.account.code, node.account.name, node.amount]
        yield values if node.account.is_postable else Styled(values)
        yield from _tree_rows(node.children, depth + 1)


def balance_sheet_xlsx(
    db: Session, organization_id: uuid.UUID, at: date, chart_status: str
) -> bytes:
    sheet = reports.balance_sheet(db, organization_id, at)
    columns = [
        Column("Código", width=18),
        Column("Cuenta", width=44),
        Column("Importe", money=True),
    ]

    def rows() -> Iterable[Row]:
        for label, section in (
            ("ACTIVO", sheet.assets),
            ("PASIVO", sheet.liabilities),
            ("PATRIMONIO NETO", sheet.equity),
        ):
            yield Styled([None, label, None])
            yield from _tree_rows(section.nodes)
            yield Styled([None, f"Total {label.lower()}", section.total])
        yield Styled([None, "Resultado no refundido", sheet.result])
        yield Styled(
            [None, "Total pasivo, patrimonio neto y resultado", sheet.liabilities_and_equity]
        )

    return workbook(
        db,
        organization_id,
        title="Balance general",
        subtitle=at_text(at),
        chart_status=chart_status,
        columns=columns,
        rows=rows(),
        sheet="Balance general",
    )


def income_statement_xlsx(
    db: Session,
    organization_id: uuid.UUID,
    date_from: date,
    date_to: date,
    chart_status: str,
    *,
    by_cost_center: bool,
) -> bytes:
    statement = reports.income_statement(
        db, organization_id, date_from, date_to, by_cost_center=by_cost_center
    )
    centers = statement.columns or []
    columns = [
        Column("Código", width=18),
        Column("Cuenta", width=44),
        *(
            Column(
                f"{c.center.code} {c.center.name}" if c.center is not None else "Sin centro",
                money=True,
            )
            for c in centers
        ),
        Column("Importe", money=True),
    ]

    def node_rows(nodes: Sequence[chart.Node], depth: int = 0) -> Iterable[Row]:
        for node in nodes:
            values = [
                "  " * depth + node.account.code,
                node.account.name,
                *statement.column_amounts.get(node.account.id, []),
                node.amount,
            ]
            yield values if node.account.is_postable else Styled(values)
            yield from node_rows(node.children, depth + 1)

    def rows() -> Iterable[Row]:
        yield from node_rows(statement.nodes)
        yield Styled(
            [None, "Total ingresos", *(c.total_income for c in centers), statement.total_income]
        )
        yield Styled(
            [None, "Total gastos", *(c.total_expense for c in centers), statement.total_expense]
        )
        yield Styled(
            [None, "Resultado del período", *(c.result for c in centers), statement.result]
        )

    return workbook(
        db,
        organization_id,
        title="Estado de resultados" + (" por centro de costos" if by_cost_center else ""),
        subtitle=range_text(date_from, date_to),
        chart_status=chart_status,
        columns=columns,
        rows=rows(),
        notes=["Sin el asiento de refundición de resultados."],
        sheet="Estado de resultados",
    )


# (título, columna del cuadro si es un importe, ancho). Numeración del Anexo de la RG 77/2020.
SCHEDULE_COLUMNS: tuple[tuple[str, str | None, int], ...] = (
    ("1. Descripción del bien", None, 36),
    ("Categoría", None, 30),
    ("3. Fecha de adquisición", None, 12),
    ("2. Valor de costo", "cost", 16),
    ("4. Coeficiente de revalúo", None, 10),
    ("5. % valor residual fiscal", None, 10),
    ("6. Valor residual fiscal", "fiscal_residual_value", 16),
    ("7. Vida útil fiscal (años)", None, 10),
    ("8. Vida útil fiscal restante (años)", None, 10),
    ("9. Valor fiscal neto del ejercicio anterior", "fiscal_net_previous", 16),
    ("10. Valor fiscal neto anterior menos residual", "fiscal_depreciable", 16),
    ("11. Cuota fiscal del ejercicio", "fiscal_depreciation", 16),
    ("12. Depreciación fiscal acumulada", "fiscal_accumulated", 16),
    ("13. Valor fiscal neto al cierre", "fiscal_net_value", 16),
    ("14. Valor residual contable", "residual_value", 16),
    ("15. Vida útil contable (años)", None, 10),
    ("16. Vida útil contable restante (años)", None, 10),
    ("17. Valor contable neto del ejercicio anterior", "accounting_net_previous", 16),
    ("18. Valor contable neto anterior menos residual", "accounting_depreciable", 16),
    ("19. Cuota contable del ejercicio", "accounting_depreciation", 16),
    ("20. Cuota no deducible", "non_deductible", 16),
    ("21. Depreciación contable acumulada", "accounting_accumulated", 16),
    ("22. Valor contable neto al cierre", "accounting_net_value", 16),
    ("Fecha de baja", None, 12),
)


def schedule_xlsx(
    db: Session, organization_id: uuid.UUID, fiscal_year_id: uuid.UUID, chart_status: str
) -> bytes:
    report = asset_schedule.schedule(db, organization_id, fiscal_year_id)
    columns = [Column(title, money=key is not None, width=w) for title, key, w in SCHEDULE_COLUMNS]

    def totals(label: str, total: Callable[[str], Decimal]) -> Styled:
        return Styled(
            [
                label if i == 0 else (total(key) if key is not None else None)
                for i, (_title, key, _w) in enumerate(SCHEDULE_COLUMNS)
            ]
        )

    def rows() -> Iterable[Row]:
        for group in report.groups:
            yield Styled(_blank(len(SCHEDULE_COLUMNS), group.category.name))
            for r in group.rows:
                yield [
                    r.asset.name,
                    group.category.name,
                    r.asset.acquired_on,
                    r.cost,
                    r.revaluation_coefficient,
                    r.fiscal_residual_rate,
                    r.fiscal_residual_value,
                    asset_schedule.years(r.fiscal_useful_life_months),
                    asset_schedule.years(r.fiscal_remaining_months),
                    r.fiscal_net_previous,
                    r.fiscal_depreciable,
                    r.fiscal_depreciation,
                    r.fiscal_accumulated,
                    r.fiscal_net_value,
                    r.residual_value,
                    asset_schedule.years(r.useful_life_months),
                    asset_schedule.years(r.remaining_months),
                    r.accounting_net_previous,
                    r.accounting_depreciable,
                    r.accounting_depreciation,
                    r.non_deductible,
                    r.accounting_accumulated,
                    r.accounting_net_value,
                    r.asset.disposed_on if r.disposed_in_year else None,
                ]
            yield totals(f"Total {group.category.name}", group.total)
        yield totals("TOTALES", report.total)
        yield []
        yield Styled(["Conciliación del valor contable neto (col. 22) con el balance"])
        yield Styled(["Cuenta", None, None, "Saldo en el mayor", None, None, "Según el cuadro"])
        for line in report.reconciliation:
            yield [
                f"{line.account.code} {line.account.name}",
                None,
                None,
                line.ledger_balance,
                None,
                None,
                line.schedule_amount,
            ]
        yield Styled(
            [
                "Total",
                None,
                None,
                report.ledger_total,
                None,
                None,
                report.total("accounting_net_value"),
            ]
        )
        yield ["Cuadra con el balance." if report.reconciled else "NO cuadra con el balance."]

    year = report.year
    return workbook(
        db,
        organization_id,
        title="Cuadro de depreciación de los bienes del activo fijo (RG 77/2020, sin revalúo)",
        subtitle=f"Ejercicio {year.start_date:%d/%m/%Y} - {year.end_date:%d/%m/%Y}",
        chart_status=chart_status,
        columns=columns,
        rows=rows(),
        notes=report.warnings,
        sheet="Cuadro de depreciación",
    )
