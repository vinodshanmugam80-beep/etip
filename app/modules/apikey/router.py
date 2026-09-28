"""HTTP routes for API keys. Managing keys requires ``apikey:manage``."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import ApiKeyServiceDep, UowDep, require_permission
from app.modules.apikey.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    PaginatedApiKeys,
)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
_MANAGE = Depends(require_permission("apikey:manage"))


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Issue an API key",
)
def create_key(
    payload: ApiKeyCreateRequest, service: ApiKeyServiceDep, uow: UowDep
) -> ApiKeyCreatedResponse:
    """Issue a key. The plaintext secret is returned once — store it now."""
    key, secret = service.create(payload)
    uow.commit()
    return ApiKeyCreatedResponse(**ApiKeyResponse.model_validate(key).model_dump(), api_key=secret)


@router.get("", response_model=PaginatedApiKeys, dependencies=[_MANAGE], summary="List API keys")
def list_keys(
    service: ApiKeyServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedApiKeys:
    """Return a paginated page of the tenant's API keys (no secrets)."""
    items, total = service.search(limit=limit, offset=offset)
    return PaginatedApiKeys(
        items=[ApiKeyResponse.model_validate(k) for k in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{key_id}",
    response_model=ApiKeyResponse,
    dependencies=[_MANAGE],
    summary="Get an API key",
)
def get_key(key_id: uuid.UUID, service: ApiKeyServiceDep) -> ApiKeyResponse:
    """Return a single API key's metadata."""
    return ApiKeyResponse.model_validate(service.get(key_id))


@router.post(
    "/{key_id}/revoke",
    response_model=ApiKeyResponse,
    dependencies=[_MANAGE],
    summary="Revoke an API key",
)
def revoke_key(key_id: uuid.UUID, service: ApiKeyServiceDep, uow: UowDep) -> ApiKeyResponse:
    """Deactivate a key so it can no longer authenticate."""
    key = service.revoke(key_id)
    uow.commit()
    return ApiKeyResponse.model_validate(key)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete an API key",
)
def delete_key(key_id: uuid.UUID, service: ApiKeyServiceDep, uow: UowDep) -> None:
    """Soft-delete an API key."""
    service.delete(key_id)
    uow.commit()
