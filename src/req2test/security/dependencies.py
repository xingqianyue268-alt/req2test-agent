"""FastAPI authentication and reusable role dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db.models import UserORM
from ..db.repositories import users
from ..db.session import get_db
from .tokens import InvalidAccessToken, decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    access_cookie: Annotated[str | None, Cookie(alias="req2test_access_token")] = None,
) -> UserORM:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif access_cookie:
        token = access_cookie
    if token is None:
        raise _unauthorized()
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload["sub"]))
    except (InvalidAccessToken, ValueError, TypeError) as exc:
        raise _unauthorized("Invalid or expired access token") from exc
    user = users.get_user_by_id(db, user_id)
    if user is None:
        raise _unauthorized("User no longer exists")
    if not user.is_active:
        raise _unauthorized("Account is inactive")
    return user


def get_optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    access_cookie: Annotated[str | None, Cookie(alias="req2test_access_token")] = None,
) -> UserORM | None:
    if credentials is None and not access_cookie:
        return None
    return get_current_user(credentials, db, access_cookie)


def require_roles(*allowed_roles: str) -> Callable[..., UserORM]:
    invalid = set(allowed_roles) - users.VALID_ROLES
    if invalid:
        raise ValueError(f"Unknown roles: {sorted(invalid)}")

    def dependency(
        current_user: Annotated[UserORM, Depends(get_current_user)],
    ) -> UserORM:
        # Authorization intentionally trusts the current PostgreSQL record, not JWT role.
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return dependency
