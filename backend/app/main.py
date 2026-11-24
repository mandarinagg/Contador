"""Punto de entrada de la API local de CONTADOR AI."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, request_id_var
from app.modules.audit.router import router as audit_router
from app.modules.finance.router import router as finance_router
from app.modules.identity.router import auth_router, users_router
from app.modules.organizations.router import router as organization_router
from app.modules.system.router import router as system_router

logger = logging.getLogger("contador.http")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="CONTADOR AI — API local",
        version="0.1.0",
        # La documentación interactiva solo en desarrollo.
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env != "production" else None,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = (
            incoming if 8 <= len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-Id"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "fields": {
                    "status": response.status_code,
                    "ms": elapsed_ms,
                    "request_id": request_id,
                }
            },
        )
        return response

    api = APIRouter(prefix="/api/v1")
    for router in (
        system_router,
        auth_router,
        users_router,
        organization_router,
        audit_router,
        finance_router,
    ):
        api.include_router(router)
    app.include_router(api)
    return app


app = create_app()
