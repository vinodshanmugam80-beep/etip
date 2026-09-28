"""Data access for the Administration module.

Reads the append-only :class:`AuditLog` and computes governance counts. This is
an admin/reporting data layer, so it deliberately queries several tables for
read-only counts (in the spirit of the report engine) rather than routing
through each module's repository.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import AuditLog
from app.modules.auth.models import Role, User
from app.modules.portfolio.models import Portfolio
from app.modules.project.models import Project


class AuditLogRepository:
    """Read access to the append-only audit log, scoped to a tenant."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entry_id: uuid.UUID, organization_id: uuid.UUID) -> AuditLog | None:
        """Return a single audit entry belonging to the tenant."""
        stmt = select(AuditLog).where(
            AuditLog.id == entry_id,
            AuditLog.organization_id == organization_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        action: str | None,
        actor_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[tuple[AuditLog]]:
        stmt = select(AuditLog).where(AuditLog.organization_id == organization_id)
        if entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if date_from is not None:
            stmt = stmt.where(AuditLog.created_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditLog.created_date <= date_to)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AuditLog]:
        """Return a filtered page of audit entries (newest first)."""
        stmt = self._filtered(
            organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = stmt.order_by(AuditLog.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        """Return the number of audit entries matching the filters."""
        inner = self._filtered(
            organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            date_from=date_from,
            date_to=date_to,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class AdminStatsRepository:
    """Governance counts for a tenant."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _scalar(self, stmt: Select[tuple[int]]) -> int:
        return int(self.session.execute(stmt).scalar_one())

    def user_counts(self, organization_id: uuid.UUID) -> tuple[int, int]:
        """Return ``(total_users, active_users)`` for the tenant."""
        base = select(func.count()).where(
            User.organization_id == organization_id,
            User.is_deleted.is_(False),
        )
        total = self._scalar(base)
        active = self._scalar(base.where(User.is_active.is_(True)))
        return total, active

    def role_count(self, organization_id: uuid.UUID) -> int:
        """Return the number of roles in the tenant."""
        return self._scalar(
            select(func.count()).where(
                Role.organization_id == organization_id,
                Role.is_deleted.is_(False),
            )
        )

    def project_count(self, organization_id: uuid.UUID) -> int:
        """Return the number of projects in the tenant."""
        return self._scalar(
            select(func.count()).where(
                Project.organization_id == organization_id,
                Project.is_deleted.is_(False),
            )
        )

    def portfolio_count(self, organization_id: uuid.UUID) -> int:
        """Return the number of portfolios in the tenant."""
        return self._scalar(
            select(func.count()).where(
                Portfolio.organization_id == organization_id,
                Portfolio.is_deleted.is_(False),
            )
        )

    def audit_count(self, organization_id: uuid.UUID) -> int:
        """Return the number of audit entries in the tenant."""
        return self._scalar(select(func.count()).where(AuditLog.organization_id == organization_id))
