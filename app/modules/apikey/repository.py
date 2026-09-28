"""Data access for API keys."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.apikey.models import ApiKey
from app.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    """Repository for :class:`ApiKey`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ApiKey)

    def find_active_by_prefix(self, prefix: str) -> ApiKey | None:
        """Return an active, non-deleted key by prefix — NOT tenant-scoped.

        Used during authentication, before a tenant is known. The full secret is
        still verified against ``key_hash`` by the caller.
        """
        stmt = select(ApiKey).where(
            ApiKey.prefix == prefix,
            ApiKey.is_deleted.is_(False),
            ApiKey.is_active.is_(True),
        )
        return self.session.execute(stmt).scalars().first()

    def search(
        self, organization_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[ApiKey]:
        """Return a paginated page of the tenant's keys (newest first)."""
        stmt = (
            self._base_query(organization_id)
            .order_by(ApiKey.created_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def count(self, organization_id: uuid.UUID) -> int:
        """Return the number of keys for the tenant."""
        inner = self._base_query(organization_id).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())
