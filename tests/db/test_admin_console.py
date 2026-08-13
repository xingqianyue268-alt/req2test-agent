from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

import req2test.api as api_module
from req2test.db.models import TaskORM
from req2test.db.repositories import users
from req2test.db.session import get_db
from req2test.security.passwords import hash_password
from req2test.security.tokens import create_access_token


PASSWORD = "correct horse battery staple"


def _client(db_session):
    def override_db():
        yield db_session

    api_module.app.dependency_overrides[get_db] = override_db
    return TestClient(api_module.app)


def _user(db_session, email, role="user"):
    record = users.create_user(
        db_session, email=email, password_hash=hash_password(PASSWORD), role=role
    )
    db_session.commit()
    return record


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(str(user.id), role=user.role)}"}


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200


def _task(db_session, owner, title, status, pass_rate=None):
    task = TaskORM(
        id=uuid.uuid4(),
        user_id=owner.id,
        title=title,
        requirement_text=f"Requirement for {title}",
        status=status,
        stage=status,
        progress=100 if status in {"completed", "failed"} else 25,
        generation_config={},
        execution_config={},
        result_summary=(
            {
                "total_test_cases": 2,
                "http_pass_rate": pass_rate,
                "failure_analysis_count": 1 if status == "failed" else 0,
            }
            if pass_rate is not None
            else None
        ),
    )
    db_session.add(task)
    db_session.commit()
    return task


def test_admin_server_side_rbac_and_product_routes(db_session):
    client = _client(db_session)
    normal = _user(db_session, "admin-rbac-user@example.com")
    admin = _user(db_session, "admin-rbac-root@example.com", role="admin")
    endpoints = [
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users",
        "/api/v1/admin/tasks",
        "/api/v1/admin/system",
    ]
    try:
        for endpoint in endpoints:
            assert client.get(endpoint, headers=_headers(normal)).status_code == 403
        _login(client, normal.email)
        forbidden = client.get("/admin")
        assert forbidden.status_code == 403 and "ADMIN" in forbidden.text
        client.post("/api/v1/auth/logout")

        _login(client, admin.email)
        for route in ["/admin", "/admin/users", "/admin/tasks", "/admin/knowledge", "/admin/system"]:
            page = client.get(route)
            assert page.status_code == 200
            assert "ADMIN" in page.text and "CONTROL" in page.text
        assert client.get("/admin/not-a-view").status_code == 404
    finally:
        api_module.app.dependency_overrides.clear()


def test_dashboard_aggregation_admin_task_list_and_detail(db_session):
    client = _client(db_session)
    admin = _user(db_session, "dashboard-admin@example.com", role="admin")
    owner = _user(db_session, "dashboard-owner@example.com")
    completed = _task(db_session, owner, "Completed checkout", "completed", 1.0)
    failed = _task(db_session, owner, "Failed contract", "failed", 0.0)
    _task(db_session, owner, "Queued work", "queued")
    try:
        headers = _headers(admin)
        dashboard = client.get("/api/v1/admin/dashboard", headers=headers)
        assert dashboard.status_code == 200
        body = dashboard.json()
        assert body["metrics"] == {
            "total_users": 2,
            "active_users": 2,
            "total_tasks": 3,
            "completed_tasks": 1,
            "failed_tasks": 1,
            "http_pass_rate": 0.5,
        }
        assert len(body["recent_tasks"]) == 3
        assert {str(completed.id), str(failed.id)} <= {
            item["id"] for item in body["recent_tasks"]
        }
        task_list = client.get(
            "/api/v1/admin/tasks?status=failed&keyword=contract", headers=headers
        ).json()
        assert task_list["total"] == 1
        assert task_list["items"][0]["id"] == str(failed.id)
        assert task_list["items"][0]["user_email"] == owner.email
        assert client.get(f"/api/v1/tasks/{completed.id}", headers=headers).status_code == 200
    finally:
        api_module.app.dependency_overrides.clear()


