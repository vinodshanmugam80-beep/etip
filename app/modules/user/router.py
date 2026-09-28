"""HTTP routes for the User Management module.

Thin adapters over :class:`UserService`. Administrative routes are guarded by
RBAC permissions (``user:create`` / ``user:read`` / ``user:update`` /
``user:delete``); the self-service password change is available to any
authenticated user for their own account.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import (
    CurrentUser,
    UowDep,
    UserServiceDep,
    require_permission,
)
from app.modules.user.schemas import (
    ChangePasswordRequest,
    MessageResponse,
    PaginatedUsers,
    ResetPasswordRequest,
    SetRolesRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["User Management"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("user:create"))],
    summary="Create a user",
)
def create_user(payload: UserCreateRequest, service: UserServiceDep, uow: UowDep) -> UserResponse:
    """Create a user within the caller's organization."""
    user = service.create_user(
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        role_ids=payload.role_ids,
        must_change_password=payload.must_change_password,
    )
    uow.commit()
    return UserResponse.model_validate(user)


@router.get(
    "",
    response_model=PaginatedUsers,
    dependencies=[Depends(require_permission("user:read"))],
    summary="List and search users",
)
def list_users(
    service: UserServiceDep,
    q: str | None = Query(default=None, description="Search email or name"),
    is_active: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedUsers:
    """Return a filtered, paginated page of users."""
    items, total = service.search_users(query=q, is_active=is_active, limit=limit, offset=offset)
    return PaginatedUsers(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:read"))],
    summary="Get a user",
)
def get_user(user_id: uuid.UUID, service: UserServiceDep) -> UserResponse:
    """Return a single user by id."""
    return UserResponse.model_validate(service.get_user(user_id))


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:update"))],
    summary="Update a user's profile",
)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    service: UserServiceDep,
    uow: UowDep,
) -> UserResponse:
    """Apply a partial profile update to a user."""
    user = service.update_user(
        user_id,
        full_name=payload.full_name,
        email=payload.email,
        is_active=payload.is_active,
    )
    uow.commit()
    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:update"))],
    summary="Deactivate a user",
)
def deactivate_user(user_id: uuid.UUID, service: UserServiceDep, uow: UowDep) -> UserResponse:
    """Deactivate a user and revoke their active sessions."""
    user = service.set_active(user_id, is_active=False)
    uow.commit()
    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/activate",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:update"))],
    summary="Activate a user",
)
def activate_user(user_id: uuid.UUID, service: UserServiceDep, uow: UowDep) -> UserResponse:
    """Re-activate a previously deactivated user."""
    user = service.set_active(user_id, is_active=True)
    uow.commit()
    return UserResponse.model_validate(user)


@router.put(
    "/{user_id}/roles",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("user:update"))],
    summary="Replace a user's roles",
)
def set_user_roles(
    user_id: uuid.UUID,
    payload: SetRolesRequest,
    service: UserServiceDep,
    uow: UowDep,
) -> UserResponse:
    """Replace the full set of roles assigned to a user."""
    user = service.set_roles(user_id, payload.role_ids)
    uow.commit()
    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("user:update"))],
    summary="Reset a user's password (admin)",
)
def reset_password(
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    service: UserServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Administratively reset a user's password and force a change on next login."""
    service.reset_password(user_id, new_password=payload.new_password)
    uow.commit()
    return MessageResponse(detail="Password reset.")


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("user:delete"))],
    summary="Delete a user",
)
def delete_user(user_id: uuid.UUID, service: UserServiceDep, uow: UowDep) -> MessageResponse:
    """Soft-delete a user (cannot delete your own account)."""
    service.delete_user(user_id)
    uow.commit()
    return MessageResponse(detail="User deleted.")


@router.post(
    "/me/change-password",
    response_model=MessageResponse,
    summary="Change your own password",
)
def change_own_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    service: UserServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Change the authenticated user's own password (verifies current password)."""
    service.change_own_password(
        current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    uow.commit()
    return MessageResponse(detail="Password changed.")
