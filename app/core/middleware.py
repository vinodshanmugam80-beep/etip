"""HTTP middleware and exception handlers.

Registers:

* A request-context middleware that assigns a ``request_id`` and populates the
  logging context.
* A security-headers middleware applying OWASP-recommended response headers.
* A lightweight fixed-window rate limiter backed by an in-process counter
  (production swaps this for the Redis-backed limiter — see comments).
* Handlers translating :class:`AppError` and unexpected exceptions into a
  consistent JSON error envelope.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger, request_context

logger = get_logger(__name__)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

# The dashboard is a self-contained HTML page that uses an inline <style> and an
# inline <script>, and loads Chart.js from cdnjs and fonts from Google Fonts. The
# strict API policy (default-src 'self') would block all of that, leaving the page
# unstyled and non-interactive. These HTML routes get a scoped policy that permits
# exactly those sources; every API/JSON response keeps the strict default above.
_DASHBOARD_PATHS = {"/", "/dashboard"}
_DASHBOARD_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'"
)

# FastAPI's built-in interactive API docs (Swagger UI and ReDoc) render an HTML
# page that loads swagger-ui/redoc's JS and CSS from a CDN and runs an inline
# bootstrap script. The strict default policy blocks all of that, leaving /docs
# and /redoc blank. Scope a policy to exactly the origins those pages need.
_API_DOCS_PATHS = {"/docs", "/redoc", "/docs/oauth2-redirect"}
_API_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
    "font-src 'self' fonts.gstatic.com; "
    "img-src 'self' data: fastapi.tiangolo.com cdn.jsdelivr.net; "
    "connect-src 'self'"
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id and expose it to logs and response headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_context.set({"request_id": request_id})
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_context.reset(token)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "ctx_request_id": request_id,
                "ctx_method": request.method,
                "ctx_path": request.url.path,
                "ctx_status": response.status_code,
                "ctx_duration_ms": duration_ms,
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP-recommended security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.path in _DASHBOARD_PATHS:
            # Override the strict default with the dashboard-scoped policy.
            response.headers["Content-Security-Policy"] = _DASHBOARD_CSP
        elif request.url.path in _API_DOCS_PATHS:
            # Override the strict default so Swagger UI / ReDoc can render.
            response.headers["Content-Security-Policy"] = _API_DOCS_CSP
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-client rate limiter.

    The in-process store is adequate for a single instance and for tests; a
    horizontally scaled deployment must back this with Redis (INCR + EXPIRE)
    so limits are shared across replicas.
    """

    def __init__(self, app: ASGIApp, limit_per_minute: int) -> None:
        super().__init__(app)
        self._limit = limit_per_minute
        self._buckets: dict[tuple[str, int], int] = defaultdict(int)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = (client, window)
        self._buckets[key] += 1
        if self._buckets[key] > self._limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests.",
                    }
                },
            )
        # Opportunistically drop stale windows to bound memory.
        for bucket_key in list(self._buckets):
            if bucket_key[1] < window:
                del self._buckets[bucket_key]
        return await call_next(request)


def register_error_handlers(app: FastAPI) -> None:
    """Register JSON error handlers for domain and unexpected errors."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.exception("application error", extra={"ctx_code": exc.code})
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
        )


def register_middleware(app: FastAPI) -> None:
    """Attach all custom middleware in the correct order."""
    settings = get_settings()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestContextMiddleware)
