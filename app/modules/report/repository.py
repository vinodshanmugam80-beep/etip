"""Repository for the Reports module."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.report.models import ReportDefinition, ReportType
from app.repositories.base import BaseRepository


class ReportDefinitionRepository(BaseRepository[ReportDefinition]):
    """Data access for :class:`ReportDefinition`.

    Visibility: a user sees definitions they own (``created_by``) plus any that
    are shared with the organization (``is_shared``).
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, ReportDefinition)

    def _visible(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Select[tuple[ReportDefinition]]:
        return self._base_query(organization_id).where(
            or_(
                ReportDefinition.created_by == user_id,
                ReportDefinition.is_shared.is_(True),
            )
        )

    def get_visible(
        self, report_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReportDefinition | None:
        """Return a definition if the user owns it or it is shared."""
        stmt = self._visible(organization_id, user_id).where(ReportDefinition.id == report_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def search(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        report_type: ReportType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ReportDefinition]:
        """Return a page of definitions visible to the user (newest first)."""
        stmt = self._visible(organization_id, user_id)
        if report_type is not None:
            stmt = stmt.where(ReportDefinition.report_type == report_type)
        stmt = stmt.order_by(ReportDefinition.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        report_type: ReportType | None = None,
    ) -> int:
        """Return the number of definitions visible to the user."""
        stmt = self._visible(organization_id, user_id)
        if report_type is not None:
            stmt = stmt.where(ReportDefinition.report_type == report_type)
        inner = stmt.subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())
