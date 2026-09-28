"""Pydantic v2 schemas for Vendor / Procurement / Contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.modules.vendor.models import (
    ContractStatus,
    ContractType,
    PurchaseOrderStatus,
    VendorCategory,
    VendorStatus,
)


# --- Vendor ----------------------------------------------------------------
class VendorCreateRequest(BaseModel):
    """Payload to create a vendor."""

    name: str = Field(min_length=2, max_length=300)
    code: str = Field(min_length=2, max_length=50)
    category: VendorCategory = VendorCategory.OTHER
    status: VendorStatus = VendorStatus.ACTIVE
    contact_name: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=320)
    description: str = Field(default="", max_length=4000)


class VendorUpdateRequest(BaseModel):
    """Payload to update a vendor (all optional)."""

    name: str | None = Field(default=None, min_length=2, max_length=300)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    category: VendorCategory | None = None
    status: VendorStatus | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    description: str | None = Field(default=None, max_length=4000)


class VendorResponse(BaseModel):
    """A vendor."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    category: VendorCategory
    status: VendorStatus
    contact_name: str
    contact_email: str
    description: str
    created_date: datetime
    version: int


class PaginatedVendors(BaseModel):
    """A page of vendors."""

    items: list[VendorResponse]
    total: int
    limit: int
    offset: int


# --- Contract --------------------------------------------------------------
class ContractCreateRequest(BaseModel):
    """Payload to create a contract."""

    vendor_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    reference: str = Field(default="", max_length=100)
    project_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    contract_type: ContractType = ContractType.FIXED_PRICE
    status: ContractStatus = ContractStatus.DRAFT
    value: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class ContractUpdateRequest(BaseModel):
    """Payload to update a contract (all optional)."""

    title: str | None = Field(default=None, min_length=2, max_length=300)
    reference: str | None = Field(default=None, max_length=100)
    project_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    contract_type: ContractType | None = None
    status: ContractStatus | None = None
    value: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    start_date: date | None = None
    end_date: date | None = None


class ContractResponse(BaseModel):
    """A contract."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    vendor_id: uuid.UUID
    project_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    title: str
    reference: str
    contract_type: ContractType
    status: ContractStatus
    value: Decimal
    currency: str
    start_date: date | None
    end_date: date | None
    created_date: datetime
    version: int


class PaginatedContracts(BaseModel):
    """A page of contracts."""

    items: list[ContractResponse]
    total: int
    limit: int
    offset: int


# --- Purchase order --------------------------------------------------------
class PurchaseOrderCreateRequest(BaseModel):
    """Payload to create a purchase order."""

    vendor_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    reference: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    status: PurchaseOrderStatus = PurchaseOrderStatus.DRAFT
    committed_amount: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2
    )
    invoiced_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    order_date: date | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class PurchaseOrderUpdateRequest(BaseModel):
    """Payload to update a purchase order (all optional)."""

    contract_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    status: PurchaseOrderStatus | None = None
    committed_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)


class PurchaseOrderInvoiceRequest(BaseModel):
    """Payload to record invoiced amount on a purchase order."""

    invoiced_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class PurchaseOrderResponse(BaseModel):
    """A purchase order with computed outstanding amount."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    vendor_id: uuid.UUID
    contract_id: uuid.UUID | None
    project_id: uuid.UUID | None
    reference: str
    description: str
    status: PurchaseOrderStatus
    committed_amount: Decimal
    invoiced_amount: Decimal
    currency: str
    order_date: date | None
    created_date: datetime
    version: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outstanding_amount(self) -> Decimal:
        """Committed minus invoiced (spend not yet billed)."""
        return self.committed_amount - self.invoiced_amount


class PaginatedPurchaseOrders(BaseModel):
    """A page of purchase orders."""

    items: list[PurchaseOrderResponse]
    total: int
    limit: int
    offset: int


# --- Summaries -------------------------------------------------------------
class VendorSpendSummary(BaseModel):
    """Aggregated spend for a vendor across its purchase orders."""

    vendor_id: uuid.UUID
    vendor_name: str
    po_count: int
    total_committed: Decimal
    total_invoiced: Decimal
    total_outstanding: Decimal


class ContractSummary(BaseModel):
    """Contract value against committed spend."""

    contract_id: uuid.UUID
    title: str
    value: Decimal
    po_count: int
    total_committed: Decimal
    total_invoiced: Decimal
    utilization_percent: float | None


class ProcurementSummary(BaseModel):
    """Aggregated procurement for a scope (e.g. a project)."""

    scope: str
    scope_id: uuid.UUID | None
    po_count: int
    total_committed: Decimal
    total_invoiced: Decimal
    total_outstanding: Decimal
