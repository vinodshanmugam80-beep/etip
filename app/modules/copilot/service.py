"""AI Copilot service.

Manages private, per-user conversations and answers questions through the
:class:`CopilotEngine`. Asking within a conversation persists the user question
and the assistant's grounded answer as messages; an ad-hoc ask answers without
persisting. Every conversation and message is scoped to the calling user.

Framework-agnostic apart from returning result schemas; raises domain exceptions
from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.copilot.engine import CopilotEngine
from app.modules.copilot.models import Conversation, Message, MessageRole
from app.modules.copilot.repository import (
    ConversationRepository,
    MessageRepository,
)
from app.modules.copilot.schemas import AnswerResult

logger = get_logger(__name__)

_DEFAULT_TITLE = "New conversation"


class CopilotService:
    """Coordinates copilot conversations and question answering within a tenant."""

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
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self._engine = CopilotEngine(session, organization_id)

    # ------------------------------------------------------------------
    # Conversations (own only)
    # ------------------------------------------------------------------
    def _get_own_or_404(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = self.conversations.get_for_user(
            conversation_id, self._org_id, self._actor_id
        )
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    def create_conversation(self, *, title: str) -> Conversation:
        """Start a new conversation owned by the caller."""
        conversation = Conversation(
            organization_id=self._org_id,
            user_id=self._actor_id,
            title=title,
            created_by=self._actor_id,
        )
        self.conversations.add(conversation)
        return conversation

    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        """Return one of the caller's own conversations."""
        return self._get_own_or_404(conversation_id)

    def search_conversations(self, *, limit: int, offset: int) -> tuple[list[Conversation], int]:
        """Return a page of the caller's conversations and the total."""
        items = list(
            self.conversations.search(self._org_id, self._actor_id, limit=limit, offset=offset)
        )
        total = self.conversations.count(self._org_id, self._actor_id)
        return items, total

    def delete_conversation(self, conversation_id: uuid.UUID) -> None:
        """Soft-delete one of the caller's conversations and its messages."""
        conversation = self._get_own_or_404(conversation_id)
        self.messages.soft_delete_for_conversation(
            self._org_id, conversation_id, actor_id=self._actor_id
        )
        self.conversations.soft_delete(conversation, actor_id=self._actor_id)

    def list_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        """Return the messages of one of the caller's conversations."""
        self._get_own_or_404(conversation_id)
        return list(self.messages.list_for_conversation(self._org_id, conversation_id))

    # ------------------------------------------------------------------
    # Asking
    # ------------------------------------------------------------------
    def ask_in_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        question: str,
        context: dict[str, Any],
    ) -> tuple[Conversation, Message, AnswerResult]:
        """Answer a question in a conversation, persisting both turns."""
        conversation = self._get_own_or_404(conversation_id)

        user_message = Message(
            organization_id=self._org_id,
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question,
            created_by=self._actor_id,
        )
        self.messages.add(user_message)

        result = self._engine.answer(question, context)

        assistant_message = Message(
            organization_id=self._org_id,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=result.answer,
            intent=result.intent,
            grounding=result.grounding,
            created_by=self._actor_id,
        )
        self.messages.add(assistant_message)

        # Auto-title an untouched conversation from its first question.
        if conversation.title == _DEFAULT_TITLE:
            conversation.title = question[:120]
            self.conversations.update(conversation)

        self._uow.record_audit(
            "CopilotMessage",
            assistant_message.id,
            "create",
            f"Answered ({result.intent.value})",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return conversation, assistant_message, result

    def ask_adhoc(self, *, question: str, context: dict[str, Any]) -> AnswerResult:
        """Answer a question without persisting anything."""
        return self._engine.answer(question, context)
