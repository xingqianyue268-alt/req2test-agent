from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import req2test.api as api_module
from req2test.db.repositories import users
from req2test.db.session import get_db
from req2test.db.services.task_persistence import TaskPersistenceService
from req2test.security.passwords import hash_password
from req2test.settings import Settings
from req2test.task_store import TaskStore


PASSWORD = "correct horse battery staple"


def _settings(*, anonymous=False):
    return Settings(
        database_url="postgresql+psycopg://unused",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout=1,
        environment="test",
        jwt_secret_key="ownership-test-secret-that-is-long-enough",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        allow_anonymous_demo=anonymous,
        auth_cookie_secure=False,
    )


def _client(db_session, monkeypatch):
    def override_db():
        yield db_session

    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    service = TaskPersistenceService(store, lambda args, eager: f"celery-{args[0]}")
    api_module.app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(api_module, "task_persistence", service)
    monkeypatch.setattr(api_module, "task_store", store)
    monkeypatch.setattr(api_module, "get_settings", lambda: _settings())
    return TestClient(api_module.app), store


def _create_user(db_session, email, role="user"):
    user = users.create_user(
        db_session,
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    db_session.commit()
    return user


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _create_task(client, title):
    response = client.post(
        "/api/v1/tasks", json={"title": title, "requirement_text": f"{title} requirement"}
    )
    assert response.status_code == 202
    return response.json()["task_id"]


def test_task_ownership_detail_list_admin_and_post_user_id(db_session, monkeypatch):
    client, _ = _client(db_session, monkeypatch)
    user_a = _create_user(db_session, "a@example.com")
    user_b = _create_user(db_session, "b@example.com")
    _create_user(db_session, "admin@example.com", role="admin")
    try:
        token_a = _login(client, user_a.email)
        task_a = _create_task(client, "A task")
        client.post("/api/v1/auth/logout")

        token_b = _login(client, user_b.email)
        task_b = _create_task(client, "B task")
        assert client.get(f"/api/v1/tasks/{task_a}").status_code == 404
        list_b = client.get("/api/v1/tasks?page=1&page_size=10").json()["items"]
        assert [item["task_id"] for item in list_b] == [task_b]
        client.post("/api/v1/auth/logout")

        _login(client, user_a.email)
        assert client.get(f"/api/v1/tasks/{task_a}").status_code == 200
        assert client.get(f"/api/v1/tasks/{task_b}").status_code == 404
        list_a = client.get("/api/v1/tasks").json()["items"]
        assert [item["task_id"] for item in list_a] == [task_a]
        client.post("/api/v1/auth/logout")

        _login(client, "admin@example.com")
        assert client.get(f"/api/v1/tasks/{task_a}").status_code == 200
        assert client.get(f"/api/v1/tasks/{task_b}").status_code == 200
        admin_ids = {item["task_id"] for item in client.get("/api/v1/tasks").json()["items"]}
        assert {task_a, task_b} <= admin_ids

        from req2test.db.repositories.tasks import get_task
        import uuid

        assert get_task(db_session, uuid.UUID(task_a)).user_id == user_a.id
        assert get_task(db_session, uuid.UUID(task_b)).user_id == user_b.id
        assert token_a and token_b
    finally:
        api_module.app.dependency_overrides.clear()


def test_websocket_enforces_owner_and_allows_admin(db_session, monkeypatch):
    client, _ = _client(db_session, monkeypatch)
    _create_user(db_session, "socket-a@example.com")
    _create_user(db_session, "socket-b@example.com")
    _create_user(db_session, "socket-admin@example.com", role="admin")
    try:
        _login(client, "socket-a@example.com")
        task_id = _create_task(client, "Socket task")
        with client.websocket_connect(f"/ws/tasks/{task_id}") as socket:
            assert socket.receive_json()["task_id"] == task_id
        client.post("/api/v1/auth/logout")

        _login(client, "socket-b@example.com")
        with pytest.raises(WebSocketDisconnect) as denied:
            with client.websocket_connect(f"/ws/tasks/{task_id}"):
                pass
        assert denied.value.code == 4404
        client.post("/api/v1/auth/logout")

        _login(client, "socket-admin@example.com")
        with client.websocket_connect(f"/ws/tasks/{task_id}") as socket:
            assert socket.receive_json()["task_id"] == task_id
    finally:
        api_module.app.dependency_overrides.clear()


def test_anonymous_production_denied_and_explicit_demo_allowed(db_session, monkeypatch):
    client, store = _client(db_session, monkeypatch)
    try:
        denied = client.post("/api/v1/tasks", json={"requirement_text": "anonymous"})
        assert denied.status_code == 401

        forged = client.post(
            "/api/v1/tasks",
            json={
                "requirement_text": "forged owner",
                "user_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert forged.status_code == 401

        monkeypatch.setattr(api_module, "get_settings", lambda: _settings(anonymous=True))
        forged = client.post(
            "/api/v1/tasks",
            json={
                "requirement_text": "forged owner",
                "user_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert forged.status_code == 422
        accepted = client.post(
            "/api/v1/tasks", json={"requirement_text": "explicit anonymous demo"}
        )
        assert accepted.status_code == 202
        assert store.get(accepted.json()["task_id"])["status"] == "queued"
    finally:
        api_module.app.dependency_overrides.clear()
