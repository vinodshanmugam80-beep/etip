"""ORM model for the Reports module.

A :class:`ReportDefinition` is a saved, re-runnable report configuration: a
report type plus JSON parameters (e.g. a project or portfolio id and a date
window). Definitions are owned by their creator and may be shared with the rest
of the organization. Running a report assembles a fresh result from the current
data across other modules (see the service); nothing is precomputed here.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class ReportType(enum.StrEnum):
    """The kind of report, which determines how the result is assembled."""

    PROJECT_STATUS = "project_status"
    RAID_SUMMARY = "raid_summary"
    TIMESHEET_HOURS = "timesheet_hours"
    MILESTONE_STATUS = "milestone_status"
    FINANCIAL_SUMMARY = "financial_summary"
    PORTFOLIO_OVERVIEW = "portfolio_overview"


class ReportDefinition(BaseEntity, TenantMixin):
    """A saved report configuration owned by its creator."""

    __tablename__ = "report_definitions"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="")
    report_type: Mapped[ReportType] = mapped_column(
        enum_column(ReportType), nullable=False, index=True
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_run_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
