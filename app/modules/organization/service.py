"""Organization Management service.

Encapsulates all business rules for business units, departments, settings and
department memberships: per-organization code uniqueness, department hierarchy
integrity (cycle prevention), cross-module user validation, the single-primary
membership invariant, and deletion guards. Framework-agnostic; raises domain
exceptions from :mod:`app.core.exceptions`.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.organization.models import (
    BusinessUnit,
    Department,
    DepartmentMembership,
    OrganizationSettings,
)
from app.modules.organization.repository import (
    BusinessUnitRepository,
    DepartmentMembershipRepository,
    DepartmentRepository,
    OrganizationSettingsRepository,
)

logger = get_logger(__name__)

_MAX_HIERARCHY_DEPTH = 20


class OrganizationService:
    """Coordinates organization-structure use cases within a tenant.

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
        self.business_units = BusinessUnitRepository(session)
        self.departments = DepartmentRepository(session)
        self.settings = OrganizationSettingsRepository(session)
        self.memberships = DepartmentMembershipRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Shared validation
    # ------------------------------------------------------------------
    def _require_user_in_org(self, user_id: uuid.UUID | None) -> None:
        """Validate that an optional user id belongs to the caller's tenant."""
        if user_id is None:
            return
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Referenced user does not belong to this organization.",
                details={"user_id": str(user_id)},
            )

    # ------------------------------------------------------------------
    # Business units
    # ------------------------------------------------------------------
    def create_business_unit(
        self,
        *,
        name: str,
        code: str,
        description: str,
        lead_user_id: uuid.UUID | None,
    ) -> BusinessUnit:
        """Create a business unit, enforcing per-organization code uniqueness."""
        if self.business_units.get_by_code(self._org_id, code):
            raise ConflictError(
                f"A business unit with code '{code}' already exists.",
                details={"code": code},
            )
        self._require_user_in_org(lead_user_id)
        unit = BusinessUnit(
            organization_id=self._org_id,
            name=name,
            code=code,
            description=description,
            lead_user_id=lead_user_id,
            created_by=self._actor_id,
        )
        self.business_units.add(unit)
        self._uow.record_audit(
            "BusinessUnit",
            unit.id,
            "create",
            f"Created business unit '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return unit

    def get_business_unit(self, unit_id: uuid.UUID) -> BusinessUnit:
        """Return a business unit or raise :class:`NotFoundError`."""
        unit = self.business_units.get(unit_id, organization_id=self._org_id)
        if unit is None:
            raise NotFoundError("Business unit not found.")
        return unit

    def list_business_units(self, *, limit: int, offset: int) -> list[BusinessUnit]:
        """Return a page of business units for the tenant."""
        return list(
            self.business_units.list(organization_id=self._org_id, limit=limit, offset=offset)
        )

    def update_business_unit(
        self,
        unit_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        lead_user_id: uuid.UUID | None,
        is_active: bool | None,
    ) -> BusinessUnit:
        """Apply a partial update to a business unit."""
        unit = self.get_business_unit(unit_id)
        if name is not None:
            unit.name = name
        if description is not None:
            unit.description = description
        if lead_user_id is not None:
            self._require_user_in_org(lead_user_id)
            unit.lead_user_id = lead_user_id
        if is_active is not None:
            unit.is_active = is_active
        unit.modified_by = self._actor_id
        self.business_units.update(unit)
        self._uow.record_audit(
            "BusinessUnit",
            unit.id,
            "update",
            f"Updated business unit '{unit.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return unit

    def delete_business_unit(self, unit_id: uuid.UUID) -> None:
        """Soft-delete a business unit, blocking if departments still reference it."""
        unit = self.get_business_unit(unit_id)
        dependents = self.departments.list_by_business_unit(self._org_id, unit_id)
        if dependents:
            raise ConflictError(
                "Cannot delete a business unit that still has departments.",
                details={"department_count": len(dependents)},
            )
        self.business_units.soft_delete(unit, actor_id=self._actor_id)
        self._uow.record_audit(
            "BusinessUnit",
            unit.id,
            "delete",
            f"Deleted business unit '{unit.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Departments
    # ------------------------------------------------------------------
    def create_department(
        self,
        *,
        name: str,
        code: str,
        description: str,
        business_unit_id: uuid.UUID | None,
        parent_department_id: uuid.UUID | None,
        head_user_id: uuid.UUID | None,
    ) -> Department:
        """Create a department, validating references and code uniqueness."""
        if self.departments.get_by_code(self._org_id, code):
            raise ConflictError(
                f"A department with code '{code}' already exists.",
                details={"code": code},
            )
        if business_unit_id is not None:
            self.get_business_unit(business_unit_id)
        if parent_department_id is not None:
            self.get_department(parent_department_id)
        self._require_user_in_org(head_user_id)

        dept = Department(
            organization_id=self._org_id,
            name=name,
            code=code,
            description=description,
            business_unit_id=business_unit_id,
            parent_department_id=parent_department_id,
            head_user_id=head_user_id,
            created_by=self._actor_id,
        )
        self.departments.add(dept)
        self._uow.record_audit(
            "Department",
            dept.id,
            "create",
            f"Created department '{name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return dept

    def get_department(self, department_id: uuid.UUID) -> Department:
        """Return a department or raise :class:`NotFoundError`."""
        dept = self.departments.get(department_id, organization_id=self._org_id)
        if dept is None:
            raise NotFoundError("Department not found.")
        return dept

    def list_departments(
        self,
        *,
        business_unit_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[Department]:
        """Return departments, optionally filtered by business unit."""
        if business_unit_id is not None:
            return list(self.departments.list_by_business_unit(self._org_id, business_unit_id))
        return list(self.departments.list(organization_id=self._org_id, limit=limit, offset=offset))

    def update_department(
        self,
        department_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        business_unit_id: uuid.UUID | None,
        parent_department_id: uuid.UUID | None,
        head_user_id: uuid.UUID | None,
        is_active: bool | None,
    ) -> Department:
        """Apply a partial update, validating hierarchy and references."""
        dept = self.get_department(department_id)
        if name is not None:
            dept.name = name
        if description is not None:
            dept.description = description
        if business_unit_id is not None:
            self.get_business_unit(business_unit_id)
            dept.business_unit_id = business_unit_id
        if parent_department_id is not None:
            self._assign_parent(dept, parent_department_id)
        if head_user_id is not None:
            self._require_user_in_org(head_user_id)
            dept.head_user_id = head_user_id
        if is_active is not None:
            dept.is_active = is_active
        dept.modified_by = self._actor_id
        self.departments.update(dept)
        self._uow.record_audit(
            "Department",
            dept.id,
            "update",
            f"Updated department '{dept.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return dept

    def _assign_parent(self, dept: Department, parent_id: uuid.UUID) -> None:
        """Set a department's parent, preventing self- and cyclic references."""
        if parent_id == dept.id:
            raise ValidationError("A department cannot be its own parent.")
        parent = self.get_department(parent_id)
        # Walk up from the proposed parent; a cycle exists if we reach ``dept``.
        cursor: Department | None = parent
        depth = 0
        while cursor is not None:
            if cursor.id == dept.id:
                raise ValidationError("Assigning this parent would create a hierarchy cycle.")
            if cursor.parent_department_id is None:
                break
            depth += 1
            if depth > _MAX_HIERARCHY_DEPTH:
                raise ValidationError("Department hierarchy is too deep.")
            cursor = self.departments.get(cursor.parent_department_id, organization_id=self._org_id)
        dept.parent_department_id = parent_id

    def delete_department(self, department_id: uuid.UUID) -> None:
        """Soft-delete a department, blocking if it still has child departments."""
        dept = self.get_department(department_id)
        if self.departments.has_children(self._org_id, department_id):
            raise ConflictError("Cannot delete a department that has child departments.")
        self.departments.soft_delete(dept, actor_id=self._actor_id)
        self._uow.record_audit(
            "Department",
            dept.id,
            "delete",
            f"Deleted department '{dept.name}'",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def get_settings(self) -> OrganizationSettings:
        """Return the tenant's settings, creating defaults on first access."""
        settings = self.settings.get_for_organization(self._org_id)
        if settings is None:
            settings = OrganizationSettings(organization_id=self._org_id, created_by=self._actor_id)
            self.settings.add(settings)
        return settings

    def update_settings(
        self,
        *,
        currency: str | None,
        timezone: str | None,
        date_format: str | None,
        fiscal_year_start_month: int | None,
        week_start_day: int | None,
    ) -> OrganizationSettings:
        """Apply a partial update to the tenant's settings."""
        settings = self.get_settings()
        if currency is not None:
            settings.currency = currency
        if timezone is not None:
            settings.timezone = timezone
        if date_format is not None:
            settings.date_format = date_format
        if fiscal_year_start_month is not None:
            settings.fiscal_year_start_month = fiscal_year_start_month
        if week_start_day is not None:
            settings.week_start_day = week_start_day
        settings.modified_by = self._actor_id
        self.settings.update(settings)
        self._uow.record_audit(
            "OrganizationSettings",
            settings.id,
            "update",
            "Updated settings",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return settings

    # ------------------------------------------------------------------
    # Department memberships
    # ------------------------------------------------------------------
    def add_member(
        self, department_id: uuid.UUID, *, user_id: uuid.UUID, is_primary: bool
    ) -> DepartmentMembership:
        """Add a user to a department, enforcing the single-primary invariant."""
        self.get_department(department_id)
        if self.users.get(user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "User does not belong to this organization.",
                details={"user_id": str(user_id)},
            )
        if self.memberships.get_membership(self._org_id, department_id, user_id):
            raise ConflictError("User is already a member of this department.")

        if is_primary:
            self.memberships.clear_primary_for_user(self._org_id, user_id)

        membership = DepartmentMembership(
            organization_id=self._org_id,
            department_id=department_id,
            user_id=user_id,
            is_primary=is_primary,
            created_by=self._actor_id,
        )
        self.memberships.add(membership)
        self._uow.record_audit(
            "DepartmentMembership",
            membership.id,
            "create",
            "Added department member",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
        return membership

    def list_members(self, department_id: uuid.UUID) -> list[DepartmentMembership]:
        """Return the memberships of a department."""
        self.get_department(department_id)
        return list(self.memberships.list_for_department(self._org_id, department_id))

    def remove_member(self, department_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Remove a user from a department (soft delete of the membership)."""
        membership = self.memberships.get_membership(self._org_id, department_id, user_id)
        if membership is None:
            raise NotFoundError("Membership not found.")
        self.memberships.soft_delete(membership, actor_id=self._actor_id)
        self._uow.record_audit(
            "DepartmentMembership",
            membership.id,
            "delete",
            "Removed department member",
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
