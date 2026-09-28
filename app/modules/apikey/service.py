"""API key service — issuance and revocation — plus the auth-time resolver.

Secrets are generated as ``etip_<random>``; only their SHA-256 hash is stored.
:func:`resolve_api_key` authenticates an inbound key and returns the linked user.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.db.base import utcnow
from app.db.unit_of_work import UnitOfWork
from app.modules.apikey.models import ApiKey
from app.modules.apikey.repository import ApiKeyRepository
from app.modules.apikey.schemas import ApiKeyCreateRequest
from app.modules.auth.repository import UserRepository

_PREFIX_LEN = 12


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def resolve_api_key(session: Session, raw_key: str) -> ApiKey:
    """Return the active, unexpired :class:`ApiKey` for a raw secret, or raise."""
    if not raw_key or len(raw_key) < _PREFIX_LEN:
        raise AuthenticationError("Invalid API key.")
    key = ApiKeyRepository(session).find_active_by_prefix(raw_key[:_PREFIX_LEN])
    if key is None or not hmac.compare_digest(_hash(raw_key), key.key_hash):
        raise AuthenticationError("Invalid API key.")
    if key.expires_date is not None and key.expires_date < utcnow().date():
        raise AuthenticationError("API key has expired.")
    return key


class ApiKeyService:
    """Issue and manage API keys, scoped to the caller's tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        self.keys = ApiKeyRepository(uow.session)
        self.users = UserRepository(uow.session)

    def create(self, payload: ApiKeyCreateRequest) -> tuple[ApiKey, str]:
        """Create a key; return ``(record, plaintext_secret)`` (secret shown once)."""
        user_id = payload.user_id or self._actor_id
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "The key's user does not belong to this organization.",
                details={"user_id": str(user_id)},
            )
        secret = "etip_" + secrets.token_urlsafe(32)
        key = ApiKey(
            organization_id=self._org_id,
            user_id=user_id,
            name=payload.name,
            prefix=secret[:_PREFIX_LEN],
            key_hash=_hash(secret),
            is_active=True,
            expires_date=payload.expires_date,
            created_by=self._actor_id,
        )
        key = self.keys.add(key)
        self._audit(key.id, "create", f"Issued API key '{key.name}'")
        return key, secret

    def revoke(self, key_id: uuid.UUID) -> ApiKey:
        """Deactivate a key (it can no longer authenticate)."""
        key = self._get_or_404(key_id)
        key.is_active = False
        key.modified_by = self._actor_id
        key = self.keys.update(key)
        self._audit(key.id, "revoke", f"Revoked API key '{key.name}'")
        return key

    def delete(self, key_id: uuid.UUID) -> None:
        """Soft-delete a key."""
        key = self._get_or_404(key_id)
        self.keys.soft_delete(key, actor_id=self._actor_id)
        self._audit(key.id, "delete", f"Deleted API key '{key.name}'")

    def get(self, key_id: uuid.UUID) -> ApiKey:
        """Return a key or raise ``NotFoundError``."""
        return self._get_or_404(key_id)

    def search(self, *, limit: int, offset: int) -> tuple[list[ApiKey], int]:
        """Return a page of keys and the total count."""
        return list(self.keys.search(self._org_id, limit=limit, offset=offset)), self.keys.count(
            self._org_id
        )

    def _get_or_404(self, key_id: uuid.UUID) -> ApiKey:
        key = self.keys.get(key_id, organization_id=self._org_id)
        if key is None:
            raise NotFoundError("API key not found.")
        return key

    def _audit(self, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            "ApiKey",
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
