"""Central application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _positive_int(name: str, default: int, *, allow_zero: bool = False) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if value < minimum:
        qualifier = "zero or greater" if allow_zero else "greater than zero"
        raise ValueError(f"{name} must be {qualifier}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Infrastructure settings shared by FastAPI, Alembic and Celery processes."""

    database_url: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://req2test:req2test_dev@localhost:5432/req2test",
            ),
            db_pool_size=_positive_int("DB_POOL_SIZE", 5),
            db_max_overflow=_positive_int("DB_MAX_OVERFLOW", 10, allow_zero=True),
            db_pool_timeout=_positive_int("DB_POOL_TIMEOUT", 30),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached immutable settings object for the current process."""

    return Settings.from_env()
