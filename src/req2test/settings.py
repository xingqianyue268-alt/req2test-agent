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
    environment: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    allow_anonymous_demo: bool
    auth_cookie_secure: bool

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("REQ2TEST_ENV", "local").strip().lower()
        jwt_secret = os.getenv(
            "JWT_SECRET_KEY", "development-only-change-me-before-production"
        )
        dangerous_secrets = {
            "",
            "changeme",
            "secret",
            "development-only-change-me-before-production",
            "replace-with-a-random-production-secret",
        }
        if environment == "production" and jwt_secret.strip().lower() in dangerous_secrets:
            raise ValueError("JWT_SECRET_KEY must be set to a secure unique value in production")
        if environment == "production" and len(jwt_secret.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters in production")
        algorithm = os.getenv("JWT_ALGORITHM", "HS256").strip().upper()
        if algorithm not in {"HS256", "HS384", "HS512"}:
            raise ValueError("JWT_ALGORITHM must be HS256, HS384, or HS512")
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://req2test:req2test_dev@localhost:5432/req2test",
            ),
            db_pool_size=_positive_int("DB_POOL_SIZE", 5),
            db_max_overflow=_positive_int("DB_MAX_OVERFLOW", 10, allow_zero=True),
            db_pool_timeout=_positive_int("DB_POOL_TIMEOUT", 30),
            environment=environment,
            jwt_secret_key=jwt_secret,
            jwt_algorithm=algorithm,
            jwt_access_token_expire_minutes=_positive_int(
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30
            ),
            allow_anonymous_demo=os.getenv("ALLOW_ANONYMOUS_DEMO", "false").lower()
            in {"1", "true", "yes"},
            auth_cookie_secure=os.getenv(
                "AUTH_COOKIE_SECURE", "true" if environment == "production" else "false"
            ).lower()
            in {"1", "true", "yes"},
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached immutable settings object for the current process."""

    return Settings.from_env()
