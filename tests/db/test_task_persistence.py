from __future__ import annotations

import pytest

from req2test.db.repositories.tasks import list_tasks, update_task_state
from req2test.db.services.task_persistence import (
    LiveProjectionUnavailable,
    TaskDispatchError,
    TaskPersistenceService,
    generate_task_title,
    sanitize_config,
    task_to_projection,
)
from req2test.task_store import TaskStore


def _create(service, session, **overrides):
    values = {
        "requirement_text": "\n\nCreate an invoice\nwith line items",
        "title": None,
        "llm_settings": {"mode": "demo"},
        "generation_config": {"max_cases": 4},
        "execution_config": {"enabled": False},
        "eager": False,
    }
    values.update(overrides)
    return service.create_and_dispatch(session, **values)


def test_title_generation_and_safe_truncation():
    assert generate_task_title("\n First useful line\nSecond") == "First useful line"
    assert generate_task_title("", None) == "Untitled Test Task"
    assert generate_task_title("ignored", " Explicit ") == "Explicit"
    assert len(generate_task_title("x" * 300)) == 255
    assert len(generate_task_title("ignored", "x" * 300)) == 255


def test_recursive_config_sanitizer_omits_secret_variants():
    sanitized = sanitize_config(
        {
            "api_key": "one",
            "API_KEY": "two",
            "Authorization": "Bearer three",
            "nested": {
                "access_token": "four",
                "PASSWORD": "five",
                "safe": [{"client_secret": "six", "timeout": 8}],
            },
            "Cookie": "seven",
        }
    )
    assert sanitized == {"nested": {"safe": [{"timeout": 8}]}}


def test_create_dispatch_uses_one_uuid_and_dual_writes_celery_id(db_session):
    captured = {}

    def publisher(args, eager):
        captured["args"] = args
        captured["eager"] = eager
        return "celery-123"

    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    service = TaskPersistenceService(store, publisher)
    task = _create(
        service,
        db_session,
        generation_config={"max_cases": 4, "API_KEY": "never-store"},
    )

    state = store.get(str(task.id))
    assert task.title == "Create an invoice"
    assert task.generation_config == {"max_cases": 4}
    assert task.state_version == 2
    assert task.celery_task_id == "celery-123"
    assert state["task_id"] == str(task.id) == captured["args"][0]
    assert state["celery_task_id"] == "celery-123"
    assert state["state_version"] == 2


def test_fast_worker_update_is_not_overwritten_by_celery_id_persistence(db_session):
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)

    def publisher(args, eager):
        store.update(
            args[0],
            status="completed",
            stage="completed",
            progress=100,
            result={"test_cases": [{"case_id": "TC-001"}]},
        )
        return "celery-fast"

    task = _create(TaskPersistenceService(store, publisher), db_session, eager=True)
    state = store.get(str(task.id))
    assert state["status"] == "completed"
    assert state["result"]["test_cases"][0]["case_id"] == "TC-001"
    assert state["celery_task_id"] == "celery-fast"
    assert state["state_version"] == 2


def test_redis_failure_compensates_database_and_does_not_publish(db_session):
    published = []
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=False)
    service = TaskPersistenceService(store, lambda args, eager: published.append(args))

    with pytest.raises(LiveProjectionUnavailable):
        _create(service, db_session)

    task = list_tasks(db_session, limit=1)[0]
    assert task.status == "failed"
    assert task.stage == "infrastructure_unavailable"
    assert task.state_version == 2
    assert published == []


def test_dispatch_failure_marks_database_and_redis_failed(db_session):
    def fail_publish(args, eager):
        raise RuntimeError("broker password=secret-value unavailable")

    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    service = TaskPersistenceService(store, fail_publish)
    with pytest.raises(TaskDispatchError):
        _create(service, db_session)

    task = list_tasks(db_session, limit=1)[0]
    state = store.get(str(task.id))
    assert task.status == state["status"] == "failed"
    assert task.stage == state["stage"] == "dispatch_failed"
    assert "secret-value" not in task.error


def test_get_redis_hit_miss_stale_and_terminal_database_priority(db_session):
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    service = TaskPersistenceService(store, lambda args, eager: "celery-read")
    task = _create(service, db_session)
    task_id = str(task.id)

    live = store.get(task_id)
    live["message"] = "live redis"
    store.set(task_id, live)
    assert service.get_task_state(db_session, task_id, allow_anonymous=True)["message"] == "live redis"

    store._memory.pop(task_id)
    fallback = service.get_task_state(db_session, task_id, allow_anonymous=True)
    assert fallback["task_id"] == task_id
    assert store.get(task_id)["state_version"] == task.state_version

    stale = store.get(task_id)
    stale["state_version"] = 1
    stale["stage"] = "old"
    store.set(task_id, stale)
    assert service.get_task_state(db_session, task_id, allow_anonymous=True)["stage"] == "queued"

    terminal = update_task_state(
        db_session, task.id, status="failed", stage="dispatch_failed", error="down"
    )
    db_session.commit()
    running = task_to_projection(terminal)
    running.update(status="running", stage="started", state_version=999)
    store.set(task_id, running)
    result = service.get_task_state(db_session, task_id, allow_anonymous=True)
    assert result["status"] == "failed"
    assert result["stage"] == "dispatch_failed"
