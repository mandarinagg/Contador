"""Estimación mensual del IVA y borrador del Formulario 120 (D-090, D-097, BR-TAX-03/11).

Es una **estimación**, no una declaración: se calcula en el momento con los comprobantes
vivos del mes que imputan al IVA (BR-TAX-03) y la persona la copia a mano en Marangatu.

Estimación genérica (D-090), por tasa:
- débito fiscal: ventas (facturas y notas de débito emitidas) menos notas de crédito
  emitidas;
- crédito fiscal: compras (facturas y notas de débito recibidas) menos notas de crédito
  recibidas;
- saldo a favor del mes anterior: el **declarado** en la obligación IVA presentada del mes
  anterior; si no la hay, el estimado, arrastrando mes a mes desde la última declarada (una
  consulta agrupada);
- resultado = débito - crédito - saldo anterior: a ingresar si es positivo, saldo a favor
  si es negativo.

La base sin IVA de cada comprobante es su importe menos su IVA guardado (impreso o calculado
por comprobante, D-088). El IVA del mes **se aplica sobre la suma de las bases**, por tasa y
redondeado a guaraníes: el instructivo del Formulario 120 v4 pide en cada casilla de impuesto
el IVA «resultante de la aplicación de dichas tasas» a los montos imponibles (D-122, resuelve
D-F4-7). El redondeo de la mitad hacia arriba no está escrito en la norma. El control contra
el mayor sigue usando el IVA de cada comprobante, que es lo que se contabiliza.

Borrador del Formulario 120 v4 (D-097): las casillas del mapa de la investigación
(`TRIBUTACION_FASE4.md` §2, regla `IVA-F120-ESTRUCTURA`), **sin IVA y sin céntimos**. Solo se
precalculan las que la investigación marca como calculables; las de exportadores, las
retenciones y percepciones (52, 169), el prorrateo (164, BR-TAX-11), el Rubro 6 y lo que
viene de la DJ anterior o de la cuenta corriente quedan vacías y con aviso. Cada casilla
lleva su número oficial y la duda que la afecta (D-F4-x). Ubicación de las notas de crédito
según la guía de la DNIT y el instructivo (D-122, resuelve D-F4-4): la recibida ajusta el
débito (Rubro 1, inc. h a k, casillas 15/23, 155/159 y 17) y la emitida da crédito (Rubro 3,
inc. e, casillas 34/37/42). Todas las compras van como «directas» (32/35/38): las
«indistintas» son las afectadas a la vez a operaciones gravadas y exoneradas, y eso solo
pasa con ventas exentas, caso en que se avisa el prorrateo (D-122, resuelve D-F4-6).

Prorrateo: si en el mes hay ventas exentas y compras con crédito, se avisa que puede
corresponder y no se calcula (BR-TAX-11). El control contra el mayor compara el movimiento
del mes de las cuentas de IVA configuradas; una diferencia es solo un aviso.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.modules.accounting import balances
from app.modules.tax import obligations, rules, tax_settings
from app.modules.tax.common import ZERO, add_months, month_end, month_start, pyg
from app.modules.tax.models import TIMBRADO_DIRECTIONS, Obligation, RuleVersion, Voucher

VAT_FILING = "IVA-GENERAL-LIQUIDACION"
FORM_RULE = "IVA-F120-ESTRUCTURA"
RELATED_RULES = (
    "IVA-GENERAL-TASAS",
    VAT_FILING,
    "IVA-INCLUIDO-CALCULO",
    "IVA-SALDOS-ARRASTRE",
    FORM_RULE,
)
PRORATION_RULE = "IVA-PRORRATEO"
PRORATION_WINDOW = 6


def rate_of(base: Decimal, percent: int) -> Decimal:
    """IVA de una base sin IVA: base por la tasa, en guaraníes enteros (D-122)."""
    return (base * percent / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)


@dataclass
class Sums:
    """Importes con IVA incluido e IVA de un grupo de comprobantes."""

    taxed_10: Decimal = ZERO
    taxed_5: Decimal = ZERO
    exempt: Decimal = ZERO
    vat_10: Decimal = ZERO
    vat_5: Decimal = ZERO
    count: int = 0

    @property
    def base_10(self) -> Decimal:
        return self.taxed_10 - self.vat_10

    @property
    def base_5(self) -> Decimal:
        return self.taxed_5 - self.vat_5

    @property
    def vat(self) -> Decimal:
        """IVA guardado en los comprobantes (lo que se contabiliza)."""
        return self.vat_10 + self.vat_5

    @property
    def form_vat_10(self) -> Decimal:
        """IVA a declarar al 10 %: la tasa sobre la suma de las bases (D-122)."""
        return rate_of(self.base_10, 10)

    @property
    def form_vat_5(self) -> Decimal:
        return rate_of(self.base_5, 5)

    @property
    def form_vat(self) -> Decimal:
        return self.form_vat_10 + self.form_vat_5


@dataclass
class MonthSums:
    """Grupos del mes: (dirección, «nota de crédito» o no) de lo que imputa al IVA."""

    sales: Sums = field(default_factory=Sums)
    sale_credit_notes: Sums = field(default_factory=Sums)
    purchases: Sums = field(default_factory=Sums)
    purchase_credit_notes: Sums = field(default_factory=Sums)
    sales_not_imputed: int = 0
    purchases_not_imputed: int = 0

    def net_debit(self) -> Decimal:
        return self.sales.form_vat - self.sale_credit_notes.form_vat

    def net_credit(self) -> Decimal:
        return self.purchases.form_vat - self.purchase_credit_notes.form_vat


def _group_key(direction: str, voucher_type: str) -> str:
    note = voucher_type == "credit_note"
    if direction == "sale":
        return "sale_credit_notes" if note else "sales"
    return "purchase_credit_notes" if note else "purchases"


def month_sums(
    db: Session, organization_id: uuid.UUID, first: date, last: date
) -> dict[date, MonthSums]:
    """Sumas por mes de `first` a `last` (meses), en una sola consulta agrupada."""
    month = func.date_trunc("month", Voucher.issued_on).cast(Voucher.issued_on.type)
    rows = db.execute(
        select(
            month,
            Voucher.direction,
            Voucher.voucher_type,
            Voucher.imputes_vat,
            func.sum(Voucher.taxed_10),
            func.sum(Voucher.taxed_5),
            func.sum(Voucher.exempt),
            func.sum(Voucher.vat_10),
            func.sum(Voucher.vat_5),
            func.count(),
            func.sum(case((Voucher.vat_10 + Voucher.vat_5 > 0, 1), else_=0)),
        )
        .where(
            Voucher.organization_id == organization_id,
            Voucher.voided_at.is_(None),
            Voucher.issued_on >= month_start(first),
            Voucher.issued_on <= month_end(last),
            # Los ingresos y egresos del IRP-RSP no son del IVA (D-143).
            Voucher.direction.in_(TIMBRADO_DIRECTIONS),
        )
        .group_by(month, Voucher.direction, Voucher.voucher_type, Voucher.imputes_vat)
    ).all()
    result: dict[date, MonthSums] = defaultdict(MonthSums)
    for key_month, direction, vtype, imputes, t10, t5, ex, v10, v5, count, with_vat in rows:
        target = result[key_month]
        if not imputes:
            if direction == "sale":
                target.sales_not_imputed += int(with_vat or 0)
            else:
                target.purchases_not_imputed += int(with_vat or 0)
            continue
        sums: Sums = getattr(target, _group_key(direction, vtype))
        sums.taxed_10 += t10
        sums.taxed_5 += t5
        sums.exempt += ex
        sums.vat_10 += v10
        sums.vat_5 += v5
        sums.count += count
    return result


def roll(balance: Decimal, sums: MonthSums) -> tuple[Decimal, Decimal]:
    """(a ingresar, saldo a favor) de un mes con el saldo anterior `balance`."""
    result = sums.net_debit() - sums.net_credit() - balance
    return (result, ZERO) if result > 0 else (ZERO, -result)


@dataclass(frozen=True)
class PreviousBalance:
    amount: Decimal
    source: str  # declared | estimated | none
    month: date
    obligation_id: uuid.UUID | None


def previous_balance(db: Session, organization_id: uuid.UUID, month: date) -> PreviousBalance:
    """Saldo a favor que viene del mes anterior a `month` (D-090)."""
    prev = add_months(month, -1)
    declared = db.execute(
        select(Obligation.period_start, Obligation.declared_credit_balance, Obligation.id)
        .where(
            Obligation.organization_id == organization_id,
            Obligation.code == VAT_FILING,
            Obligation.status.in_(("filed", "paid")),
            Obligation.declared_credit_balance.is_not(None),
            Obligation.period_start <= prev,
        )
        .order_by(Obligation.period_start.desc())
        .limit(1)
    ).first()
    if declared is not None and declared[0] == prev:
        return PreviousBalance(declared[1] or ZERO, "declared", prev, declared[2])
    balance: Decimal
    if declared is not None:
        first, balance = add_months(declared[0], 1), declared[1] or ZERO
    else:
        earliest = db.scalar(
            select(func.min(Voucher.issued_on)).where(
                Voucher.organization_id == organization_id,
                Voucher.voided_at.is_(None),
                Voucher.direction.in_(TIMBRADO_DIRECTIONS),
            )
        )
        if earliest is None or month_start(earliest) > prev:
            return PreviousBalance(ZERO, "none", prev, None)
        first, balance = month_start(earliest), ZERO
    sums = month_sums(db, organization_id, first, prev)
    current = first
    while current <= prev:
        _, balance = roll(balance, sums.get(current, MonthSums()))
        current = add_months(current, 1)
    return PreviousBalance(balance, "estimated", prev, None)


# ------------------------------------------------------------------ Formulario 120


@dataclass(frozen=True)
class Box:
    number: str
    rubro: int
    label: str
    value: Decimal | None
    status: str  # calculated | from_previous | not_calculated
    doubts: tuple[str, ...] = ()
    note: str | None = None

    def out(self) -> dict[str, Any]:
        return {
            "box": self.number,
            "rubro": self.rubro,
            "label": self.label,
            "value": pyg(self.value),
            "status": self.status,
            "doubts": list(self.doubts),
            "note": self.note,
        }


EXPORTERS = "Solo para exportadores: la app no la calcula."
FROM_USER = "Viene de la DJ anterior o de la cuenta corriente en Marangatu: la app no la calcula."
ROUNDING_DOUBT = "D-F4-7"


def form_120(
    sums: MonthSums, window: list[MonthSums], previous: PreviousBalance
) -> tuple[list[Box], list[str]]:
    """Casillas del Formulario 120 v4 y avisos. `window` son los 6 meses del Rubro 2."""
    s, scn, p, pcn = sums.sales, sums.sale_credit_notes, sums.purchases, sums.purchase_credit_notes
    warnings: list[str] = []

    def calc(number: str, rubro: int, label: str, value: Decimal, *doubts: str) -> Box:
        return Box(number, rubro, label, value, "calculated", doubts)

    def empty(number: str, rubro: int, label: str, note: str, *doubts: str) -> Box:
        return Box(number, rubro, label, None, "not_calculated", doubts, note)

    v: dict[str, Decimal] = {
        "10": s.base_10,
        "22": s.form_vat_10,
        "151": s.base_5,
        "157": s.form_vat_5,
        "12": s.exempt,
        "15": pcn.base_10,
        "23": pcn.form_vat_10,
        "155": pcn.base_5,
        "159": pcn.form_vat_5,
        "17": pcn.exempt,
        "32": p.base_5,
        "35": p.base_10,
        "38": p.form_vat,
        "34": scn.base_5,
        "37": scn.base_10,
        "42": scn.form_vat,
    }
    v["18"] = v["10"] + v["151"] + v["12"] + v["15"] + v["155"] + v["17"]
    v["21"] = v["157"] + v["159"]
    v["24"] = v["22"] + v["23"]
    v["160"] = sum((m.sales.base_10 + m.sales.base_5 for m in window), ZERO) + sum(
        (m.purchase_credit_notes.base_10 + m.purchase_credit_notes.base_5 for m in window), ZERO
    )
    v["26"] = sum((m.sales.exempt + m.purchase_credit_notes.exempt for m in window), ZERO)
    v["27"] = v["160"] + v["26"]
    v["43"] = v["38"] + v["42"]
    v["44"] = v["21"] + v["24"]
    v["45"] = v["43"]
    v["46"] = previous.amount
    if v["44"] < v["45"] + v["46"]:
        v["166"], v["48"] = v["45"] + v["46"] - v["44"], ZERO
    else:
        v["166"], v["48"] = ZERO, v["44"] - v["45"] - v["46"]
    v["47"] = v["166"]
    v["50"] = v["48"]
    v["55"] = v["50"]

    boxes = [
        calc("10", 1, "Gravadas al 10 %: monto imponible", v["10"]),
        empty(
            "150",
            1,
            "Productos agrícolas al 5 %: monto imponible",
            "Solo productos agrícolas en estado natural y sus derivados del primer proceso: "
            "la app carga el 5 % en la casilla 151.",
        ),
        calc("151", 1, "Otros bienes y servicios al 5 %: monto imponible", v["151"]),
        calc("12", 1, "Exoneradas o no alcanzadas", v["12"]),
        empty("152", 1, "Exportaciones", EXPORTERS),
        empty("153", 1, "Exportaciones", EXPORTERS),
        empty("14", 1, "Exportaciones", EXPORTERS),
        calc(
            "15",
            1,
            "Ajustes, devoluciones realizadas y descuentos obtenidos al 10 % (notas de crédito "
            "recibidas): monto",
            v["15"],
        ),
        empty(
            "154",
            1,
            "Ídem al 5 %, productos agrícolas",
            "La app carga el 5 % en la casilla 155.",
        ),
        calc("155", 1, "Ídem al 5 %, otros bienes y servicios: monto", v["155"]),
        calc("17", 1, "Ídem exonerados o no alcanzados", v["17"]),
        calc("18", 1, "Total del monto imponible (Col. I)", v["18"]),
        empty(
            "156",
            1,
            "IVA débito 5 %, productos agrícolas",
            "La app carga el 5 % en la casilla 157.",
        ),
        calc("157", 1, "IVA débito 5 %, otros bienes y servicios", v["157"], ROUNDING_DOUBT),
        empty(
            "158",
            1,
            "IVA de ajustes al 5 %, productos agrícolas",
            "La app carga el 5 % en la casilla 159.",
        ),
        calc("159", 1, "IVA de ajustes al 5 %, otros bienes y servicios", v["159"], ROUNDING_DOUBT),
        calc("21", 1, "Total IVA débito 5 % (Col. II)", v["21"]),
        calc("22", 1, "IVA débito 10 %", v["22"], ROUNDING_DOUBT),
        calc("23", 1, "IVA de ajustes al 10 %", v["23"], ROUNDING_DOUBT),
        calc("24", 1, "Total IVA débito 10 % (Col. III)", v["24"]),
        calc(
            "160",
            2,
            "Gravadas en el mercado interno, últimos 6 meses (10, 151, 15 y 155)",
            v["160"],
        ),
        empty(
            "161",
            2,
            "Productos agrícolas, últimos 6 meses",
            "La app no usa las casillas 150 y 154.",
        ),
        calc("26", 2, "Exoneradas o no alcanzadas, últimos 6 meses (12 y 17)", v["26"]),
        calc("27", 2, "Total del mercado interno, últimos 6 meses", v["27"]),
        empty("162", 2, "Exportaciones, últimos 6 meses", EXPORTERS),
        empty("163", 2, "Exportaciones, últimos 6 meses", EXPORTERS),
        empty("29", 2, "Exportaciones, últimos 6 meses", EXPORTERS),
        empty("30", 2, "Total exportaciones, últimos 6 meses", EXPORTERS),
        empty(
            "31",
            2,
            "Total de los últimos 6 meses",
            "Suma del mercado interno y las exportaciones: completala en Marangatu.",
        ),
        calc(
            "32",
            3,
            "Compras atribuidas directamente a operaciones gravadas: base 5 %",
            v["32"],
        ),
        calc(
            "35",
            3,
            "Compras atribuidas directamente a operaciones gravadas: base 10 %",
            v["35"],
        ),
        calc("38", 3, "IVA crédito de compras directas", v["38"], ROUNDING_DOUBT),
        empty(
            "33",
            3,
            "Compras atribuidas indistintamente: base 5 %",
            "Solo si hay operaciones gravadas y exoneradas a la vez: la app carga todas las "
            "compras como directas (casillas 32, 35 y 38) y avisa el prorrateo.",
        ),
        empty(
            "36",
            3,
            "Compras atribuidas indistintamente: base 10 %",
            "La app carga todas las compras como directas.",
        ),
        empty(
            "39",
            3,
            "IVA crédito de compras indistintas",
            "La app carga todas las compras como directas.",
        ),
        empty(
            "164",
            3,
            "IVA crédito proporcional (prorrateo)",
            "El prorrateo todavía no se calcula (BR-TAX-11, D-F4-14).",
        ),
        empty("165", 3, "IVA crédito proporcional con exportación", EXPORTERS),
        calc(
            "34",
            3,
            "Ajustes por ventas ya declaradas (notas de crédito emitidas): base 5 %",
            v["34"],
        ),
        calc(
            "37",
            3,
            "Ajustes por ventas ya declaradas (notas de crédito emitidas): base 10 %",
            v["37"],
        ),
        calc("42", 3, "IVA de los ajustes por ventas ya declaradas", v["42"], ROUNDING_DOUBT),
        calc("43", 3, "Total IVA crédito (38 + 164 + 165 + 42; sin 164 ni 165)", v["43"]),
        calc("44", 4, "IVA débito (21 + 24)", v["44"]),
        calc("45", 4, "IVA crédito (43)", v["45"]),
        Box(
            "46",
            4,
            "Saldo a favor del período anterior (casilla 47 de la DJ anterior)",
            v["46"],
            "from_previous",
            (),
            {
                "declared": "Es el declarado en la DJ del mes anterior.",
                "estimated": "Estimado con los comprobantes: no hay DJ del mes anterior con el "
                "saldo declarado. Copiá el de la casilla 47 de tu DJ anterior.",
                "none": "No hay DJ ni comprobantes anteriores: cero.",
            }[previous.source],
        ),
        calc("166", 4, "Saldo a favor del contribuyente (si 44 < 45 + 46)", v["166"]),
        empty("167", 4, "Saldo remitido al fisco (art. 91)", FROM_USER),
        calc(
            "47", 4, "Saldo a favor a trasladar al período siguiente (166 - 167; sin 167)", v["47"]
        ),
        calc("48", 4, "Saldo a favor del fisco (si 44 > 45 + 46)", v["48"]),
        empty("49", 4, "Crédito del exportador", EXPORTERS),
        empty("168", 4, "Deducción de la Ley 4962/2013", FROM_USER),
        calc("50", 4, "Impuesto determinado (48 - 49 - 168; sin 49 ni 168)", v["50"]),
        calc("55", 5, "Impuesto determinado (de la casilla 50)", v["55"]),
        empty(
            "51",
            5,
            "Saldo financiero a favor del período anterior (casilla 54 de la DJ anterior)",
            FROM_USER,
        ),
        empty(
            "52",
            5,
            "Retenciones computables a favor del contribuyente",
            "La cargás vos: las retenciones de IVA que te practicaron en el mes (instructivo, "
            "Rubro 5, inc. c). La app no las calcula: consultalas en Marangatu.",
        ),
        empty("169", 5, "Percepciones", FROM_USER),
        empty("56", 5, "Multa por presentación tardía", FROM_USER),
        empty(
            "53", 5, "Total de créditos (51 + 52 + 169)", "Depende de las casillas 51, 52 y 169."
        ),
        empty("57", 5, "Total de débitos (55 + 56)", "Depende de la casilla 56."),
        empty(
            "54",
            5,
            "Saldo a favor del contribuyente (si 53 > 57)",
            "Depende de las casillas 51, 52, 169 y 56.",
        ),
        empty(
            "58",
            5,
            "Saldo a pagar (si 57 > 53)",
            "Depende de las casillas 51, 52, 169 y 56: sin ellas es igual a la 55.",
        ),
        empty(
            "59-66, 170",
            6,
            "Compras vinculadas a operaciones exoneradas o no alcanzadas e IVA costo",
            "No se calcula en esta fase.",
        ),
    ]
    if scn.exempt > 0:
        warnings.append(
            "Las notas de crédito emitidas tienen una parte exenta que no tiene casilla en el "
            "Rubro 3: queda sin declarar hasta resolverlo contra la norma."
        )
    warnings.append(
        "Borrador para copiar a mano en Marangatu: los importes van sin IVA y sin céntimos. "
        "Las casillas vacías no las calcula la app."
    )
    return boxes, warnings


# ------------------------------------------------------------------ estimación


def _rate_block(sums: Sums) -> dict[str, Any]:
    """Por tasa: importe con IVA, base y el IVA a declarar (tasa sobre la base, D-122)."""
    return {
        "rate_10": {
            "taxed": pyg(sums.taxed_10),
            "base": pyg(sums.base_10),
            "vat": pyg(sums.form_vat_10),
        },
        "rate_5": {
            "taxed": pyg(sums.taxed_5),
            "base": pyg(sums.base_5),
            "vat": pyg(sums.form_vat_5),
        },
        "exempt": pyg(sums.exempt),
        "vat": pyg(sums.form_vat),
        "count": sums.count,
    }


def _ledger_control(
    db: Session, organization_id: uuid.UUID, first: date, last: date, sums: MonthSums
) -> dict[str, Any]:
    accounts = tax_settings.effective(db, organization_id).effective
    expected = {
        "vat_debit_10_account_id": sums.sales.vat_10 - sums.sale_credit_notes.vat_10,
        "vat_debit_5_account_id": sums.sales.vat_5 - sums.sale_credit_notes.vat_5,
        "vat_credit_10_account_id": sums.purchases.vat_10 - sums.purchase_credit_notes.vat_10,
        "vat_credit_5_account_id": sums.purchases.vat_5 - sums.purchase_credit_notes.vat_5,
    }
    missing = [name for name in expected if accounts[name] is None]
    if missing:
        return {
            "available": False,
            "matches": None,
            "accounts": [],
            "message": "Faltan cuentas de IVA (cargá el plan propuesto o configuralas): no se "
            "puede comparar con el mayor.",
        }
    movement = balances.account_sums(db, organization_id, date_from=first, date_to=last)
    rows = []
    for name, estimate in expected.items():
        account = accounts[name]
        assert account is not None
        sums_ = movement.get(account.id, balances.Sums())
        ledger = balances.natural(account.kind, sums_)
        rows.append(
            {
                "field": name,
                "account_id": str(account.id),
                "account_code": account.code,
                "account_name": account.name,
                "ledger": pyg(ledger),
                "estimate": pyg(estimate),
                "difference": pyg(ledger - estimate),
                "matches": ledger == estimate,
            }
        )
    matches = all(r["matches"] for r in rows)
    return {
        "available": True,
        "matches": matches,
        "accounts": rows,
        "message": None
        if matches
        else "El movimiento contabilizado del mes en las cuentas de IVA no coincide con la "
        "estimación: puede faltar contabilizar comprobantes, o el asiento de liquidación del "
        "IVA está en el mismo mes. Es solo un aviso.",
    }


def estimate(db: Session, organization_id: uuid.UUID, year: int, month: int) -> dict[str, Any]:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise NotFound("PERIOD_NOT_FOUND", "El mes no existe.")
    first = date(year, month, 1)
    last = month_end(first)
    window_start = add_months(first, -(PRORATION_WINDOW - 1))
    by_month = month_sums(db, organization_id, window_start, first)
    sums = by_month.get(first, MonthSums())
    window = [by_month.get(add_months(window_start, i), MonthSums()) for i in range(6)]
    previous = previous_balance(db, organization_id, first)
    to_pay, credit_balance = roll(previous.amount, sums)

    applied: list[RuleVersion] = []
    for code in RELATED_RULES:
        rule = rules.rule_for(db, code, first)
        if rule is not None:
            applied.append(rule)
    used_ids = set(
        db.scalars(
            select(Voucher.vat_rule_version_id)
            .where(
                Voucher.organization_id == organization_id,
                Voucher.voided_at.is_(None),
                Voucher.vat_rule_version_id.is_not(None),
                Voucher.issued_on >= first,
                Voucher.issued_on <= last,
            )
            .distinct()
        )
    ) - {r.id for r in applied}
    if used_ids:
        applied.extend(db.scalars(select(RuleVersion).where(RuleVersion.id.in_(used_ids))))

    warnings: list[dict[str, str]] = []
    proration = sums.sales.exempt > 0 and sums.purchases.vat > 0
    if proration:
        warnings.append(
            {
                "code": "PRORATION_POSSIBLE",
                "message": "En el mes hay ventas exentas y compras con crédito fiscal: puede "
                "corresponder el prorrateo del crédito (Ley 6380, art. 88; Decreto 3107, art. "
                "18). La app todavía no lo calcula (D-F4-14).",
            }
        )
        proration_rule = rules.rule_for(db, PRORATION_RULE, first)
        if proration_rule is not None:
            applied.append(proration_rule)
    if sums.sales_not_imputed:
        warnings.append(
            {
                "code": "SALES_NOT_IMPUTED",
                "message": f"{sums.sales_not_imputed} venta(s) con IVA no imputan al IVA y no "
                "entran en el débito fiscal: revisalas.",
            }
        )
    if sums.purchases_not_imputed:
        warnings.append(
            {
                "code": "PURCHASES_NOT_IMPUTED",
                "message": f"{sums.purchases_not_imputed} compra(s) con IVA no imputan al IVA: "
                "su IVA no es crédito fiscal (va al costo).",
            }
        )
    form_rule = next((r for r in applied if r.code == FORM_RULE), None)
    if form_rule is not None:
        boxes, form_warnings = form_120(sums, window, previous)
        form: dict[str, Any] = {
            "available": True,
            "version": 4,
            "rule": rules.applied(form_rule),
            "boxes": [b.out() for b in boxes],
            "warnings": form_warnings,
            "message": None,
        }
    else:
        form = {
            "available": False,
            "version": None,
            "rule": None,
            "boxes": [],
            "warnings": [],
            "message": f"No hay una versión vigente de la regla {FORM_RULE} para el mes: se "
            "muestran solo los rubros genéricos.",
        }
    obligation = obligations.obligation_for(db, organization_id, VAT_FILING, first)
    return {
        "year": year,
        "month": month,
        "period_start": first.isoformat(),
        "period_end": last.isoformat(),
        "debit": {
            "sales": _rate_block(sums.sales),
            "credit_notes": _rate_block(sums.sale_credit_notes),
            "total": pyg(sums.net_debit()),
        },
        "credit": {
            "purchases": _rate_block(sums.purchases),
            "credit_notes": _rate_block(sums.purchase_credit_notes),
            "total": pyg(sums.net_credit()),
        },
        "previous_balance": {
            "amount": pyg(previous.amount),
            "source": previous.source,
            "month": previous.month.isoformat(),
            "obligation_id": str(previous.obligation_id) if previous.obligation_id else None,
        },
        "result": {
            "to_pay": pyg(to_pay),
            "credit_balance": pyg(credit_balance),
        },
        "proration_warning": proration,
        "warnings": warnings,
        "ledger_control": _ledger_control(db, organization_id, first, last, sums),
        "form_120": form,
        "obligation": None
        if obligation is None
        else {
            "id": str(obligation.id),
            "status": obligation.status,
            "calculated_amount": pyg(obligation.calculated_amount),
            "declared_amount": pyg(obligation.declared_amount),
        },
        "rules_applied": [rules.applied(r) for r in applied],
        "rule_status": rules.worst_status(applied),
        "is_estimate": True,
    }


def apply(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, year: int, month: int
) -> tuple[Obligation, dict[str, Any]]:
    """Lleva el estimado a `calculated_amount` de la obligación IVA del mes (D-090)."""
    result = estimate(db, organization_id, year, month)
    first = date(year, month, 1)
    obligation = obligations.obligation_for(db, organization_id, VAT_FILING, first, lock=True)
    if obligation is None:
        raise AppError(
            "OBLIGATION_NOT_FOUND",
            "No hay obligación de IVA para ese mes: revisá el perfil fiscal y abrí el "
            "calendario para generarla.",
            status_code=404,
        )
    to_pay = Decimal(result["result"]["to_pay"])
    balance = Decimal(result["result"]["credit_balance"])
    obligations.set_calculated(
        db,
        organization_id,
        actor_id,
        obligation,
        amount=to_pay,
        credit_balance=balance,
        source={"source": "vat_estimate", "rule_status": result["rule_status"]},
    )
    return obligation, result