def test_admin_user_list_mutation_old_token_and_role_changes(db_session):
    client = _client(db_session)
    admin = _user(db_session, "mutation-admin@example.com", role="admin")
    target = _user(db_session, "mutation-user@example.com")
    target_headers = _headers(target)
    try:
        admin_headers = _headers(admin)
        listing = client.get("/api/v1/admin/users", headers=admin_headers)
        assert listing.status_code == 200 and listing.json()["total"] == 2
        assert "password" not in listing.text
        assert "password_hash" not in listing.text

        disabled = client.patch(
            f"/api/v1/admin/users/{target.id}/status",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert disabled.status_code == 200 and disabled.json()["is_active"] is False
        assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 401
        assert client.post(
            "/api/v1/auth/login", json={"email": target.email, "password": PASSWORD}
        ).status_code == 401
        assert client.patch(
            f"/api/v1/admin/users/{target.id}/status",
            headers=admin_headers,
            json={"is_active": True},
        ).status_code == 200

        promoted = client.patch(
            f"/api/v1/admin/users/{target.id}/role",
            headers=admin_headers,
            json={"role": "admin"},
        )
        assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
        demoted = client.patch(
            f"/api/v1/admin/users/{target.id}/role",
            headers=admin_headers,
            json={"role": "user"},
        )
        assert demoted.status_code == 200 and demoted.json()["role"] == "user"
        assert client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}/status",
            headers=admin_headers,
            json={"is_active": False},
        ).status_code == 404
    finally:
        api_module.app.dependency_overrides.clear()


def test_last_active_admin_self_disable_and_demotion_are_blocked(db_session):
    client = _client(db_session)
    only_admin = _user(db_session, "only-admin@example.com", role="admin")
    headers = _headers(only_admin)
    try:
        disable = client.patch(
            f"/api/v1/admin/users/{only_admin.id}/status",
            headers=headers,
            json={"is_active": False},
        )
        demote = client.patch(
            f"/api/v1/admin/users/{only_admin.id}/role",
            headers=headers,
            json={"role": "user"},
        )
        assert disable.status_code == 409
        assert demote.status_code == 409
        db_session.refresh(only_admin)
        assert only_admin.is_active is True and only_admin.role == "admin"

        second = _user(db_session, "second-admin@example.com", role="admin")
        assert client.patch(
            f"/api/v1/admin/users/{only_admin.id}/role",
            headers=headers,
            json={"role": "user"},
        ).status_code == 200
        assert client.get("/api/v1/admin/dashboard", headers=headers).status_code == 403
        assert second.role == "admin"
    finally:
        api_module.app.dependency_overrides.clear()


def test_admin_system_truthful_probe_and_configured_states(db_session, monkeypatch):
    client = _client(db_session)
    admin = _user(db_session, "system-admin@example.com", role="admin")

    class KB:
        def count(self):
            return 7

    monkeypatch.setattr(api_module, "database_is_ready", lambda: True)
    monkeypatch.setattr(api_module, "redis_is_ready", lambda store: False)
    monkeypatch.setattr(api_module, "rabbitmq_is_ready", lambda: True)
    monkeypatch.setattr(api_module.knowledge_service, "_kb", lambda: KB())
    try:
        response = client.get("/api/v1/admin/system", headers=_headers(admin))
        assert response.status_code == 200
        services = {item["name"]: item for item in response.json()["services"]}
        assert services["PostgreSQL"]["state"] == "HEALTHY"
        assert services["Redis"]["state"] == "UNAVAILABLE"
        assert services["RabbitMQ"]["state"] == "HEALTHY"
        assert services["Celery Worker"]["state"] == "CONFIGURED"
        assert services["Chroma / Knowledge"]["documents"] == 7
        assert services["Pytest"]["state"] == "CONFIGURED"
        assert services["Failure Analysis"]["state"] == "CONFIGURED"
    finally:
        api_module.app.dependency_overrides.clear()
