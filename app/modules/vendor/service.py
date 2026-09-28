"""Vendor / Procurement / Contracts service.

Manages vendors, contracts and purchase orders, records invoicing against POs,
and derives vendor-spend, contract-utilization and project-procurement rollups.
Validates vendor / contract / project / owner references via repositories (never
services) and records audit entries on mutations.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lifecycle import validate_status_transition
from app.core.logging import get_logger
from app.db.unit_of_work import UnitOfWork
from app.modules.auth.repository import UserRepository
from app.modules.project.repository import ProjectRepository
from app.modules.vendor.models import (
    Contract,
    ContractStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
    Vendor,
    VendorCategory,
    VendorStatus,
)
from app.modules.vendor.repository import (
    ContractRepository,
    PurchaseOrderRepository,
    VendorRepository,
)
from app.modules.vendor.schemas import (
    ContractCreateRequest,
    ContractSummary,
    ContractUpdateRequest,
    ProcurementSummary,
    PurchaseOrderCreateRequest,
    PurchaseOrderInvoiceRequest,
    PurchaseOrderUpdateRequest,
    VendorCreateRequest,
    VendorSpendSummary,
    VendorUpdateRequest,
)

logger = get_logger(__name__)

_PO_TRANSITIONS: dict[PurchaseOrderStatus, set[PurchaseOrderStatus]] = {
    PurchaseOrderStatus.DRAFT: {
        PurchaseOrderStatus.ISSUED,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.ISSUED: {
        PurchaseOrderStatus.PARTIALLY_INVOICED,
        PurchaseOrderStatus.INVOICED,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.PARTIALLY_INVOICED: {
        PurchaseOrderStatus.INVOICED,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.INVOICED: {
        PurchaseOrderStatus.PAID,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.PAID: set(),
    PurchaseOrderStatus.CANCELLED: set(),
}


class VendorService:
    """Manage procurement, scoped to the caller's tenant."""

    def __init__(self, uow: UnitOfWork, *, organization_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self._uow = uow
        self._org_id = organization_id
        self._actor_id = actor_id
        session = uow.session
        self.vendors = VendorRepository(session)
        self.contracts = ContractRepository(session)
        self.orders = PurchaseOrderRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------
    def create_vendor(self, payload: VendorCreateRequest) -> Vendor:
        """Create a vendor (unique code per tenant)."""
        if self.vendors.get_by_code(self._org_id, payload.code) is not None:
            raise ConflictError("A vendor with that code already exists.")
        vendor = Vendor(
            organization_id=self._org_id,
            name=payload.name,
            code=payload.code,
            category=payload.category,
            status=payload.status,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            description=payload.description,
            created_by=self._actor_id,
        )
        vendor = self.vendors.add(vendor)
        self._audit("Vendor", vendor.id, "create", f"Created vendor '{vendor.name}'")
        return vendor

    def update_vendor(self, vendor_id: uuid.UUID, payload: VendorUpdateRequest) -> Vendor:
        """Update a vendor."""
        vendor = self._get_vendor_or_404(vendor_id)
        if payload.code is not None and payload.code.lower() != vendor.code.lower():
            if self.vendors.get_by_code(self._org_id, payload.code) is not None:
                raise ConflictError("A vendor with that code already exists.")
            vendor.code = payload.code
        for field in (
            "name",
            "category",
            "status",
            "contact_name",
            "contact_email",
            "description",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(vendor, field, value)
        vendor.modified_by = self._actor_id
        vendor = self.vendors.update(vendor)
        self._audit("Vendor", vendor.id, "update", f"Updated vendor '{vendor.name}'")
        return vendor

    def delete_vendor(self, vendor_id: uuid.UUID) -> None:
        """Soft-delete a vendor and its contracts and purchase orders."""
        vendor = self._get_vendor_or_404(vendor_id)
        for contract in self.contracts.search(self._org_id, vendor_id=vendor_id, limit=1000):
            self.contracts.soft_delete(contract, actor_id=self._actor_id)
        for order in self.orders.search(self._org_id, vendor_id=vendor_id, limit=1000):
            self.orders.soft_delete(order, actor_id=self._actor_id)
        self.vendors.soft_delete(vendor, actor_id=self._actor_id)
        self._audit("Vendor", vendor.id, "delete", f"Deleted vendor '{vendor.name}'")

    def get_vendor(self, vendor_id: uuid.UUID) -> Vendor:
        """Return a vendor or raise ``NotFoundError``."""
        return self._get_vendor_or_404(vendor_id)

    def search_vendors(
        self,
        *,
        query: str | None,
        category: VendorCategory | None,
        status: VendorStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Vendor], int]:
        """Return a filtered page of vendors and the total count."""
        items = list(
            self.vendors.search(
                self._org_id,
                query=query,
                category=category,
                status=status,
                limit=limit,
                offset=offset,
            )
        )
        total = self.vendors.count(self._org_id, query=query, category=category, status=status)
        return items, total

    # ------------------------------------------------------------------
    # Contracts
    # ------------------------------------------------------------------
    def create_contract(self, payload: ContractCreateRequest) -> Contract:
        """Create a contract under a vendor."""
        self._get_vendor_or_404(payload.vendor_id)
        self._validate_project(payload.project_id)
        self._validate_owner(payload.owner_user_id)
        contract = Contract(
            organization_id=self._org_id,
            vendor_id=payload.vendor_id,
            project_id=payload.project_id,
            owner_user_id=payload.owner_user_id,
            title=payload.title,
            reference=payload.reference,
            contract_type=payload.contract_type,
            status=payload.status,
            value=payload.value,
            currency=payload.currency,
            start_date=payload.start_date,
            end_date=payload.end_date,
            created_by=self._actor_id,
        )
        contract = self.contracts.add(contract)
        self._audit("Contract", contract.id, "create", f"Created contract '{contract.title}'")
        return contract

    def update_contract(self, contract_id: uuid.UUID, payload: ContractUpdateRequest) -> Contract:
        """Update a contract."""
        contract = self._get_contract_or_404(contract_id)
        if payload.project_id is not None:
            self._validate_project(payload.project_id)
            contract.project_id = payload.project_id
        if payload.owner_user_id is not None:
            self._validate_owner(payload.owner_user_id)
            contract.owner_user_id = payload.owner_user_id
        for field in (
            "title",
            "reference",
            "contract_type",
            "status",
            "value",
            "start_date",
            "end_date",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(contract, field, value)
        contract.modified_by = self._actor_id
        contract = self.contracts.update(contract)
        self._audit("Contract", contract.id, "update", f"Updated contract '{contract.title}'")
        return contract

    def delete_contract(self, contract_id: uuid.UUID) -> None:
        """Soft-delete a contract."""
        contract = self._get_contract_or_404(contract_id)
        self.contracts.soft_delete(contract, actor_id=self._actor_id)
        self._audit("Contract", contract.id, "delete", f"Deleted contract '{contract.title}'")

    def get_contract(self, contract_id: uuid.UUID) -> Contract:
        """Return a contract or raise ``NotFoundError``."""
        return self._get_contract_or_404(contract_id)

    def search_contracts(
        self,
        *,
        vendor_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        status: ContractStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Contract], int]:
        """Return a filtered page of contracts and the total count."""
        items = list(
            self.contracts.search(
                self._org_id,
                vendor_id=vendor_id,
                project_id=project_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )
        total = self.contracts.count(
            self._org_id, vendor_id=vendor_id, project_id=project_id, status=status
        )
        return items, total

    # ------------------------------------------------------------------
    # Purchase orders
    # ------------------------------------------------------------------
    def create_order(self, payload: PurchaseOrderCreateRequest) -> PurchaseOrder:
        """Create a purchase order against a vendor."""
        self._get_vendor_or_404(payload.vendor_id)
        if payload.contract_id is not None:
            contract = self._get_contract_or_404(payload.contract_id)
            if contract.vendor_id != payload.vendor_id:
                raise ValidationError("Contract does not belong to the given vendor.")
        self._validate_project(payload.project_id)
        order = PurchaseOrder(
            organization_id=self._org_id,
            vendor_id=payload.vendor_id,
            contract_id=payload.contract_id,
            project_id=payload.project_id,
            reference=payload.reference,
            description=payload.description,
            status=payload.status,
            committed_amount=payload.committed_amount,
            invoiced_amount=payload.invoiced_amount,
            currency=payload.currency,
            order_date=payload.order_date,
            created_by=self._actor_id,
        )
        order = self.orders.add(order)
        self._audit(
            "PurchaseOrder",
            order.id,
            "create",
            f"Created PO '{order.reference or order.id}'",
        )
        return order

    def update_order(
        self, order_id: uuid.UUID, payload: PurchaseOrderUpdateRequest
    ) -> PurchaseOrder:
        """Update a purchase order."""
        order = self._get_order_or_404(order_id)
        if payload.status is not None:
            validate_status_transition(_PO_TRANSITIONS, order.status, payload.status)
            order.status = payload.status
        if payload.contract_id is not None:
            contract = self._get_contract_or_404(payload.contract_id)
            if contract.vendor_id != order.vendor_id:
                raise ValidationError("Contract does not belong to the PO's vendor.")
            order.contract_id = payload.contract_id
        if payload.project_id is not None:
            self._validate_project(payload.project_id)
            order.project_id = payload.project_id
        for field in ("reference", "description", "committed_amount"):
            value = getattr(payload, field)
            if value is not None:
                setattr(order, field, value)
        order.modified_by = self._actor_id
        order = self.orders.update(order)
        self._audit("PurchaseOrder", order.id, "update", "Updated purchase order")
        return order

    def record_invoice(
        self, order_id: uuid.UUID, payload: PurchaseOrderInvoiceRequest
    ) -> PurchaseOrder:
        """Record invoiced amount; auto-advances status."""
        order = self._get_order_or_404(order_id)
        order.invoiced_amount = payload.invoiced_amount
        order.status = self._infer_status(order)
        order.modified_by = self._actor_id
        order = self.orders.update(order)
        self._audit(
            "PurchaseOrder",
            order.id,
            "invoice",
            f"Recorded invoiced {order.invoiced_amount}",
        )
        return order

    def delete_order(self, order_id: uuid.UUID) -> None:
        """Soft-delete a purchase order."""
        order = self._get_order_or_404(order_id)
        self.orders.soft_delete(order, actor_id=self._actor_id)
        self._audit("PurchaseOrder", order.id, "delete", "Deleted purchase order")

    def get_order(self, order_id: uuid.UUID) -> PurchaseOrder:
        """Return a purchase order or raise ``NotFoundError``."""
        return self._get_order_or_404(order_id)

    def search_orders(
        self,
        *,
        vendor_id: uuid.UUID | None,
        contract_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        status: PurchaseOrderStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PurchaseOrder], int]:
        """Return a filtered page of purchase orders and the total count."""
        items = list(
            self.orders.search(
                self._org_id,
                vendor_id=vendor_id,
                contract_id=contract_id,
                project_id=project_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )
        total = self.orders.count(
            self._org_id,
            vendor_id=vendor_id,
            contract_id=contract_id,
            project_id=project_id,
            status=status,
        )
        return items, total

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------
    def vendor_spend(self, vendor_id: uuid.UUID) -> VendorSpendSummary:
        """Return aggregated spend for a vendor across its POs."""
        vendor = self._get_vendor_or_404(vendor_id)
        committed, invoiced, count = self.orders.totals(self._org_id, vendor_id=vendor_id)
        return VendorSpendSummary(
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            po_count=count,
            total_committed=committed,
            total_invoiced=invoiced,
            total_outstanding=committed - invoiced,
        )

    def contract_summary(self, contract_id: uuid.UUID) -> ContractSummary:
        """Return contract value against committed spend."""
        contract = self._get_contract_or_404(contract_id)
        committed, invoiced, count = self.orders.totals(self._org_id, contract_id=contract_id)
        utilization = (
            round(float(committed / contract.value) * 100, 2) if contract.value > 0 else None
        )
        return ContractSummary(
            contract_id=contract.id,
            title=contract.title,
            value=contract.value,
            po_count=count,
            total_committed=committed,
            total_invoiced=invoiced,
            utilization_percent=utilization,
        )

    def project_procurement(self, project_id: uuid.UUID) -> ProcurementSummary:
        """Return aggregated procurement for a project."""
        self._validate_project(project_id, required=True)
        committed, invoiced, count = self.orders.totals(self._org_id, project_id=project_id)
        return ProcurementSummary(
            scope="project",
            scope_id=project_id,
            po_count=count,
            total_committed=committed,
            total_invoiced=invoiced,
            total_outstanding=committed - invoiced,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_status(order: PurchaseOrder) -> PurchaseOrderStatus:
        if order.committed_amount <= 0:
            return order.status
        if order.invoiced_amount >= order.committed_amount:
            return PurchaseOrderStatus.INVOICED
        if order.invoiced_amount > Decimal("0.00"):
            return PurchaseOrderStatus.PARTIALLY_INVOICED
        return order.status

    def _get_vendor_or_404(self, vendor_id: uuid.UUID) -> Vendor:
        vendor = self.vendors.get(vendor_id, organization_id=self._org_id)
        if vendor is None:
            raise NotFoundError("Vendor not found.")
        return vendor

    def _get_contract_or_404(self, contract_id: uuid.UUID) -> Contract:
        contract = self.contracts.get(contract_id, organization_id=self._org_id)
        if contract is None:
            raise NotFoundError("Contract not found.")
        return contract

    def _get_order_or_404(self, order_id: uuid.UUID) -> PurchaseOrder:
        order = self.orders.get(order_id, organization_id=self._org_id)
        if order is None:
            raise NotFoundError("Purchase order not found.")
        return order

    def _validate_project(self, project_id: uuid.UUID | None, *, required: bool = False) -> None:
        if project_id is None:
            if required:
                raise NotFoundError("Project not found.")
            return
        if self.projects.get(project_id, organization_id=self._org_id) is None:
            if required:
                raise NotFoundError("Project not found.")
            raise ValidationError(
                "Project does not belong to this organization.",
                details={"project_id": str(project_id)},
            )

    def _validate_owner(self, owner_user_id: uuid.UUID | None) -> None:
        if owner_user_id is None:
            return
        if self.users.get(owner_user_id, organization_id=self._org_id) is None:
            raise ValidationError(
                "Owner does not belong to this organization.",
                details={"owner_user_id": str(owner_user_id)},
            )

    def _audit(self, entity_type: str, entity_id: uuid.UUID, action: str, summary: str) -> None:
        self._uow.record_audit(
            entity_type,
            entity_id,
            action,
            summary,
            actor_id=self._actor_id,
            organization_id=self._org_id,
        )
