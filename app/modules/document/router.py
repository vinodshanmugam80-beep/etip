"""HTTP routes for the Document Management module.

Thin adapters over :class:`DocumentService`. Reads require ``document:read``;
create and versioning require ``document:create``; metadata edits require
``document:update``; delete requires ``document:delete``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import DocumentServiceDep, UowDep, require_permission
from app.modules.document.models import DocumentOwnerType
from app.modules.document.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentUpdateRequest,
    DocumentVersionRequest,
    MessageResponse,
    PaginatedDocuments,
)

router = APIRouter(tags=["Document Management"])


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("document:create"))],
    summary="Register a document",
)
def create_document(
    payload: DocumentCreateRequest, service: DocumentServiceDep, uow: UowDep
) -> DocumentResponse:
    """Register the first revision of a document against an owner entity."""
    document = service.create_document(
        owner_type=payload.owner_type,
        owner_id=payload.owner_id,
        name=payload.name,
        description=payload.description,
        storage_key=payload.storage_key,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        checksum=payload.checksum,
    )
    uow.commit()
    return DocumentResponse.model_validate(document)


@router.get(
    "/documents",
    response_model=PaginatedDocuments,
    dependencies=[Depends(require_permission("document:read"))],
    summary="List and search documents",
)
def list_documents(
    service: DocumentServiceDep,
    q: str | None = Query(default=None, description="Search name"),
    owner_type: DocumentOwnerType | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(default=None),
    content_type: str | None = Query(default=None),
    is_current: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedDocuments:
    """Return a filtered, paginated page of documents (newest first)."""
    items, total = service.search_documents(
        query=q,
        owner_type=owner_type,
        owner_id=owner_id,
        content_type=content_type,
        is_current=is_current,
        limit=limit,
        offset=offset,
    )
    return PaginatedDocuments(
        items=[DocumentResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    dependencies=[Depends(require_permission("document:read"))],
    summary="Get a document",
)
def get_document(document_id: uuid.UUID, service: DocumentServiceDep) -> DocumentResponse:
    """Return a single document by id."""
    return DocumentResponse.model_validate(service.get_document(document_id))


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[DocumentResponse],
    dependencies=[Depends(require_permission("document:read"))],
    summary="List a document's revisions",
)
def get_versions(document_id: uuid.UUID, service: DocumentServiceDep) -> list[DocumentResponse]:
    """Return every revision in the document's lineage (newest first)."""
    return [DocumentResponse.model_validate(d) for d in service.get_versions(document_id)]


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("document:create"))],
    summary="Add a new revision",
)
def add_version(
    document_id: uuid.UUID,
    payload: DocumentVersionRequest,
    service: DocumentServiceDep,
    uow: UowDep,
) -> DocumentResponse:
    """Add a new revision to the lineage and make it the current one."""
    document = service.add_version(
        document_id,
        name=payload.name,
        description=payload.description,
        storage_key=payload.storage_key,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        checksum=payload.checksum,
    )
    uow.commit()
    return DocumentResponse.model_validate(document)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    dependencies=[Depends(require_permission("document:update"))],
    summary="Update document metadata",
)
def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdateRequest,
    service: DocumentServiceDep,
    uow: UowDep,
) -> DocumentResponse:
    """Update a document's name or description."""
    document = service.update_document(
        document_id, name=payload.name, description=payload.description
    )
    uow.commit()
    return DocumentResponse.model_validate(document)


@router.delete(
    "/documents/{document_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("document:delete"))],
    summary="Delete a document",
)
def delete_document(
    document_id: uuid.UUID, service: DocumentServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a document (promoting the next revision if it was current)."""
    service.delete_document(document_id)
    uow.commit()
    return MessageResponse(detail="Document deleted.")
