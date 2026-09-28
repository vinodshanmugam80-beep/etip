"""FastAPI dependency providers.

Wires the request scope to a Unit of Work, resolves the authenticated user
from the bearer token, and provides a permission-checking guard used to
protect endpoints.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.session import SessionFactory
from app.db.unit_of_work import UnitOfWork
from app.modules.admin.service import AdminService
from app.modules.aidelivery.service import AiDeliveryService
from app.modules.apikey.service import ApiKeyService
from app.modules.auth.models import User
from app.modules.auth.service import AuthService
from app.modules.benefit.service import BenefitService
from app.modules.change.service import ChangeRequestService
from app.modules.copilot.service import CopilotService
from app.modules.dashboard.service import DashboardService
from app.modules.dependency.service import DependencyService
from app.modules.document.service import DocumentService
from app.modules.finance.service import FinanceService
from app.modules.initiative.service import InitiativeService
from app.modules.integration.service import IntegrationService
from app.modules.intelligence.service import IntelligenceService
from app.modules.issue.service import IssueService
from app.modules.jira.service import JiraService
from app.modules.meeting.service import MeetingService
from app.modules.metrics.service import MetricsService
from app.modules.milestone.service import MilestoneService
from app.modules.notification.service import NotificationService
from app.modules.organization.service import OrganizationService
from app.modules.portfolio.service import PortfolioService
from app.modules.program.service import ProgramService
from app.modules.project.service import ProjectService
from app.modules.projectkpi.service import ProjectKPIService
from app.modules.raid.service import RaidService
from app.modules.rbac.service import RbacService
from app.modules.report.service import ReportService
from app.modules.resource.service import ResourceService
from app.modules.risk.service import RiskService
from app.modules.skill.service import SkillService
from app.modules.sprint.service import SprintService
from app.modules.sso.service import SsoService
from app.modules.task.service import TaskService
from app.modules.timesheet.service import TimesheetService
from app.modules.user.service import UserService
from app.modules.vendor.service import VendorService
from app.modules.workflow.service import WorkflowService

_bearer = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_uow() -> Iterator[UnitOfWork]:
    """Yield an open Unit of Work for the duration of the request."""
    with UnitOfWork(SessionFactory) as uow:
        yield uow


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_auth_service(settings: SettingsDep, uow: UowDep) -> AuthService:
    """Construct an :class:`AuthService` bound to the request's Unit of Work."""
    return AuthService(settings, uow)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(
    request: Request,
    settings: SettingsDep,
    service: AuthServiceDep,
    uow: UowDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    """Resolve the authenticated user from the ``Authorization`` header.

    :raises AuthenticationError: When the token is missing, invalid or the
        user no longer exists.
    """
    if credentials is not None:
        try:
            claims = decode_token(settings, credentials.credentials, expected_type="access")
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired token.") from exc
        user = service.get_active_user(claims.subject, claims.organization_id)
        request.state.user_id = str(user.id)
        request.state.organization_id = str(user.organization_id)
        return user

    api_key = request.headers.get("X-API-Key")
    if api_key:
        from app.modules.apikey.service import resolve_api_key

        key = resolve_api_key(uow.session, api_key)
        user = service.get_active_user(key.user_id, key.organization_id)
        request.state.user_id = str(user.id)
        request.state.organization_id = str(user.organization_id)
        return user

    raise AuthenticationError("Authentication required.")


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission_code: str) -> Callable[[User], User]:
    """Return a dependency asserting the current user holds ``permission_code``.

    Usage::

        @router.post(..., dependencies=[Depends(require_permission("user:create"))])
    """

    def _guard(user: CurrentUser) -> User:
        if permission_code not in user.permission_codes:
            raise PermissionDeniedError(
                "You do not have permission to perform this action.",
                details={"required": permission_code},
            )
        return user

    return _guard


def get_organization_service(user: CurrentUser, uow: UowDep) -> OrganizationService:
    """Construct an :class:`OrganizationService` scoped to the caller's tenant."""
    return OrganizationService(uow, organization_id=user.organization_id, actor_id=user.id)


OrganizationServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]


def get_user_service(user: CurrentUser, uow: UowDep) -> UserService:
    """Construct a :class:`UserService` scoped to the caller's tenant."""
    return UserService(uow, organization_id=user.organization_id, actor_id=user.id)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_rbac_service(user: CurrentUser, uow: UowDep) -> RbacService:
    """Construct an :class:`RbacService` scoped to the caller's tenant."""
    return RbacService(uow, organization_id=user.organization_id, actor_id=user.id)


RbacServiceDep = Annotated[RbacService, Depends(get_rbac_service)]


def get_portfolio_service(user: CurrentUser, uow: UowDep) -> PortfolioService:
    """Construct a :class:`PortfolioService` scoped to the caller's tenant."""
    return PortfolioService(uow, organization_id=user.organization_id, actor_id=user.id)


PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]


def get_program_service(user: CurrentUser, uow: UowDep) -> ProgramService:
    """Construct a :class:`ProgramService` scoped to the caller's tenant."""
    return ProgramService(uow, organization_id=user.organization_id, actor_id=user.id)


