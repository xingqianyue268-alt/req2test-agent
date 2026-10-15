"""Cookie mutations must have an explicitly trusted Origin, without changing Bearer APIs."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from req2test import api
from req2test.db.session import get_db
from req2test.security.tokens import create_access_token


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setenv("REQ2TEST_TRUSTED_ORIGINS", "https://app.example.test")
    user = SimpleNamespace(id=uuid.uuid4(), role="user", is_active=True)
    api.app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr("req2test.security.dependencies.users.get_user_by_id", lambda *_: user)
    dispatch = Mock(return_value=SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(api.task_persistence, "create_and_dispatch", dispatch)
    token = create_access_token(str(user.id))
    with TestClient(api.app, base_url="https://app.example.test") as client:
        client.cookies.set("req2test_access_token", token)
        yield client, token, dispatch
    api.app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://evil.example.test",
        "https://app.example.test.evil.test",
        "http://app.example.test",
        "https://app.example.test:444",
        "https://app.example.test:0",
        "https://app.example.test/path",
    ],
)
def test_cookie_mutations_reject_untrusted_origin(browser, origin):
    client, _, dispatch = browser
    headers = {"Origin": origin} if origin else {}
    response = client.post(
        "/api/v1/tasks", json={"requirement_text": "synthetic local requirement"}, headers=headers
    )
    assert response.status_code == 403
    dispatch.assert_not_called()


def test_trusted_browser_origin_and_bearer_compatibility(browser):
    client, token, dispatch = browser
    assert (
        client.post(
            "/api/v1/tasks",
            json={"requirement_text": "local"},
            headers={"Origin": "https://app.example.test"},
        ).status_code
        == 202
    )
    # Explicit Bearer is authoritative even if a browser cookie also exists.
    assert (
        client.post(
            "/api/v1/tasks",
            json={"requirement_text": "local"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 202
    )
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/tasks",
            json={"requirement_text": "local"},
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": "https://api-client.example.test",
            },
        ).status_code
        == 202
    )
    assert dispatch.call_count == 3


@pytest.mark.parametrize("auth", ["Basic abc", "Bearer ", "Bearer"])
def test_malformed_auth_header_does_not_bypass_cookie_guard(browser, auth):
    client, _, dispatch = browser
    assert (
        client.post(
            "/api/v1/tasks", json={"requirement_text": "local"}, headers={"Authorization": auth}
        ).status_code
        == 403
    )
    dispatch.assert_not_called()


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/auth/logout"),
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/knowledge/documents"),
        ("delete", f"/api/v1/knowledge/documents/{uuid.UUID(int=1)}"),
        ("post", "/api/v1/knowledge/rebuild"),
        ("patch", f"/api/v1/admin/users/{uuid.UUID(int=1)}/role"),
        ("post", "/api/v1/evaluations/runs"),
        ("post", "/api/v1/evaluations/comparisons"),
    ],
)
def test_guard_covers_mutating_routes_before_side_effects(browser, method, path):
    client, _, _ = browser
    assert (
        client.request(
            method, path, headers={"Origin": "https://evil.example.test"}, json={}
        ).status_code
        == 403
    )


def test_login_cannot_set_cookie_from_untrusted_origin_even_without_existing_cookie(browser):
    client, _, _ = browser
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login", json={}, headers={"Origin": "https://evil.example.test"}
    )
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_host_and_forwarded_headers_do_not_define_trust(browser):
    client, _, dispatch = browser
    response = client.post(
        "/api/v1/tasks",
        json={"requirement_text": "local"},
        headers={
            "Origin": "https://evil.example.test",
            "Host": "evil.example.test",
            "X-Forwarded-Host": "evil.example.test",
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 403
    dispatch.assert_not_called()


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example.test"])
def test_cookie_websocket_rejects_untrusted_origin(browser, monkeypatch, origin):
    client, _, _ = browser
    monkeypatch.setattr(
        api.task_persistence, "get_task_state", lambda *a, **k: {"status": "completed"}
    )
    monkeypatch.setattr(api.task_store, "get", lambda *a: {"status": "completed"})
    with (
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect(
            "/ws/tasks/synthetic", headers={"Origin": origin} if origin else {}
        ),
    ):
        pass
    assert error.value.code == 4403


def test_cookie_websocket_allows_trusted_origin(browser, monkeypatch):
    client, _, _ = browser
    monkeypatch.setattr(
        api.task_persistence, "get_task_state", lambda *a, **k: {"status": "completed"}
    )
    monkeypatch.setattr(
        api.task_store, "get", lambda *a: {"status": "completed", "updated_at": "now"}
    )
    with client.websocket_connect(
        "/ws/tasks/synthetic", headers={"Origin": "https://app.example.test"}
    ) as socket:
        assert socket.receive_json()["status"] == "completed"


def test_validation_response_does_not_echo_password(browser):
    client, _, _ = browser
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "https://app.example.test"},
        json={"email": "fake@example.test", "password": "p0short"},
    )
    assert response.status_code == 422
    assert "p0short" not in response.text
