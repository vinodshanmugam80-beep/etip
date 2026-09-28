"""Version 1 API router.

Aggregates the routers of every module behind the ``/api/v1`` prefix. As new
modules are delivered, their routers are included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.aidelivery.router import router as aidelivery_router
from app.modules.apikey.router import router as apikey_router
from app.modules.auth.router import router as auth_router
from app.modules.benefit.router import router as benefit_router
from app.modules.change.router import router as change_router
from app.modules.copilot.router import router as copilot_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dependency.router import router as dependency_router
from app.modules.document.router import router as document_router
from app.modules.export.router import router as export_router
from app.modules.finance.router import router as finance_router
from app.modules.initiative.router import router as initiative_router
from app.modules.integration.router import router as integration_router
from app.modules.intelligence.router import router as intelligence_router
from app.modules.issue.router import router as issue_router
from app.modules.jira.router import router as jira_router
from app.modules.meeting.router import router as meeting_router
from app.modules.metrics.router import router as metrics_router
from app.modules.milestone.router import router as milestone_router
from app.modules.notification.router import router as notification_router
from app.modules.organization.router import router as organization_router
from app.modules.portfolio.router import router as portfolio_router
from app.modules.program.router import router as program_router
from app.modules.project.router import router as project_router
from app.modules.projectkpi.router import router as projectkpi_router
from app.modules.raid.router import router as raid_router
from app.modules.rbac.router import router as rbac_router
from app.modules.report.router import router as report_router
from app.modules.resource.router import router as resource_router
from app.modules.risk.router import router as risk_router
from app.modules.skill.router import router as skill_router
from app.modules.sprint.router import router as sprint_router
from app.modules.sso.router import router as sso_router
from app.modules.task.router import router as task_router
from app.modules.timesheet.router import router as timesheet_router
from app.modules.user.router import router as user_router
from app.modules.vendor.router import router as vendor_router
from app.modules.workflow.router import router as workflow_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(organization_router)
api_router.include_router(user_router)
api_router.include_router(rbac_router)
api_router.include_router(portfolio_router)
api_router.include_router(program_router)
api_router.include_router(project_router)
api_router.include_router(task_router)
api_router.include_router(sprint_router)
api_router.include_router(resource_router)
api_router.include_router(finance_router)
api_router.include_router(risk_router)
api_router.include_router(issue_router)
api_router.include_router(raid_router)
api_router.include_router(change_router)
api_router.include_router(dependency_router)
api_router.include_router(milestone_router)
api_router.include_router(projectkpi_router)
api_router.include_router(timesheet_router)
api_router.include_router(meeting_router)
api_router.include_router(notification_router)
api_router.include_router(report_router)
api_router.include_router(dashboard_router)
api_router.include_router(copilot_router)
api_router.include_router(admin_router)
api_router.include_router(intelligence_router)
api_router.include_router(benefit_router)
api_router.include_router(skill_router)
api_router.include_router(initiative_router)
api_router.include_router(workflow_router)
api_router.include_router(vendor_router)
api_router.include_router(export_router)
api_router.include_router(integration_router)
api_router.include_router(apikey_router)
api_router.include_router(aidelivery_router)
api_router.include_router(sso_router)
api_router.include_router(jira_router)
api_router.include_router(metrics_router)
api_router.include_router(document_router)
