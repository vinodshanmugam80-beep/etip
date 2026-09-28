"""ORM models for the Dashboards module.

A :class:`Dashboard` is a user-configurable, owned (optionally shared) layout of
widgets. A :class:`DashboardWidget` is one tile on that layout: a REPORT widget
is backed by a report type and parameters (rendered live through the report
engine), while a TEXT widget carries static content. Rendering a dashboard runs
every REPORT widget and embeds its result, so a dashboard is a saved,
live-rendered view of report results.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column
from app.modules.report.models import ReportType


class WidgetType(enum.StrEnum):
    """The kind of dashboard widget."""

    REPORT = "report"
    TEXT = "text"


class Dashboard(BaseEntity, TenantMixin):
    """A user-configurable layout of widgets, owned by its creator."""

    __tablename__ = "dashboards"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="")
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DashboardWidget(BaseEntity, TenantMixin):
    """A single tile on a dashboard."""

    __tablename__ = "dashboard_widgets"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    widget_type: Mapped[WidgetType] = mapped_column(enum_column(WidgetType), nullable=False)

    # REPORT widgets: what to render.
    report_type: Mapped[ReportType | None] = mapped_column(enum_column(ReportType), nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # TEXT widgets: static content.
    content: Mapped[str] = mapped_column(String(8000), default="")

    position: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=6)
