"""Security primitives.

Centralises the cryptographic operations used by the authentication module so
they can be audited and swapped in one place:

* Password hashing with Argon2id (memory-hard, OWASP-recommended).
* JWT access/refresh token issuance and verification.
* TOTP secret generation and verification for multi-factor authentication.

No web-framework or ORM types leak into this module.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    """Return an Argon2id hash of ``plain_password``."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` when ``plain_password`` matches ``hashed_password``."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Return ``True`` when the stored hash uses outdated parameters."""
    return _hasher.check_needs_rehash(hashed_password)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TokenClaims:
    """Decoded and validated JWT claims relevant to the application."""

    subject: uuid.UUID
    organization_id: uuid.UUID
    token_type: TokenType
    jti: uuid.UUID
    expires_at: datetime


def _create_token(
    settings: Settings,
    *,
    subject: uuid.UUID,
    organization_id: uuid.UUID,
    token_type: TokenType,
    expires_delta: timedelta,
    jti: uuid.UUID | None = None,
) -> tuple[str, uuid.UUID]:
    """Encode a signed JWT and return it together with its ``jti``."""
    now = datetime.now(UTC)
    token_id = jti or uuid.uuid4()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "org": str(organization_id),
        "type": token_type,
        "jti": str(token_id),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_id


def create_access_token(
    settings: Settings, *, subject: uuid.UUID, organization_id: uuid.UUID
) -> str:
    """Issue a short-lived access token."""
    token, _ = _create_token(
        settings,
        subject=subject,
        organization_id=organization_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return token


def create_refresh_token(
    settings: Settings, *, subject: uuid.UUID, organization_id: uuid.UUID
) -> tuple[str, uuid.UUID, datetime]:
    """Issue a long-lived refresh token.

    :returns: A tuple of ``(token, jti, expires_at)``. The ``jti`` is stored
        server-side so the token can be rotated and revoked.
    """
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    token, jti = _create_token(
        settings,
        subject=subject,
        organization_id=organization_id,
        token_type="refresh",
        expires_delta=expires_delta,
    )
    expires_at = datetime.now(UTC) + expires_delta
    return token, jti, expires_at


def decode_token(settings: Settings, token: str, *, expected_type: TokenType) -> TokenClaims:
    """Decode, verify and type-check a JWT.

    :raises jwt.PyJWTError: When the token is invalid, expired or the wrong
        type. Callers translate this into an authentication error.
    """
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type.")
    return TokenClaims(
        subject=uuid.UUID(payload["sub"]),
        organization_id=uuid.UUID(payload["org"]),
        token_type=expected_type,
        jti=uuid.UUID(payload["jti"]),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )


# ---------------------------------------------------------------------------
# MFA (TOTP)
# ---------------------------------------------------------------------------
def generate_mfa_secret() -> str:
    """Return a new base32 TOTP secret."""
    return pyotp.random_base32()


def mfa_provisioning_uri(secret: str, account_name: str, issuer: str) -> str:
    """Return an ``otpauth://`` URI for authenticator-app enrolment."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def verify_mfa_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP ``code`` against ``secret`` (±1 window)."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_code() -> str:
    """Return a single-use recovery code for MFA fallback."""
    return secrets.token_hex(5)
