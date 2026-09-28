"""Engine and session factory.

Builds a single SQLAlchemy engine and a ``sessionmaker`` from application
settings. SQLite (used only for tests) receives connection arguments that
allow cross-thread usage; PostgreSQL receives connection pooling settings.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_engine(settings: Settings) -> Engine:
    """Construct the SQLAlchemy engine appropriate for the configured URL."""
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_engine(
            url,
            echo=settings.db_echo,
            connect_args={"check_same_thread": False},
            future=True,
        )
    return create_engine(
        url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


_settings = get_settings()
engine: Engine = build_engine(_settings)
SessionFactory: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, class_=Session
)