ProgramServiceDep = Annotated[ProgramService, Depends(get_program_service)]


def get_project_service(user: CurrentUser, uow: UowDep) -> ProjectService:
    """Construct a :class:`ProjectService` scoped to the caller's tenant."""
    return ProjectService(uow, organization_id=user.organization_id, actor_id=user.id)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


def get_task_service(user: CurrentUser, uow: UowDep) -> TaskService:
    """Construct a :class:`TaskService` scoped to the caller's tenant."""
    return TaskService(uow, organization_id=user.organization_id, actor_id=user.id)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


def get_sprint_service(user: CurrentUser, uow: UowDep) -> SprintService:
    """Construct a :class:`SprintService` scoped to the caller's tenant."""
    return SprintService(uow, organization_id=user.organization_id, actor_id=user.id)


SprintServiceDep = Annotated[SprintService, Depends(get_sprint_service)]


def get_resource_service(user: CurrentUser, uow: UowDep) -> ResourceService:
    """Construct a :class:`ResourceService` scoped to the caller's tenant."""
    return ResourceService(uow, organization_id=user.organization_id, actor_id=user.id)


ResourceServiceDep = Annotated[ResourceService, Depends(get_resource_service)]


def get_finance_service(user: CurrentUser, uow: UowDep) -> FinanceService:
    """Construct a :class:`FinanceService` scoped to the caller's tenant."""
    return FinanceService(uow, organization_id=user.organization_id, actor_id=user.id)


FinanceServiceDep = Annotated[FinanceService, Depends(get_finance_service)]


def get_risk_service(user: CurrentUser, uow: UowDep) -> RiskService:
    """Construct a :class:`RiskService` scoped to the caller's tenant."""
    return RiskService(uow, organization_id=user.organization_id, actor_id=user.id)


RiskServiceDep = Annotated[RiskService, Depends(get_risk_service)]


def get_issue_service(user: CurrentUser, uow: UowDep) -> IssueService:
    """Construct an :class:`IssueService` scoped to the caller's tenant."""
    return IssueService(uow, organization_id=user.organization_id, actor_id=user.id)


IssueServiceDep = Annotated[IssueService, Depends(get_issue_service)]


def get_raid_service(user: CurrentUser, uow: UowDep) -> RaidService:
    """Construct a :class:`RaidService` scoped to the caller's tenant."""
    return RaidService(uow, organization_id=user.organization_id, actor_id=user.id)


RaidServiceDep = Annotated[RaidService, Depends(get_raid_service)]


def get_change_service(user: CurrentUser, uow: UowDep) -> ChangeRequestService:
    """Construct a :class:`ChangeRequestService` scoped to the caller's tenant."""
    return ChangeRequestService(uow, organization_id=user.organization_id, actor_id=user.id)


ChangeServiceDep = Annotated[ChangeRequestService, Depends(get_change_service)]


def get_dependency_service(user: CurrentUser, uow: UowDep) -> DependencyService:
    """Construct a :class:`DependencyService` scoped to the caller's tenant."""
    return DependencyService(uow, organization_id=user.organization_id, actor_id=user.id)


DependencyServiceDep = Annotated[DependencyService, Depends(get_dependency_service)]


def get_milestone_service(user: CurrentUser, uow: UowDep) -> MilestoneService:
    """Construct a :class:`MilestoneService` scoped to the caller's tenant."""
    return MilestoneService(uow, organization_id=user.organization_id, actor_id=user.id)


MilestoneServiceDep = Annotated[MilestoneService, Depends(get_milestone_service)]


def get_project_kpi_service(user: CurrentUser, uow: UowDep) -> ProjectKPIService:
    """Construct a :class:`ProjectKPIService` scoped to the caller's tenant."""
    return ProjectKPIService(uow, organization_id=user.organization_id, actor_id=user.id)


ProjectKPIServiceDep = Annotated[ProjectKPIService, Depends(get_project_kpi_service)]


def get_timesheet_service(user: CurrentUser, uow: UowDep) -> TimesheetService:
    """Construct a :class:`TimesheetService` scoped to the caller's tenant."""
    return TimesheetService(uow, organization_id=user.organization_id, actor_id=user.id)


TimesheetServiceDep = Annotated[TimesheetService, Depends(get_timesheet_service)]


def get_meeting_service(user: CurrentUser, uow: UowDep) -> MeetingService:
    """Construct a :class:`MeetingService` scoped to the caller's tenant."""
    return MeetingService(uow, organization_id=user.organization_id, actor_id=user.id)


MeetingServiceDep = Annotated[MeetingService, Depends(get_meeting_service)]


def get_notification_service(user: CurrentUser, uow: UowDep) -> NotificationService:
    """Construct a :class:`NotificationService` scoped to the caller's tenant."""
    return NotificationService(uow, organization_id=user.organization_id, actor_id=user.id)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


def get_report_service(user: CurrentUser, uow: UowDep) -> ReportService:
    """Construct a :class:`ReportService` scoped to the caller's tenant."""
    return ReportService(uow, organization_id=user.organization_id, actor_id=user.id)


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


