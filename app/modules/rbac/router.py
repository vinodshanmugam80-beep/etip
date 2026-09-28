"""HTTP routes for the Roles & Permissions module.

Thin adapters over :class:`RbacService`. Reads require ``role:read``; role
creation/modification/deletion require the corresponding ``role:*`` permission.
The permission catalogue is global (identical for every tenant) and read-only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import RbacServiceDep, UowDep, require_permission
from app.modules.rbac.schemas import (
    MessageResponse,
    PermissionResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
    SetPermissionsRequest,
)

router = APIRouter(tags=["Roles & Permissions"])


# --- Permission catalogue --------------------------------------------------
@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    dependencies=[Depends(require_permission("role:read"))],
    summary="List the permission catalogue",
)
def list_permissions(service: RbacServiceDep) -> list[PermissionResponse]:
    """Return the global catalogue of assignable permissions."""
    return [PermissionResponse.model_validate(p) for p in service.list_permissions()]


# --- Roles -----------------------------------------------------------------
@router.post(
    "/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("role:create"))],
    summary="Create a custom role",
)
def create_role(payload: RoleCreateRequest, service: RbacServiceDep, uow: UowDep) -> RoleResponse:
    """Create a custom role with an optional initial permission set."""
    role = service.create_role(
        name=payload.name,
        description=payload.description,
        permission_codes=payload.permissions,
    )
    uow.commit()
    return RoleResponse.model_validate(role)


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=[Depends(require_permission("role:read"))],
    summary="List roles",
)
def list_roles(
    service: RbacServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[RoleResponse]:
    """Return a page of roles (system and custom) for the tenant."""
    return [RoleResponse.model_validate(r) for r in service.list_roles(limit=limit, offset=offset)]


@router.get(
    "/roles/{role_id}",
    response_model=RoleResponse,
    dependencies=[Depends(require_permission("role:read"))],
    summary="Get a role",
)
def get_role(role_id: uuid.UUID, service: RbacServiceDep) -> RoleResponse:
    """Return a single role with its granted permissions."""
    return RoleResponse.model_validate(service.get_role(role_id))


@router.patch(
    "/roles/{role_id}",
    response_model=RoleResponse,
    dependencies=[Depends(require_permission("role:update"))],
    summary="Update a role",
)
def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdateRequest,
    service: RbacServiceDep,
    uow: UowDep,
) -> RoleResponse:
    """Update a custom role's name/description (system roles are protected)."""
    role = service.update_role(role_id, name=payload.name, description=payload.description)
    uow.commit()
    return RoleResponse.model_validate(role)


@router.put(
    "/roles/{role_id}/permissions",
    response_model=RoleResponse,
    dependencies=[Depends(require_permission("role:update"))],
    summary="Replace a role's permissions",
)
def set_permissions(
    role_id: uuid.UUID,
    payload: SetPermissionsRequest,
    service: RbacServiceDep,
    uow: UowDep,
) -> RoleResponse:
    """Replace the full permission set of a custom role."""
    role = service.set_permissions(role_id, payload.permissions)
    uow.commit()
    return RoleResponse.model_validate(role)


@router.post(
    "/roles/{role_id}/permissions/{code}",
    response_model=RoleResponse,
    dependencies=[Depends(require_permission("role:update"))],
    summary="Grant a single permission to a role",
)
def grant_permission(
    role_id: uuid.UUID, code: str, service: RbacServiceDep, uow: UowDep
) -> RoleResponse:
    """Grant one permission (by code) to a custom role (idempotent)."""
    role = service.grant_permission(role_id, code)
    uow.commit()
    return RoleResponse.model_validate(role)


@router.delete(
    "/roles/{role_id}/permissions/{code}",
    response_model=RoleResponse,
    dependencies=[Depends(require_permission("role:update"))],
    summary="Revoke a single permission from a role",
)
def revoke_permission(
    role_id: uuid.UUID, code: str, service: RbacServiceDep, uow: UowDep
) -> RoleResponse:
    """Revoke one permission (by code) from a custom role (idempotent)."""
    role = service.revoke_permission(role_id, code)
    uow.commit()
    return RoleResponse.model_validate(role)


@router.delete(
    "/roles/{role_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("role:delete"))],
    summary="Delete a role",
)
def delete_role(role_id: uuid.UUID, service: RbacServiceDep, uow: UowDep) -> MessageResponse:
    """Delete a custom role (blocked for system roles or roles in use)."""
    service.delete_role(role_id)
    uow.commit()
    return MessageResponse(detail="Role deleted.")
