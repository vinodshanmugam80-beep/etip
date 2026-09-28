"""Repository for the Document Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.document.models import Document, DocumentOwnerType
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Data access for :class:`Document`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Document)

    def get_by_storage_key(self, organization_id: uuid.UUID, storage_key: str) -> Document | None:
        """Return a document by its storage key, if any."""
        stmt = self._base_query(organization_id).where(Document.storage_key == storage_key)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_lineage(self, organization_id: uuid.UUID, lineage_id: uuid.UUID) -> Sequence[Document]:
        """Return every live revision in a lineage, newest revision first."""
        stmt = (
            self._base_query(organization_id)
            .where(Document.lineage_id == lineage_id)
            .order_by(Document.revision.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def highest_remaining(
        self,
        organization_id: uuid.UUID,
        lineage_id: uuid.UUID,
        *,
        exclude_id: uuid.UUID,
    ) -> Document | None:
        """Return the top live revision in a lineage, excluding one document."""
        stmt = (
            self._base_query(organization_id)
            .where(
                Document.lineage_id == lineage_id,
                Document.id != exclude_id,
            )
            .order_by(Document.revision.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        owner_type: DocumentOwnerType | None,
        owner_id: uuid.UUID | None,
        content_type: str | None,
        is_current: bool | None,
    ) -> Select[tuple[Document]]:
        """Build the filtered (unpaginated) document query."""
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(func.lower(Document.name).like(f"%{query.lower()}%"))
        if owner_type is not None:
            stmt = stmt.where(Document.owner_type == owner_type)
        if owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)
        if content_type is not None:
            stmt = stmt.where(Document.content_type == content_type)
        if is_current is not None:
            stmt = stmt.where(Document.is_current.is_(is_current))
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        owner_type: DocumentOwnerType | None = None,
        owner_id: uuid.UUID | None = None,
        content_type: str | None = None,
        is_current: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Document]:
        """Return a filtered, paginated page of documents (newest first)."""
        stmt = self._search_stmt(
            organization_id,
            query=query,
            owner_type=owner_type,
            owner_id=owner_id,
            content_type=content_type,
            is_current=is_current,
        )
        stmt = stmt.order_by(Document.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        owner_type: DocumentOwnerType | None = None,
        owner_id: uuid.UUID | None = None,
        content_type: str | None = None,
        is_current: bool | None = None,
    ) -> int:
        """Return the number of documents matching the filters."""
        inner = self._search_stmt(
            organization_id,
            query=query,
            owner_type=owner_type,
            owner_id=owner_id,
            content_type=content_type,
            is_current=is_current,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def soft_delete_for_owners(
        self,
        organization_id: uuid.UUID,
        owner_type: DocumentOwnerType,
        owner_ids: Sequence[uuid.UUID],
        *,
        actor_id: uuid.UUID,
    ) -> int:
        """Soft-delete every live document attached to the given owners."""
        if not owner_ids:
            return 0
        stmt = self._base_query(organization_id).where(
            Document.owner_type == owner_type,
            Document.owner_id.in_(list(owner_ids)),
        )
        rows = list(self.session.execute(stmt).scalars().all())
        for doc in rows:
            doc.soft_delete(actor_id)
        self.session.flush()
        return len(rows)
