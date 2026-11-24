"""Lectura de extractos bancarios (CSV y XLSX) y mapeo de columnas a movimientos.

No toca la base: convierte bytes + mapeo en filas analizadas (fecha, importe, textos y un
error legible por fila). El servicio de importación decide duplicados y guarda el lote.

Seguridad y límites:
- XLSX con `openpyxl` en `read_only=True, data_only=True`: no se evalúan fórmulas ni se
  ejecutan macros; se lee el valor guardado en el archivo.
- `.xls` (formato binario antiguo) se rechaza con un mensaje claro.
- 10 MB por archivo y 20.000 filas de datos.
"""

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.errors import AppError
from app.modules.finance.money import AmountError, check_amount
from app.modules.finance.normalize import normalize_text

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000

_XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE2: .xls antiguo
_ZIP_MAGIC = b"PK\x03\x04"

ColumnName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SingleAmount(_Strict):
    mode: Literal["single"]
    column: ColumnName


class SplitAmount(_Strict):
    mode: Literal["split"]
    debit_column: ColumnName
    credit_column: ColumnName


class ImportMapping(_Strict):
    """Cómo leer el archivo. Sin encabezado, las columnas se nombran por posición: "1", "2"…"""

    has_header: bool = True
    delimiter: Literal[";", ",", "\t", "|"] = ";"
    encoding: Literal["auto", "utf-8", "cp1252"] = "auto"
    date_column: ColumnName
    date_format: Annotated[str, StringConstraints(min_length=2, max_length=40)] = "%d/%m/%Y"
    description_column: ColumnName
    reference_column: ColumnName | None = None
    amount: Annotated[SingleAmount | SplitAmount, Field(discriminator="mode")]
    decimal_separator: Literal[",", "."] = ","
    thousands_separator: Literal[".", ",", " ", ""] = "."
    skip_rows: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def _separators(self) -> "ImportMapping":
        if self.decimal_separator == self.thousands_separator:
            raise ValueError("El separador decimal y el de miles tienen que ser distintos.")
        if "%" not in self.date_format:
            raise ValueError("El formato de fecha usa códigos como %d/%m/%Y.")
        return self


@dataclass
class ParsedRow:
    row_number: int  # fila del archivo (1 = primera fila), para que la persona la encuentre
    raw: dict[str, str]
    booked_on: date | None = None
    amount: Decimal | None = None
    description: str | None = None
    reference: str | None = None
    error: str | None = None


@dataclass
class ParsedFile:
    file_format: Literal["csv", "xlsx"]
    rows: list[ParsedRow]


def import_error(code: str, message: str, status_code: int = 422) -> AppError:
    return AppError(code, message, status_code=status_code)


# --- Detección de formato y lectura -----------------------------------------------------


def detect_format(filename: str, content: bytes) -> Literal["csv", "xlsx"]:
    lower = filename.lower()
    if content.startswith(_XLS_MAGIC) or lower.endswith(".xls"):
        raise import_error(
            "IMPORT_UNSUPPORTED_FORMAT",
            "El formato .xls antiguo no se admite. Exportá el extracto como CSV o XLSX "
            "(en Excel: Guardar como → Libro de Excel .xlsx).",
        )
    if content.startswith(_ZIP_MAGIC):
        if lower.endswith((".csv", ".txt")):
            raise import_error("IMPORT_UNSUPPORTED_FORMAT", "El archivo no es un CSV de texto.")
        return "xlsx"
    if lower.endswith((".xlsx", ".xlsm")):
        raise import_error("IMPORT_UNREADABLE", "El archivo XLSX está dañado o no es un XLSX.")
    return "csv"


def _decode(content: bytes, encoding: str) -> str:
    # Los bancos paraguayos exportan en UTF-8 (a veces con BOM) o en Windows-1252.
    candidates = ["utf-8-sig", "cp1252"] if encoding == "auto" else [encoding]
    for candidate in candidates:
        try:
            return content.decode("utf-8-sig" if candidate == "utf-8" else candidate)
        except UnicodeDecodeError:
            continue
    raise import_error(
        "IMPORT_UNREADABLE",
        "No se pudo leer el texto del archivo (codificación desconocida). "
        "Exportalo como CSV UTF-8.",
    )


