"""Data access for the Jira connector."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.jira.models import ExternalLink, JiraConnection, JiraSyncLog
from app.repositories.base import BaseRepository


class JiraConnectionRepository(BaseRepository[JiraConnection]):
    """Repository for the per-tenant :class:`JiraConnection`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, JiraConnection)

    def get_for_org(self, organization_id: uuid.UUID) -> JiraConnection | None:
        return self.session.execute(self._base_query(organization_id)).scalars().first()

    def find_enabled_unscoped(self, organization_id: uuid.UUID) -> JiraConnection | None:
        stmt = select(JiraConnection).where(
            JiraConnection.organization_id == organization_id,
            JiraConnection.is_enabled.is_(True),
            JiraConnection.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalars().first()


class ExternalLinkRepository(BaseRepository[ExternalLink]):
    """Repository for :class:`ExternalLink` mappings."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ExternalLink)

    def by_entity(
        self,
        organization_id: uuid.UUID,
        system: str,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> ExternalLink | None:
        stmt = self._base_query(organization_id).where(
            ExternalLink.system == system,
            ExternalLink.entity_type == entity_type,
            ExternalLink.entity_id == entity_id,
        )
        return self.session.execute(stmt).scalars().first()

    def by_external_key(
        self, organization_id: uuid.UUID, system: str, external_key: str
    ) -> ExternalLink | None:
        stmt = self._base_query(organization_id).where(
            ExternalLink.system == system, ExternalLink.external_key == external_key
        )
        return self.session.execute(stmt).scalars().first()

    def list_for_org(
        self,
        organization_id: uuid.UUID,
        system: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ExternalLink]:
        stmt = (
            self._base_query(organization_id)
            .where(ExternalLink.system == system)
            .order_by(ExternalLink.external_key)
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()


class JiraSyncLogRepository(BaseRepository[JiraSyncLog]):
    """Repository for :class:`JiraSyncLog` audit records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, JiraSyncLog)

    def recent(self, organization_id: uuid.UUID, *, limit: int = 50) -> Sequence[JiraSyncLog]:
        stmt = (
            self._base_query(organization_id).order_by(JiraSyncLog.created_date.desc()).limit(limit)
        )
        return self.session.execute(stmt).scalars().all()
