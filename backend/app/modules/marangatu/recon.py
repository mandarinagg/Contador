"""Modo reconocimiento (spec §3 y §10, B1): ingresa, recorre los menús y captura, sin llenar ni
presentar nada.

1. **Ingreso** (un solo intento): abre la pantalla de ingreso, la captura **antes** de escribir
   la clave y la reconoce con el catálogo. Solo hace las acciones del catálogo para esa
   pantalla. Después del clic reconoce a dónde llegó: el inicio sigue; el ingreso fallido o el
   captcha detienen (`LOGIN_FAILED`, `CAPTCHA`) y **no se reintenta**. Una pantalla desconocida
   se toma como **inicio provisorio** (D-145) solo si no tiene campo de clave, no pide captcha
   y no es la del ingreso; si no, detiene con `UNKNOWN_SCREEN`.
2. **Recorrido:** desde el inicio sigue **solo enlaces** (`<a href>`) del mismo sitio, abriendo
   su dirección. **Nunca hace clic** en botones ni envía formularios, y salta los enlaces con
   palabras de la lista negra (presentar, enviar, confirmar, pagar…), las descargas y el de
   salir (por su dirección o su texto, no solo por el id). Antes de leer cada página espera, con
   tope, a que termine de cargar lo que arma JavaScript (D-146). Respeta el máximo de páginas y
   el tiempo. En el recorrido, una pantalla desconocida no detiene: es lo que se viene a
   conocer. De cada una guarda la captura y la estructura.
3. **Borrador del catálogo:** un YAML con una pantalla por página visitada, para revisar a mano.
   Reconoce por URL y título (y campos), nunca por textos de la página: pueden traer datos
   personales (D-146).
4. **Salida:** sale de Marangatu y cierra el navegador **siempre**, también ante un error.
"""

import logging
import re
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

import yaml
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from app.modules.marangatu import browser, credentials
from app.modules.marangatu.catalog import (
    Action,
    Catalog,
    FinalActionBlocked,
    Screen,
    ensure_action_in_screen,
    ensure_final_allowed,
    packaged,
    recognize,
)
from app.modules.marangatu.protocol import EndEvent, Job, StepEvent, StepResult
from app.modules.marangatu.stop_codes import StopCode

logger = logging.getLogger("contador.marangatu.recon")

# Espera (con tope) a que JavaScript termine de armar la página: menú, mensajes (D-146).
CONTENT_WAIT_MS = 15_000
HIDDEN = "[oculta]"
DRAFT_NAME = "catalogo_borrador.yaml"
# Palabras que nunca se siguen en un enlace (texto o dirección), sin tildes y en minúscula.
# Conservadora a propósito: «cargar» también salta «descargar», «cambiar» salta «cambiar clave».
DENYLIST = (
    "presentar",
    "enviar",
    "confirmar",
    "pagar",
    "firmar",
    "aceptar",
    "guardar",
    "eliminar",
    "borrar",
    "anular",
    "rectificar",
    "generar",
    "solicitar",
    "registrar",
    "cancelar",
    "modificar",
    "cambiar",
    "subir",
    "cargar",
    "salir",
    "cerrar",
    "logout",
    "desconectar",
)
SKIPPED_EXTENSIONS = (".pdf", ".zip", ".xls", ".xlsx", ".csv", ".txt", ".doc", ".docx", ".xml")

Emit = Callable[[StepEvent | EndEvent], None]


