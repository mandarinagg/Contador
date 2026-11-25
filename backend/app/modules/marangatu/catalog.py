"""Motor del catálogo de pantallas (spec §3).

- **Reconocer:** una pantalla del catálogo coincide solo si está TODO lo que pide (`url`,
  `titulo`, `textos`, `campos`). Si coincide una pantalla que `detiene`, gana (detenerse es lo
  seguro). Si no coincide ninguna, o coinciden varias normales, es pantalla desconocida.
- **Acciones:** el bot solo hace las acciones de la pantalla reconocida. El clic `final` (el
  que presenta) pasa por `ensure_final_allowed`, que en el B1 lo niega siempre.

Funciones puras sobre una `Probe` (lo que se ve de la página): se prueban sin navegador.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.modules.marangatu import pantallas
from app.modules.marangatu.stop_codes import StopCode

# B1: ninguna etapa puede ejecutar el clic final todavía. Se habilita recién con la tarea que
# presenta (B3/B4) y las 12 condiciones de la D-119; hasta entonces, ni con la etapa
# `habilitada` (D-129).
FINAL_ACTIONS_ENABLED = False

DATA_KINDS = ("usuario", "clave")


class FinalActionBlocked(Exception):
    """Se intentó el clic final sin estar habilitado: no se hace y la corrida se detiene."""

    code = StopCode.NOT_ENABLED


@dataclass(frozen=True)
class Recognition:
    url: str | None
    title: str | None
    texts: tuple[str, ...]
    fields: tuple[str, ...]


@dataclass(frozen=True)
class Action:
    kind: Literal["llenar", "clic"]
    selector: str
    data: str | None = None  # llenar: qué dato escribe
    button: str | None = None  # clic: texto del botón
    goes_to: tuple[str, ...] = ()
    final: bool = False


@dataclass(frozen=True)
class Screen:
    id: str
    version: int
    recognition: Recognition
    actions: tuple[Action, ...]
    stops_with: StopCode | None = None
    provisional: bool = True


@dataclass(frozen=True)
class Catalog:
    screens: tuple[Screen, ...]
    login_screen: str
    home_screen: str
    logout_selector: str
    meta: dict[str, Any] = field(default_factory=dict)

    def screen(self, screen_id: str) -> Screen:
        for screen in self.screens:
            if screen.id == screen_id:
                return screen
        raise KeyError(screen_id)

    def selectors(self) -> tuple[str, ...]:
        """Todos los selectores que hace falta mirar para reconocer cualquier pantalla."""
        seen: dict[str, None] = {}
        for screen in self.screens:
            for selector in screen.recognition.fields:
                seen[selector] = None
        return tuple(seen)


class Probe(Protocol):
    """Lo que el motor necesita ver de una página."""

    @property
    def url(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def text(self) -> str: ...
    def has(self, selector: str) -> bool: ...


@dataclass(frozen=True)
class StaticProbe:
    """Una página ya leída (el navegador la arma con `browser.probe`; las pruebas, a mano)."""

    url: str
    title: str
    text: str
    present: frozenset[str]

    def has(self, selector: str) -> bool:
        return selector in self.present


def _action(raw: dict[str, Any]) -> Action:
    if len(raw) != 1:
        raise ValueError(f"Acción con más de un tipo: {sorted(raw)}")
    kind, body = next(iter(raw.items()))
    if kind == "llenar":
        if body["dato"] not in DATA_KINDS:
            raise ValueError(f"Dato desconocido: {body['dato']}")
        return Action(kind="llenar", selector=body["campo"], data=body["dato"])
    if kind == "clic":
        return Action(
            kind="clic",
            selector=body["campo"],
            button=body.get("boton"),
            goes_to=tuple(body.get("va_a") or ()),
            final=bool(body.get("final", False)),
        )
    raise ValueError(f"Acción desconocida: {kind}")


def _screen(raw: dict[str, Any]) -> Screen:
    rec = raw.get("reconoce") or {}
    recognition = Recognition(
        url=rec.get("url"),
        title=rec.get("titulo"),
        texts=tuple(rec.get("textos") or ()),
        fields=tuple(rec.get("campos") or ()),
    )
    if not (recognition.url or recognition.title or recognition.texts or recognition.fields):
        raise ValueError(f"La pantalla {raw['id']} no tiene cómo reconocerse")
    stops = raw.get("detiene")
    return Screen(
        id=raw["id"],
        version=int(raw["version"]),
        recognition=recognition,
        actions=tuple(_action(a) for a in raw.get("acciones") or ()),
        stops_with=StopCode(stops) if stops else None,
        provisional=bool(raw.get("provisoria", False)),
    )


def build(meta: dict[str, Any], screens: Sequence[dict[str, Any]]) -> Catalog:
    catalog = Catalog(
        screens=tuple(_screen(s) for s in screens),
        login_screen=meta["ingreso"],
        home_screen=meta["inicio"],
        logout_selector=meta["salida"]["campo"],
        meta=dict(meta),
    )
    ids = [s.id for s in catalog.screens]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay pantallas repetidas en el catálogo")
    for screen in catalog.screens:
        for action in screen.actions:
            unknown = set(action.goes_to) - set(ids)
            if unknown:
                raise ValueError(f"{screen.id}: va_a a pantallas que no existen: {unknown}")
    catalog.screen(catalog.login_screen)
    catalog.screen(catalog.home_screen)
    return catalog


def packaged() -> Catalog:
    return build(pantallas.META, pantallas.PANTALLAS)


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def matches(screen: Screen, probe: Probe) -> bool:
    rec = screen.recognition
    if rec.url is not None and re.search(rec.url, probe.url) is None:
        return False
    if rec.title is not None and _normalize(rec.title) not in _normalize(probe.title):
        return False
    page_text = _normalize(probe.text)
    if any(_normalize(t) not in page_text for t in rec.texts):
        return False
    return all(probe.has(selector) for selector in rec.fields)


def recognize(catalog: Catalog, probe: Probe) -> Screen | None:
    """La pantalla reconocida, o `None` si es desconocida (o ambigua)."""
    found = [s for s in catalog.screens if matches(s, probe)]
    stopping = [s for s in found if s.stops_with is not None]
    if stopping:
        return stopping[0]
    return found[0] if len(found) == 1 else None


def ensure_action_in_screen(screen: Screen, action: Action) -> None:
    """Solo se ejecutan acciones del catálogo para la pantalla reconocida (condición 7)."""
    if action not in screen.actions:
        raise ValueError(f"La acción no es de la pantalla {screen.id}")


def ensure_final_allowed(action: Action, *, stage: str) -> None:
    """El clic final no se ejecuta en el B1, en ninguna etapa (D-129).

    Cuando exista la tarea que presenta, hará falta además la etapa `habilitada` y las 12
    condiciones evaluadas en ese instante (spec §4, paso 7).
    """
    if not action.final:
        return
    if not FINAL_ACTIONS_ENABLED or stage != "habilitada":
        raise FinalActionBlocked(f"Clic final bloqueado (etapa {stage})")
    raise FinalActionBlocked("Clic final bloqueado: faltan las condiciones de la D-119")
