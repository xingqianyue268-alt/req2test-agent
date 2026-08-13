"""Strict access-token creation and verification."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from ..settings import Settings, get_settings


class InvalidAccessToken(ValueError):
    """The JWT is invalid, expired, incomplete, or is not an access token."""


def create_access_token(
    subject: str,
    *,
    role: str | None = None,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> str:
    config = settings or get_settings()
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + (
        expires_delta or timedelta(minutes=config.jwt_access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings | None = None) -> dict[str, Any]:
    config = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm],
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessToken("Invalid or expired access token") from exc
    if payload.get("type") != "access":
        raise InvalidAccessToken("Invalid token type")
    try:
        uuid.UUID(str(payload["sub"]))
        uuid.UUID(str(payload["jti"]))
    except (ValueError, TypeError) as exc:
        raise InvalidAccessToken("Invalid token subject or identifier") from exc
    return payload
