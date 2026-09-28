"""HTTP routes for the Organization Management module.

Thin adapters over :class:`OrganizationService`. Every mutating route is guarded
by an RBAC permission; reads require the corresponding ``:read`` permission.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import OrganizationServiceDep, UowDep, require_permission
from app.modules.organization.schemas import (
    BusinessUnitCreateRequest,
    BusinessUnitResponse,
    BusinessUnitUpdateRequest,
    DepartmentCreateRequest,
    DepartmentMemberAddRequest,
    DepartmentMemberResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    MessageResponse,
    OrganizationSettingsResponse,
    OrganizationSettingsUpdateRequest,
)

router = APIRouter(prefix="/organization", tags=["Organization Management"])


# --- Business units --------------------------------------------------------
@router.post(
    "/business-units",
    response_model=BusinessUnitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Create a business unit",
)
def create_business_unit(
    payload: BusinessUnitCreateRequest,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> BusinessUnitResponse:
    """Create a business unit within the caller's organization."""
    unit = service.create_business_unit(
        name=payload.name,
        code=payload.code,
        description=payload.description,
        lead_user_id=payload.lead_user_id,
    )
    uow.commit()
    return BusinessUnitResponse.model_validate(unit)


@router.get(
    "/business-units",
    response_model=list[BusinessUnitResponse],
    dependencies=[Depends(require_permission("organization:read"))],
    summary="List business units",
)
def list_business_units(
    service: OrganizationServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[BusinessUnitResponse]:
    """Return a page of business units."""
    units = service.list_business_units(limit=limit, offset=offset)
    return [BusinessUnitResponse.model_validate(u) for u in units]


@router.get(
    "/business-units/{unit_id}",
    response_model=BusinessUnitResponse,
    dependencies=[Depends(require_permission("organization:read"))],
    summary="Get a business unit",
)
def get_business_unit(unit_id: uuid.UUID, service: OrganizationServiceDep) -> BusinessUnitResponse:
    """Return a single business unit by id."""
    return BusinessUnitResponse.model_validate(service.get_business_unit(unit_id))


@router.patch(
    "/business-units/{unit_id}",
    response_model=BusinessUnitResponse,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Update a business unit",
)
def update_business_unit(
    unit_id: uuid.UUID,
    payload: BusinessUnitUpdateRequest,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> BusinessUnitResponse:
    """Apply a partial update to a business unit."""
    unit = service.update_business_unit(
        unit_id,
        name=payload.name,
        description=payload.description,
        lead_user_id=payload.lead_user_id,
        is_active=payload.is_active,
    )
    uow.commit()
    return BusinessUnitResponse.model_validate(unit)


@router.delete(
    "/business-units/{unit_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Delete a business unit",
)
def delete_business_unit(
    unit_id: uuid.UUID, service: OrganizationServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a business unit (blocked if it still has departments)."""
    service.delete_business_unit(unit_id)
    uow.commit()
    return MessageResponse(detail="Business unit deleted.")


# --- Departments -----------------------------------------------------------
@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Create a department",
)
def create_department(
    payload: DepartmentCreateRequest,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> DepartmentResponse:
    """Create a department within the caller's organization."""
    dept = service.create_department(
        name=payload.name,
        code=payload.code,
        description=payload.description,
        business_unit_id=payload.business_unit_id,
        parent_department_id=payload.parent_department_id,
        head_user_id=payload.head_user_id,
    )
    uow.commit()
    return DepartmentResponse.model_validate(dept)


@router.get(
    "/departments",
    response_model=list[DepartmentResponse],
    dependencies=[Depends(require_permission("organization:read"))],
    summary="List departments",
)
def list_departments(
    service: OrganizationServiceDep,
    business_unit_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[DepartmentResponse]:
    """Return departments, optionally filtered by business unit."""
    departments = service.list_departments(
        business_unit_id=business_unit_id, limit=limit, offset=offset
    )
    return [DepartmentResponse.model_validate(d) for d in departments]


@router.get(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(require_permission("organization:read"))],
    summary="Get a department",
)
def get_department(department_id: uuid.UUID, service: OrganizationServiceDep) -> DepartmentResponse:
    """Return a single department by id."""
    return DepartmentResponse.model_validate(service.get_department(department_id))


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Update a department",
)
def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdateRequest,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> DepartmentResponse:
    """Apply a partial update to a department."""
    dept = service.update_department(
        department_id,
        name=payload.name,
        description=payload.description,
        business_unit_id=payload.business_unit_id,
        parent_department_id=payload.parent_department_id,
        head_user_id=payload.head_user_id,
        is_active=payload.is_active,
    )
    uow.commit()
    return DepartmentResponse.model_validate(dept)


@router.delete(
    "/departments/{department_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Delete a department",
)
def delete_department(
    department_id: uuid.UUID, service: OrganizationServiceDep, uow: UowDep
) -> MessageResponse:
    """Soft-delete a department (blocked if it has child departments)."""
    service.delete_department(department_id)
    uow.commit()
    return MessageResponse(detail="Department deleted.")


# --- Settings --------------------------------------------------------------
@router.get(
    "/settings",
    response_model=OrganizationSettingsResponse,
    dependencies=[Depends(require_permission("organization:read"))],
    summary="Get organization settings",
)
def get_settings(service: OrganizationServiceDep, uow: UowDep) -> OrganizationSettingsResponse:
    """Return the tenant's settings, initialising defaults on first access."""
    settings = service.get_settings()
    uow.commit()
    return OrganizationSettingsResponse.model_validate(settings)


@router.put(
    "/settings",
    response_model=OrganizationSettingsResponse,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Update organization settings",
)
def update_settings(
    payload: OrganizationSettingsUpdateRequest,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> OrganizationSettingsResponse:
    """Apply a partial update to the tenant's settings."""
    settings = service.update_settings(
        currency=payload.currency,
        timezone=payload.timezone,
        date_format=payload.date_format,
        fiscal_year_start_month=payload.fiscal_year_start_month,
        week_start_day=payload.week_start_day,
    )
    uow.commit()
    return OrganizationSettingsResponse.model_validate(settings)


# --- Department memberships ------------------------------------------------
@router.post(
    "/departments/{department_id}/members",
    response_model=DepartmentMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Add a user to a department",
)
def add_member(
    department_id: uuid.UUID,
    payload: DepartmentMemberAddRequest,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> DepartmentMemberResponse:
    """Add a user to a department (enforces a single primary department)."""
    membership = service.add_member(
        department_id, user_id=payload.user_id, is_primary=payload.is_primary
    )
    uow.commit()
    return DepartmentMemberResponse.model_validate(membership)


@router.get(
    "/departments/{department_id}/members",
    response_model=list[DepartmentMemberResponse],
    dependencies=[Depends(require_permission("organization:read"))],
    summary="List department members",
)
def list_members(
    department_id: uuid.UUID, service: OrganizationServiceDep
) -> list[DepartmentMemberResponse]:
    """Return the memberships of a department."""
    members = service.list_members(department_id)
    return [DepartmentMemberResponse.model_validate(m) for m in members]


@router.delete(
    "/departments/{department_id}/members/{user_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("organization:update"))],
    summary="Remove a user from a department",
)
def remove_member(
    department_id: uuid.UUID,
    user_id: uuid.UUID,
    service: OrganizationServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Remove a user's membership from a department."""
    service.remove_member(department_id, user_id)
    uow.commit()
    return MessageResponse(detail="Member removed.")
