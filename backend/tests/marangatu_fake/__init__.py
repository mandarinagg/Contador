"""Portal simulado de Marangatu para las pruebas (spec §2 y §9). Nunca se toca el portal real.

HTML local (`pages/`) servido por un servidor HTTP en un hilo, en 127.0.0.1 y un puerto libre.
Imita las pantallas del catálogo PROVISORIO (`docs/research/marangatu_pantallas.yaml`) y anota
cada pedido, así las pruebas comprueban lo que el bot hizo y lo que **no** hizo (presentar,
reintentar el ingreso, cambiar la clave…).

Modos:
- `normal`: ingreso, inicio con menú, una consulta, una pantalla fuera del catálogo y salir;
- `captcha`: la pantalla de ingreso ya pide captcha;
- `login_cambiado`: la pantalla de ingreso cambió (otro título y otros campos);
- `inicio_cambiado`: después de ingresar aparece un inicio que el catálogo no conoce.
"""

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

PAGES = Path(__file__).parent / "pages"
SESSION_COOKIE = "MARANGATU_SIMULADO"


@dataclass
class PortalState:
    password: str
    user: str
    mode: str = "normal"
    hits: list[tuple[str, str]] = field(default_factory=list)
    login_attempts: int = 0
    logged_out: bool = False
    received_forms: list[dict[str, list[str]]] = field(default_factory=list)

    def count(self, path: str) -> int:
        return sum(1 for _, p in self.hits if p == path)


def _handler(state: PortalState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # sin registro: el portal simulado no escribe nada

        def _send(
            self,
            status: int,
            body: bytes,
            ctype: str = "text/html; charset=utf-8",
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _page(self, name: str, headers: dict[str, str] | None = None) -> None:
            self._send(200, (PAGES / name).read_bytes(), headers=headers)

        def _redirect(self, to: str, headers: dict[str, str] | None = None) -> None:
            self._send(303, b"", headers={"Location": to, **(headers or {})})

        def _logged_in(self) -> bool:
            return f"{SESSION_COOKIE}=ok" in (self.headers.get("Cookie") or "")

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            state.hits.append(("GET", path))
            if path == "/eset/login":
                page = {
                    "captcha": "login_captcha.html",
                    "login_cambiado": "login_cambiado.html",
                }.get(state.mode, "login.html")
                return self._page(page)
            if path == "/eset/salir":
                state.logged_out = True
                return self._page(
                    "salir.html", headers={"Set-Cookie": f"{SESSION_COOKIE}=; Max-Age=0; Path=/"}
                )
            if not self._logged_in():
                return self._redirect("/eset/login")
            pages = {
                "/eset/inicio": (
                    "inicio_cambiado.html" if state.mode == "inicio_cambiado" else "inicio.html"
                ),
                "/eset/consultas/obligaciones": "obligaciones.html",
                "/eset/consultas/novedades": "novedades.html",
            }
            if path in pages:
                return self._page(pages[path])
            if path.endswith(".pdf"):
                return self._send(200, b"%PDF-1.4 simulado", ctype="application/pdf")
            return self._send(200, b"<html><body><h1>Hecho</h1></body></html>")

        def do_POST(self) -> None:
            path = self.path.split("?")[0]
            state.hits.append(("POST", path))
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            if path != "/eset/login":
                state.received_forms.append(form)
                return self._send(200, b"<html><body><h1>Presentado</h1></body></html>")
            state.login_attempts += 1
            ok = form.get("usuario") == [state.user] and form.get("clave") == [state.password]
            if ok:
                return self._redirect(
                    "/eset/inicio", headers={"Set-Cookie": f"{SESSION_COOKIE}=ok; Path=/"}
                )
            return self._page("login_fallido.html")

    return Handler


class FakePortal:
    def __init__(self, *, password: str, user: str, mode: str = "normal") -> None:
        self.state = PortalState(password=password, user=user, mode=mode)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self.state))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    @property
    def login_url(self) -> str:
        return f"{self.base_url}/eset/login"

    def __enter__(self) -> "FakePortal":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()
