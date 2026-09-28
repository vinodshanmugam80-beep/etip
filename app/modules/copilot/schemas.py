"""Pydantic v2 schemas for the AI Copilot module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.copilot.models import CopilotIntent, MessageRole


class ConversationCreateRequest(BaseModel):
    """Payload to start a conversation."""

    title: str = Field(default="New conversation", min_length=2, max_length=300)


class ConversationResponse(BaseModel):
    """Conversation representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_date: datetime
    version: int


class PaginatedConversations(BaseModel):
    """A page of conversations with total-count metadata."""

    items: list[ConversationResponse]
    total: int
    limit: int
    offset: int


class AskRequest(BaseModel):
    """A natural-language question, with optional structured context."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "How is ATLAS doing?",
                "context": {"project_code": "ATLAS"},
            }
        }
    )

    question: str = Field(min_length=2, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


class AnswerResult(BaseModel):
    """A grounded answer: the resolved intent, the reply, and its provenance."""

    intent: CopilotIntent
    answer: str
    grounding: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """A single conversation message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    intent: CopilotIntent | None
    grounding: dict[str, Any]
    created_date: datetime


class AskResponse(BaseModel):
    """The result of asking within a conversation."""

    conversation_id: uuid.UUID
    question: str
    intent: CopilotIntent
    answer: str
    grounding: dict[str, Any]
    assistant_message_id: uuid.UUID


class GenericMessage(BaseModel):
    """Generic success envelope."""

    detail: str
