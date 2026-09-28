"""Repositories for the AI Copilot module (conversations are user-scoped)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.copilot.models import Conversation, Message
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Data access for :class:`Conversation` (owner-scoped)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Conversation)

    def get_for_user(
        self, conversation_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        """Return a conversation only if it belongs to the given user."""
        stmt = self._base_query(organization_id).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def search(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Conversation]:
        """Return a page of the user's conversations (newest first)."""
        stmt = (
            self._base_query(organization_id)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def count(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """Return the number of the user's conversations."""
        stmt = select(func.count()).where(
            Conversation.organization_id == organization_id,
            Conversation.user_id == user_id,
            Conversation.is_deleted.is_(False),
        )
        return int(self.session.execute(stmt).scalar_one())


class MessageRepository(BaseRepository[Message]):
    """Data access for :class:`Message`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Message)

    def list_for_conversation(
        self, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Sequence[Message]:
        """Return a conversation's messages in chronological order."""
        stmt = (
            self._base_query(organization_id)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_date.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def soft_delete_for_conversation(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
    ) -> int:
        """Soft-delete every message of a conversation."""
        stmt = self._base_query(organization_id).where(Message.conversation_id == conversation_id)
        rows = list(self.session.execute(stmt).scalars().all())
        for message in rows:
            message.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