def _csv_rows(content: bytes, mapping: ImportMapping) -> Iterator[tuple[int, list[Any]]]:
    text = _decode(content, mapping.encoding)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=mapping.delimiter)
    try:
        for record in reader:
            yield reader.line_num, list(record)
    except csv.Error as exc:
        raise import_error(
            "IMPORT_UNREADABLE",
            f"El CSV está mal formado cerca de la fila {reader.line_num}: {exc}",
        ) from exc


def _xlsx_rows(content: bytes) -> Iterator[tuple[int, list[Any]]]:
    # Importación diferida: openpyxl solo se carga si alguien importa un XLSX.
    from openpyxl import load_workbook

    unreadable = "El archivo XLSX está dañado o no es un XLSX."
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # archivo ajeno: cualquier falla de lectura es "dañado"
        raise import_error("IMPORT_UNREADABLE", unreadable) from exc
    try:
        if not workbook.worksheets:
            raise import_error("IMPORT_EMPTY", "El archivo no tiene hojas.")
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        index = 0
        while True:
            try:
                values = next(rows)
            except StopIteration:
                break
            except Exception as exc:
                raise import_error("IMPORT_UNREADABLE", unreadable) from exc
            index += 1
            yield index, list(values)
    finally:
        workbook.close()


def _cell_text(value: Any) -> str:
    """Texto de una celda para `raw` y para el análisis (sin pasar nunca por float)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "VERDADERO" if value else "FALSO"
    if isinstance(value, float):
        # XLSX guarda los números como dobles: repr() da el decimal más corto que los
        # representa (el mismo texto que muestra Excel), sin redondeos de punto flotante.
        return repr(value)
    return str(value).strip()


# --- Conversión de valores --------------------------------------------------------------


def parse_date(value: Any, fmt: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _cell_text(value)
    if not text:
        raise ValueError("Falta la fecha")
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        raise ValueError(f"Fecha inválida: {text}") from None


def parse_amount(value: Any, mapping: ImportMapping) -> Decimal | None:
    """Importe de una celda. `None` si está vacía. Admite `1.234.567`, `1.234,50`, `-`, `( )`."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Importe inválido: {_cell_text(value)}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, Decimal):
        return value
    original = str(value).strip()
    text = "".join(original.replace(chr(0xA0), " ").split())  # sin espacios (ni duros)
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text[:1] in "+-":
        negative, text = negative ^ (text[0] == "-"), text[1:]
    elif text.endswith("-"):  # algunos bancos escriben el signo al final
        negative, text = not negative, text[:-1]
    ts = mapping.thousands_separator.strip()
    ds = re.escape(mapping.decimal_separator)
    if ts:
        grouped = rf"[0-9]{{1,3}}(?:{re.escape(ts)}[0-9]{{3}})+"
        pattern = rf"^(?:{grouped}|[0-9]+)(?:{ds}[0-9]+)?$"
    else:
        pattern = rf"^[0-9]+(?:{ds}[0-9]+)?$"
    if not re.match(pattern, text):
        raise ValueError(f"Importe inválido: {original}")
    if ts:
        text = text.replace(ts, "")
    text = text.replace(mapping.decimal_separator, ".")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Importe inválido: {original}") from None
    return -amount if negative else amount


# --- Lectura completa -------------------------------------------------------------------


def _resolve_columns(header: list[str], mapping: ImportMapping) -> dict[str, int]:
    """Posición de cada columna del mapeo. Coincidencia exacta o normalizada (sin tildes)."""
    exact = {name: i for i, name in reversed(list(enumerate(header)))}
    loose = {normalize_text(name): i for i, name in reversed(list(enumerate(header)))}
    wanted: dict[str, str | None] = {
        "date": mapping.date_column,
        "description": mapping.description_column,
        "reference": mapping.reference_column,
    }
    if isinstance(mapping.amount, SingleAmount):
        wanted["amount"] = mapping.amount.column
    else:
        wanted["debit"] = mapping.amount.debit_column
        wanted["credit"] = mapping.amount.credit_column
    resolved: dict[str, int] = {}
    missing: list[str] = []
    for key, name in wanted.items():
        if name is None:
            continue
        if not mapping.has_header:
            if name.isdigit() and 1 <= int(name) <= max(len(header), 1):
                resolved[key] = int(name) - 1
                continue
            missing.append(name)
            continue
        index = exact.get(name, loose.get(normalize_text(name)))
        if index is None:
            missing.append(name)
        else:
            resolved[key] = index
    if missing:
        available = [h for h in header if h] if mapping.has_header else []
        raise AppError(
            "IMPORT_COLUMN_NOT_FOUND",
            "No se encontraron estas columnas en el archivo: " + ", ".join(missing),
            status_code=422,
            details={"missing": missing, "available": available},
        )
    return resolved


