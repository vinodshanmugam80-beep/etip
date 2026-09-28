"""Repositories for the authentication aggregate.

Each repository encapsulates the queries for one model, keeping raw SQLAlchemy
statements out of the service layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import (
    Organization,
    Permission,
    RefreshToken,
    Role,
    User,
    user_roles,
)
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Data access for :class:`Organization`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Organization)

    def get_by_slug(self, slug: str) -> Organization | None:
        """Return an active organization by its unique slug."""
        stmt = self._base_query(None).where(Organization.slug == slug)
        return self.session.execute(stmt).scalar_one_or_none()


class UserRepository(BaseRepository[User]):
    """Data access for :class:`User`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_email(self, organization_id: uuid.UUID, email: str) -> User | None:
        """Return a user by email within a specific organization."""
        stmt = self._base_query(organization_id).where(User.email == email.lower())
        return self.session.execute(stmt).scalar_one_or_none()

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[User]:
        """Return a filtered, paginated page of users within a tenant.

        :param query: Case-insensitive substring matched against email and
            full name.
        :param is_active: Optional active-state filter.
        """
        stmt = self._search_stmt(organization_id, query, is_active)
        stmt = stmt.order_by(User.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Return the total number of users matching the search filters."""
        inner = self._search_stmt(organization_id, query, is_active).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def _search_stmt(
        self,
        organization_id: uuid.UUID,
        query: str | None,
        is_active: bool | None,
    ) -> Select[tuple[User]]:
        """Build the filtered (unpaginated) user query used by search/count."""
        stmt = self._base_query(organization_id)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                func.lower(User.email).like(like) | func.lower(User.full_name).like(like)
            )
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))
        return stmt


class RoleRepository(BaseRepository[Role]):
    """Data access for :class:`Role`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Role)

    def get_by_name(self, organization_id: uuid.UUID, name: str) -> Role | None:
        """Return a role by name within an organization."""
        stmt = self._base_query(organization_id).where(Role.name == name)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_many(self, organization_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[Role]:
        """Return all non-deleted roles in ``ids`` belonging to the tenant."""
        if not ids:
            return []
        stmt = self._base_query(organization_id).where(Role.id.in_(list(ids)))
        return list(self.session.execute(stmt).scalars().all())

    def has_assigned_users(self, role_id: uuid.UUID) -> bool:
        """Return ``True`` if any user is currently assigned this role."""
        stmt = select(user_roles.c.user_id).where(user_roles.c.role_id == role_id)
        return self.session.execute(stmt.limit(1)).first() is not None


class PermissionRepository(BaseRepository[Permission]):
    """Data access for the global :class:`Permission` catalogue."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Permission)

    def get_by_code(self, code: str) -> Permission | None:
        """Return a permission by its unique code."""
        stmt = self._base_query(None).where(Permission.code == code)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_many_by_codes(self, codes: Sequence[str]) -> list[Permission]:
        """Return all catalogue permissions whose code is in ``codes``."""
        if not codes:
            return []
        stmt = select(Permission).where(Permission.code.in_(list(codes)))
        return list(self.session.execute(stmt).scalars().all())

    def list_all(self) -> list[Permission]:
        """Return every permission in the catalogue."""
        return list(self.session.execute(select(Permission)).scalars().all())


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Data access for :class:`RefreshToken`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, RefreshToken)

    def get_by_jti(self, jti: uuid.UUID) -> RefreshToken | None:
        """Return a refresh-token record by its JWT id."""
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        return self.session.execute(stmt).scalar_one_or_none()

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every active refresh token belonging to a user."""
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked.is_(False),
        )
        for token in self.session.execute(stmt).scalars():
            token.revoked = True
        self.session.flush()
