"""Navegador del trabajador (Playwright para Python, spec §2).

- Windows: el **Microsoft Edge** del sistema (`channel="msedge"`), con ventana. No se empaqueta
  Chromium. Linux y CI: el Chromium de Playwright (sin ventana en las pruebas).
- Los diálogos del sitio (`confirm`, `alert`) se **descartan**: ante un «¿Confirma?» el bot
  contesta que no.
- Las descargas se rechazan en el reconocimiento.
- `structure` lee la estructura de la página **sin los valores** de los campos (ni `value` ni lo
  escrito): solo ids, nombres, tipos y etiquetas.
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from app.modules.marangatu.catalog import StaticProbe

CAPTCHA_SELECTORS = (
    'iframe[src*="recaptcha" i]',
    'iframe[src*="hcaptcha" i]',
    ".g-recaptcha",
    ".h-captcha",
    '[id*="captcha" i]',
    '[name*="captcha" i]',
    '[class*="captcha" i]',
    'img[src*="captcha" i]',
    'img[alt*="captcha" i]',
)
MAX_ITEMS = 300
MAX_TEXT = 200


def default_channel() -> str | None:
    return "msedge" if sys.platform == "win32" else None


@contextmanager
def open_page(*, headless: bool, channel: str | None, timeout_ms: int) -> Iterator[Page]:
    """Abre el navegador y una pestaña; al salir cierra todo, también ante un error."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, channel=channel)
        try:
            context = browser.new_context(accept_downloads=False, locale="es-PY")
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            page.on("dialog", lambda dialog: dialog.dismiss())
            try:
                yield page
            finally:
                context.close()
        finally:
            browser.close()


def probe(page: Page, selectors: tuple[str, ...]) -> StaticProbe:
    try:
        text = page.inner_text("body")
    except Exception:
        text = ""
    present = frozenset(s for s in selectors if page.locator(s).count() > 0)
    return StaticProbe(url=page.url, title=page.title(), text=text, present=present)


_STILL_LOADING_JS = """
(texts) => {
  const body = (document.body && document.body.innerText || '').toLowerCase();
  return !texts.some((t) => body.includes(t));
}
"""


def wait_for_content(
    page: Page, loading_texts: tuple[str, ...], *, timeout_ms: int, idle_ms: int = 10_000
) -> None:
    """Espera, con límite, a que termine de cargar el contenido que arma JavaScript (D-146).

    Primero la red quieta (`networkidle`, con un tope corto: el portal puede consultar cada
    tanto y nunca quedar quieto) y después, hasta `timeout_ms`, que ninguno de los textos de
    «cargando» siga en la página. Los vencimientos no son un error: se lee lo que haya.
    """
    timeout_ms = max(0, timeout_ms)
    with suppress(PlaywrightError):
        page.wait_for_load_state("networkidle", timeout=min(idle_ms, timeout_ms))
    texts = [t.casefold() for t in loading_texts if t.strip()]
    if not texts or timeout_ms <= 0:
        return
    with suppress(PlaywrightError):
        page.wait_for_function(_STILL_LOADING_JS, arg=texts, timeout=timeout_ms)


def looks_like_captcha(page: Page) -> bool:
    return any(page.locator(selector).count() > 0 for selector in CAPTCHA_SELECTORS)


def capture(page: Page, path: Path) -> Path:
    page.screenshot(path=str(path), full_page=True)
    return path


_STRUCTURE_JS = """
([maxItems, maxText]) => {
  const clip = (s) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, maxText);
  const labelOf = (el) => {
    if (el.labels && el.labels.length) return clip(el.labels[0].innerText);
    return clip(el.getAttribute('aria-label') || el.getAttribute('placeholder') || '');
  };
  const take = (sel) => Array.from(document.querySelectorAll(sel)).slice(0, maxItems);
  return {
    url: location.href,
    titulo: clip(document.title),
    encabezados: take('h1, h2, h3, h4, legend, caption').map((e) => clip(e.innerText))
      .filter(Boolean),
    campos: take('input, select, textarea')
      .filter((e) => !['submit', 'button', 'reset', 'image'].includes((e.type || '').toLowerCase()))
      .map((e) => ({
        tipo: e.tagName.toLowerCase() === 'input' ? (e.type || 'text').toLowerCase()
          : e.tagName.toLowerCase(),
        id: e.id || null,
        nombre: e.getAttribute('name'),
        etiqueta: labelOf(e) || null,
      })),
    botones: take('button, input[type=submit], input[type=button], input[type=reset], ' +
                  'input[type=image], [role=button]')
      .map((e) => ({
        texto: clip(e.innerText || e.getAttribute('value') || e.getAttribute('aria-label') || ''),
        id: e.id || null,
        nombre: e.getAttribute('name'),
        tipo: (e.getAttribute('type') || e.tagName).toLowerCase(),
      })),
    enlaces: take('a[href]').map((e) => ({
      texto: clip(e.innerText || e.getAttribute('title') || ''),
      href: e.href,
      id: e.id || null,
      descarga: e.hasAttribute('download'),
    })),
  };
}
"""


def structure(page: Page) -> dict[str, Any]:
    """Título, encabezados, campos (sin valores), botones y enlaces de la página."""
    result: dict[str, Any] = page.evaluate(_STRUCTURE_JS, [MAX_ITEMS, MAX_TEXT])
    return result
