"""Roles & Permissions service.

Manages custom roles and their permission grants within a tenant, over the
:class:`Role`/:class:`Permission` models owned by the auth module. Enforces the
key access-control invariants: seeded **system roles are immutable and
undeletable**, role names are unique per organization, only catalogue
permissions may be granted, and a role that is still assigned to users cannot
be deleted.

Framework-agnostic; raises domain exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.models import Permission, Role
from app.modules.auth.repository import PermissionRepository, RoleRepository

logger = get_logger(__name__)


class RbacService:
    """Coordinates role and permission management within a tenant.

    :param uow: An open Unit of Work bound to the current transaction.
    :param organization_id: The caller's tenant, bound from the access token.
    :param actor_id: The acting user's id, used for audit stamping.
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
        self.roles = RoleRepository(session)
        self.permissions = PermissionRepository(session)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_role_or_404(self, role_id: uuid.UUID) -> Role:
        """Return a role in the caller's tenant or raise :class:`NotFoundError`."""
        role = self.roles.get(role_id, organization_id=self._org_id)
        if role is None:
            raise NotFoundError("Role not found.")
        return role

    @staticmethod
    def _assert_not_system(role: Role) -> None:
        """Reject any mutation of a seeded system role."""
        if role.is_system:
            raise ConflictError(
                "System roles cannot be modified or deleted.",
                code="protected_role",
                details={"role": role.name},
            )

    def _resolve_permissions(self, codes: Sequence[str]) -> list[Permission]:
        """Return catalogue permissions for ``codes``, validating each exists."""
        unique = list(dict.fromkeys(codes))
        found = self.permissions.get_many_by_codes(unique)
        if len(found) != len(unique):
            known = {perm.code for perm in found}
            unknown = [code for code in unique if code not in known]
            raise ValidationError(
                "One or more permission codes are not recognised.",
                details={"unknown_permissions": unknown},
            )
        return found

    # ------------------------------------------------------------------
    # Permission catalogue
    # ------------------------------------------------------------------
    def list_permissions(self) -> list[Permission]:
        """Return the global permission catalogue, ordered by code."""
        return sorted(self.permissions.list_all(), key=lambda perm: perm.code)

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------
    def create_role(self, *, name: str, description: str, permission_codes: Sequence[str]) -> Role:
        """Create a custom role, enforcing per-organization name uniqueness."""
        if self.roles.get_by_name(self._org_id, name):
            raise ConflictError(f"A role named '{name}' already exists.", details={"name": name})
        permissions = self._resolve_permissions(permission_codes)
        role = Role(
            organization_id=self._org_id,
            name=name,
            description=description,
            is_system=False,
            created_by=self._actor_id,
        )
        role.permissions = permissions
        self.roles.add(role)
        self._uow.record_audit(
            "Role",
            role.id,
            "create",
            f"Created role '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return role

    def get_role(self, role_id: uuid.UUID) -> Role:
        """Return a single role by id."""
        return self._get_role_or_404(role_id)

    def list_roles(self, *, limit: int, offset: int) -> list[Role]:
        """Return a page of roles for the tenant."""
        return list(self.roles.list(organization_id=self._org_id, limit=limit, offset=offset))

    def update_role(self, role_id: uuid.UUID, *, name: str | None, description: str | None) -> Role:
        """Update a custom role's descriptive fields (system roles rejected)."""
        role = self._get_role_or_404(role_id)
        self._assert_not_system(role)
        if name is not None and name != role.name:
            if self.roles.get_by_name(self._org_id, name):
                raise ConflictError(
                    f"A role named '{name}' already exists.",
                    details={"name": name},
                )
            role.name = name
        if description is not None:
            role.description = description
        role.modified_by = self._actor_id
        self.roles.update(role)
        self._uow.record_audit(
            "Role",
            role.id,
            "update",
            f"Updated role '{role.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return role

    def set_permissions(self, role_id: uuid.UUID, codes: Sequence[str]) -> Role:
        """Replace the full permission set of a custom role."""
        role = self._get_role_or_404(role_id)
        self._assert_not_system(role)
        role.permissions = self._resolve_permissions(codes)
        role.modified_by = self._actor_id
        self.roles.update(role)
        self._uow.record_audit(
            "Role",
            role.id,
            "set_permissions",
            f"Set permissions on role '{role.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return role

    def grant_permission(self, role_id: uuid.UUID, code: str) -> Role:
        """Grant a single permission to a custom role (idempotent)."""
        role = self._get_role_or_404(role_id)
        self._assert_not_system(role)
        (permission,) = self._resolve_permissions([code])
        if permission.code not in {perm.code for perm in role.permissions}:
            role.permissions.append(permission)
            role.modified_by = self._actor_id
            self.roles.update(role)
            self._uow.record_audit(
                "Role",
                role.id,
                "grant_permission",
                f"Granted '{code}' to role '{role.name}'",
                actor_id=self._actor_id,
                organization_id=self._org_id,
            )
        return role

    def revoke_permission(self, role_id: uuid.UUID, code: str) -> Role:
        """Revoke a single permission from a custom role (idempotent)."""
        role = self._get_role_or_404(role_id)
        self._assert_not_system(role)
        remaining = [perm for perm in role.permissions if perm.code != code]
        if len(remaining) != len(role.permissions):
            role.permissions = remaining
            role.modified_by = self._actor_id
            self.roles.update(role)
            self._uow.record_audit(
                "Role",
                role.id,
                "revoke_permission",
                f"Revoked '{code}' from role '{role.name}'",
                actor_id=self._actor_id,
                organization_id=self._org_id,
            )
        return role

    def delete_role(self, role_id: uuid.UUID) -> None:
        """Delete a custom role, blocking system roles and in-use roles."""
        role = self._get_role_or_404(role_id)
        self._assert_not_system(role)
        if self.roles.has_assigned_users(role.id):
            raise ConflictError(
                "Cannot delete a role that is still assigned to users.",
                code="role_in_use",
            )
        self.roles.soft_delete(role, actor_id=self._actor_id)
        self._uow.record_audit(
            "Role",
            role.id,
            "delete",
            f"Deleted role '{role.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
