"""Permission-catalogue reconciliation.

Shared logic used by both the admin API (`POST /admin/reconcile-permissions`)
and the optional startup job. New modules extend ``PERMISSION_CATALOGUE`` and
``SYSTEM_ROLES``, but those only reach a tenant at registration; reconciliation
backfills missing catalogue permissions and system-role grants for tenants
created earlier. It never removes custom grants and is idempotent.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.modules.admin.schemas import ReconcileResult, RoleReconcileItem
from app.modules.auth.models import Organization, Permission
from app.modules.auth.repository import PermissionRepository, RoleRepository
from app.modules.auth.seeds import PERMISSION_CATALOGUE, SYSTEM_ROLES

logger = get_logger(__name__)


def reconcile_organization(
    session: Session, organization_id: uuid.UUID, actor_id: uuid.UUID | None
) -> ReconcileResult:
    """Backfill catalogue permissions and system-role grants for one tenant.

    Pure data operation: it flushes changes but does not commit or record audit,
    leaving those to the caller.
    """
    permissions = PermissionRepository(session)
    roles = RoleRepository(session)

    existing = {perm.code: perm for perm in permissions.list_all()}
    permissions_created = 0
    for code, description in PERMISSION_CATALOGUE.items():
        if code not in existing:
            existing[code] = permissions.add(Permission(code=code, description=description))
            permissions_created += 1

    role_items: list[RoleReconcileItem] = []
    total_grants_added = 0
    for role_name, permission_codes in SYSTEM_ROLES.items():
        role = roles.get_by_name(organization_id, role_name)
        if role is None or not role.is_system:
            continue
        granted = {perm.code for perm in role.permissions}
        missing = [code for code in permission_codes if code not in granted]
        for code in missing:
            role.permissions.append(existing[code])
        if missing:
            roles.update(role)
        role_items.append(RoleReconcileItem(role=role_name, grants_added=len(missing)))
        total_grants_added += len(missing)

    return ReconcileResult(
        permissions_created=permissions_created,
        total_grants_added=total_grants_added,
        roles=role_items,
        detail="Permission catalogue reconciled for this organization.",
    )


def reconcile_all_tenants(session: Session, *, actor_id: uuid.UUID | None = None) -> dict[str, int]:
    """Reconcile every organization. Returns an aggregate summary.

    The caller is responsible for committing the session.
    """
    stmt = select(Organization).where(Organization.is_deleted.is_(False))
    organizations = list(session.execute(stmt).scalars().all())
    total_permissions = 0
    total_grants = 0
    for org in organizations:
        result = reconcile_organization(session, org.id, actor_id)
        total_permissions += result.permissions_created
        total_grants += result.total_grants_added
    return {
        "organizations": len(organizations),
        "permissions_created": total_permissions,
        "grants_added": total_grants,
    }


def run_startup_reconciliation(session_factory: sessionmaker[Session]) -> dict[str, int]:
    """Open a session, reconcile all tenants, commit, and log the outcome."""
    with session_factory() as session:
        summary = reconcile_all_tenants(session)
        session.commit()
    logger.info(
        "startup permission reconciliation complete",
        extra={
            "ctx_organizations": summary["organizations"],
            "ctx_permissions_created": summary["permissions_created"],
            "ctx_grants_added": summary["grants_added"],
        },
    )
    return summary
