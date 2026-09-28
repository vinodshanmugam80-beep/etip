"""SSO routes.

Config management requires ``sso:manage``. Login and callback are public
(pre-authentication): the tenant is carried in the signed ``state``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import SettingsDep, SsoServiceDep, UowDep, require_permission
from app.modules.auth.schemas import TokenResponse
from app.modules.sso.schemas import (
    SsoConfigResponse,
    SsoConfigUpsert,
    SsoDiscoverRequest,
    SsoLoginResponse,
)
from app.modules.sso.service import SsoService

router = APIRouter(tags=["SSO"])


@router.put(
    "/auth/sso/config",
    response_model=SsoConfigResponse,
    dependencies=[Depends(require_permission("sso:manage"))],
    summary="Create or update the tenant's OIDC configuration",
)
def upsert_sso_config(
    payload: SsoConfigUpsert, service: SsoServiceDep, uow: UowDep
) -> SsoConfigResponse:
    """Configure the organization's identity provider."""
    config = service.upsert_config(payload)
    uow.commit()
    return SsoConfigResponse.model_validate(config)


@router.get(
    "/auth/sso/config",
    response_model=SsoConfigResponse,
    dependencies=[Depends(require_permission("sso:manage"))],
    summary="Get the tenant's OIDC configuration",
)
def get_sso_config(service: SsoServiceDep) -> SsoConfigResponse:
    """Return the organization's SSO configuration (secret hidden)."""
    config = service.get_config()
    if config is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("No SSO configuration for this organization.")
    return SsoConfigResponse.model_validate(config)


@router.post(
    "/auth/sso/discover",
    response_model=SsoConfigResponse,
    dependencies=[Depends(require_permission("sso:manage"))],
    summary="Auto-fill OIDC endpoints from the issuer's discovery document",
)
def discover_sso(
    payload: SsoDiscoverRequest, service: SsoServiceDep, uow: UowDep
) -> SsoConfigResponse:
    """Populate authorize/token/JWKS URLs from <issuer>/.well-known/openid-configuration."""
    config = service.discover(payload.issuer)
    uow.commit()
    return SsoConfigResponse.model_validate(config)


@router.get(
    "/auth/sso/login",
    response_model=SsoLoginResponse,
    summary="Begin SSO login (returns the IdP authorize URL)",
)
def sso_login(
    settings: SettingsDep,
    uow: UowDep,
    organization_slug: str = Query(...),
) -> SsoLoginResponse:
    """Return the identity-provider URL to redirect the user to."""
    service = SsoService(uow, settings)
    return SsoLoginResponse(authorize_url=service.begin_login(organization_slug))


@router.get(
    "/auth/sso/callback",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="SSO callback — exchanges the code and returns ETIP tokens",
)
def sso_callback(
    settings: SettingsDep,
    uow: UowDep,
    code: str = Query(...),
    state: str = Query(...),
) -> TokenResponse:
    """Complete the OIDC flow and issue ETIP access/refresh tokens."""
    service = SsoService(uow, settings)
    access, refresh, expires_in = service.complete_login(state, code)
    uow.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=expires_in)
