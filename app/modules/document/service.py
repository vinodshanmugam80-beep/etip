"""Document Management service.

Business rules for attachment metadata. A document attaches to any supported
entity (validated against that entity's repository — no database foreign key,
since the owner is polymorphic). Revisions of the same logical document share a
``lineage_id``; adding a version supersedes the current revision, and deleting
the current revision promotes the next-highest one. Actual file bytes live in
object storage; this module manages only metadata keyed by ``storage_key``.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.change.repository import ChangeRequestRepository
from app.modules.document.models import Document, DocumentOwnerType
from app.modules.document.repository import DocumentRepository
from app.modules.issue.repository import IssueRepository
from app.modules.milestone.repository import MilestoneRepository
from app.modules.project.repository import ProjectRepository
from app.modules.risk.repository import RiskRepository
from app.modules.task.repository import TaskRepository
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class DocumentService:
    """Coordinates document metadata use cases within a tenant."""

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
        self.documents = DocumentRepository(session)
        # Owner-type dispatch for existence validation.
        self._owner_repos: dict[DocumentOwnerType, BaseRepository[Any]] = {
            DocumentOwnerType.PROJECT: ProjectRepository(session),
            DocumentOwnerType.TASK: TaskRepository(session),
            DocumentOwnerType.RISK: RiskRepository(session),
            DocumentOwnerType.ISSUE: IssueRepository(session),
            DocumentOwnerType.CHANGE_REQUEST: ChangeRequestRepository(session),
            DocumentOwnerType.MILESTONE: MilestoneRepository(session),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_or_404(self, document_id: uuid.UUID) -> Document:
        document = self.documents.get(document_id, organization_id=self._org_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    def _require_owner(self, owner_type: DocumentOwnerType, owner_id: uuid.UUID) -> None:
        repo = self._owner_repos[owner_type]
        if repo.get(owner_id, organization_id=self._org_id) is None:
            raise NotFoundError(f"Owner {owner_type.value} not found.")

    def _require_unique_key(self, storage_key: str) -> None:
        if self.documents.get_by_storage_key(self._org_id, storage_key):
            raise ConflictError(
                "A document with this storage key already exists.",
                code="duplicate_storage_key",
            )

    # ------------------------------------------------------------------
    # Create / version
    # ------------------------------------------------------------------
    def create_document(
        self,
        *,
        owner_type: DocumentOwnerType,
        owner_id: uuid.UUID,
        name: str,
        description: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        checksum: str,
    ) -> Document:
        """Register the first revision of a document against an owner."""
        self._require_owner(owner_type, owner_id)
        self._require_unique_key(storage_key)
        document = Document(
            organization_id=self._org_id,
            owner_type=owner_type,
            owner_id=owner_id,
            uploaded_by_user_id=self._actor_id,
            name=name,
            description=description,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
            lineage_id=uuid.uuid4(),
            revision=1,
            is_current=True,
            created_by=self._actor_id,
        )
        self.documents.add(document)
        self._uow.record_audit(
            "Document",
            document.id,
            "create",
            f"Uploaded document '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return document

    def add_version(
        self,
        document_id: uuid.UUID,
        *,
        name: str | None,
        description: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        checksum: str,
    ) -> Document:
        """Add a new revision to a document's lineage and make it current."""
        base = self._get_or_404(document_id)
        self._require_unique_key(storage_key)
        lineage = list(self.documents.list_lineage(self._org_id, base.lineage_id))
        top_revision = max(doc.revision for doc in lineage)
        for doc in lineage:
            if doc.is_current:
                doc.is_current = False
                doc.modified_by = self._actor_id
                self.documents.update(doc)
        new_doc = Document(
            organization_id=self._org_id,
            owner_type=base.owner_type,
            owner_id=base.owner_id,
            uploaded_by_user_id=self._actor_id,
            name=name if name is not None else base.name,
            description=description,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
            lineage_id=base.lineage_id,
            revision=top_revision + 1,
            is_current=True,
            supersedes_id=base.id,
            created_by=self._actor_id,
        )
        self.documents.add(new_doc)
        self._uow.record_audit(
            "Document",
            new_doc.id,
            "version",
            f"Added revision {new_doc.revision} of '{new_doc.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return new_doc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_document(self, document_id: uuid.UUID) -> Document:
        """Return a single document by id."""
        return self._get_or_404(document_id)

    def get_versions(self, document_id: uuid.UUID) -> list[Document]:
        """Return every revision in a document's lineage (newest first)."""
        document = self._get_or_404(document_id)
        return list(self.documents.list_lineage(self._org_id, document.lineage_id))

    def search_documents(
        self,
        *,
        query: str | None,
        owner_type: DocumentOwnerType | None,
        owner_id: uuid.UUID | None,
        content_type: str | None,
        is_current: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        """Return a filtered page of documents and the total matching count."""
        items = list(
            self.documents.search(
                self._org_id,
                query=query,
                owner_type=owner_type,
                owner_id=owner_id,
                content_type=content_type,
                is_current=is_current,
                limit=limit,
                offset=offset,
            )
        )
        total = self.documents.count(
            self._org_id,
            query=query,
            owner_type=owner_type,
            owner_id=owner_id,
            content_type=content_type,
            is_current=is_current,
        )
        return items, total

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------
    def update_document(
        self,
        document_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
    ) -> Document:
        """Update a document's name or description."""
        document = self._get_or_404(document_id)
        if name is not None:
            document.name = name
        if description is not None:
            document.description = description
        document.modified_by = self._actor_id
        self.documents.update(document)
        self._uow.record_audit(
            "Document",
            document.id,
            "update",
            f"Updated document '{document.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return document

    def delete_document(self, document_id: uuid.UUID) -> None:
        """Soft-delete a document, promoting the next revision if it was current."""
        document = self._get_or_404(document_id)
        was_current = document.is_current
        lineage_id = document.lineage_id
        self.documents.soft_delete(document, actor_id=self._actor_id)
        if was_current:
            successor = self.documents.highest_remaining(
                self._org_id, lineage_id, exclude_id=document.id
            )
            if successor is not None:
                successor.is_current = True
                successor.modified_by = self._actor_id
                self.documents.update(successor)
        self._uow.record_audit(
            "Document",
            document.id,
            "delete",
            f"Deleted document '{document.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    def documents_for_owners(
        self, owner_type: DocumentOwnerType, owner_ids: Sequence[uuid.UUID]
    ) -> int:
        """Soft-delete documents attached to the given owners."""
        return self.documents.soft_delete_for_owners(
            self._org_id, owner_type, owner_ids, actor_id=self._actor_id
        )
