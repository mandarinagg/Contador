"""Motor del catálogo de pantallas y motivos de detención (BOT_MARANGATU.md §3 y §8).

Sin navegador ni base: el reconocimiento se prueba con páginas armadas a mano.
"""

import importlib.util
import os
import re

import pytest
import yaml

from app.modules.marangatu import catalog, pantallas
from app.modules.marangatu.catalog import (
    FinalActionBlocked,
    StaticProbe,
    build,
    ensure_final_allowed,
    recognize,
)
from app.modules.marangatu.models import STAGES
from app.modules.marangatu.stop_codes import STOP_TEXTS, StopCode
from tests.conftest import BACKEND_DIR

YAML_PATH = os.path.join(BACKEND_DIR, "..", "docs", "research", "marangatu_pantallas.yaml")
SPEC_PATH = os.path.join(BACKEND_DIR, "..", "docs", "specs", "BOT_MARANGATU.md")
MIGRATION = os.path.join(BACKEND_DIR, "migrations", "versions", "0007_marangatu.py")

LOGIN = StaticProbe(
    url="https://marangatu.example/eset/login",
    title="Bienvenido | MARANGATU",
    text="Acceder  ¿ Olvidó su contraseña ?  ¿ Quiere saber más sobre Marangatu ?",
    present=frozenset({"#usuario", "#clave", "form[name=loginForm] button[type=submit]"}),
)


def test_packaged_catalog_is_identical_to_research_yaml() -> None:
    with open(YAML_PATH, encoding="utf-8") as handle:
        research = yaml.safe_load(handle)
    assert research["meta"] == pantallas.META
    assert research["pantallas"] == list(pantallas.PANTALLAS)
    # Provisorio hasta el reconocimiento real (spec §10, paso 2).
    assert pantallas.META["provisorio"] is True
    assert all(s["provisoria"] for s in pantallas.PANTALLAS)


def test_packaged_catalog_is_valid() -> None:
    packaged = catalog.packaged()
    assert packaged.login_screen == "login"
    assert packaged.home_screen == "inicio"
    # El B1 no trae ningún clic final.
    assert not any(a.final for s in packaged.screens for a in s.actions)


def test_recognition_needs_everything() -> None:
    packaged = catalog.packaged()
    screen = recognize(packaged, LOGIN)
    assert screen is not None and screen.id == "login"
    # Falta un campo, el título o un texto: desconocida.
    for probe in (
        StaticProbe(LOGIN.url, LOGIN.title, LOGIN.text, frozenset({"#usuario", "#clave"})),
        StaticProbe(LOGIN.url, "Otro portal", LOGIN.text, LOGIN.present),
        StaticProbe(LOGIN.url, LOGIN.title, "Usuario Contraseña", LOGIN.present),
        StaticProbe("https://marangatu.example/eset/otra", LOGIN.title, LOGIN.text, LOGIN.present),
    ):
        assert recognize(packaged, probe) is None


def test_real_login_page_is_recognized_as_login() -> None:
    """Forma de la página real (leída el 2026-11-28): sin etiquetas, botón «Acceder» sin id."""
    real = StaticProbe(
        url="https://marangatu.set.gov.py/eset/login",
        title="Bienvenido | MARANGATU",
        text="Acceder  ¿ Olvidó su contraseña ?  ¿ Quiere saber más sobre Marangatu ?",
        present=frozenset(
            {"#usuario", "#clave", "form[name=loginForm] button[type=submit]", "#usuarioRecuperar"}
        ),
    )
    screen = recognize(catalog.packaged(), real)
    assert screen is not None and screen.id == "login" and screen.version == 2
    assert [a.selector for a in screen.actions] == [
        "#usuario",
        "#clave",
        "form[name=loginForm] button[type=submit]",
    ]
    assert screen.actions[2].button == "Acceder"


def test_stopping_screen_wins() -> None:
    """El ingreso fallido también tiene el formulario de ingreso: gana la que detiene."""
    packaged = catalog.packaged()
    failed = StaticProbe(
        LOGIN.url, LOGIN.title, LOGIN.text + " Usuario o contraseña incorrectos", LOGIN.present
    )
    screen = recognize(packaged, failed)
    assert screen is not None and screen.stops_with is StopCode.LOGIN_FAILED
    captcha = StaticProbe(LOGIN.url, LOGIN.title, LOGIN.text + " No soy un robot", LOGIN.present)
    screen = recognize(packaged, captcha)
    assert screen is not None and screen.stops_with is StopCode.CAPTCHA


def test_ambiguous_match_is_unknown() -> None:
    raw = [dict(s) for s in pantallas.PANTALLAS]
    twin = dict(raw[0], id="login_gemela")
    twin["acciones"] = []
    twin_catalog = build(pantallas.META, [*raw, twin])
    assert recognize(twin_catalog, LOGIN) is None


@pytest.mark.parametrize("stage", STAGES)
def test_final_action_is_blocked_in_every_stage(stage: str) -> None:
    """B1: el clic que presenta no se ejecuta en ninguna etapa, ni siquiera `habilitada`."""
    assert catalog.FINAL_ACTIONS_ENABLED is False
    final = catalog.Action(kind="clic", selector="#presentar", button="Presentar", final=True)
    with pytest.raises(FinalActionBlocked) as caught:
        ensure_final_allowed(final, stage=stage)
    assert caught.value.code is StopCode.NOT_ENABLED
    ensure_final_allowed(catalog.Action(kind="clic", selector="#x"), stage=stage)


