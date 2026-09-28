"""Repository for the Issue Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.issue.models import (
    Issue,
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    IssueType,
)
from app.repositories.base import BaseRepository


class IssueRepository(BaseRepository[Issue]):
    """Data access for :class:`Issue`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Issue)

    def next_number(self, project_id: uuid.UUID) -> int:
        """Return the next running issue number within a project."""
        stmt = select(func.coalesce(func.max(Issue.number), 0)).where(
            Issue.project_id == project_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def open_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the number of non-closed issues for a project."""
        stmt = select(func.count()).where(
            Issue.organization_id == organization_id,
            Issue.project_id == project_id,
            Issue.is_deleted.is_(False),
            Issue.status != IssueStatus.CLOSED,
        )
        return int(self.session.execute(stmt).scalar_one())

    def total_count(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> int:
        """Return the total number of live issues for a project."""
        stmt = select(func.count()).where(
            Issue.organization_id == organization_id,
            Issue.project_id == project_id,
            Issue.is_deleted.is_(False),
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_status(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[tuple[IssueStatus, int]]:
        """Return live issue counts grouped by workflow state."""
        stmt = (
            select(Issue.status, func.count())
            .where(
                Issue.organization_id == organization_id,
                Issue.project_id == project_id,
                Issue.is_deleted.is_(False),
            )
            .group_by(Issue.status)
        )
        return [(row[0], int(row[1])) for row in self.session.execute(stmt).all()]

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        status: IssueStatus | None,
        issue_type: IssueType | None,
        severity: IssueSeverity | None,
        priority: IssuePriority | None,
        assignee_user_id: uuid.UUID | None,
    ) -> Select[tuple[Issue]]:
        """Build the filtered (unpaginated) issue query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Issue.title).like(f"%{query.lower()}%"))
        if project_id is not None:
            stmt = stmt.where(Issue.project_id == project_id)
        if task_id is not None:
            stmt = stmt.where(Issue.task_id == task_id)
        if status is not None:
            stmt = stmt.where(Issue.status == status)
        if issue_type is not None:
            stmt = stmt.where(Issue.issue_type == issue_type)
        if severity is not None:
            stmt = stmt.where(Issue.severity == severity)
        if priority is not None:
            stmt = stmt.where(Issue.priority == priority)
        if assignee_user_id is not None:
            stmt = stmt.where(Issue.assignee_user_id == assignee_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        status: IssueStatus | None = None,
        issue_type: IssueType | None = None,
        severity: IssueSeverity | None = None,
        priority: IssuePriority | None = None,
        assignee_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Issue]:
        """Return a filtered, paginated page of issues (newest number first)."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            task_id=task_id,
            status=status,
            issue_type=issue_type,
            severity=severity,
            priority=priority,
            assignee_user_id=assignee_user_id,
        )
        stmt = stmt.order_by(Issue.number.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        project_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        status: IssueStatus | None = None,
        issue_type: IssueType | None = None,
        severity: IssueSeverity | None = None,
        priority: IssuePriority | None = None,
        assignee_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the total number of issues matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            project_id=project_id,
            task_id=task_id,
            status=status,
            issue_type=issue_type,
            severity=severity,
            priority=priority,
            assignee_user_id=assignee_user_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live issue of a project."""
        stmt = self._base_query(organization_id).where(Issue.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for issue in rows:
            issue.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
