"""Origin protection for ambient-cookie authentication and browser sessions."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

COOKIE_NAME = "req2test_access_token"
_SESSION_ROUTES = {"/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/register"}


def _origin(value: str | None) -> tuple[str, str, int] | None:
    if not value or value == "null" or any(char.isspace() for char in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def trusted_origin(headers: Headers) -> bool:
    values = headers.getlist("origin")
    if len(values) != 1:
        return False
    candidate = _origin(values[0])
    configured = os.getenv(
        "REQ2TEST_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    )
    allowed = {_origin(item.strip()) for item in configured.split(",")}
    return candidate is not None and candidate in allowed


class CookieOriginMiddleware:
    """Bearer-only requests need no CSRF proof; cookie mutations fail closed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        connection = HTTPConnection(scope)
        cookie = COOKIE_NAME in connection.cookies
        if scope["type"] == "websocket":
            if cookie and not trusted_origin(connection.headers):
                await send({"type": "websocket.close", "code": 4403, "reason": "Untrusted Origin"})
                return
        elif scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            authorization = connection.headers.get("authorization", "")
            scheme, _, credentials = authorization.partition(" ")
            bearer = scheme.lower() == "bearer" and bool(credentials.strip())
            session_route = scope["path"].rstrip("/") in _SESSION_ROUTES
            needs_origin = (cookie and (not bearer or session_route)) or (
                session_route and "origin" in connection.headers
            )
            if needs_origin and not trusted_origin(connection.headers):
                response = JSONResponse(
                    {"detail": "Trusted Origin required for cookie requests"}, status_code=403
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
