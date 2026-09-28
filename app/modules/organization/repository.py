"""Repositories for the Organization Management aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.organization.models import (
    BusinessUnit,
    Department,
    DepartmentMembership,
    OrganizationSettings,
)
from app.repositories.base import BaseRepository


class BusinessUnitRepository(BaseRepository[BusinessUnit]):
    """Data access for :class:`BusinessUnit`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, BusinessUnit)

    def get_by_code(self, organization_id: uuid.UUID, code: str) -> BusinessUnit | None:
        """Return a business unit by its per-organization code."""
        stmt = self._base_query(organization_id).where(BusinessUnit.code == code)
        return self.session.execute(stmt).scalar_one_or_none()


class DepartmentRepository(BaseRepository[Department]):
    """Data access for :class:`Department`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Department)

    def get_by_code(self, organization_id: uuid.UUID, code: str) -> Department | None:
        """Return a department by its per-organization code."""
        stmt = self._base_query(organization_id).where(Department.code == code)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_business_unit(
        self, organization_id: uuid.UUID, business_unit_id: uuid.UUID
    ) -> Sequence[Department]:
        """Return departments belonging to a business unit."""
        stmt = self._base_query(organization_id).where(
            Department.business_unit_id == business_unit_id
        )
        return self.session.execute(stmt).scalars().all()

    def has_children(self, organization_id: uuid.UUID, department_id: uuid.UUID) -> bool:
        """Return ``True`` if any non-deleted department names this parent."""
        stmt = self._base_query(organization_id).where(
            Department.parent_department_id == department_id
        )
        return self.session.execute(stmt).first() is not None


class OrganizationSettingsRepository(BaseRepository[OrganizationSettings]):
    """Data access for :class:`OrganizationSettings`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, OrganizationSettings)

    def get_for_organization(self, organization_id: uuid.UUID) -> OrganizationSettings | None:
        """Return the settings row for an organization, if present."""
        stmt = self._base_query(organization_id)
        return self.session.execute(stmt).scalar_one_or_none()


class DepartmentMembershipRepository(BaseRepository[DepartmentMembership]):
    """Data access for :class:`DepartmentMembership`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, DepartmentMembership)

    def list_for_department(
        self, organization_id: uuid.UUID, department_id: uuid.UUID
    ) -> Sequence[DepartmentMembership]:
        """Return the memberships of a department."""
        stmt = self._base_query(organization_id).where(
            DepartmentMembership.department_id == department_id
        )
        return self.session.execute(stmt).scalars().all()

    def get_membership(
        self,
        organization_id: uuid.UUID,
        department_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DepartmentMembership | None:
        """Return a specific user's membership in a department."""
        stmt = self._base_query(organization_id).where(
            DepartmentMembership.department_id == department_id,
            DepartmentMembership.user_id == user_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def clear_primary_for_user(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Unset the ``is_primary`` flag on all of a user's memberships."""
        stmt = select(DepartmentMembership).where(
            DepartmentMembership.organization_id == organization_id,
            DepartmentMembership.user_id == user_id,
            DepartmentMembership.is_primary.is_(True),
            DepartmentMembership.is_deleted.is_(False),
        )
        for membership in self.session.execute(stmt).scalars():
            membership.is_primary = False
        self.session.flush()
