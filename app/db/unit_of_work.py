"""Unit of Work.

The Unit of Work owns a single database session and its transaction boundary.
Services receive a :class:`UnitOfWork`, access repositories through it, and the
whole operation commits or rolls back atomically. Audit-log rows are collected
during the transaction and flushed as part of the same commit.
"""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Any, Self

from sqlalchemy.orm import Session, sessionmaker

from app.db.base import AuditLog, OutboxEvent


class UnitOfWork:
    """Transactional scope wrapping a single SQLAlchemy session.

    Usage::

        with UnitOfWork(session_factory) as uow:
            user = uow.users.add(user)
            uow.record_audit("User", user.id, "create", "registered")
            uow.commit()

    Repositories are attached lazily by the service layer or eagerly by
    subclasses; the base implementation exposes the raw :attr:`session` plus
    :meth:`record_audit` for audit trailing.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session
        self._pending_audit: list[AuditLog] = []
        self._pending_events: list[OutboxEvent] = []

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        self._pending_audit = []
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                self.rollback()
        finally:
            self.session.close()

    def record_audit(
        self,
        entity_type: str,
        entity_id: uuid.UUID | None,
        action: str,
        summary: str = "",
        *,
        actor_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> None:
        """Queue an audit-log entry to be persisted on :meth:`commit`."""
        self._pending_audit.append(
            AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                summary=summary,
                actor_id=actor_id,
                organization_id=organization_id,
            )
        )

    def add_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        organization_id: uuid.UUID,
    ) -> None:
        """Queue a domain event for the transactional outbox (persisted on commit)."""
        self._pending_events.append(
            OutboxEvent(
                organization_id=organization_id,
                event_type=event_type,
                payload=payload,
                status="pending",
            )
        )

    def commit(self) -> None:
        """Persist queued audit rows and commit the transaction."""
        if self._pending_audit:
            self.session.add_all(self._pending_audit)
            self._pending_audit = []
        if self._pending_events:
            self.session.add_all(self._pending_events)
            self._pending_events = []
        self.session.commit()

    def rollback(self) -> None:
        """Discard all changes made within the transaction."""
        self._pending_audit = []
        self.session.rollback()

    def flush(self) -> None:
        """Flush pending changes to obtain generated identifiers."""
        self.session.flush()
