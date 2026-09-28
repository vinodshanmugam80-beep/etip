"""Pydantic v2 schemas for the Document Management module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.document.models import DocumentOwnerType


class DocumentCreateRequest(BaseModel):
    """Payload to register the first revision of a document."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "owner_type": "project",
                "owner_id": "00000000-0000-0000-0000-000000000000",
                "name": "Statement of Work.pdf",
                "description": "Signed SOW",
                "storage_key": "org/proj/sow-v1.pdf",
                "content_type": "application/pdf",
                "size_bytes": 248193,
                "checksum": "",
            }
        }
    )

    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)
    storage_key: str = Field(min_length=1, max_length=1024)
    content_type: str = Field(default="", max_length=255)
    size_bytes: int = Field(default=0, ge=0)
    checksum: str = Field(default="", max_length=128)

    @field_validator("name", "storage_key")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be blank.")
        return cleaned


class DocumentVersionRequest(BaseModel):
    """Payload to add a new revision to an existing document lineage."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Statement of Work.pdf",
                "description": "Countersigned SOW",
                "storage_key": "org/proj/sow-v2.pdf",
                "content_type": "application/pdf",
                "size_bytes": 251020,
                "checksum": "",
            }
        }
    )

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)
    storage_key: str = Field(min_length=1, max_length=1024)
    content_type: str = Field(default="", max_length=255)
    size_bytes: int = Field(default=0, ge=0)
    checksum: str = Field(default="", max_length=128)


class DocumentUpdateRequest(BaseModel):
    """Partial update of document metadata (name/description only)."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)


class DocumentResponse(BaseModel):
    """Document representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    owner_type: DocumentOwnerType
    owner_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None
    name: str
    description: str
    storage_key: str
    content_type: str
    size_bytes: int
    checksum: str
    lineage_id: uuid.UUID
    revision: int
    is_current: bool
    supersedes_id: uuid.UUID | None
    created_date: datetime
    version: int


class PaginatedDocuments(BaseModel):
    """A page of documents with total-count metadata."""

    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Generic success envelope."""

    detail: str
