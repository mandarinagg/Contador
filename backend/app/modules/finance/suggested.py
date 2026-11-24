"""Categorías sugeridas para empezar (`POST /contexts/{cid}/categories/suggested`).

Se crean solo si el contexto todavía no tiene ninguna categoría. Son de un solo nivel y
la persona puede renombrarlas, archivarlas o agregar subcategorías después.
"""

# (nombre, tipo)
BUSINESS: tuple[tuple[str, str], ...] = (
    ("Ventas", "income"),
    ("Servicios prestados", "income"),
    ("Intereses y rendimientos", "income"),
    ("Otros ingresos", "income"),
    ("Compras de mercaderías", "expense"),
    ("Sueldos y cargas sociales", "expense"),
    ("Honorarios profesionales", "expense"),
    ("Alquileres", "expense"),
    ("Servicios básicos (ANDE, ESSAP, internet, telefonía)", "expense"),
    ("Impuestos y tasas", "expense"),
    ("Comisiones y gastos bancarios", "expense"),
    ("Transporte y combustible", "expense"),
    ("Publicidad y marketing", "expense"),
    ("Mantenimiento y reparaciones", "expense"),
    ("Insumos de oficina", "expense"),
    ("Software y suscripciones", "expense"),
    ("Otros gastos", "expense"),
)

PERSONAL: tuple[tuple[str, str], ...] = (
    ("Sueldo", "income"),
    ("Trabajos independientes", "income"),
    ("Retiros de la empresa", "income"),
    ("Otros ingresos", "income"),
    ("Supermercado", "expense"),
    ("Vivienda (alquiler o cuota)", "expense"),
    ("Servicios básicos (ANDE, ESSAP, internet, telefonía)", "expense"),
    ("Transporte y combustible", "expense"),
    ("Salud", "expense"),
    ("Educación", "expense"),
    ("Restaurantes y salidas", "expense"),
    ("Ropa", "expense"),
    ("Entretenimiento", "expense"),
    ("Seguros", "expense"),
    ("Impuestos personales", "expense"),
    ("Aportes a la empresa", "expense"),
    ("Otros gastos", "expense"),
)


def for_kind(context_kind: str) -> tuple[tuple[str, str], ...]:
    return BUSINESS if context_kind == "business" else PERSONAL
