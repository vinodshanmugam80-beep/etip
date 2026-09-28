"""Data access for Vendor / Procurement / Contracts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.vendor.models import (
    Contract,
    ContractStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
    Vendor,
    VendorCategory,
    VendorStatus,
)
from app.repositories.base import BaseRepository


class VendorRepository(BaseRepository[Vendor]):
    """Repository for :class:`Vendor`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Vendor)

    def get_by_code(self, organization_id: uuid.UUID, code: str) -> Vendor | None:
        """Return a non-deleted vendor by case-insensitive code."""
        stmt = self._base_query(organization_id).where(func.lower(Vendor.code) == code.lower())
        return self.session.execute(stmt).scalars().first()

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None,
        category: VendorCategory | None,
        status: VendorStatus | None,
    ) -> Select[tuple[Vendor]]:
        stmt = self._base_query(organization_id)
        if query:
            stmt = stmt.where(Vendor.name.ilike(f"%{query}%"))
        if category is not None:
            stmt = stmt.where(Vendor.category == category)
        if status is not None:
            stmt = stmt.where(Vendor.status == status)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        category: VendorCategory | None = None,
        status: VendorStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Vendor]:
        """Return a filtered, paginated page of vendors (by name)."""
        stmt = self._filtered(organization_id, query=query, category=category, status=status)
        stmt = stmt.order_by(Vendor.name).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        category: VendorCategory | None = None,
        status: VendorStatus | None = None,
    ) -> int:
        """Return the number of vendors matching the filters."""
        inner = self._filtered(
            organization_id, query=query, category=category, status=status
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class ContractRepository(BaseRepository[Contract]):
    """Repository for :class:`Contract`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Contract)

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        status: ContractStatus | None,
    ) -> Select[tuple[Contract]]:
        stmt = self._base_query(organization_id)
        if vendor_id is not None:
            stmt = stmt.where(Contract.vendor_id == vendor_id)
        if project_id is not None:
            stmt = stmt.where(Contract.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Contract.status == status)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: ContractStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Contract]:
        """Return a filtered, paginated page of contracts (newest first)."""
        stmt = self._filtered(
            organization_id, vendor_id=vendor_id, project_id=project_id, status=status
        )
        stmt = stmt.order_by(Contract.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: ContractStatus | None = None,
    ) -> int:
        """Return the number of contracts matching the filters."""
        inner = self._filtered(
            organization_id, vendor_id=vendor_id, project_id=project_id, status=status
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())


class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    """Repository for :class:`PurchaseOrder`."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, PurchaseOrder)

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None,
        contract_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        status: PurchaseOrderStatus | None,
    ) -> Select[tuple[PurchaseOrder]]:
        stmt = self._base_query(organization_id)
        if vendor_id is not None:
            stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
        if contract_id is not None:
            stmt = stmt.where(PurchaseOrder.contract_id == contract_id)
        if project_id is not None:
            stmt = stmt.where(PurchaseOrder.project_id == project_id)
        if status is not None:
            stmt = stmt.where(PurchaseOrder.status == status)
        return stmt

    def search(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        contract_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: PurchaseOrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[PurchaseOrder]:
        """Return a filtered, paginated page of purchase orders (newest first)."""
        stmt = self._filtered(
            organization_id,
            vendor_id=vendor_id,
            contract_id=contract_id,
            project_id=project_id,
            status=status,
        )
        stmt = stmt.order_by(PurchaseOrder.created_date.desc()).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        contract_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: PurchaseOrderStatus | None = None,
    ) -> int:
        """Return the number of purchase orders matching the filters."""
        inner = self._filtered(
            organization_id,
            vendor_id=vendor_id,
            contract_id=contract_id,
            project_id=project_id,
            status=status,
        ).subquery()
        return int(self.session.execute(select(func.count()).select_from(inner)).scalar_one())

    def totals(
        self,
        organization_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        contract_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> tuple[Decimal, Decimal, int]:
        """Return ``(committed, invoiced, count)`` for the matching POs."""
        stmt = select(
            func.coalesce(func.sum(PurchaseOrder.committed_amount), 0),
            func.coalesce(func.sum(PurchaseOrder.invoiced_amount), 0),
            func.count(),
        ).where(
            PurchaseOrder.organization_id == organization_id,
            PurchaseOrder.is_deleted.is_(False),
        )
        if vendor_id is not None:
            stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
        if contract_id is not None:
            stmt = stmt.where(PurchaseOrder.contract_id == contract_id)
        if project_id is not None:
            stmt = stmt.where(PurchaseOrder.project_id == project_id)
        committed, invoiced, count = self.session.execute(stmt).one()
        return Decimal(str(committed)), Decimal(str(invoiced)), int(count)
