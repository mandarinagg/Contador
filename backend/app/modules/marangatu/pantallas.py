"""Catálogo de pantallas de Marangatu, empaquetado. **Archivo generado: no editar a mano.**

Es una copia literal de `docs/research/marangatu_pantallas.yaml` (mismas claves y valores, en
el vocabulario del YAML). Va como módulo de Python, y no como archivo de datos, para que
PyInstaller lo incluya sin configuración extra (igual que las reglas candidatas, D-084). La
prueba `tests/test_marangatu_catalog.py::test_packaged_catalog_is_identical_to_research_yaml`
compara los dos: si el YAML cambia, la prueba falla hasta regenerar este archivo
(`scripts/generar_pantallas_marangatu.py`).

PROVISORIO: son las pantallas del portal simulado. Se reemplazan con el reconocimiento real.
"""

from typing import Any

META: dict[str, Any] = {
    "formato": 1,
    "provisorio": True,
    "aviso": "PROVISORIO: solo el ingreso viene del portal real; el resto es del portal simulado.",
    "actualizado": "2026-11-28",
    "ingreso": "login",
    "inicio": "inicio",
    "salida": {"campo": "#salir", "texto": "Salir"},
}

PANTALLAS: tuple[dict[str, Any], ...] = (
    {
        "id": "login",
        "version": 2,
        "provisoria": True,
        "reconoce": {
            "url": "/eset/login",
            "titulo": "Marangatu",
            "textos": ["Acceder"],
            "campos": ["#usuario", "#clave", "form[name=loginForm] button[type=submit]"],
        },
        "acciones": [
            {"llenar": {"dato": "usuario", "campo": "#usuario"}},
            {"llenar": {"dato": "clave", "campo": "#clave"}},
            {
                "clic": {
                    "boton": "Acceder",
                    "campo": "form[name=loginForm] button[type=submit]",
                    "va_a": ["inicio", "login_fallido", "login_captcha"],
                    "final": False,
                }
            },
        ],
        "capturada_en": "2026-11-28",
    },
    {
        "id": "login_fallido",
        "version": 1,
        "provisoria": True,
        "detiene": "LOGIN_FAILED",
        "reconoce": {
            "url": "/eset/(login|authenticate)",
            "textos": ["Usuario o contraseña incorrectos"],
        },
        "acciones": [],
        "capturada_en": None,
    },
    {
        "id": "login_captcha",
        "version": 1,
        "provisoria": True,
        "detiene": "CAPTCHA",
        "reconoce": {"url": "/eset/(login|authenticate)", "textos": ["No soy un robot"]},
        "acciones": [],
        "capturada_en": None,
    },
    {
        "id": "inicio",
        "version": 1,
        "provisoria": True,
        "reconoce": {
            "url": "/eset/inicio",
            "titulo": "Marangatu",
            "textos": ["Menú principal"],
            "campos": ["#salir"],
        },
        "acciones": [],
        "capturada_en": None,
    },
    {
        "id": "sesion_cerrada",
        "version": 1,
        "provisoria": True,
        "reconoce": {"url": "/eset/salir", "textos": ["Sesión finalizada"]},
        "acciones": [],
        "capturada_en": None,
    },
)
