"""Dígito verificador del RUC paraguayo (módulo 11 de la SET).

Port fiel de `setCheckDigit` del proyecto de facturación
(`facturacion-sifen-zestia/packages/contracts/src/sifen.ts`, basado en el Manual Técnico
SIFEN v150): cada dígito, de derecha a izquierda, se multiplica por un peso de 2 a 11
que vuelve a 2; con el resto de la suma entre 11, el dígito es 11 - resto, o 0 si el
resto es 0 o 1. Vector oficial del manual: RUC 44444401 → DV 7.
"""

import re

_DIGITS = re.compile(r"^\d+$")


def ruc_check_digit(digits: str) -> int:
    if not _DIGITS.match(digits):
        raise ValueError("El dígito verificador se calcula sobre dígitos")
    total = 0
    weight = 2
    for char in reversed(digits):
        total += int(char) * weight
        weight = 2 if weight == 11 else weight + 1
    rest = total % 11
    return 11 - rest if rest > 1 else 0