def test_actions_outside_the_screen_are_refused() -> None:
    login = catalog.packaged().screen("login")
    with pytest.raises(ValueError, match="no es de la pantalla"):
        catalog.ensure_action_in_screen(login, catalog.Action(kind="clic", selector="#otro"))


def test_invalid_catalogs_are_rejected() -> None:
    raw = [dict(s) for s in pantallas.PANTALLAS]
    broken = dict(raw[0], acciones=[{"clic": {"campo": "#x", "va_a": ["no_existe"]}}])
    with pytest.raises(ValueError, match="no existen"):
        build(pantallas.META, [broken, *raw[1:]])
    with pytest.raises(ValueError, match="Dato desconocido"):
        build(pantallas.META, [dict(raw[0], acciones=[{"llenar": {"dato": "x", "campo": "#x"}}])])
    with pytest.raises(ValueError, match="repetidas"):
        build(pantallas.META, [*raw, raw[0]])


def test_stop_codes_match_spec_and_migration() -> None:
    assert set(STOP_TEXTS) == set(StopCode)
    for text in STOP_TEXTS.values():
        assert len(text) > 40  # qué pasó y qué hacer
    with open(SPEC_PATH, encoding="utf-8") as handle:
        spec = handle.read()
    section = spec[spec.index("## 8.") : spec.index("## 9.")]
    assert set(re.findall(r"`([A-Z_]+)`", section)) == {c.value for c in StopCode}
    loader = importlib.util.spec_from_file_location("migration_0007", MIGRATION)
    assert loader is not None and loader.loader is not None
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    assert tuple(c.value for c in StopCode) == module.STOP_CODES


REAL_PAGES = {
    "/eset/": ("Bienvenido | MARANGATU", "inicio"),
    "/eset/?lang=es": ("Bienvenido | MARANGATU", "inicio"),
    "/eset/datosBasicosContribuyente.do": (
        "Información del Contribuyente | MARANGATU",
        "informacion_contribuyente",
    ),
    "/eset/recibirDDJJContribuyente.do": (
        "Presentar Declaración | MARANGATU",
        "presentar_declaracion",
    ),
    "/eset/mantenerAbmXsl.do": (
        "Consultar Cuenta Corriente Contribuyente | MARANGATU",
        "cuenta_corriente",
    ),
    "/eset/buzon/marandu": ("Marandu | MARANGATU", "marandu"),
}


@pytest.mark.parametrize("path", sorted(REAL_PAGES))
def test_real_pages_are_recognized_by_url_and_title_only(path: str) -> None:
    """Las pantallas reales (D-146) no dependen de los textos de la página: pueden traer datos
    personales. Cada una se reconoce sola, y el ingreso no se confunde con el inicio."""
    title, expected = REAL_PAGES[path]
    packaged = catalog.packaged()
    for text in ("", "Recuperando opciones de menú ...", "cualquier texto"):
        probe = StaticProbe(f"https://marangatu.example{path}", title, text, frozenset())
        screen = recognize(packaged, probe)
        assert screen is not None and screen.id == expected, (path, text)
    # Otro título, o un camino parecido, no coincide.
    other = StaticProbe(f"https://x.test{path}", "Otro", "", frozenset())
    assert recognize(packaged, other) is None
    similar = ("?" not in path) * [f"https://x.test{path}x"] + [f"https://x.test/otro{path}"]
    for url in similar:
        assert recognize(packaged, StaticProbe(url, title, "", frozenset())) is None


def test_real_screens_have_no_texts_and_the_login_is_not_the_home() -> None:
    packaged = catalog.packaged()
    real = {s for _, s in REAL_PAGES.values()}
    for screen_id in real:
        screen = packaged.screen(screen_id)
        assert screen.recognition.texts == () and screen.recognition.url
        assert screen.actions == () and screen.provisional
    # La URL de cualquier otra pantalla de /eset/ no es el inicio.
    home = packaged.screen("inicio")
    other = StaticProbe("https://x.test/eset/login", "Bienvenido | MARANGATU", "", frozenset())
    assert not catalog.matches(home, other)
    assert recognize(packaged, other) is None  # el ingreso real exige además sus campos
    assert recognize(packaged, LOGIN) is not None and recognize(packaged, LOGIN).id == "login"  # type: ignore[union-attr]


def test_logout_link_is_the_real_one() -> None:
    packaged = catalog.packaged()
    assert packaged.logout_selector == "a[href$='/eset/logout']"
    assert packaged.logout_text == "Salir"
    # Por dirección, aunque el texto cambie, y por texto, aunque cambie la dirección.
    assert packaged.is_logout_link(link_id=None, text="Cerrar", href="https://x.test/eset/logout")
    assert packaged.is_logout_link(link_id=None, text=" salir ", href="https://x.test/otra")
    assert not packaged.is_logout_link(link_id=None, text="Marandu", href="https://x.test/eset/")
    # Con selector por id, también.
    by_id = build({**pantallas.META, "salida": {"campo": "#salir"}}, pantallas.PANTALLAS)
    assert by_id.is_logout_link(link_id="salir", text="x", href="/a")


def test_loading_texts_come_from_the_catalog_meta() -> None:
    packaged = catalog.packaged()
    assert packaged.loading_texts == (
        "Recuperando opciones de menú",
        "Recuperando Mensajes",
    )
    assert pantallas.META["cargando"] == list(packaged.loading_texts)
    without = {k: v for k, v in pantallas.META.items() if k != "cargando"}
    assert build(without, pantallas.PANTALLAS).loading_texts == ()
