"""OIDC helpers for SSO.

The network- and crypto-heavy step (code exchange + ID-token verification via the
IdP's JWKS) is isolated in :func:`fetch_oidc_claims` so it can be mocked in tests.
The OAuth ``state`` is a short-lived signed JWT carrying the tenant id and nonce,
so the callback needs no server-side session store.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import timedelta
from typing import Any

import jwt

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.db.base import utcnow
from app.modules.sso.models import SsoConfiguration

_STATE_TTL_MIN = 10


def fetch_discovery(issuer: str) -> dict[str, str]:
    """Fetch an IdP's OpenID Connect discovery document.

    Reads ``<issuer>/.well-known/openid-configuration`` and returns the
    authorization, token and JWKS endpoints. Isolated (network) so it can be
    mocked in tests.
    """
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            doc = json.loads(resp.read().decode())
    except (
        urllib.error.URLError,
        ValueError,
    ) as exc:  # pragma: no cover - network guard
        raise AuthenticationError(f"Could not read OIDC discovery from {url}.") from exc
    required = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    missing = [k for k in required if not doc.get(k)]
    if missing:
        raise AuthenticationError(f"Discovery document is missing: {', '.join(missing)}.")
    return {
        "issuer": str(doc.get("issuer") or issuer),
        "authorize_url": str(doc["authorization_endpoint"]),
        "token_url": str(doc["token_endpoint"]),
        "jwks_url": str(doc["jwks_uri"]),
    }


def sign_state(settings: Settings, organization_id: uuid.UUID, nonce: str) -> str:
    """Return a short-lived signed state token binding the tenant and nonce."""
    payload = {
        "typ": "sso_state",
        "org_id": str(organization_id),
        "nonce": nonce,
        "exp": utcnow() + timedelta(minutes=_STATE_TTL_MIN),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_state(settings: Settings, state: str) -> tuple[uuid.UUID, str]:
    """Return ``(organization_id, nonce)`` from a valid state token, or raise."""
    try:
        claims = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired SSO state.") from exc
    if claims.get("typ") != "sso_state":
        raise AuthenticationError("Invalid SSO state.")
    return uuid.UUID(claims["org_id"]), str(claims["nonce"])


def build_authorize_url(config: SsoConfiguration, state: str, nonce: str, redirect_uri: str) -> str:
    """Build the IdP authorization-endpoint URL for the redirect."""
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
    )
    sep = "&" if "?" in config.authorize_url else "?"
    return f"{config.authorize_url}{sep}{query}"


def fetch_oidc_claims(
    config: SsoConfiguration, code: str, redirect_uri: str, nonce: str
) -> dict[str, Any]:
    """Exchange the auth code, verify the ID token via JWKS, and return its claims.

    Isolated (network + crypto) so tests can mock it. Verifies signature (RS256),
    audience (client_id), issuer and nonce.
    """
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
    ).encode()
    req = urllib.request.Request(
        config.token_url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        token_response = json.loads(resp.read().decode())
    id_token = token_response.get("id_token")
    if not id_token:
        raise AuthenticationError("The identity provider did not return an ID token.")

    signing_key = jwt.PyJWKClient(config.jwks_url).get_signing_key_from_jwt(id_token)
    options = {"verify_aud": True}
    decode_kwargs: dict[str, Any] = {"audience": config.client_id, "options": options}
    if config.issuer:
        decode_kwargs["issuer"] = config.issuer
    try:
        claims = jwt.decode(id_token, signing_key.key, algorithms=["RS256"], **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Could not verify the identity provider's token.") from exc
    if claims.get("nonce") != nonce:
        raise AuthenticationError("SSO nonce mismatch.")
    return claims
