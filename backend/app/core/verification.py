"""Verificación por la herramienta (D-118, D-120): no hay contador; verifica CONTADOR AI.

Quien verifica queda como `TOOL_VERIFIER`; la columna que antes guardaba la matrícula guarda
la fuente oficial contra la que se verificó. El usuario que aprobó queda en la auditoría.
"""

TOOL_VERIFIER = "CONTADOR AI"
# Largo de las columnas `*_reference` / `verified_license` (String(100)).
REFERENCE_MAX = 100
CHART_SOURCE = "RG 49/2014 (DNIT): códigos del modelo de estados financieros"
PROFILE_SOURCE = "Constancia de RUC (DNIT)"


def source_reference(text: str) -> str:
    """La referencia legal, recortada al largo de la columna (la completa queda en el dato)."""
    clean = " ".join(text.split())
    return clean if len(clean) <= REFERENCE_MAX else clean[: REFERENCE_MAX - 1] + "…"
