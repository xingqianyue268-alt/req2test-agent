from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import req2test.api as api_module
from req2test.db.repositories.tasks import get_task
from req2test.db.services.task_persistence import TaskPersistenceService
from req2test.db.session import get_db
from req2test.task_store import TaskStore


def _client_with_session(db_session):
    def override_db():
        yield db_session

    api_module.app.dependency_overrides[get_db] = override_db
    api_module.app.dependency_overrides[api_module.task_actor] = lambda: None
    return TestClient(api_module.app)


def test_post_persists_same_uuid_to_database_redis_and_celery(db_session, monkeypatch):
    captured = {}

    def publisher(args, eager):
        captured["args"] = args
        return "celery-api"

    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    monkeypatch.setattr(api_module, "task_persistence", TaskPersistenceService(store, publisher))
    client = _client_with_session(db_session)
    try:
        response = client.post(
            "/api/v1/tasks",
            json={"requirement_text": "\nAPI task title\nsecond line"},
        )
    finally:
        api_module.app.dependency_overrides.clear()

    assert response.status_code == 202
    assert set(response.json()) == {"task_id", "status_url", "ws_url"}
    task_id = response.json()["task_id"]
    task = get_task(db_session, uuid.UUID(task_id))
    assert str(task.id) == store.get(task_id)["task_id"] == captured["args"][0]
    assert task.title == "API task title"
    assert task.celery_task_id == store.get(task_id)["celery_task_id"] == "celery-api"


def test_get_redis_miss_falls_back_to_postgres(db_session, monkeypatch):
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    service = TaskPersistenceService(store, lambda args, eager: "celery-get")
    task = service.create_and_dispatch(
        db_session,
        requirement_text="GET fallback",
        title=None,
        llm_settings={"mode": "demo"},
        generation_config={},
        execution_config={"enabled": False},
        eager=False,
    )
    store._memory.clear()
    monkeypatch.setattr(api_module, "task_persistence", service)
    monkeypatch.setattr(
        api_module,
        "get_settings",
        lambda: SimpleNamespace(allow_anonymous_demo=True),
    )
    client = _client_with_session(db_session)
    try:
        response = client.get(f"/api/v1/tasks/{task.id}")
    finally:
        api_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["task_id"] == str(task.id)
    assert store.get(str(task.id))["state_version"] == 2


class _BrokenSession:
    def add(self, value):
        return None

    def flush(self):
        raise OperationalError("INSERT", {}, RuntimeError("database down"))

    def rollback(self):
        return None

    def close(self):
        return None


def test_post_database_failure_does_not_write_redis_or_publish(monkeypatch):
    published = []
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    monkeypatch.setattr(
        api_module,
        "task_persistence",
        TaskPersistenceService(store, lambda args, eager: published.append(args)),
    )

    def broken_db():
        yield _BrokenSession()

    api_module.app.dependency_overrides[get_db] = broken_db
    api_module.app.dependency_overrides[api_module.task_actor] = lambda: None
    try:
        response = TestClient(api_module.app).post(
            "/api/v1/tasks", json={"requirement_text": "DB failure"}
        )
    finally:
        api_module.app.dependency_overrides.clear()

    assert response.status_code == 503
    assert store._memory == {}
    assert published == []


def test_post_rejects_production_redis_failure(db_session, monkeypatch):
    published = []
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=False)
    monkeypatch.setattr(
        api_module,
        "task_persistence",
        TaskPersistenceService(store, lambda args, eager: published.append(args)),
    )
    client = _client_with_session(db_session)
    try:
        response = client.post(
            "/api/v1/tasks", json={"requirement_text": "Redis required"}
        )
    finally:
        api_module.app.dependency_overrides.clear()

    assert response.status_code == 503
    assert published == []
