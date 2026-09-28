"""Pydantic v2 schemas for API keys."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreateRequest(BaseModel):
    """Payload to issue an API key.

    ``user_id`` is the identity the key acts as (defaults to the caller). Use a
    dedicated service-account user for integrations rather than a person.
    """

    name: str = Field(min_length=2, max_length=200)
    user_id: uuid.UUID | None = None
    expires_date: date | None = None


class ApiKeyResponse(BaseModel):
    """An API key's metadata (never includes the secret or its hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    prefix: str
    is_active: bool
    expires_date: date | None
    key_hash: str = Field(exclude=True, default="")
    created_date: datetime
    version: int


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned once on creation — carries the plaintext key (shown only here)."""

    api_key: str


class PaginatedApiKeys(BaseModel):
    """A page of API keys."""

    items: list[ApiKeyResponse]
    total: int
    limit: int
    offset: int
