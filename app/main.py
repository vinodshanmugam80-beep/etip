"""Application factory and ASGI entrypoint.

Builds the FastAPI application, wires middleware, error handlers and the
versioned API router, and exposes a health-check endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import register_error_handlers, register_middleware


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Optionally self-heal tenant permissions on startup, then serve."""
        if settings.reconcile_on_startup:
            from app.db.session import SessionFactory
            from app.modules.admin.reconcile import run_startup_reconciliation

            run_startup_reconciliation(SessionFactory)
        yield

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Enterprise Transformation Intelligence Platform — Plan. Execute. Govern. Transform."
        ),
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_middleware(app)
    register_error_handlers(app)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["System"], summary="Liveness probe")
    def health() -> dict[str, str]:
        """Return a simple liveness response for orchestrators."""
        return {"status": "ok", "environment": settings.app_env}

    @app.get(
        "/health/ready",
        tags=["System"],
        summary="Readiness probe (checks the database)",
    )
    def readiness() -> JSONResponse:
        """Verify database connectivity; 200 when ready, 503 when the DB is unreachable."""
        from sqlalchemy import text

        from app.db.session import SessionFactory

        try:
            with SessionFactory() as session:
                session.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - any DB error means not ready
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "database": "down"},
            )
        return JSONResponse(status_code=200, content={"status": "ready", "database": "up"})

    _web_dir = Path(__file__).parent / "web"
    _dashboard_file = _web_dir / "dashboard.html"
    _fonts_dir = _web_dir / "fonts"
    if _fonts_dir.is_dir():
        # Self-hosted webfonts (offline; no external CDN dependency).
        app.mount("/fonts", StaticFiles(directory=str(_fonts_dir)), name="fonts")
    _vendor_dir = _web_dir / "vendor"
    if _vendor_dir.is_dir():
        # Vendored front-end libraries (Chart.js) — served locally, fully offline.
        app.mount("/vendor", StaticFiles(directory=str(_vendor_dir)), name="vendor")

    @app.get("/", include_in_schema=False)
    def _root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> HTMLResponse:
        """Serve the read-only executive dashboard (single-page app)."""
        return HTMLResponse(_dashboard_file.read_text(encoding="utf-8"))

    return app


app = create_app()
