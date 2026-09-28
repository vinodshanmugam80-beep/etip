"""HTTP routes for the authentication module.

Thin adapters: validate input via schemas, delegate to :class:`AuthService`,
commit the Unit of Work, and shape the response. All error translation is
handled centrally by the exception handlers registered in
:mod:`app.core.middleware`.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencies import (
    AuthServiceDep,
    CurrentUser,
    UowDep,
)
from app.modules.auth.schemas import (
    LoginRequest,
    MessageResponse,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RefreshRequest,
    RegisterOrganizationRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organization and its first administrator",
)
def register_organization(
    payload: RegisterOrganizationRequest,
    service: AuthServiceDep,
    uow: UowDep,
) -> UserResponse:
    """Bootstrap a tenant and return the created administrator account."""
    _, admin = service.register_organization(
        name=payload.organization_name,
        admin_email=payload.admin_email,
        admin_full_name=payload.admin_full_name,
        password=payload.password,
    )
    uow.commit()
    return UserResponse.model_validate(admin)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with password (and MFA when enabled)",
)
def login(
    payload: LoginRequest,
    service: AuthServiceDep,
    uow: UowDep,
) -> TokenResponse:
    """Return an access/refresh token pair for valid credentials."""
    access, refresh, expires_in = service.authenticate(
        organization_slug=payload.organization_slug,
        email=payload.email,
        password=payload.password,
        mfa_code=payload.mfa_code,
    )
    uow.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=expires_in)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token for a new token pair",
)
def refresh_tokens(
    payload: RefreshRequest,
    service: AuthServiceDep,
    uow: UowDep,
) -> TokenResponse:
    """Exchange a valid refresh token for a rotated token pair."""
    access, refresh, expires_in = service.refresh(payload.refresh_token)
    uow.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=expires_in)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke a refresh token",
)
def logout(
    payload: RefreshRequest,
    service: AuthServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Revoke the supplied refresh token (idempotent)."""
    service.logout(payload.refresh_token)
    uow.commit()
    return MessageResponse(detail="Logged out.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the current authenticated user",
)
def read_current_user(current_user: CurrentUser) -> UserResponse:
    """Return the profile of the authenticated user."""
    return UserResponse.model_validate(current_user)


@router.get(
    "/me/permissions",
    response_model=list[str],
    summary="Return the current user's effective permission codes",
)
def read_current_permissions(current_user: CurrentUser) -> list[str]:
    """Return the sorted set of permission codes granted via the user's roles."""
    return sorted(current_user.permission_codes)


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    summary="Begin MFA enrolment (returns a TOTP secret and URI)",
)
def enroll_mfa(
    current_user: CurrentUser,
    service: AuthServiceDep,
    uow: UowDep,
) -> MfaEnrollResponse:
    """Generate a provisional TOTP secret for authenticator-app setup."""
    secret, uri = service.begin_mfa_enrollment(current_user)
    uow.commit()
    return MfaEnrollResponse(secret=secret, otpauth_uri=uri)


@router.post(
    "/mfa/verify",
    response_model=MessageResponse,
    summary="Confirm MFA enrolment with a TOTP code",
)
def verify_mfa(
    payload: MfaVerifyRequest,
    current_user: CurrentUser,
    service: AuthServiceDep,
    uow: UowDep,
) -> MessageResponse:
    """Activate MFA after verifying the first TOTP code."""
    service.confirm_mfa_enrollment(current_user, payload.code)
    uow.commit()
    return MessageResponse(detail="MFA enabled.")
