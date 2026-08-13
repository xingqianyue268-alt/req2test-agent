"""Synchronous SQLAlchemy engine and session lifecycle helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ..settings import get_settings


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transaction boundary reusable by later Worker persistence."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """Yield one synchronous Session for a FastAPI request."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def database_is_ready() -> bool:
    """Return whether the configured PostgreSQL database accepts a trivial query."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # The readiness endpoint must translate dependency failures to 503.
        return False
    return True
