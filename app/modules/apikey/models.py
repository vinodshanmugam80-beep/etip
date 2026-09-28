"""API key model — service-account authentication for external tools.

An :class:`ApiKey` lets an external system (Jira, Microsoft Project, CI, a data
pipeline) call the REST API on behalf of a user identity without a human login.
Only a SHA-256 hash of the secret is stored; the plaintext key is shown once at
creation. The key's effective permissions are those of its linked user's roles.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin


class ApiKey(BaseEntity, TenantMixin):
    """A hashed API key bound to a user identity within a tenant."""

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expires_date: Mapped[date | None] = mapped_column(Date, nullable=True)