class Stop(Exception):
    def __init__(self, code: StopCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def denied(text: str, href: str) -> bool:
    haystack = f"{_plain(text)} {_plain(href)}"
    return any(word in haystack for word in DENYLIST)


def url_regex(path: str) -> str:
    """Expresión que reconoce exactamente ese camino (con o sin consulta), en cualquier sitio."""
    return rf"^https?://[^/]+{re.escape(path)}(\?|;|$)"


def _normalize_url(url: str) -> str:
    return urldefrag(url)[0].rstrip("/")


class Recon:
    def __init__(self, job: Job, emit: Emit, catalog: Catalog) -> None:
        self.job = job
        self.emit = emit
        self.catalog = catalog
        self.dir = Path(job.capture_dir)
        self.deadline = time.monotonic() + job.timeout_seconds
        self.counter = 0
        self.logged_in = False
        self.provisional_home = False
        self.home_url: str | None = None
        self.pages: list[dict[str, Any]] = []

    # --- utilidades -------------------------------------------------------------------

    def _capture(self, page: Page, name: str) -> str:
        self.counter += 1
        path = self.dir / f"{self.counter:03d}-{name}.png"
        browser.capture(page, path)
        return str(path)

    def _step(
        self,
        action: str,
        *,
        screen: Screen | None = None,
        values: dict[str, Any] | None = None,
        result: StepResult = "ok",
        message: str | None = None,
        capture: str | None = None,
    ) -> None:
        self.emit(
            StepEvent(
                screen_id=screen.id if screen else None,
                screen_version=screen.version if screen else None,
                action=action,
                values=values or {},
                result=result,
                message=message,
                capture=capture,
            )
        )

    def _settle(self, page: Page) -> None:
        """Espera, con tope y dentro del tiempo de la corrida, el contenido que arma JavaScript."""
        self._check_time()
        remaining_ms = int((self.deadline - time.monotonic()) * 1000)
        browser.wait_for_content(
            page,
            self.catalog.loading_texts,
            timeout_ms=min(CONTENT_WAIT_MS, remaining_ms),
        )

    def _see(
        self,
        page: Page,
        name: str,
        action: str,
        *,
        unknown_stops: bool = True,
        settle: bool = False,
    ) -> Screen | None:
        """Captura y reconoce la pantalla actual, y la anota como paso."""
        if settle:
            self._settle(page)
        shot = self._capture(page, name)
        screen = recognize(self.catalog, browser.probe(page, self.catalog.selectors()))
        self._step(
            action,
            screen=screen,
            values={"url": page.url},
            result="detenido" if screen is None and unknown_stops else "ok",
            message=None if screen else "Pantalla desconocida",
            capture=shot,
        )
        return screen

    def _check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise Stop(StopCode.BROWSER_ERROR, "Se agotó el tiempo del reconocimiento")

    # --- ingreso ----------------------------------------------------------------------

    def _type_password(self, page: Page, action: Action) -> None:
        """Lee la clave del almacén y la escribe ya. No queda en ninguna variable que sobreviva."""
        try:
            secret = credentials.read_for_login(self.job.ruc)
        except credentials.CredentialStoreError:
            raise Stop(StopCode.NO_CREDENTIALS, "Almacén de credenciales no disponible") from None
        if secret is None:
            raise Stop(StopCode.NO_CREDENTIALS, "No hay clave guardada")
        try:
            page.fill(action.selector, secret)
        except Exception:
            # Sin el texto original: un error del navegador podría citar lo que se escribía.
            raise Stop(
                StopCode.BROWSER_ERROR, "No se pudo escribir la clave en el formulario"
            ) from None
        finally:
            del secret

    def _do(self, page: Page, screen: Screen, action: Action) -> Screen | None:
        """Ejecuta una acción del catálogo. Devuelve la pantalla a la que llevó un clic."""
        ensure_action_in_screen(screen, action)
        if action.kind == "llenar":
            if action.data == "clave":
                if browser.looks_like_captcha(page):
                    raise Stop(StopCode.CAPTCHA, "La pantalla de ingreso pide captcha")
                self._type_password(page, action)
                shown = HIDDEN
            else:
                page.fill(action.selector, self.job.ruc)
                shown = self.job.ruc
            self._step(
                "llenar",
                screen=screen,
                values={"campo": action.selector, "dato": action.data, "valor": shown},
            )
            return None
        ensure_final_allowed(action, stage=self.job.stage)
        page.click(action.selector)
        page.wait_for_load_state("domcontentloaded")
        self._step("clic", screen=screen, values={"campo": action.selector, "boton": action.button})
        reached = self._see(page, "despues-del-clic", "reconocer", unknown_stops=False, settle=True)
        if reached is not None and reached.stops_with is not None:
            raise Stop(reached.stops_with, f"Pantalla {reached.id}")
        if browser.looks_like_captcha(page):
            raise Stop(StopCode.CAPTCHA, "Marangatu pide captcha")
        if reached is None:
            if self._provisional_home(page):
                return None
            raise Stop(StopCode.UNKNOWN_SCREEN, "Pantalla desconocida después del clic")
        if reached.id not in action.goes_to:
            raise Stop(
                StopCode.UNKNOWN_SCREEN, f"Pantalla {reached.id} no esperada después del clic"
            )
        return reached

    def _provisional_home(self, page: Page) -> bool:
        """¿La pantalla desconocida tras el clic de ingreso es un inicio? (D-145)

        Solo si no tiene campo de clave visible (si lo tiene, lo más probable es un ingreso
        fallido con un mensaje que todavía no se conoce), no pide captcha y no es la URL del
        ingreso. Si lo es, lo anota como paso y el recorrido sigue desde ahí.
        """
        if page.locator("input[type=password]:visible").count() > 0:
            return False
        if browser.looks_like_captcha(page):
            return False
        login = self.catalog.screen(self.catalog.login_screen)
        if login.recognition.url and re.search(login.recognition.url, page.url):
            return False
        self._step(
            "inicio_provisorio",
            values={"url": page.url},
            message="Inicio desconocido: se toma como inicio provisorio para el reconocimiento",
        )
        self.provisional_home = True
        return True

    def login(self, page: Page) -> None:
        page.goto(self.job.login_url, wait_until="domcontentloaded")
        # Captura ANTES de escribir nada (spec §2).
        screen = self._see(page, "ingreso", "abrir_ingreso")
        if browser.looks_like_captcha(page):
            raise Stop(StopCode.CAPTCHA, "La pantalla de ingreso pide captcha")
        if screen is not None and screen.stops_with is not None:
            raise Stop(screen.stops_with, f"Pantalla {screen.id}")
        if screen is None or screen.id != self.catalog.login_screen:
            raise Stop(StopCode.UNKNOWN_SCREEN, "La pantalla de ingreso no es la del catálogo")
        reached: Screen | None = None
        for action in screen.actions:
            self._check_time()
            reached = self._do(page, screen, action) or reached
        if not self.provisional_home and (
            reached is None or reached.id != self.catalog.home_screen
        ):
            raise Stop(StopCode.UNKNOWN_SCREEN, "El ingreso no llegó al inicio")
        self.logged_in = True
        self.home_url = page.url

    # --- recorrido --------------------------------------------------------------------

    def _followable(self, link: dict[str, Any], origin: str) -> bool:
        href = str(link.get("href") or "")
        parts = urlsplit(href)
        if parts.scheme not in ("http", "https") or f"{parts.scheme}://{parts.netloc}" != origin:
            return False
        if link.get("descarga") or parts.path.lower().endswith(SKIPPED_EXTENSIONS):
            return False
        # Nunca se sigue el enlace de salir: cerraría la sesión en mitad del recorrido.
        if self.catalog.is_logout_link(
            link_id=link.get("id"), text=str(link.get("texto") or ""), href=href
        ):
            return False
        return not denied(str(link.get("texto") or ""), href)

    def crawl(self, page: Page) -> None:
        start = page.url
        parts = urlsplit(start)
        origin = f"{parts.scheme}://{parts.netloc}"
        queue: deque[str] = deque([start])
        seen = {_normalize_url(start)}
        while queue and len(self.pages) < self.job.max_pages:
            self._check_time()
            url = queue.popleft()
            if url != start:
                try:
                    page.goto(url, wait_until="domcontentloaded")
                except PlaywrightError as exc:
                    self._step(
                        "navegar",
                        values={"url": url},
                        result="error",
                        message=str(exc).splitlines()[0][:300],
                    )
                    continue
            self._settle(page)
            info = browser.structure(page)
            screen = recognize(self.catalog, browser.probe(page, self.catalog.selectors()))
            shot = self._capture(page, "pagina")
            self._step(
                "reconocer_pagina",
                screen=screen,
                values={"url": page.url, "estructura": info},
                capture=shot,
            )
            if screen is not None and screen.stops_with is not None:
                raise Stop(screen.stops_with, f"Pantalla {screen.id} durante el recorrido")
            if screen is not None and screen.id == self.catalog.login_screen:
                # Se cerró la sesión: no hay nada más que recorrer.
                self.logged_in = False
                raise Stop(StopCode.UNKNOWN_SCREEN, "La sesión se cerró durante el recorrido")
            self.pages.append({"info": info, "captura": Path(shot).name, "pantalla": screen})
            for link in info.get("enlaces", []):
                if not self._followable(link, origin):
                    continue
                key = _normalize_url(str(link["href"]))
                if key not in seen:
                    seen.add(key)
                    queue.append(urldefrag(str(link["href"]))[0])

    # --- borrador y salida ------------------------------------------------------------

    def write_draft(self) -> str:
        today = datetime.now(UTC).date().isoformat()
        screens = []
        for n, page in enumerate(self.pages, start=1):
            info = page["info"]
            known: Screen | None = page["pantalla"]
            path = urlsplit(info["url"]).path
            fields = [f"#{f['id']}" for f in info["campos"] if f.get("id")][:8]
            screens.append(
                {
                    "id": known.id if known else f"pantalla_{n:03d}",
                    "version": known.version + 1 if known else 1,
                    "provisoria": True,
                    "reconoce": {
                        # Solo URL, título y campos: los textos y encabezados pueden traer
                        # nombres, RUC o números de declaración (D-146).
                        "url": url_regex(path),
                        "titulo": info["titulo"] or None,
                        "campos": fields,
                    },
                    "acciones": [],
                    "capturada_en": today,
                    "captura": page["captura"],
                    "estructura": {
                        "botones": info["botones"],
                        "enlaces": [
                            {"texto": a["texto"], "href": urlsplit(a["href"]).path}
                            for a in info["enlaces"]
                        ],
                        "campos": info["campos"],
                    },
                }
            )
        draft = {
            "meta": {
                "formato": 1,
                "provisorio": True,
                "aviso": "BORRADOR del reconocimiento: revisar a mano antes de copiarlo al "
                "catálogo (docs/research/marangatu_pantallas.yaml).",
                "corrida": str(self.job.run_id),
                "actualizado": today,
            },
            "pantallas": screens,
        }
        path = self.dir / DRAFT_NAME
        path.write_text(
            yaml.safe_dump(draft, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
        return str(path)

    def logout(self, page: Page) -> None:
        """Sale de Marangatu si hay sesión (o si se ve el enlace de salir)."""
        selector = self.catalog.logout_selector
        try:
            if not self.logged_in and page.locator(selector).count() == 0:
                return
            if page.locator(selector).count() == 0 and self.home_url:
                page.goto(self.home_url, wait_until="domcontentloaded")
            if page.locator(selector).count() == 0:
                # No se conoce el enlace de salir: sin él no se espera un tiempo de más.
                self._step(
                    "salir",
                    values={"campo": selector},
                    message="No se encontró el enlace para salir; la sesión se cierra al "
                    "cerrar el navegador",
                )
                self.logged_in = False
                return
            link = page.locator(selector).first
            href = link.get_attribute("href")
            if link.is_visible() or not href:
                link.click()
            else:
                # El enlace está en un menú desplegable cerrado: se abre su dirección.
                page.goto(urljoin(page.url, href), wait_until="domcontentloaded")
            page.wait_for_load_state("domcontentloaded")
            self._step("salir", values={"campo": selector})
            self._see(page, "salida", "reconocer", unknown_stops=False)
        except PlaywrightError as exc:
            self._step(
                "salir",
                values={"campo": selector},
                result="error",
                message=str(exc).splitlines()[0][:300],
            )
        self.logged_in = False


def run(job: Job, emit: Emit, catalog: Catalog | None = None) -> None:
    """Corre el reconocimiento y termina siempre con un `EndEvent`."""
    recon = Recon(job, emit, catalog or packaged())
    end = EndEvent(status="completada")
    try:
        with browser.open_page(
            headless=job.headless, channel=job.channel, timeout_ms=job.navigation_timeout_ms
        ) as page:
            try:
                recon.login(page)
                recon.crawl(page)
                draft = recon.write_draft()
                recon._step(
                    "borrador_catalogo", values={"pantallas": len(recon.pages)}, capture=draft
                )
            except Stop as stop:
                end = EndEvent(status="detenida", stop_code=stop.code, detail=stop.detail)
            except FinalActionBlocked as blocked:
                end = EndEvent(status="detenida", stop_code=blocked.code, detail=str(blocked))
            except PlaywrightError as exc:
                end = EndEvent(
                    status="detenida",
                    stop_code=StopCode.BROWSER_ERROR,
                    detail=str(exc).splitlines()[0][:300],
                )
            finally:
                recon.logout(page)
    except PlaywrightError as exc:
        # No se pudo abrir el navegador (p. ej. falta Edge).
        end = EndEvent(
            status="detenida",
            stop_code=StopCode.BROWSER_ERROR,
            detail=str(exc).splitlines()[0][:300],
        )
    if end.status == "detenida":
        recon._step("detener", values={"motivo": end.stop_code}, result="detenido")
    emit(end)
