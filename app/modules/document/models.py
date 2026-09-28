"""ORM model for the Document Management module.

A :class:`Document` is an attachment **metadata** record — the actual bytes are
expected to live in object storage, referenced by ``storage_key``. Documents are
polymorphic: they attach to any supported entity (project, task, risk, …) via an
``owner_type`` discriminator plus an ``owner_id`` UUID (validated in the service,
no database foreign key). Versioning is modelled by grouping revisions under a
shared ``lineage_id``; exactly one revision in a lineage is the ``is_current``
one, and ``supersedes_id`` points at the immediate predecessor.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class DocumentOwnerType(enum.StrEnum):
    """The kind of entity a document is attached to."""

    PROJECT = "project"
    TASK = "task"
    RISK = "risk"
    ISSUE = "issue"
    CHANGE_REQUEST = "change_request"
    MILESTONE = "milestone"


class Document(BaseEntity, TenantMixin):
    """Attachment metadata for a file stored in object storage."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "storage_key", name="uq_document_storage_key"),
    )

    owner_type: Mapped[DocumentOwnerType] = mapped_column(
        enum_column(DocumentOwnerType), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="")
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[str] = mapped_column(String(128), default="")

    # Versioning.
    lineage_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
