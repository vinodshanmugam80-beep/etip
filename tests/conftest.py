"""Shared test fixtures.

Builds an isolated in-memory SQLite database per test, creates the full schema
from the ORM metadata, and overrides the Unit-of-Work dependency so the running
application uses the test database. A ``TestClient`` exercises the real ASGI
app end to end.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.dependencies import get_uow
from app.db.base import Base
from app.db.unit_of_work import UnitOfWork
from app.main import create_app

# When TEST_DATABASE_URL is set (e.g. a PostgreSQL DSN in CI) the suite runs
# against that database; otherwise it uses an isolated in-memory SQLite database.
_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    """Provide a sessionmaker bound to a fresh database (SQLite or Postgres)."""
    if _TEST_DATABASE_URL:
        engine = create_engine(_TEST_DATABASE_URL)
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    """Return a TestClient whose Unit of Work uses the test database."""
    app = create_app()

    def _override_uow() -> Iterator[UnitOfWork]:
        with UnitOfWork(session_factory) as uow:
            yield uow

    app.dependency_overrides[get_uow] = _override_uow
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def registered_org(client: TestClient) -> dict[str, str]:
    """Register an organization and return the login-ready credentials."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Contoso Ltd",
            "admin_email": "admin@contoso.com",
            "admin_full_name": "Ada Admin",
            "password": "Str0ng-Passphrase!",
        },
    )
    assert response.status_code == 201, response.text
    return {
        "organization_slug": "contoso-ltd",
        "email": "admin@contoso.com",
        "password": "Str0ng-Passphrase!",
    }


def _login(client: TestClient, creds: dict[str, str]) -> dict[str, str]:
    """Helper performing a login and returning the token payload."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": creds["organization_slug"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def admin_headers(client: TestClient, registered_org: dict[str, str]) -> dict[str, str]:
    """Return Authorization headers for the seeded organization admin."""
    tokens = _login(client, registered_org)
    return {"Authorization": f"Bearer {tokens['access_token']}"}
