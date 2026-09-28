"""Vendor / Procurement / Contracts models.

A ``Vendor`` is a supplier; a ``Contract`` is an agreement with that vendor
(optionally tied to a project); a ``PurchaseOrder`` is a spend commitment against
a vendor (optionally under a contract and against a project). Committed vs
invoiced amounts give outstanding spend, which ties supplier cost into the
finance and benefits picture. Additive: the Finance module is untouched.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseEntity, TenantMixin
from app.db.enums import enum_column


class VendorCategory(enum.StrEnum):
    """The nature of a vendor's offering."""

    TECHNOLOGY = "technology"
    PROFESSIONAL_SERVICES = "prof_services"
    STAFFING = "staffing"
    HARDWARE = "hardware"
    FACILITIES = "facilities"
    OTHER = "other"


class VendorStatus(enum.StrEnum):
    """Standing of a vendor."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BLACKLISTED = "blacklisted"


class ContractType(enum.StrEnum):
    """Commercial model of a contract."""

    FIXED_PRICE = "fixed_price"
    TIME_AND_MATERIALS = "time_and_materials"
    RETAINER = "retainer"
    SUBSCRIPTION = "subscription"
    OTHER = "other"


class ContractStatus(enum.StrEnum):
    """Lifecycle of a contract."""

    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    COMPLETED = "completed"


class PurchaseOrderStatus(enum.StrEnum):
    """Lifecycle of a purchase order / spend commitment."""

    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_INVOICED = "partially_invoiced"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"


class Vendor(BaseEntity, TenantMixin):
    """A supplier the organization procures from."""

    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[VendorCategory] = mapped_column(
        enum_column(VendorCategory), default=VendorCategory.OTHER, index=True
    )
    status: Mapped[VendorStatus] = mapped_column(
        enum_column(VendorStatus), default=VendorStatus.ACTIVE, index=True
    )
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    description: Mapped[str] = mapped_column(String(4000), default="")


class Contract(BaseEntity, TenantMixin):
    """An agreement with a vendor, optionally tied to a project."""

    __tablename__ = "contracts"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), default="")
    contract_type: Mapped[ContractType] = mapped_column(
        enum_column(ContractType), default=ContractType.FIXED_PRICE, index=True
    )
    status: Mapped[ContractStatus] = mapped_column(
        enum_column(ContractStatus), default=ContractStatus.DRAFT, index=True
    )
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class PurchaseOrder(BaseEntity, TenantMixin):
    """A spend commitment against a vendor (optionally under a contract)."""

    __tablename__ = "purchase_orders"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        enum_column(PurchaseOrderStatus), default=PurchaseOrderStatus.DRAFT, index=True
    )
    committed_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    invoiced_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