def _cell(values: list[Any], index: int | None) -> Any:
    if index is None or index >= len(values):
        return None
    return values[index]


def _analyze(
    row_number: int,
    values: list[Any],
    names: list[str],
    columns: dict[str, int],
    mapping: ImportMapping,
    currency: str,
) -> ParsedRow:
    raw = {names[i] if i < len(names) else str(i + 1): _cell_text(v) for i, v in enumerate(values)}
    row = ParsedRow(row_number=row_number, raw=raw)
    errors: list[str] = []

    try:
        row.booked_on = parse_date(_cell(values, columns["date"]), mapping.date_format)
    except ValueError as exc:
        errors.append(str(exc))

    try:
        if "amount" in columns:
            amount = parse_amount(_cell(values, columns["amount"]), mapping)
            if amount is None:
                raise ValueError("Falta el importe")
        else:
            debit = parse_amount(_cell(values, columns["debit"]), mapping)
            credit = parse_amount(_cell(values, columns["credit"]), mapping)
            debit = abs(debit) if debit else None
            credit = abs(credit) if credit else None
            if debit is None and credit is None:
                raise ValueError("Falta el importe (débito y crédito vacíos)")
            if debit is not None and credit is not None:
                raise ValueError("La fila tiene débito y crédito a la vez")
            amount = credit if credit is not None else -(debit or Decimal(0))
        row.amount = check_amount(amount, currency, allow_zero=False)
    except AmountError as exc:
        errors.append(f"{exc} ({_amount_text(values, columns)})")
    except ValueError as exc:
        errors.append(str(exc))

    description = _cell_text(_cell(values, columns["description"]))
    description = " ".join(description.split())
    if not description:
        errors.append("Falta la descripción")
    elif len(description) > 500:
        errors.append("La descripción supera los 500 caracteres")
    else:
        row.description = description

    if "reference" in columns:
        reference = " ".join(_cell_text(_cell(values, columns["reference"])).split())
        if len(reference) > 100:
            errors.append("La referencia supera los 100 caracteres")
        else:
            row.reference = reference or None

    if errors:
        row.error = "; ".join(errors)[:300]
    return row


def _amount_text(values: list[Any], columns: dict[str, int]) -> str:
    keys = ("amount",) if "amount" in columns else ("debit", "credit")
    return " / ".join(_cell_text(_cell(values, columns[k])) for k in keys if k in columns)


def parse_file(filename: str, content: bytes, mapping: ImportMapping, currency: str) -> ParsedFile:
    if len(content) > MAX_FILE_BYTES:
        raise import_error(
            "IMPORT_FILE_TOO_LARGE", "El archivo supera los 10 MB permitidos.", status_code=413
        )
    if not content:
        raise import_error("IMPORT_EMPTY", "El archivo está vacío.")
    file_format = detect_format(filename, content)
    source = _xlsx_rows(content) if file_format == "xlsx" else _csv_rows(content, mapping)

    names: list[str] = []
    columns: dict[str, int] | None = None
    rows: list[ParsedRow] = []
    header_pending = mapping.has_header
    for row_number, values in source:
        if row_number <= mapping.skip_rows:
            continue
        if all(_cell_text(v) == "" for v in values):
            continue  # filas vacías: se ignoran
        if header_pending:
            names = [_cell_text(v) for v in values]
            columns = _resolve_columns(names, mapping)
            header_pending = False
            continue
        if columns is None:
            names = [str(i + 1) for i in range(len(values))]
            columns = _resolve_columns(names, mapping)
        if len(rows) >= MAX_ROWS:
            raise import_error(
                "IMPORT_TOO_MANY_ROWS",
                f"El archivo tiene más de {MAX_ROWS:,} filas de datos. Dividilo en partes.".replace(
                    ",", "."
                ),
            )
        rows.append(_analyze(row_number, values, names, columns, mapping, currency))
    if not rows:
        raise import_error("IMPORT_EMPTY", "El archivo no tiene filas de datos.")
    return ParsedFile(file_format=file_format, rows=rows)
