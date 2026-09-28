"""Repositories for the Project Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.project.models import (
    Project,
    ProjectComment,
    ProjectStage,
    ProjectStatus,
    ProjectTeamMember,
)
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Data access for :class:`Project`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Project)

    def get_by_code(self, organization_id: uuid.UUID, code: str) -> Project | None:
        """Return a project by its per-organization code."""
        stmt = self._base_query(organization_id).where(Project.code == code)
        return self.session.execute(stmt).scalar_one_or_none()

    def next_number(self, organization_id: uuid.UUID) -> int:
        """Return the next running project number for the tenant.

        Uses ``MAX(number) + 1`` scoped to the organization. The
        ``(organization_id, number)`` unique constraint is the backstop against
        a concurrent race; callers translate a violation into a retry/conflict.
        """
        stmt = select(func.coalesce(func.max(Project.number), 0)).where(
            Project.organization_id == organization_id
        )
        return int(self.session.execute(stmt).scalar_one()) + 1

    def has_for_portfolio(self, organization_id: uuid.UUID, portfolio_id: uuid.UUID) -> bool:
        """Return ``True`` if any live project belongs to the portfolio."""
        stmt = self._base_query(organization_id).where(Project.portfolio_id == portfolio_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def has_for_program(self, organization_id: uuid.UUID, program_id: uuid.UUID) -> bool:
        """Return ``True`` if any live project belongs to the program."""
        stmt = self._base_query(organization_id).where(Project.program_id == program_id)
        return self.session.execute(stmt.limit(1)).first() is not None

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        status: ProjectStatus | None,
        stage: ProjectStage | None,
        portfolio_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        manager_user_id: uuid.UUID | None,
    ) -> Select[tuple[Project]]:
        """Build the filtered (unpaginated) project query."""
        stmt = self._base_query(organization_id)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                func.lower(Project.name).like(like) | func.lower(Project.code).like(like)
            )
        if status is not None:
            stmt = stmt.where(Project.status == status)
        if stage is not None:
            stmt = stmt.where(Project.stage == stage)
        if portfolio_id is not None:
            stmt = stmt.where(Project.portfolio_id == portfolio_id)
        if program_id is not None:
            stmt = stmt.where(Project.program_id == program_id)
        if manager_user_id is not None:
            stmt = stmt.where(Project.manager_user_id == manager_user_id)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: ProjectStatus | None = None,
        stage: ProjectStage | None = None,
        portfolio_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        manager_user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Project]:
        """Return a filtered, paginated page of projects."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            status=status,
            stage=stage,
            portfolio_id=portfolio_id,
            program_id=program_id,
            manager_user_id=manager_user_id,
        )
        stmt = stmt.order_by(Project.number.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: ProjectStatus | None = None,
        stage: ProjectStage | None = None,
        portfolio_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        manager_user_id: uuid.UUID | None = None,
    ) -> int:
        """Return the total number of projects matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            status=status,
            stage=stage,
            portfolio_id=portfolio_id,
            program_id=program_id,
            manager_user_id=manager_user_id,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class ProjectTeamMemberRepository(BaseRepository[ProjectTeamMember]):
    """Data access for :class:`ProjectTeamMember`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProjectTeamMember)

    def list_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sequence[ProjectTeamMember]:
        """Return the team members of a project."""
        stmt = self._base_query(organization_id).where(ProjectTeamMember.project_id == project_id)
        return self.session.execute(stmt).scalars().all()

    def get_membership(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProjectTeamMember | None:
        """Return a specific user's membership in a project."""
        stmt = self._base_query(organization_id).where(
            ProjectTeamMember.project_id == project_id,
            ProjectTeamMember.user_id == user_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()


class ProjectCommentRepository(BaseRepository[ProjectComment]):
    """Data access for :class:`ProjectComment`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProjectComment)

    def list_for_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sequence[ProjectComment]:
        """Return the comments of a project, newest first."""
        stmt = (
            self._base_query(organization_id)
            .where(ProjectComment.project_id == project_id)
            .order_by(ProjectComment.created_date.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def get_in_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        comment_id: uuid.UUID,
    ) -> ProjectComment | None:
        """Return a specific comment scoped to its project."""
        stmt = self._base_query(organization_id).where(
            ProjectComment.project_id == project_id,
            ProjectComment.id == comment_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()
