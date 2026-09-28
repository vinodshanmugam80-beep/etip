"""User Management service.

Administrative use cases over the identity aggregate owned by the auth module:
create/search/update users, manage active status, assign roles, and handle
passwords (self-service change and admin reset). Enforces email uniqueness per
tenant, validates role assignments, guards against self-lockout, and revokes
refresh tokens whenever credentials or active status change.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.models import Role, User
from app.modules.auth.repository import (
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)

logger = get_logger(__name__)


class UserService:
    """Coordinates administrative user-management use cases within a tenant.

    :param uow: An open Unit of Work bound to the current transaction.
    :param organization_id: The caller's tenant, bound from the access token.
    :param actor_id: The acting user's id, used for audit stamping and
        self-action guards.
    """

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
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_user_or_404(self, user_id: uuid.UUID) -> User:
        """Return a user in the caller's tenant or raise :class:`NotFoundError`."""
        user = self.users.get(user_id, organization_id=self._org_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    def _resolve_roles(self, role_ids: Sequence[uuid.UUID]) -> list[Role]:
        """Return the roles for ``role_ids``, validating they all exist in tenant."""
        unique_ids = list(dict.fromkeys(role_ids))
        roles = self.roles.get_many(self._org_id, unique_ids)
        if len(roles) != len(unique_ids):
            found = {role.id for role in roles}
            missing = [str(rid) for rid in unique_ids if rid not in found]
            raise ValidationError(
                "One or more roles do not exist in this organization.",
                details={"missing_role_ids": missing},
            )
        return roles

    # ------------------------------------------------------------------
    # Create / read
    # ------------------------------------------------------------------
    def create_user(
        self,
        *,
        email: str,
        full_name: str,
        password: str,
        role_ids: Sequence[uuid.UUID],
        must_change_password: bool,
    ) -> User:
        """Create a user within the tenant, enforcing email uniqueness."""
        normalised_email = email.lower()
        if self.users.get_by_email(self._org_id, normalised_email):
            raise ConflictError(
                "A user with this email already exists in the organization.",
                details={"email": normalised_email},
            )
        roles = self._resolve_roles(role_ids)
        user = User(
            organization_id=self._org_id,
            email=normalised_email,
            full_name=full_name,
            hashed_password=hash_password(password),
            must_change_password=must_change_password,
            created_by=self._actor_id,
        )
        user.roles = roles
        self.users.add(user)
        self._uow.record_audit(
            "User",
            user.id,
            "create",
            f"Created user '{normalised_email}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return user

    def get_user(self, user_id: uuid.UUID) -> User:
        """Return a single user by id."""
        return self._get_user_or_404(user_id)

    def search_users(
        self,
        *,
        query: str | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        """Return a page of users and the total matching count."""
        items = list(
            self.users.search(
                self._org_id,
                query=query,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )
        )
        total = self.users.count(self._org_id, query=query, is_active=is_active)
        return items, total

    # ------------------------------------------------------------------
    # Update / status
    # ------------------------------------------------------------------
    def update_user(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None,
        email: str | None,
        is_active: bool | None,
    ) -> User:
        """Apply a partial profile update, enforcing email uniqueness."""
        user = self._get_user_or_404(user_id)
        if full_name is not None:
            user.full_name = full_name
        if email is not None:
            normalised = email.lower()
            if normalised != user.email:
                existing = self.users.get_by_email(self._org_id, normalised)
                if existing is not None and existing.id != user.id:
                    raise ConflictError(
                        "A user with this email already exists in the organization.",
                        details={"email": normalised},
                    )
                user.email = normalised
        if is_active is not None:
            self._set_active(user, is_active)
        user.modified_by = self._actor_id
        self.users.update(user)
        self._uow.record_audit(
            "User",
            user.id,
            "update",
            f"Updated user '{user.email}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return user

    def set_active(self, user_id: uuid.UUID, *, is_active: bool) -> User:
        """Activate or deactivate a user."""
        user = self._get_user_or_404(user_id)
        self._set_active(user, is_active)
        user.modified_by = self._actor_id
        self.users.update(user)
        action = "activate" if is_active else "deactivate"
        self._uow.record_audit(
            "User",
            user.id,
            action,
            f"{action.capitalize()}d user '{user.email}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return user

    def _set_active(self, user: User, is_active: bool) -> None:
        """Set active status, guarding against self-deactivation."""
        if not is_active and user.id == self._actor_id:
            raise ValidationError("You cannot deactivate your own account.")
        user.is_active = is_active
        if not is_active:
            # Revoking sessions is a security requirement on deactivation.
            self.refresh_tokens.revoke_all_for_user(user.id)

    def set_roles(self, user_id: uuid.UUID, role_ids: Sequence[uuid.UUID]) -> User:
        """Replace the full set of roles assigned to a user."""
        user = self._get_user_or_404(user_id)
        user.roles = self._resolve_roles(role_ids)
        user.modified_by = self._actor_id
        self.users.update(user)
        self._uow.record_audit(
            "User",
            user.id,
            "set_roles",
            f"Set roles for '{user.email}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return user

    def delete_user(self, user_id: uuid.UUID) -> None:
        """Soft-delete a user, guarding against self-deletion."""
        user = self._get_user_or_404(user_id)
        if user.id == self._actor_id:
            raise ValidationError("You cannot delete your own account.")
        self.refresh_tokens.revoke_all_for_user(user.id)
        self.users.soft_delete(user, actor_id=self._actor_id)
        self._uow.record_audit(
            "User",
            user.id,
            "delete",
            f"Deleted user '{user.email}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Passwords
    # ------------------------------------------------------------------
    def change_own_password(self, user: User, *, current_password: str, new_password: str) -> None:
        """Change the caller's own password after verifying the current one."""
        if not verify_password(current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect.")
        user.hashed_password = hash_password(new_password)
        user.must_change_password = False
        user.modified_by = user.id
        self.users.update(user)
        # Invalidate all existing sessions after a credential change.
        self.refresh_tokens.revoke_all_for_user(user.id)
        self._uow.record_audit(
            "User",
            user.id,
            "change_password",
            "Password changed by user",
            actor_id=user.id,
            organization_id=self._org_id,
        )

    def reset_password(self, user_id: uuid.UUID, *, new_password: str) -> User:
        """Administratively reset a user's password and force a change."""
        user = self._get_user_or_404(user_id)
        user.hashed_password = hash_password(new_password)
        user.must_change_password = True
        user.modified_by = self._actor_id
        self.users.update(user)
        self.refresh_tokens.revoke_all_for_user(user.id)
        self._uow.record_audit(
            "User",
            user.id,
            "reset_password",
            f"Password reset for '{user.email}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return user
