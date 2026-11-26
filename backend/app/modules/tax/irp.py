"""Borrador anual del IRP-RSP y del Formulario 515 v1 (fase M8, D-144).

Es una **estimación**, como la del IVA (D-090, D-097): se calcula en el momento con los
comprobantes vivos del año que imputan al IRP-RSP, y la persona la copia a mano en Marangatu.
Solo para el año cuyo perfil vigente al 31 de diciembre tiene la 715 dada de alta a esa fecha
(la misma regla que genera la obligación, D-087, D-142).

De dónde sale cada importe (el instructivo del 515 dice «de acuerdo con lo declarado en el
Libro de Ingresos» y «en el Libro de Egresos»: es el registro de comprobantes, D-143):
- **ingresos**: los INGRESOS del registro (`income`: `taxed_10` gravado en la casilla 12,
  `exempt` no gravado o exonerado en la 10) y las ventas con timbrado al contado (base sin
  IVA en la 12; las notas de crédito emitidas restan). El instructivo: «Se excluirán de los
  ingresos el IVA»;
- **egresos**: los EGRESOS del registro (`expense`, el total) y las compras con timbrado al
  contado (con el IVA si no imputa al IVA, sin el IVA si es crédito fiscal: Ley 6380, art. 68;
  las notas de crédito recibidas restan);
- **a crédito**: los comprobantes con timbrado a crédito no entran, porque el IRP va por lo
  percibido y lo pagado (art. 52): entran sus cobros (203) y pagos (201). Se avisa cuántos;
- la app no guarda el rubro de cada egreso: el total va a la casilla 22 y las casillas 15 a
  21 quedan vacías, para repartirlo en Marangatu (D-PF-19).

Lo que necesita datos personales que la app no tiene (D-PF-16: familiares a cargo, el
autovehículo cada 3 años, la vivienda cada 5 años y su pérdida arrastrable, los préstamos del
Anexo) y las retenciones (casilla 41, D-PF-5) quedan **vacías** con «no calculado: falta el
dato», nunca estimadas. Las casillas que dependen de ellas se calculan sin ellas y lo dicen
(«sin 23»), como el borrador del Formulario 120.

Tasas por tramo de la renta neta (casilla 45) desde la regla `IRP-RSP-DJ` (Ley 6380, art. 69):
8 % hasta ₲ 50.000.000, 9 % hasta ₲ 150.000.000 y 10 % por encima, cada una sobre su porción
y redondeada a guaraníes enteros (la mitad hacia arriba, como en el IVA: D-122, D-F4-7). Con
ingresos gravados de hasta el monto no alcanzado (₲ 80.000.000) la DJ se presenta igual (RG
69/2020, arts. 11 y 28), pero no se paga (art. 69, último párrafo): las casillas 46 a 48
muestran lo que da la escala y el resultado estimado a pagar es cero (D-PF-19).

**Condición 3 de la D-119 sin contabilidad** (`condition_3`, `register_control`): para la
persona física sin IRE General, el cuadre se hace al guaraní entre las casillas que salen del
registro y la suma, comprobante por comprobante, del registro. El bot (B4 en adelante) lo va a
consumir; hoy no presenta nada.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.modules.marangatu.stop_codes import StopCode
from app.modules.organizations.models import Organization
from app.modules.tax import obligations, rule_params, rules, vouchers
from app.modules.tax import profile as profiles
from app.modules.tax.common import ZERO, pyg
from app.modules.tax.models import RuleVersion, Voucher

IRP_RULE = "IRP-RSP-DJ"
IRP_OBLIGATION = "715"
REGISTER_RULE = vouchers.ANNUAL_REGISTER_RULE
ROUNDING_DOUBT = "D-F4-7"
DRAFT_DOUBT = "D-PF-19"
PERSONAL_DATA = "D-PF-16"
WITHHOLDINGS = "D-PF-5"
# Casillas que salen directamente del registro de comprobantes (las que cuadra la condición 3).
REGISTER_BOXES = ("10", "12", "14", "22")

MISSING = "No calculado: falta el dato."
FROM_USER = "Viene de la DJ anterior o de la cuenta corriente en Marangatu: la app no la calcula."


def whole(amount: Decimal) -> Decimal:
    """Guaraníes enteros, la mitad hacia arriba (D-122): el 515 va «sin céntimos»."""
    return amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ alcance


def irp_registration(db: Session, organization_id: uuid.UUID, year: int) -> date | None:
    """Alta de la 715 en el perfil vigente al 31 de diciembre de `year`, o `None`."""
    end = date(year, 12, 31)
    current = profiles.vigente(profiles.versions(db, organization_id), end)
    if current is None:
        return None
    return next(
        (
            o.registered_on
            for o in current.obligations
            if o.code == IRP_OBLIGATION and o.registered_on <= end
        ),
        None,
    )


def keeps_accounting(db: Session, organization_id: uuid.UUID, day: date) -> bool:
    """Si la organización lleva contabilidad por partida doble a `day` (D-PF-11, D-142): todas,
    salvo la persona física sin IRE General (el mismo criterio que el aviso del frontend)."""
    org = db.get(Organization, organization_id)
    assert org is not None
    if org.legal_form != "PERSONA_FISICA":
        return True
    current = profiles.vigente(profiles.versions(db, organization_id), day)
    return current is not None and current.profile.ire_regime == "ire_general"


# ------------------------------------------------------------------ registro


@dataclass
class RegisterSums:
    """Lo que el registro del año aporta al 515 (casillas 10, 12 y 22) y lo que queda afuera."""

    income_taxed: Decimal = ZERO  # casilla 12
    income_exempt: Decimal = ZERO  # casilla 10
    expenses: Decimal = ZERO  # casilla 22
    income_count: int = 0
    expense_count: int = 0
    credit_excluded: int = 0
    card_with_vat: int = 0

    def boxes(self) -> dict[str, Decimal]:
        taxed = whole(self.income_taxed)
        return {
            "10": whole(self.income_exempt),
            "12": taxed,
            "14": taxed,
            "22": whole(self.expenses),
        }


def _year_filter(organization_id: uuid.UUID, year: int) -> tuple[Any, ...]:
    return (
        Voucher.organization_id == organization_id,
        Voucher.voided_at.is_(None),
        Voucher.issued_on >= date(year, 1, 1),
        Voucher.issued_on <= date(year, 12, 31),
        Voucher.imputes_irp.is_(True),
    )


def register_sums(db: Session, organization_id: uuid.UUID, year: int) -> RegisterSums:
    """Sumas del año en una consulta agrupada (como `vat.month_sums`)."""
    rows = db.execute(
        select(
            Voucher.direction,
            Voucher.voucher_type,
            Voucher.condition,
            Voucher.imputes_vat,
            func.sum(Voucher.taxed_10),
            func.sum(Voucher.taxed_5),
            func.sum(Voucher.exempt),
            func.sum(Voucher.vat_10),
            func.sum(Voucher.vat_5),
            func.count(),
        )
        .where(*_year_filter(organization_id, year))
        .group_by(Voucher.direction, Voucher.voucher_type, Voucher.condition, Voucher.imputes_vat)
    ).all()
    sums = RegisterSums()
    for direction, vtype, condition, imputes_vat, t10, t5, ex, v10, v5, count in rows:
        if direction == "income":
            sums.income_taxed += t10
            sums.income_exempt += ex
            sums.income_count += count
        elif direction == "expense":
            sums.expenses += t10
            sums.expense_count += count
            if vtype == "card_statement" and imputes_vat:
                sums.card_with_vat += count
        elif condition == "credit":
            sums.credit_excluded += count
        else:
            sign = -1 if vtype == "credit_note" else 1
            total = t10 + t5 + ex
            if direction == "sale":
                sums.income_taxed += sign * (total - v10 - v5)
                sums.income_count += count
            else:
                sums.expenses += sign * (total - (v10 + v5 if imputes_vat else ZERO))
                sums.expense_count += count
    return sums


def _voucher_amounts(voucher: Voucher) -> tuple[Decimal, Decimal, Decimal] | None:
    """(gravado, exonerado, egreso) de un comprobante, o `None` si no entra (a crédito)."""
    if voucher.direction == "income":
        return voucher.taxed_10, voucher.exempt, ZERO
    if voucher.direction == "expense":
        return ZERO, ZERO, voucher.taxed_10
    if voucher.condition == "credit":
        return None
    sign = -1 if voucher.voucher_type == "credit_note" else 1
    vat = voucher.vat_10 + voucher.vat_5
    total = voucher.taxed_10 + voucher.taxed_5 + voucher.exempt
    if voucher.direction == "sale":
        return sign * (total - vat), ZERO, ZERO
    return ZERO, ZERO, sign * (total - (vat if voucher.imputes_vat else ZERO))


# ------------------------------------------------------------------ Formulario 515


@dataclass(frozen=True)
class Box:
    number: str
    rubro: int
    label: str
    value: Decimal | None
    # calculated | not_calculated (depende de otras casillas o la carga Marangatu) |
    # missing_data (falta un dato personal que la app no tiene: D-PF-16, D-PF-5)
    status: str
    doubts: tuple[str, ...] = ()
    note: str | None = None
    # De dónde sale: `income` o `expense` (el registro), o `None` (fórmula o vacía).
    origin: str | None = None

    def out(self) -> dict[str, Any]:
        return {
            "box": self.number,
            "rubro": self.rubro,
            "label": self.label,
            "value": pyg(self.value),
            "status": self.status,
            "doubts": list(self.doubts),
            "note": self.note,
            "origin": self.origin,
        }


@dataclass
class Liquidation:
    net_income: Decimal
    by_bracket: list[Decimal]
    reached: bool

    @property
    def tax(self) -> Decimal:
        return sum(self.by_bracket, ZERO)

    @property
    def to_pay(self) -> Decimal:
        return self.tax if self.reached else ZERO


@dataclass
class Draft:
    boxes: list[Box] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def bracket_taxes(net_income: Decimal, params: rule_params.IrpServicesParams) -> list[Decimal]:
    """Impuesto de cada tramo sobre su porción de la renta neta (art. 69), en guaraníes."""
    taxes: list[Decimal] = []
    lower = ZERO
    for bracket in params.rate_brackets:
        upper = None if bracket.up_to_pyg is None else Decimal(bracket.up_to_pyg)
        top = net_income if upper is None else min(net_income, upper)
        portion = max(top - lower, ZERO)
        taxes.append(whole(portion * bracket.rate))
        if upper is not None:
            lower = upper
    return taxes


def form_515(
    sums: RegisterSums, params: rule_params.IrpServicesParams
) -> tuple[Draft, Liquidation]:
    """Casillas del Formulario 515 v1 (`TRIBUTACION_PERSONA_FISICA.md` §4.5) y avisos."""
    draft = Draft()
    v = sums.boxes()
    v["24"] = v["22"]
    v["25"] = v["14"]
    v["26"] = min(v["22"], v["25"])
    v["27"] = v["25"] - v["26"]
    v["29"] = v["27"]
    v["45"] = v["29"]
    threshold = Decimal(params.not_reached_amount_pyg)
    reached = v["14"] > threshold
    taxes = bracket_taxes(v["45"], params)
    liquidation = Liquidation(v["45"], taxes, reached)
    tramos = _tramos(params)

    def calc(number: str, rubro: int, label: str, *doubts: str, **kw: Any) -> Box:
        return Box(number, rubro, label, v[number], "calculated", doubts, **kw)

    def empty(number: str, rubro: int, label: str, note: str, *doubts: str) -> Box:
        return Box(number, rubro, label, None, "not_calculated", doubts, note)

    def missing(number: str, rubro: int, label: str, why: str, *doubts: str) -> Box:
        return Box(number, rubro, label, None, "missing_data", doubts, f"{MISSING} {why}")

    housing = "La vivienda cada 5 años depende de datos que la app no tiene."
    split = (
        "La app no guarda el rubro de cada egreso: el total va en la casilla 22. Repartilo en "
        "Marangatu."
    )
    below = (
        None
        if reached
        else f"Ingresos gravados de hasta ₲ {_thousands(params.not_reached_amount_pyg)}: "
        "presentás la DJ, pero no pagás el impuesto (Ley 6380, art. 69)."
    )
    draft.boxes = [
        calc(
            "10",
            1,
            "Ingresos propios exonerados (Col. I)",
            DRAFT_DOUBT,
            note="El «no gravado o exonerado» de los ingresos del registro.",
            origin="income",
        ),
        missing(
            "11",
            1,
            "Ingresos como padre, tutor o curador, exonerados (Col. I)",
            "La app no registra ingresos de hijos o personas bajo tutela.",
        ),
        calc(
            "12",
            1,
            "Ingresos propios gravados (Col. II)",
            DRAFT_DOUBT,
            note="Ingresos del registro y ventas al contado, sin IVA.",
            origin="income",
        ),
        missing(
            "13",
            1,
            "Ingresos como padre, tutor o curador, gravados (Col. II)",
            "La app no registra ingresos de hijos o personas bajo tutela.",
        ),
        calc("14", 1, "Total de ingresos brutos gravados percibidos (12 + 13; sin 13)", note=below),
        missing("15", 2, "Egresos relacionados con la actividad gravada", split, DRAFT_DOUBT),
        missing("16", 2, "Egresos personales y de familiares a cargo en el país", split),
        missing("17", 2, "Salud y educación en el exterior", split),
        missing("18", 2, "Autovehículo cada 3 años", "Depende de datos personales.", PERSONAL_DATA),
        missing("19", 2, "Aporte patronal a la seguridad social", split),
        missing("20", 2, "Aporte a un sistema privado de seguridad social", split),
        missing(
            "21",
            2,
            "Cuotas, aportes y donaciones (hasta el 5 % de la renta bruta gravada)",
            split,
        ),
        calc(
            "22",
            2,
            "Egresos deducidos del ejercicio (15 a 21)",
            DRAFT_DOUBT,
            note="Total de los egresos del registro y las compras al contado que imputan al IRP. "
            "Si alguno es la compra de la vivienda (casilla 23), restalo.",
            origin="expense",
        ),
        missing("23", 2, "Vivienda al contado cada 5 años", housing, PERSONAL_DATA),
        calc("24", 2, "Total de egresos deducibles (22 + 23; sin 23)"),
        calc("25", 3, "Ingresos brutos gravados (de la casilla 14)"),
        calc("26", 3, "Egresos deducidos (22, hasta el monto de la 25)"),
        calc("27", 3, "Resultado después de los egresos (25 - 26)"),
        empty("28", 3, "Vivienda (de la casilla 23, hasta la 27)", housing, PERSONAL_DATA),
        calc("29", 3, "Subtotal de la renta neta imponible (27 - 28; sin 28)"),
        missing(
            "30",
            3,
            "Préstamos o remanente usados (casilla 102 del Anexo)",
            "Solo con la vivienda: la app no registra los préstamos.",
            PERSONAL_DATA,
        ),
        empty("31", 3, "Pérdida no arrastrable por la vivienda", housing, PERSONAL_DATA),
        empty("32", 3, "Pérdida arrastrable por la vivienda", housing, PERSONAL_DATA),
        empty(
            "33-39",
            4,
            "Pérdida fiscal arrastrable por la vivienda (5 años; la 38 hasta el 20 % de la 29)",
            "Depende de la vivienda y de la DJ anterior: la app no la calcula.",
            PERSONAL_DATA,
        ),
        calc("45", 5, "Renta neta imponible (29 - 38; sin 38)"),
        Box(
            "46",
            5,
            f"Impuesto al {tramos[0]}",
            taxes[0],
            "calculated",
            (ROUNDING_DOUBT, DRAFT_DOUBT),
            below,
        ),
        Box(
            "47",
            5,
            f"Impuesto al {tramos[1]}",
            taxes[1],
            "calculated",
            (ROUNDING_DOUBT, DRAFT_DOUBT),
            below,
        ),
        Box(
            "48",
            5,
            f"Impuesto al {tramos[2]}",
            taxes[2],
            "calculated",
            (ROUNDING_DOUBT, DRAFT_DOUBT),
            below,
        ),
        empty(
            "40",
            5,
            "Saldo a favor del ejercicio anterior (casilla 44 de la DJ anterior)",
            FROM_USER,
        ),
        missing(
            "41",
            5,
            "Retenciones computables",
            "La app no sabe qué retenciones generales se computan: consultalas en Marangatu.",
            WITHHOLDINGS,
        ),
        empty("42", 5, "Percepciones computables", FROM_USER),
        empty("49", 5, "Multa por presentación tardía", FROM_USER, "D-PF-15"),
        empty("43", 5, "Subtotal a favor del contribuyente (40 a 42)", "Depende de 40, 41 y 42."),
        empty(
            "50",
            5,
            "Subtotal a favor del fisco (46 a 49)",
            "Depende de la casilla 49: sin multa, es la suma de 46 a 48.",
        ),
        empty("44", 5, "Saldo a favor del contribuyente (si 43 > 50)", "Depende de 40 a 42 y 49."),
        empty(
            "51",
            5,
            "Saldo a ingresar (si 50 > 43)",
            "Depende de 40 a 42 y 49: sin ellas es la suma de 46 a 48.",
        ),
    ]
    if v["22"] > v["25"]:
        draft.warnings.append(
            "Los egresos superan a los ingresos gravados: la casilla 26 se limita a la 25 y el "
            "excedente no se arrastra (Ley 6380, art. 64)."
        )
    draft.warnings.append(
        "Las donaciones (casilla 21) se deducen hasta el "
        f"{_percent(params.donations_cap_pct_of_gross)} % "
        "de la renta bruta gravada: la app no separa las donaciones, revisá ese tope al repartir."
    )
    draft.warnings.append(
        "Borrador para copiar a mano en Marangatu: los importes van sin céntimos. Las casillas "
        "vacías no las calcula la app; las de «falta el dato» necesitan datos tuyos."
    )
    return draft, liquidation


def _tramos(params: rule_params.IrpServicesParams) -> list[str]:
    """«8 % (renta neta hasta ₲ 50.000.000)», … para el nombre de las casillas 46 a 48."""
    out: list[str] = []
    lower = 0
    for bracket in params.rate_brackets:
        rate = f"{_percent(bracket.rate)} %"
        if bracket.up_to_pyg is None:
            out.append(f"{rate} (renta neta desde ₲ {_thousands(lower + 1)})")
            continue
        if lower == 0:
            out.append(f"{rate} (renta neta hasta ₲ {_thousands(bracket.up_to_pyg)})")
        else:
            out.append(
                f"{rate} (renta neta de ₲ {_thousands(lower + 1)} a ₲ "
                f"{_thousands(bracket.up_to_pyg)})"
            )
        lower = bracket.up_to_pyg
    return out


def _percent(rate: Decimal) -> str:
    """0,08 → «8»; 0,095 → «9,5»."""
    value = rate * 100
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f").replace(".", ",")


def _thousands(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


# ------------------------------------------------------------------ condición 3 (D-119)


@dataclass(frozen=True)
class CuadreRow:
    box: str
    draft: Decimal | None
    register: Decimal

    @property
    def matches(self) -> bool:
        return self.draft is not None and self.draft == self.register

    def out(self) -> dict[str, Any]:
        return {
            "box": self.box,
            "draft": pyg(self.draft),
            "register": pyg(self.register),
            "difference": None if self.draft is None else pyg(self.draft - self.register),
            "matches": self.matches,
        }


@dataclass(frozen=True)
class Cuadre:
    """Resultado de la condición 3 de la D-119 para el bot: `stop_code` si no cuadra."""

    method: Literal["voucher_register", "ledger"]
    available: bool
    rows: tuple[CuadreRow, ...]
    vouchers: int
    message: str | None

    @property
    def matches(self) -> bool | None:
        if not self.available:
            return None
        return all(r.matches for r in self.rows)

    @property
    def stop_code(self) -> StopCode | None:
        return None if self.matches else StopCode.LEDGER_MISMATCH

    def out(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "available": self.available,
            "matches": self.matches,
            "rows": [r.out() for r in self.rows],
            "vouchers": self.vouchers,
            "message": self.message,
            "stop_code": None if self.stop_code is None else self.stop_code.value,
        }


def register_control(
    db: Session, organization_id: uuid.UUID, year: int, boxes: Mapping[str, Decimal | None]
) -> Cuadre:
    """Cuadra al guaraní las casillas del registro (10, 12, 14 y 22) contra la suma de los
    comprobantes del año, uno por uno (respuesta 5 del propietario, enmienda de la D-119).

    `boxes` son los importes a comprobar: los del borrador o, en el bot, los leídos de vuelta.
    Sin diferencias toleradas: una casilla vacía o con ₲ 1 de más no cuadra."""
    taxed = exempt = expenses = ZERO
    count = 0
    for voucher in db.scalars(select(Voucher).where(*_year_filter(organization_id, year))):
        amounts = _voucher_amounts(voucher)
        if amounts is None:
            continue
        count += 1
        taxed += amounts[0]
        exempt += amounts[1]
        expenses += amounts[2]
    register = {"10": whole(exempt), "12": whole(taxed), "14": whole(taxed), "22": whole(expenses)}
    rows = tuple(CuadreRow(b, boxes.get(b), register[b]) for b in REGISTER_BOXES)
    matches = all(r.matches for r in rows)
    return Cuadre(
        "voucher_register",
        True,
        rows,
        count,
        None
        if matches
        else "El borrador no cuadra al guaraní con el registro de comprobantes del año: el bot "
        "no presentaría (condición 3 de la D-119).",
    )


def condition_3(
    db: Session, organization_id: uuid.UUID, year: int, boxes: Mapping[str, Decimal | None]
) -> Cuadre:
    """Condición 3 de la D-119 para la DJ del IRP-RSP del año.

    Sin contabilidad (persona física sin IRE General) se cuadra contra el registro. Con
    contabilidad haría falta el control contra el mayor, que para el IRP todavía no existe:
    no está disponible y el bot se detiene (ante la duda no presenta)."""
    if keeps_accounting(db, organization_id, date(year, 12, 31)):
        return Cuadre(
            "ledger",
            False,
            (),
            0,
            "La organización lleva contabilidad: el cuadre del IRP es contra el mayor, que la "
            "app todavía no calcula.",
        )
    return register_control(db, organization_id, year, boxes)


# ------------------------------------------------------------------ estimación


def estimate(db: Session, organization_id: uuid.UUID, year: int) -> dict[str, Any]:
    if not 2000 <= year <= 2100:
        raise NotFound("PERIOD_NOT_FOUND", "El año no existe.")
    registered_on = irp_registration(db, organization_id, year)
    if registered_on is None:
        raise AppError(
            "IRP_NOT_APPLICABLE",
            f"El perfil fiscal vigente al cierre de {year} no incluye el IRP por servicios "
            "personales (715).",
            details={"year": year},
            status_code=422,
        )
    first, last = date(year, 1, 1), date(year, 12, 31)
    sums = register_sums(db, organization_id, year)

    applied: list[RuleVersion] = []
    rule = rules.rule_for(db, IRP_RULE, last)
    if rule is not None:
        applied.append(rule)
    if vouchers.annual_register_applies(db, organization_id, year):
        register_rule = rules.rule_for(db, REGISTER_RULE, first)
        if register_rule is not None:
            applied.append(register_rule)
    rule_status = rules.worst_status(applied)

    warnings: list[dict[str, str]] = []
    if rule_status == "pending":
        warnings.append(
            {
                "code": "RULE_PENDING",
                "message": "Las reglas del IRP están sin verificar contra la fuente oficial: el "
                "borrador sirve para controlar, no para presentar tal cual.",
            }
        )
    if registered_on > first:
        warnings.append(
            {
                "code": "FIRST_YEAR",
                "message": f"La 715 está dada de alta desde el {registered_on:%d/%m/%Y}: en el "
                "primer ejercicio solo se deducen los egresos desde el día siguiente a superar "
                "el monto no alcanzado (Ley 6380, art. 62). La app toma los de todo el año.",
            }
        )
    if sums.credit_excluded:
        warnings.append(
            {
                "code": "CREDIT_VOUCHERS_EXCLUDED",
                "message": f"{sums.credit_excluded} comprobante(s) con timbrado a crédito no "
                "entran: el IRP va por lo cobrado y lo pagado (art. 52). Cargá los cobros (203) "
                "y los pagos (201) en el registro.",
            }
        )
    if sums.card_with_vat:
        warnings.append(
            {
                "code": "CARD_VAT_INCLUDED",
                "message": f"{sums.card_with_vat} extracto(s) de tarjeta imputan al IVA: el "
                "egreso va con el IVA incluido porque el extracto no lo separa. Si es crédito "
                "fiscal, no es deducible (art. 68).",
            }
        )

    params = None if rule is None else rule_params.parse(rule.code, rule.parameters)
    if isinstance(params, rule_params.IrpServicesParams) and len(params.rate_brackets) == 3:
        draft, liquidation = form_515(sums, params)
        values = {b.number: b.value for b in draft.boxes}
        form: dict[str, Any] = {
            "available": True,
            "version": 1,
            "rule": rules.applied(rule) if rule is not None else None,
            "boxes": [b.out() for b in draft.boxes],
            "warnings": draft.warnings,
            "message": None,
        }
        threshold: dict[str, Any] | None = {
            "amount": pyg(Decimal(params.not_reached_amount_pyg)),
            "reached": liquidation.reached,
        }
        result: dict[str, Any] | None = {
            "net_income": pyg(liquidation.net_income),
            "tax": pyg(liquidation.tax),
            "to_pay": pyg(liquidation.to_pay),
        }
        if not liquidation.reached:
            warnings.append(
                {
                    "code": "BELOW_THRESHOLD",
                    "message": "Los ingresos gravados no superan el monto no alcanzado: la DJ "
                    "se presenta igual, aunque sea en cero (RG 69/2020, arts. 11 y 28), pero no "
                    "pagás el impuesto (Ley 6380, art. 69). Si pasa dos años seguidos, cesa la "
                    "obligación de declarar (Decreto 3184, art. 62).",
                }
            )
    else:
        values = dict(sums.boxes())
        form = {
            "available": False,
            "version": None,
            "rule": None,
            "boxes": [],
            "warnings": [],
            "message": f"No hay una versión vigente de la regla {IRP_RULE} para {year}: se "
            "muestran solo los totales del registro.",
        }
        threshold = result = None
    obligation = obligations.obligation_for(db, organization_id, IRP_RULE, first)
    return {
        "year": year,
        "period_start": first.isoformat(),
        "period_end": last.isoformat(),
        "registered_on": registered_on.isoformat(),
        "register": {
            "income_taxed": pyg(whole(sums.income_taxed)),
            "income_exempt": pyg(whole(sums.income_exempt)),
            "income_count": sums.income_count,
            "expenses": pyg(whole(sums.expenses)),
            "expense_count": sums.expense_count,
            "credit_excluded": sums.credit_excluded,
        },
        "threshold": threshold,
        "result": result,
        "warnings": warnings,
        "register_control": condition_3(db, organization_id, year, values).out(),
        "form_515": form,
        "obligation": None
        if obligation is None
        else {
            "id": str(obligation.id),
            "status": obligation.status,
            "calculated_amount": pyg(obligation.calculated_amount),
            "declared_amount": pyg(obligation.declared_amount),
        },
        "rules_applied": [rules.applied(r) for r in applied],
        "rule_status": rule_status,
        "is_estimate": True,
    }
