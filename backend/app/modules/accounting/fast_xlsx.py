"""XLSX de una hoja escrito a mano, para los libros con muchas filas (D-100, D-117).

Mismo contenido y formato que `exports.workbook()` (encabezado, títulos en negrita,
importes como enteros con `#,##0`, fechas como fechas de Excel, totales destacados), pero
arma el XML de la hoja como texto. Motivo: `openpyxl` sin `lxml` (que no se agrega: no hay
dependencias nuevas de producción) es lento con cientos de miles de celdas. Lo usan el
registro de comprobantes de un año (20.000 comprobantes por 24 columnas, spec 4 §5.12) y el
libro diario (20.000 líneas, spec 3B §5.10), los dos con un límite de 3 s. El resto de los
XLSX sigue con `openpyxl`.

Formato: Office Open XML mínimo (tipos de contenido, relaciones, libro, estilos y una hoja),
con las cadenas en línea (`inlineStr`). Las pruebas lo abren con `openpyxl`.
"""

import io
import re
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from sqlalchemy.orm import Session

from app.modules.accounting.exports import (
    DATE_FORMAT,
    MONEY_FORMAT,
    UNVALIDATED_NOTICE,
    Column,
    Row,
    Styled,
    _organization_lines,
)

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
# Caracteres que XML 1.0 no admite (los mismos que rechaza openpyxl).
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Índices de `cellXfs` en styles.xml.
PLAIN, BOLD, MONEY, MONEY_BOLD, DATE, DATE_BOLD = range(6)
# Día 0 de las fechas de Excel (sistema 1900, con el 29/02/1900 inexistente ya descontado).
EXCEL_EPOCH = date(1899, 12, 30)

CONTENT_TYPES = (
    HEADER + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    HEADER + f'<Relationships xmlns="{PKG_RELS}">'
    f'<Relationship Id="rId1" Type="{RELS}/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
WORKBOOK_RELS = (
    HEADER + f'<Relationships xmlns="{PKG_RELS}">'
    f'<Relationship Id="rId1" Type="{RELS}/worksheet" Target="worksheets/sheet1.xml"/>'
    f'<Relationship Id="rId2" Type="{RELS}/styles" Target="styles.xml"/>'
    "</Relationships>"
)
STYLES = (
    HEADER + f'<styleSheet xmlns="{MAIN}">'
    '<numFmts count="2">'
    f'<numFmt numFmtId="164" formatCode={quoteattr(MONEY_FORMAT)}/>'
    f'<numFmt numFmtId="165" formatCode={quoteattr(DATE_FORMAT)}/>'
    "</numFmts>"
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="6">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"'
    ' applyFont="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"'
    ' applyFont="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


def _letters(count: int) -> list[str]:
    result = []
    for index in range(1, count + 1):
        name = ""
        while index:
            index, rest = divmod(index - 1, 26)
            name = chr(65 + rest) + name
        result.append(name)
    return result


def _text(value: str) -> str:
    clean = escape(_ILLEGAL.sub("", value))
    space = ' xml:space="preserve"' if clean != clean.strip() else ""
    return f"<is><t{space}>{clean}</t></is>"


class _Sheet:
    def __init__(self, width: int) -> None:
        self.parts: list[str] = []
        self.number = 0
        self.letters = _letters(max(width, 1))

    def _letter(self, index: int) -> str:
        while index >= len(self.letters):
            self.letters = _letters(len(self.letters) * 2)
        return self.letters[index]

    def append(self, values: Sequence[Any], money: Sequence[bool], strong: bool) -> None:
        self.number += 1
        n = self.number
        cells: list[str] = []
        for index, value in enumerate(values):
            if value is None or value == "":
                continue  # celda vacía: no se escribe
            ref = f"{self._letter(index)}{n}"
            is_money = index < len(money) and money[index]
            if isinstance(value, bool):
                raise TypeError("Booleano en un XLSX: usá S/N")  # pragma: no cover
            if isinstance(value, datetime):
                raise TypeError("Fecha y hora en un XLSX: pasala como texto")  # pragma: no cover
            if isinstance(value, date):
                style = DATE_BOLD if strong else DATE
                serial = (value - EXCEL_EPOCH).days
                cells.append(f'<c r="{ref}" s="{style}"><v>{serial}</v></c>')
                continue
            if isinstance(value, int | Decimal):
                if is_money:
                    style = MONEY_BOLD if strong else MONEY
                    number = str(int(value))
                else:
                    style = BOLD if strong else PLAIN
                    integral = isinstance(value, int) or value == value.to_integral_value()
                    number = str(int(value)) if integral else format(value, "f")
                cells.append(f'<c r="{ref}" s="{style}"><v>{number}</v></c>')
            else:
                style = BOLD if strong else PLAIN
                cells.append(f'<c r="{ref}" s="{style}" t="inlineStr">{_text(str(value))}</c>')
        self.parts.append(f'<row r="{n}">{"".join(cells)}</row>')


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
    """Igual que `exports.workbook()`, más rápido para muchas filas."""
    ws = _Sheet(len(columns))
    no_money: list[bool] = []
    for i, line in enumerate(_organization_lines(db, organization_id)):
        ws.append([line], no_money, strong=i == 0)
    ws.append([title], no_money, strong=True)
    ws.append([subtitle], no_money, strong=False)
    ws.append([f"Emitido el {datetime.now():%d/%m/%Y %H:%M}"], no_money, strong=False)
    if chart_status != "validated":
        ws.append([UNVALIDATED_NOTICE], no_money, strong=True)
    for note in notes:
        ws.append([note], no_money, strong=False)
    ws.append([], no_money, strong=False)
    ws.append([c.title for c in columns], no_money, strong=True)
    money = [c.money for c in columns]
    for row in rows:
        if isinstance(row, Styled):
            ws.append(row.values, money, strong=row.bold)
        else:
            ws.append(row, money, strong=False)

    cols = "".join(
        f'<col min="{i}" max="{i}" width="{c.width}" customWidth="1"/>'
        for i, c in enumerate(columns, start=1)
    )
    sheet_xml = (
        HEADER
        + f'<worksheet xmlns="{MAIN}" xmlns:r="{RELS}">'
        + (f"<cols>{cols}</cols>" if cols else "")
        + "<sheetData>"
        + "".join(ws.parts)
        + "</sheetData></worksheet>"
    )
    workbook_xml = (
        HEADER + f'<workbook xmlns="{MAIN}" xmlns:r="{RELS}"><sheets>'
        f'<sheet name={quoteattr(_ILLEGAL.sub("", sheet[:31]))} sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml.encode("utf-8"))
    return buffer.getvalue()
