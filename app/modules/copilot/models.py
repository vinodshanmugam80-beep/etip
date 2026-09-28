"""ORM models for the AI Copilot module.

A :class:`Conversation` is a private, per-user chat session with the assistant.
A :class:`Message` is one turn — a user question or an assistant answer. Assistant
messages carry the resolved ``intent`` and a ``grounding`` payload: the exact
structured data (and its provenance) the answer was composed from, so every
answer is traceable to real platform data rather than free-form generation.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class MessageRole(enum.StrEnum):
    """Who authored a message."""

    USER = "user"
    ASSISTANT = "assistant"


class CopilotIntent(enum.StrEnum):
    """The resolved intent of a question / the kind of answer produced."""

    PROJECT_STATUS = "project_status"
    RAID_SUMMARY = "raid_summary"
    MILESTONE_STATUS = "milestone_status"
    TIMESHEET_HOURS = "timesheet_hours"
    FINANCIAL_SUMMARY = "financial_summary"
    PORTFOLIO_OVERVIEW = "portfolio_overview"
    HELP = "help"
    NEEDS_PROJECT = "needs_project"
    NEEDS_PORTFOLIO = "needs_portfolio"
    UNKNOWN = "unknown"


class Conversation(BaseEntity, TenantMixin):
    """A private copilot chat session owned by a single user."""

    __tablename__ = "copilot_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), default="New conversation")


class Message(BaseEntity, TenantMixin):
    """A single turn in a copilot conversation."""

    __tablename__ = "copilot_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("copilot_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(enum_column(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(String(8000), default="")
    intent: Mapped[CopilotIntent | None] = mapped_column(enum_column(CopilotIntent), nullable=True)
    grounding: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