def get_dashboard_service(user: CurrentUser, uow: UowDep) -> DashboardService:
    """Construct a :class:`DashboardService` scoped to the caller's tenant."""
    return DashboardService(uow, organization_id=user.organization_id, actor_id=user.id)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


def get_copilot_service(user: CurrentUser, uow: UowDep) -> CopilotService:
    """Construct a :class:`CopilotService` scoped to the caller's tenant."""
    return CopilotService(uow, organization_id=user.organization_id, actor_id=user.id)


CopilotServiceDep = Annotated[CopilotService, Depends(get_copilot_service)]


def get_admin_service(user: CurrentUser, uow: UowDep, settings: SettingsDep) -> AdminService:
    """Construct an :class:`AdminService` scoped to the caller's tenant."""
    return AdminService(
        uow,
        organization_id=user.organization_id,
        actor_id=user.id,
        app_name=settings.app_name,
        app_env=settings.app_env,
    )


AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


def get_intelligence_service(user: CurrentUser, uow: UowDep) -> IntelligenceService:
    """Construct an :class:`IntelligenceService` scoped to the caller's tenant."""
    return IntelligenceService(uow, organization_id=user.organization_id, actor_id=user.id)


IntelligenceServiceDep = Annotated[IntelligenceService, Depends(get_intelligence_service)]


def get_benefit_service(user: CurrentUser, uow: UowDep) -> BenefitService:
    """Construct a :class:`BenefitService` scoped to the caller's tenant."""
    return BenefitService(uow, organization_id=user.organization_id, actor_id=user.id)


BenefitServiceDep = Annotated[BenefitService, Depends(get_benefit_service)]


def get_skill_service(user: CurrentUser, uow: UowDep) -> SkillService:
    """Construct a :class:`SkillService` scoped to the caller's tenant."""
    return SkillService(uow, organization_id=user.organization_id, actor_id=user.id)


SkillServiceDep = Annotated[SkillService, Depends(get_skill_service)]


def get_initiative_service(user: CurrentUser, uow: UowDep) -> InitiativeService:
    """Construct an :class:`InitiativeService` scoped to the caller's tenant."""
    return InitiativeService(uow, organization_id=user.organization_id, actor_id=user.id)


InitiativeServiceDep = Annotated[InitiativeService, Depends(get_initiative_service)]


def get_workflow_service(user: CurrentUser, uow: UowDep) -> WorkflowService:
    """Construct a :class:`WorkflowService` scoped to the caller's tenant."""
    return WorkflowService(uow, organization_id=user.organization_id, actor_id=user.id)


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]


def get_vendor_service(user: CurrentUser, uow: UowDep) -> VendorService:
    """Construct a :class:`VendorService` scoped to the caller's tenant."""
    return VendorService(uow, organization_id=user.organization_id, actor_id=user.id)


VendorServiceDep = Annotated[VendorService, Depends(get_vendor_service)]


def get_integration_service(user: CurrentUser, uow: UowDep) -> IntegrationService:
    """Construct an :class:`IntegrationService` scoped to the caller's tenant."""
    return IntegrationService(uow, organization_id=user.organization_id, actor_id=user.id)


IntegrationServiceDep = Annotated[IntegrationService, Depends(get_integration_service)]


def get_apikey_service(user: CurrentUser, uow: UowDep) -> ApiKeyService:
    """Construct an :class:`ApiKeyService` scoped to the caller's tenant."""
    return ApiKeyService(uow, organization_id=user.organization_id, actor_id=user.id)


ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_apikey_service)]


def get_aidelivery_service(user: CurrentUser, uow: UowDep) -> AiDeliveryService:
    """Construct an :class:`AiDeliveryService` scoped to the caller's tenant."""
    return AiDeliveryService(uow, organization_id=user.organization_id, actor_id=user.id)


AiDeliveryServiceDep = Annotated[AiDeliveryService, Depends(get_aidelivery_service)]


def get_sso_service(user: CurrentUser, uow: UowDep, settings: SettingsDep) -> SsoService:
    """Construct an :class:`SsoService` scoped to the caller's tenant (config admin)."""
    return SsoService(uow, settings, organization_id=user.organization_id, actor_id=user.id)


SsoServiceDep = Annotated[SsoService, Depends(get_sso_service)]


def get_jira_service(user: CurrentUser, uow: UowDep) -> JiraService:
    """Construct a :class:`JiraService` scoped to the caller's tenant."""
    return JiraService(uow, organization_id=user.organization_id, actor_id=user.id)


JiraServiceDep = Annotated[JiraService, Depends(get_jira_service)]


def get_metrics_service(user: CurrentUser, uow: UowDep) -> MetricsService:
    """Construct a :class:`MetricsService` scoped to the caller's tenant."""
    return MetricsService(uow, organization_id=user.organization_id, actor_id=user.id)


MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]


def get_document_service(user: CurrentUser, uow: UowDep) -> DocumentService:
    """Construct a :class:`DocumentService` scoped to the caller's tenant."""
    return DocumentService(uow, organization_id=user.organization_id, actor_id=user.id)


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
