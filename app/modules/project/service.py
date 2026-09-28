"""Project Management service.

Business rules for the project aggregate and its children (team members and
comments). Highlights:

* Per-organization ``code`` uniqueness and an auto-assigned running ``number``.
* Portfolio/program consistency: a project's program (if any) must live in the
  project's portfolio; supplying only a program derives the portfolio from it.
* Reference validation for department, sponsor and manager against the tenant.
* Status lifecycle via the shared transition validator.
* Effective date-range validation for both the actual and baseline schedules.

Portfolio and program are set at creation and are immutable thereafter (moving
a project between parents is intentionally out of scope for a partial update).
Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.change.repository import ChangeRequestRepository
from app.modules.dependency.models import DependencyEntityType
from app.modules.dependency.repository import DependencyRepository
from app.modules.document.models import DocumentOwnerType
from app.modules.document.repository import DocumentRepository
from app.modules.finance.repository import FinancialEntryRepository
from app.modules.issue.repository import IssueRepository
from app.modules.meeting.repository import MeetingRepository
from app.modules.milestone.repository import MilestoneRepository
from app.modules.organization.repository import DepartmentRepository
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.program.repository import ProgramRepository
from app.modules.project.models import (
    Project,
    ProjectComment,
    ProjectHealth,
    ProjectPriority,
    ProjectStage,
    ProjectStatus,
    ProjectTeamMember,
)
from app.modules.project.repository import (
    ProjectCommentRepository,
    ProjectRepository,
    ProjectTeamMemberRepository,
)
from app.modules.raid.repository import ActionRepository, DecisionRepository
from app.modules.resource.repository import AllocationRepository
from app.modules.risk.repository import RiskRepository
from app.modules.task.repository import TaskRepository
from app.modules.timesheet.repository import TimeEntryRepository

logger = get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.PROPOSED: {ProjectStatus.ACTIVE, ProjectStatus.CANCELLED},
    ProjectStatus.ACTIVE: {
        ProjectStatus.ON_HOLD,
        ProjectStatus.CLOSED,
        ProjectStatus.CANCELLED,
    },
    ProjectStatus.ON_HOLD: {ProjectStatus.ACTIVE, ProjectStatus.CANCELLED},
    ProjectStatus.CLOSED: set(),
    ProjectStatus.CANCELLED: set(),
}


class ProjectService:
    """Coordinates project use cases within a tenant."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.projects = ProjectRepository(session)
        self.team = ProjectTeamMemberRepository(session)
        self.comments = ProjectCommentRepository(session)
        self.portfolios = PortfolioRepository(session)
        self.programs = ProgramRepository(session)
        self.departments = DepartmentRepository(session)
        self.users = UserRepository(session)
        self.tasks = TaskRepository(session)
        self.allocations = AllocationRepository(session)
        self.financials = FinancialEntryRepository(session)
        self.risks = RiskRepository(session)
        self.issues = IssueRepository(session)
        self.actions = ActionRepository(session)
        self.decisions = DecisionRepository(session)
        self.changes = ChangeRequestRepository(session)
        self.dependencies = DependencyRepository(session)
        self.milestones = MilestoneRepository(session)
        self.time_entries = TimeEntryRepository(session)
        self.meetings = MeetingRepository(session)
        self.documents = DocumentRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, project_id: uuid.UUID) -> Project:
        project = self.projects.get(project_id, organization_id=self._org_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    def _require_user_in_org(self, user_id: uuid.UUID | None, *, label: str) -> None:
        if user_id is None:
            return
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                f"{label} does not belong to this organization.",
                details={"user_id": str(user_id)},
            )

    def _require_department(self, department_id: uuid.UUID | None) -> None:
        if department_id is None:
            return
        if self.departments.get(department_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Department does not belong to this organization.",
                details={"department_id": str(department_id)},
            )

    def _resolve_hierarchy(
        self, portfolio_id: uuid.UUID | None, program_id: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Validate portfolio/program references and return the effective pair.

        If a program is supplied its portfolio is authoritative: an explicit
        portfolio must match it, and an omitted portfolio is derived from it.
        """
        if program_id is not None:
            program = self.programs.get(program_id, organization_id=self._org_id)
            if program is None:
                raise NotFoundError("Program not found.")
            if portfolio_id is not None and portfolio_id != program.portfolio_id:
                raise ValidationError(
                    "Program does not belong to the specified portfolio.",
                    code="hierarchy_mismatch",
                )
            return program.portfolio_id, program_id

        if portfolio_id is not None:
            if self.portfolios.get(portfolio_id, organization_id=self._org_id) is None:
                raise NotFoundError("Portfolio not found.")
        return portfolio_id, None

    @staticmethod
    def _validate_schedule(
        start: date | None,
        end: date | None,
        baseline_start: date | None,
        baseline_end: date | None,
    ) -> None:
        if start and end and end < start:
            raise ValidationError("end_date must not be before start_date.")
        if baseline_start and baseline_end and baseline_end < baseline_start:
            raise ValidationError("baseline_end_date must not be before baseline_start_date.")

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_project(
        self,
        *,
        name: str,
        code: str,
        description: str,
        portfolio_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        sponsor_user_id: uuid.UUID | None,
        manager_user_id: uuid.UUID | None,
        stage: ProjectStage,
        priority: ProjectPriority,
        budget: Decimal,
        forecast: Decimal,
        currency: str,
        start_date: date | None,
        end_date: date | None,
        baseline_start_date: date | None,
        baseline_end_date: date | None,
        tags: list[str],
        custom_fields: dict[str, Any],
    ) -> Project:
        """Create a project, validating references and hierarchy consistency."""
        if self.projects.get_by_code(self._org_id, code):
            raise ConflictError(
                f"A project with code '{code}' already exists.",
                details={"code": code},
            )
        effective_portfolio, effective_program = self._resolve_hierarchy(portfolio_id, program_id)
        self._require_department(department_id)
        self._require_user_in_org(sponsor_user_id, label="Sponsor")
        self._require_user_in_org(manager_user_id, label="Manager")
        self._validate_schedule(start_date, end_date, baseline_start_date, baseline_end_date)

        project = Project(
            organization_id=self._org_id,
            number=self.projects.next_number(self._org_id),
            code=code,
            name=name,
            description=description,
            portfolio_id=effective_portfolio,
            program_id=effective_program,
            department_id=department_id,
            sponsor_user_id=sponsor_user_id,
            manager_user_id=manager_user_id,
            status=ProjectStatus.PROPOSED,
            stage=stage,
            priority=priority,
            budget=budget,
            forecast=forecast,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            baseline_start_date=baseline_start_date,
            baseline_end_date=baseline_end_date,
            tags=tags,
            custom_fields=custom_fields,
            created_by=self._actor_id,
        )
        self.projects.add(project)
        self._uow.record_audit(
            "Project",
            project.id,
            "create",
            f"Created project '{name}' (#{project.number})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        self._uow.add_event(
            "project.created",
            {"project_id": str(project.id), "code": project.code, "name": project.name},
            organization_id=self._org_id,
        )
        return project

    def get_project(self, project_id: uuid.UUID) -> Project:
        """Return a single project by id."""
        return self._get_or_404(project_id)

    def search_projects(
        self,
        *,
        query: str | None,
        status: ProjectStatus | None,
        stage: ProjectStage | None,
        portfolio_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        manager_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Project], int]:
        """Return a filtered page of projects and the total matching count."""
        items = list(
            self.projects.search(
                self._org_id,
                query=query,
                status=status,
                stage=stage,
                portfolio_id=portfolio_id,
                program_id=program_id,
                manager_user_id=manager_user_id,
                limit=limit,
                offset=offset,
            )
        )
        total = self.projects.count(
            self._org_id,
            query=query,
            status=status,
            stage=stage,
            portfolio_id=portfolio_id,
            program_id=program_id,
            manager_user_id=manager_user_id,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_project(
        self,
        project_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        department_id: uuid.UUID | None,
        sponsor_user_id: uuid.UUID | None,
        manager_user_id: uuid.UUID | None,
        status: ProjectStatus | None,
        stage: ProjectStage | None,
        priority: ProjectPriority | None,
        health: ProjectHealth | None,
        budget: Decimal | None,
        forecast: Decimal | None,
        actual_cost: Decimal | None,
        currency: str | None,
        start_date: date | None,
        end_date: date | None,
        baseline_start_date: date | None,
        baseline_end_date: date | None,
        progress_percent: int | None,
        tags: list[str] | None,
        custom_fields: dict[str, Any] | None,
    ) -> Project:
        """Apply a partial update, validating transitions, refs and dates."""
        project = self._get_or_404(project_id)

        if status is not None:
            validate_status_transition(_ALLOWED_TRANSITIONS, project.status, status)
            project.status = status
        if department_id is not None:
            self._require_department(department_id)
            project.department_id = department_id
        if sponsor_user_id is not None:
            self._require_user_in_org(sponsor_user_id, label="Sponsor")
            project.sponsor_user_id = sponsor_user_id
        if manager_user_id is not None:
            self._require_user_in_org(manager_user_id, label="Manager")
            project.manager_user_id = manager_user_id

        for attr, value in (
            ("name", name),
            ("description", description),
            ("stage", stage),
            ("priority", priority),
            ("health", health),
            ("budget", budget),
            ("forecast", forecast),
            ("actual_cost", actual_cost),
            ("currency", currency),
            ("start_date", start_date),
            ("end_date", end_date),
            ("baseline_start_date", baseline_start_date),
            ("baseline_end_date", baseline_end_date),
            ("progress_percent", progress_percent),
            ("tags", tags),
            ("custom_fields", custom_fields),
        ):
            if value is not None:
                setattr(project, attr, value)

        self._validate_schedule(
            project.start_date,
            project.end_date,
            project.baseline_start_date,
            project.baseline_end_date,
        )

        project.modified_by = self._actor_id
        self.projects.update(project)
        self._uow.record_audit(
            "Project",
            project.id,
            "update",
            f"Updated project '{project.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return project

    def delete_project(self, project_id: uuid.UUID) -> None:
        """Soft-delete a project and all of its dependent records."""
        project = self._get_or_404(project_id)
        # Clean up dependency edges first, while the task ids are still live:
        # project-level edges touching this project, and task-level edges
        # touching any of its tasks.
        task_ids = [task.id for task in self.tasks.list_for_project(self._org_id, project_id)]
        self.dependencies.soft_delete_for_entities(
            self._org_id,
            DependencyEntityType.PROJECT,
            [project_id],
            actor_id=self._actor_id,
        )
        self.dependencies.soft_delete_for_entities(
            self._org_id,
            DependencyEntityType.TASK,
            task_ids,
            actor_id=self._actor_id,
        )
        self.documents.soft_delete_for_owners(
            self._org_id,
            DocumentOwnerType.PROJECT,
            [project_id],
            actor_id=self._actor_id,
        )
        self.documents.soft_delete_for_owners(
            self._org_id,
            DocumentOwnerType.TASK,
            task_ids,
            actor_id=self._actor_id,
        )
        self.tasks.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.allocations.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.financials.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.risks.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.issues.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.actions.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.decisions.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.changes.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.milestones.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.time_entries.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.meetings.soft_delete_for_project(self._org_id, project_id, actor_id=self._actor_id)
        self.projects.soft_delete(project, actor_id=self._actor_id)
        self._uow.record_audit(
            "Project",
            project.id,
            "delete",
            f"Deleted project '{project.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Team members
    # ------------------------------------------------------------------
    def add_team_member(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        role_label: str,
        allocation_percent: int,
    ) -> ProjectTeamMember:
        """Add a user to the project team."""
        self._get_or_404(project_id)
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "User does not belong to this organization.",
                details={"user_id": str(user_id)},
            )
        if self.team.get_membership(self._org_id, project_id, user_id):
            raise ConflictError("User is already a member of this project.")
        member = ProjectTeamMember(
            organization_id=self._org_id,
            project_id=project_id,
            user_id=user_id,
            role_label=role_label,
            allocation_percent=allocation_percent,
            created_by=self._actor_id,
        )
        self.team.add(member)
        self._uow.record_audit(
            "ProjectTeamMember",
            member.id,
            "create",
            "Added team member",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return member

    def list_team_members(self, project_id: uuid.UUID) -> Sequence[ProjectTeamMember]:
        """Return the team members of a project."""
        self._get_or_404(project_id)
        return self.team.list_for_project(self._org_id, project_id)

    def remove_team_member(self, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove a user from the project team."""
        member = self.team.get_membership(self._org_id, project_id, user_id)
        if member is None:
            raise NotFoundError("Team member not found.")
        self.team.soft_delete(member, actor_id=self._actor_id)
        self._uow.record_audit(
            "ProjectTeamMember",
            member.id,
            "delete",
            "Removed team member",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------
    def add_comment(self, project_id: uuid.UUID, *, body: str) -> ProjectComment:
        """Post a comment on a project, authored by the acting user."""
        self._get_or_404(project_id)
        comment = ProjectComment(
            organization_id=self._org_id,
            project_id=project_id,
            author_user_id=self._actor_id,
            body=body,
            created_by=self._actor_id,
        )
        self.comments.add(comment)
        self._uow.record_audit(
            "ProjectComment",
            comment.id,
            "create",
            "Posted comment",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return comment

    def list_comments(self, project_id: uuid.UUID) -> Sequence[ProjectComment]:
        """Return the comments of a project, newest first."""
        self._get_or_404(project_id)
        return self.comments.list_for_project(self._org_id, project_id)

    def remove_comment(self, project_id: uuid.UUID, comment_id: uuid.UUID) -> None:
        """Remove a comment from a project."""
        comment = self.comments.get_in_project(self._org_id, project_id, comment_id)
        if comment is None:
            raise NotFoundError("Comment not found.")
        self.comments.soft_delete(comment, actor_id=self._actor_id)
        self._uow.record_audit(
            "ProjectComment",
            comment.id,
            "delete",
            "Removed comment",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
