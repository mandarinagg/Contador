"""Regenera la copia empaquetada del catálogo de pantallas de Marangatu.

Uso (desde la raíz del repositorio, con el entorno del backend):
    backend/.venv/bin/python scripts/generar_pantallas_marangatu.py
    backend/.venv/bin/ruff format backend/app/modules/marangatu/pantallas.py

Lee `docs/research/marangatu_pantallas.yaml` y escribe `backend/app/modules/marangatu/pantallas.py`.
La prueba `test_packaged_catalog_is_identical_to_research_yaml` controla que sean iguales.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "research" / "marangatu_pantallas.yaml"
TARGET = ROOT / "backend" / "app" / "modules" / "marangatu" / "pantallas.py"

HEADER = (
    (
        '"""Catálogo de pantallas de Marangatu, empaquetado. '
        "**Archivo generado: no editar a mano.**\n"
    )
    + '''
Es una copia literal de `docs/research/marangatu_pantallas.yaml` (mismas claves y valores, en
el vocabulario del YAML). Va como módulo de Python, y no como archivo de datos, para que
PyInstaller lo incluya sin configuración extra (igual que las reglas candidatas, D-084). La
prueba `tests/test_marangatu_catalog.py::test_packaged_catalog_is_identical_to_research_yaml`
compara los dos: si el YAML cambia, la prueba falla hasta regenerar este archivo
(`scripts/generar_pantallas_marangatu.py`).

PROVISORIO: el ingreso y cinco pantallas son del portal real (D-145, D-146); el resto, del
portal simulado. `meta.cargando` lista los textos de «cargando» que el bot espera que se vayan.
"""

from typing import Any

'''
)


def main() -> None:
    data = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    screens = "".join(f"    {screen!r},\n" for screen in data["pantallas"])
    TARGET.write_text(
        HEADER
        + f"META: dict[str, Any] = {data['meta']!r}\n\n"
        + f"PANTALLAS: tuple[dict[str, Any], ...] = (\n{screens})\n",
        encoding="utf-8",
    )
    print(f"Escrito {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
