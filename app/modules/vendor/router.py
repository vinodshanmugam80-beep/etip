"""HTTP routes for Vendor / Procurement / Contracts.

Reads require ``vendor:read``; mutations require ``vendor:manage``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import UowDep, VendorServiceDep, require_permission
from app.modules.vendor.models import (
    ContractStatus,
    PurchaseOrderStatus,
    VendorCategory,
    VendorStatus,
)
from app.modules.vendor.schemas import (
    ContractCreateRequest,
    ContractResponse,
    ContractSummary,
    ContractUpdateRequest,
    PaginatedContracts,
    PaginatedPurchaseOrders,
    PaginatedVendors,
    ProcurementSummary,
    PurchaseOrderCreateRequest,
    PurchaseOrderInvoiceRequest,
    PurchaseOrderResponse,
    PurchaseOrderUpdateRequest,
    VendorCreateRequest,
    VendorResponse,
    VendorSpendSummary,
    VendorUpdateRequest,
)

router = APIRouter(tags=["Procurement"])
_READ = Depends(require_permission("vendor:read"))
_MANAGE = Depends(require_permission("vendor:manage"))


# --- Vendors ---------------------------------------------------------------
@router.post(
    "/vendors",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create a vendor",
)
def create_vendor(
    payload: VendorCreateRequest, service: VendorServiceDep, uow: UowDep
) -> VendorResponse:
    """Create a vendor."""
    vendor = service.create_vendor(payload)
    uow.commit()
    return VendorResponse.model_validate(vendor)


@router.get(
    "/vendors",
    response_model=PaginatedVendors,
    dependencies=[_READ],
    summary="Search vendors",
)
def list_vendors(
    service: VendorServiceDep,
    query: str | None = Query(default=None),
    category: VendorCategory | None = Query(default=None),
    vendor_status: VendorStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedVendors:
    """Return a filtered, paginated page of vendors."""
    items, total = service.search_vendors(
        query=query, category=category, status=vendor_status, limit=limit, offset=offset
    )
    return PaginatedVendors(
        items=[VendorResponse.model_validate(v) for v in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/vendors/{vendor_id}",
    response_model=VendorResponse,
    dependencies=[_READ],
    summary="Get a vendor",
)
def get_vendor(vendor_id: uuid.UUID, service: VendorServiceDep) -> VendorResponse:
    """Return a single vendor."""
    return VendorResponse.model_validate(service.get_vendor(vendor_id))


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorResponse,
    dependencies=[_MANAGE],
    summary="Update a vendor",
)
def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdateRequest,
    service: VendorServiceDep,
    uow: UowDep,
) -> VendorResponse:
    """Update a vendor."""
    vendor = service.update_vendor(vendor_id, payload)
    uow.commit()
    return VendorResponse.model_validate(vendor)


@router.delete(
    "/vendors/{vendor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a vendor",
)
def delete_vendor(vendor_id: uuid.UUID, service: VendorServiceDep, uow: UowDep) -> None:
    """Soft-delete a vendor and its contracts and purchase orders."""
    service.delete_vendor(vendor_id)
    uow.commit()


@router.get(
    "/vendors/{vendor_id}/spend",
    response_model=VendorSpendSummary,
    dependencies=[_READ],
    summary="Vendor spend summary",
)
def vendor_spend(vendor_id: uuid.UUID, service: VendorServiceDep) -> VendorSpendSummary:
    """Return aggregated spend for a vendor."""
    return service.vendor_spend(vendor_id)


# --- Contracts -------------------------------------------------------------
@router.post(
    "/contracts",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create a contract",
)
def create_contract(
    payload: ContractCreateRequest, service: VendorServiceDep, uow: UowDep
) -> ContractResponse:
    """Create a contract under a vendor."""
    contract = service.create_contract(payload)
    uow.commit()
    return ContractResponse.model_validate(contract)


@router.get(
    "/contracts",
    response_model=PaginatedContracts,
    dependencies=[_READ],
    summary="Search contracts",
)
def list_contracts(
    service: VendorServiceDep,
    vendor_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    contract_status: ContractStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedContracts:
    """Return a filtered, paginated page of contracts."""
    items, total = service.search_contracts(
        vendor_id=vendor_id,
        project_id=project_id,
        status=contract_status,
        limit=limit,
        offset=offset,
    )
    return PaginatedContracts(
        items=[ContractResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/contracts/{contract_id}",
    response_model=ContractResponse,
    dependencies=[_READ],
    summary="Get a contract",
)
def get_contract(contract_id: uuid.UUID, service: VendorServiceDep) -> ContractResponse:
    """Return a single contract."""
    return ContractResponse.model_validate(service.get_contract(contract_id))


@router.patch(
    "/contracts/{contract_id}",
    response_model=ContractResponse,
    dependencies=[_MANAGE],
    summary="Update a contract",
)
def update_contract(
    contract_id: uuid.UUID,
    payload: ContractUpdateRequest,
    service: VendorServiceDep,
    uow: UowDep,
) -> ContractResponse:
    """Update a contract."""
    contract = service.update_contract(contract_id, payload)
    uow.commit()
    return ContractResponse.model_validate(contract)


@router.delete(
    "/contracts/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a contract",
)
def delete_contract(contract_id: uuid.UUID, service: VendorServiceDep, uow: UowDep) -> None:
    """Soft-delete a contract."""
    service.delete_contract(contract_id)
    uow.commit()


@router.get(
    "/contracts/{contract_id}/summary",
    response_model=ContractSummary,
    dependencies=[_READ],
    summary="Contract utilization summary",
)
def contract_summary(contract_id: uuid.UUID, service: VendorServiceDep) -> ContractSummary:
    """Return contract value against committed spend."""
    return service.contract_summary(contract_id)


# --- Purchase orders -------------------------------------------------------
@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE],
    summary="Create a purchase order",
)
def create_order(
    payload: PurchaseOrderCreateRequest, service: VendorServiceDep, uow: UowDep
) -> PurchaseOrderResponse:
    """Create a purchase order against a vendor."""
    order = service.create_order(payload)
    uow.commit()
    return PurchaseOrderResponse.model_validate(order)


@router.get(
    "/purchase-orders",
    response_model=PaginatedPurchaseOrders,
    dependencies=[_READ],
    summary="Search purchase orders",
)
def list_orders(
    service: VendorServiceDep,
    vendor_id: uuid.UUID | None = Query(default=None),
    contract_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    order_status: PurchaseOrderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedPurchaseOrders:
    """Return a filtered, paginated page of purchase orders."""
    items, total = service.search_orders(
        vendor_id=vendor_id,
        contract_id=contract_id,
        project_id=project_id,
        status=order_status,
        limit=limit,
        offset=offset,
    )
    return PaginatedPurchaseOrders(
        items=[PurchaseOrderResponse.model_validate(o) for o in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/purchase-orders/{order_id}",
    response_model=PurchaseOrderResponse,
    dependencies=[_READ],
    summary="Get a purchase order",
)
def get_order(order_id: uuid.UUID, service: VendorServiceDep) -> PurchaseOrderResponse:
    """Return a single purchase order."""
    return PurchaseOrderResponse.model_validate(service.get_order(order_id))


@router.patch(
    "/purchase-orders/{order_id}",
    response_model=PurchaseOrderResponse,
    dependencies=[_MANAGE],
    summary="Update a purchase order",
)
def update_order(
    order_id: uuid.UUID,
    payload: PurchaseOrderUpdateRequest,
    service: VendorServiceDep,
    uow: UowDep,
) -> PurchaseOrderResponse:
    """Update a purchase order."""
    order = service.update_order(order_id, payload)
    uow.commit()
    return PurchaseOrderResponse.model_validate(order)


@router.post(
    "/purchase-orders/{order_id}/invoice",
    response_model=PurchaseOrderResponse,
    dependencies=[_MANAGE],
    summary="Record invoiced amount",
)
def record_invoice(
    order_id: uuid.UUID,
    payload: PurchaseOrderInvoiceRequest,
    service: VendorServiceDep,
    uow: UowDep,
) -> PurchaseOrderResponse:
    """Record invoiced amount on a purchase order (auto-advances status)."""
    order = service.record_invoice(order_id, payload)
    uow.commit()
    return PurchaseOrderResponse.model_validate(order)


@router.delete(
    "/purchase-orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_MANAGE],
    summary="Delete a purchase order",
)
def delete_order(order_id: uuid.UUID, service: VendorServiceDep, uow: UowDep) -> None:
    """Soft-delete a purchase order."""
    service.delete_order(order_id)
    uow.commit()


# --- Procurement rollup ----------------------------------------------------
@router.get(
    "/procurement/projects/{project_id}/summary",
    response_model=ProcurementSummary,
    dependencies=[_READ],
    summary="Project procurement summary",
)
def project_procurement(project_id: uuid.UUID, service: VendorServiceDep) -> ProcurementSummary:
    """Return aggregated procurement for a project."""
    return service.project_procurement(project_id)
