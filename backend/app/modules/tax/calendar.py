"""Días hábiles, excepciones fechadas y vencimientos (D-086, BR-TAX-05).

- Días inhábiles: sábados, domingos y los feriados de `tax.holidays` (cualquiera sea su
  estado de verificación: un feriado sin verificar igual corre el vencimiento, que es lo
  prudente).
- Un vencimiento que cae en un día inhábil pasa al siguiente hábil (RG 38/2020, art. 3°),
  aunque haya varios inhábiles seguidos.
- Una excepción fechada **reemplaza** la fecha calculada. Se busca por el mes del
  vencimiento nominal (el del calendario, antes de correr inhábiles), la terminación del RUC
  y la obligación: primero las que nombran la obligación, después las del grupo
  `determinative` (declaraciones determinativas). Las excepciones inactivas o cuya regla de
  origen está deprecada no se aplican.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tax import rule_params
from app.modules.tax.models import DueDateException, Holiday, RuleVersion

SATURDAY = 5


def holidays_between(db: Session, start: date, end: date) -> set[date]:
    return set(db.scalars(select(Holiday.day).where(Holiday.day >= start, Holiday.day <= end)))


class BusinessDays:
    """Calendario de días hábiles con los feriados de un rango (una consulta)."""

    def __init__(self, db: Session, start: date, end: date):
        # Margen: un vencimiento del último día puede correrse unos días.
        self._holidays = holidays_between(db, start, end + timedelta(days=31))

    @classmethod
    def from_days(cls, days: Iterable[date]) -> "BusinessDays":
        calendar = cls.__new__(cls)
        calendar._holidays = set(days)
        return calendar

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < SATURDAY and day not in self._holidays

    def next_business_day(self, day: date) -> date:
        """El mismo día si es hábil; si no, el primer hábil siguiente."""
        while not self.is_business_day(day):
            day += timedelta(days=1)
        return day


@dataclass(frozen=True)
class ExceptionMatch:
    exception: DueDateException
    rule: RuleVersion | None


class Exceptions:
    """Excepciones activas de un rango de meses (una consulta)."""

    def __init__(self, db: Session, first_month: date, last_month: date):
        rows = db.execute(
            select(DueDateException, RuleVersion)
            .outerjoin(RuleVersion, RuleVersion.id == DueDateException.rule_version_id)
            .where(
                DueDateException.is_active.is_(True),
                DueDateException.due_month >= first_month,
                DueDateException.due_month <= last_month,
            )
            .order_by(DueDateException.id)
        ).all()
        self._rows = [
            ExceptionMatch(exception, rule)
            for exception, rule in rows
            if rule is None or rule.validation_status != "deprecated"
        ]

    def find(self, code: str, due_month: date, digit: int) -> ExceptionMatch | None:
        group = "determinative" if code in rule_params.DETERMINATIVE_RULES else None
        best: ExceptionMatch | None = None
        for match in self._rows:
            exc = match.exception
            if exc.due_month != due_month or (exc.ruc_digits and digit not in exc.ruc_digits):
                continue
            if exc.obligation_code == code:
                return match  # la que nombra la obligación gana
            if best is None and group is not None and exc.obligation_group == group:
                best = match
        return best
