"""Domain and application exception hierarchy.

Services raise these framework-agnostic exceptions; a single FastAPI exception
handler (see :mod:`app.core.middleware`) maps them to HTTP responses. This
keeps the service layer free of any web-framework imports.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application errors.

    :param message: Human-readable error description.
    :param code: Stable machine-readable error code (e.g. ``"not_found"``).
    :param status_code: HTTP status to return at the API boundary.
    :param details: Optional structured context for the client.
    """

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    """Raised when a requested entity does not exist."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """Raised on a uniqueness or state conflict (e.g. duplicate email)."""

    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    """Raised when business validation fails beyond schema validation."""

    status_code = 422
    code = "validation_error"


class AuthenticationError(AppError):
    """Raised when credentials are missing or invalid."""

    status_code = 401
    code = "authentication_error"


class PermissionDeniedError(AppError):
    """Raised when an authenticated principal lacks a required permission."""

    status_code = 403
    code = "permission_denied"


class OptimisticLockError(ConflictError):
    """Raised when a stale ``version`` is submitted on update."""

    code = "stale_version"
