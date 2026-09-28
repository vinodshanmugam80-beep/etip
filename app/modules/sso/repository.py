"""Data access for SSO configuration."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.sso.models import SsoConfiguration
from app.repositories.base import BaseRepository


class SsoConfigRepository(BaseRepository[SsoConfiguration]):
    """Repository for :class:`SsoConfiguration` (one row per organization)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, SsoConfiguration)

    def get_for_org(self, organization_id: uuid.UUID) -> SsoConfiguration | None:
        """Return the tenant's single SSO configuration, if any."""
        return self.session.execute(self._base_query(organization_id)).scalars().first()

    def find_enabled(self, organization_id: uuid.UUID) -> SsoConfiguration | None:
        """Return the tenant's SSO config only if it exists and is enabled."""
        stmt = self._base_query(organization_id).where(SsoConfiguration.is_enabled.is_(True))
        return self.session.execute(stmt).scalars().first()

    def find_enabled_unscoped(self, organization_id: uuid.UUID) -> SsoConfiguration | None:
        """Enabled config lookup without a caller tenant context (used at callback).

        Still filtered to the given organization id (carried in the signed state),
        so it never crosses tenants.
        """
        stmt = select(SsoConfiguration).where(
            SsoConfiguration.organization_id == organization_id,
            SsoConfiguration.is_enabled.is_(True),
            SsoConfiguration.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalars().first()
