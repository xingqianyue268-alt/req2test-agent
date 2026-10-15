"""Authenticated import/preview and existing durable task dispatch with PostgreSQL."""

import base64
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from req2test import api
from req2test.db.repositories.tasks import get_task
from req2test.db.services.task_persistence import TaskPersistenceService
from req2test.db.session import get_db
from req2test.task_store import TaskStore


@pytest.fixture
def client(db_session, monkeypatch):
    captured = []
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)

    def publish(args, eager):
        captured.append(args)
        return "openapi-test"

    monkeypatch.setattr(api, "task_persistence", TaskPersistenceService(store, publish))
    api.app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(api.app, headers={"Origin": "http://testserver"}) as client:
            credentials = {
                "email": "openapi@example.test",
                "password": "Synthetic-contract-password!",
            }
            assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
            token = client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
            yield client, captured, token
    finally:
        api.app.dependency_overrides.clear()


def payload():
    source = Path(__file__).resolve().parents[2] / "examples/openapi/synthetic-shop.json"
    return {
        "filename": source.name,
        "content_base64": base64.b64encode(source.read_bytes()).decode(),
    }


def plan():
    return {
        **payload(),
        "selected_operations": ["POST /products"],
        "base_url": "http://127.0.0.1:8081",
        "headers": {"Authorization": "Bearer private-synthetic-contract-token"},
    }


def test_import_preview_dispatch_and_redacted_persistence(client, db_session):
    browser, captured, _ = client
    assert browser.get("/contracts").status_code == 200
    imported = browser.post("/api/v1/contracts/import", json=payload())
    assert imported.status_code == 200 and len(imported.json()["operations"]) == 5
    preview = browser.post("/api/v1/contracts/preview", json=plan())
    assert preview.status_code == 200
    assert "private-synthetic-contract-token" not in preview.text
    assert not captured
    created = browser.post(
        "/api/v1/tasks", json={"requirement_text": "OpenAPI contract", "openapi_contract": plan()}
    )
    assert created.status_code == 202
    task_id = created.json()["task_id"]
    task = get_task(db_session, uuid.UUID(task_id))
    assert task.user_id is not None
    # Execution receives the actual synthetic auth; persistence and public output remain redacted.
    assert "private-synthetic-contract-token" in json.dumps(captured)
    public = browser.get("/api/v1/tasks/" + task_id)
    assert public.status_code == 200 and "private-synthetic-contract-token" not in public.text
    assert "content_base64" not in json.dumps(captured)


@pytest.mark.parametrize(
    "path", ["/api/v1/contracts/import", "/api/v1/contracts/preview", "/api/v1/tasks"]
)
def test_contract_cookie_csrf_and_bearer_compatibility(client, path):
    browser, captured, token = client
    body = (
        payload()
        if path.endswith("/import")
        else plan()
        if path.endswith("/preview")
        else {"requirement_text": "contract", "openapi_contract": plan()}
    )
    assert (
        browser.post(path, json=body, headers={"Origin": "https://evil.invalid"}).status_code == 403
    )
    assert not captured
    browser.cookies.clear()
    assert browser.post(
        path,
        json=body,
        headers={"Authorization": "Bearer " + token, "Origin": "https://api-client.invalid"},
    ).status_code in (200, 202)


def test_unauthenticated_import_and_remote_dispatch_denied(client):
    browser, captured, _ = client
    p = plan()
    p["base_url"] = "https://evil.invalid"
    assert (
        browser.post(
            "/api/v1/tasks", json={"requirement_text": "contract", "openapi_contract": p}
        ).status_code
        == 422
    )
    assert not captured
    browser.cookies.clear()
    assert browser.post("/api/v1/contracts/import", json=payload()).status_code == 401
    assert browser.post("/api/v1/contracts/preview", json=plan()).status_code == 401
    assert (
        browser.post(
            "/api/v1/tasks", json={"requirement_text": "contract", "openapi_contract": plan()}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("endpoint", ["/api/v1/contracts/preview", "/api/v1/tasks"])
def test_contract_validation_never_echoes_encoded_document(client, endpoint):
    browser, _, _ = client
    p = plan()
    p["unexpected"] = {"content_base64": "SYNTHETIC_ENCODED_CREDENTIAL"}
    body = (
        p
        if endpoint.endswith("/preview")
        else {"requirement_text": "contract", "openapi_contract": p}
    )
    response = browser.post(endpoint, json=body)
    assert response.status_code == 422
    assert "SYNTHETIC_ENCODED_CREDENTIAL" not in response.text
