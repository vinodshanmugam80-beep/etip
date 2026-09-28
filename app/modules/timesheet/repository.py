"""Repository for the Timesheet Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.timesheet.models import (
    ActivityType,
    TimeEntry,
    TimeEntryStatus,
)
from app.repositories.base import BaseRepository


class TimeEntryRepository(BaseRepository[TimeEntry]):
    """Data access for :class:`TimeEntry`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, TimeEntry)

    def _filters(
        self,
        *,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        status: TimeEntryStatus | None,
        billable: bool | None,
        activity_type: ActivityType | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[ColumnElement[bool]]:
        """Return the WHERE clauses common to search, count and summary."""
        clauses: list[ColumnElement[bool]] = []
        if project_id is not None:
            clauses.append(TimeEntry.project_id == project_id)
        if task_id is not None:
            clauses.append(TimeEntry.task_id == task_id)
        if user_id is not None:
            clauses.append(TimeEntry.user_id == user_id)
        if status is not None:
            clauses.append(TimeEntry.status == status)
        if billable is not None:
            clauses.append(TimeEntry.billable.is_(billable))
        if activity_type is not None:
            clauses.append(TimeEntry.activity_type == activity_type)
        if date_from is not None:
            clauses.append(TimeEntry.work_date >= date_from)
        if date_to is not None:
            clauses.append(TimeEntry.work_date <= date_to)
        return clauses

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        status: TimeEntryStatus | None,
        billable: bool | None,
        activity_type: ActivityType | None,
        date_from: date | None,
        date_to: date | None,
    ) -> Select[tuple[TimeEntry]]:
        stmt = self._base_query(organization_id)
        for clause in self._filters(
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            status=status,
            billable=billable,
            activity_type=activity_type,
            date_from=date_from,
            date_to=date_to,
        ):
            stmt = stmt.where(clause)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        status: TimeEntryStatus | None = None,
        billable: bool | None = None,
        activity_type: ActivityType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[TimeEntry]:
        """Return a filtered, paginated page of entries (newest work date first)."""
        stmt = self._search_stmt(
            organization_id,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            status=status,
            billable=billable,
            activity_type=activity_type,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = stmt.order_by(TimeEntry.work_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        status: TimeEntryStatus | None = None,
        billable: bool | None = None,
        activity_type: ActivityType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> int:
        """Return the number of entries matching the filters."""
        inner = self._search_stmt(
            organization_id,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            status=status,
            billable=billable,
            activity_type=activity_type,
            date_from=date_from,
            date_to=date_to,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def approved_hours_for_task(self, organization_id: uuid.UUID, task_id: uuid.UUID) -> Decimal:
        """Return the sum of approved hours logged against a task."""
        stmt = select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.task_id == task_id,
            TimeEntry.is_deleted.is_(False),
            TimeEntry.status == TimeEntryStatus.APPROVED,
        )
        return Decimal(str(self.session.execute(stmt).scalar_one()))

    def sum_hours(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        billable: bool | None = None,
        status: TimeEntryStatus | None = None,
    ) -> Decimal:
        """Return the total hours over a filtered set of entries."""
        stmt = select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.is_deleted.is_(False),
            *self._filters(
                project_id=project_id,
                task_id=None,
                user_id=user_id,
                status=status,
                billable=billable,
                activity_type=None,
                date_from=date_from,
                date_to=date_to,
            ),
        )
        return Decimal(str(self.session.execute(stmt).scalar_one()))

    def hours_by_status(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[tuple[TimeEntryStatus, Decimal, int]]:
        """Return (status, hours, count) grouped by workflow state."""
        stmt = (
            select(
                TimeEntry.status,
                func.coalesce(func.sum(TimeEntry.hours), 0),
                func.count(),
            )
            .where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.is_deleted.is_(False),
                *self._filters(
                    project_id=project_id,
                    task_id=None,
                    user_id=user_id,
                    status=None,
                    billable=None,
                    activity_type=None,
                    date_from=date_from,
                    date_to=date_to,
                ),
            )
            .group_by(TimeEntry.status)
        )
        return [
            (row[0], Decimal(str(row[1])), int(row[2])) for row in self.session.execute(stmt).all()
        ]

    def soft_delete_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> int:
        """Soft-delete every live time entry of a project."""
        stmt = self._base_query(organization_id).where(TimeEntry.project_id == project_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for entry in rows:
            entry.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
