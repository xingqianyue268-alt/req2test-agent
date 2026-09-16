import pytest
from sqlalchemy.engine import make_url

from req2test.settings import normalize_database_url, single_service_mode
from req2test.task_store import TaskStore


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_provider_url_uses_psycopg_without_corrupting_credentials(scheme):
    url = make_url(normalize_database_url(
        f"{scheme}://user:p%40ss%25word@host/db?sslmode=require&channel_binding=require"
    ))
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss%word"
    assert url.query == {"sslmode": "require", "channel_binding": "require"}


def test_production_memory_mode_requires_both_eager_flags(monkeypatch):
    monkeypatch.setenv("REQ2TEST_TASK_STORE", "memory")
    monkeypatch.setenv("REQ2TEST_EAGER_TASKS", "true")
    monkeypatch.setenv("REQ2TEST_EAGER_EVALUATIONS", "false")
    with pytest.raises(ValueError, match="both eager"):
        single_service_mode()


def test_explicit_memory_mode_never_connects_to_redis(monkeypatch):
    import req2test.task_store as module

    monkeypatch.setenv("REQ2TEST_ENV", "production")
    monkeypatch.setenv("REQ2TEST_TASK_STORE", "memory")
    monkeypatch.setenv("REQ2TEST_EAGER_TASKS", "true")
    monkeypatch.setenv("REQ2TEST_EAGER_EVALUATIONS", "true")
    monkeypatch.setattr(module.redis.Redis, "from_url", lambda *a, **k: pytest.fail("Redis used"))
    store = TaskStore()
    store.create("task")
    assert store.backend == "memory"
    assert store.get("task")["status"] == "queued"
    for index in range(120):
        store.create(str(index))
    assert len(store._memory) == 100


def test_single_service_readiness_does_not_probe_brokers(monkeypatch):
    import req2test.api as api

    monkeypatch.setenv("REQ2TEST_TASK_STORE", "memory")
    monkeypatch.setenv("REQ2TEST_EAGER_TASKS", "true")
    monkeypatch.setenv("REQ2TEST_EAGER_EVALUATIONS", "true")
    monkeypatch.setattr(api, "task_store", TaskStore())
    monkeypatch.setattr(api, "database_is_ready", lambda: True)
    monkeypatch.setattr(api, "redis_is_ready", lambda *_: pytest.fail("Redis probe"))
    monkeypatch.setattr(api, "rabbitmq_is_ready", lambda: pytest.fail("RabbitMQ probe"))
    assert api.ready() == {"ready": True, "checks": {"database": "ok", "task_store": "ok"}}


def test_knowledge_failure_does_not_abort_startup(monkeypatch):
    from req2test.deploy import prepare_knowledge
    from req2test.services.knowledge_service import KnowledgeService

    def fail(*args):
        raise RuntimeError("broken disposable vector index")

    monkeypatch.setattr(KnowledgeService, "seed", fail)
    prepare_knowledge()


def test_single_service_demo_targets_own_port(monkeypatch):
    from req2test.demo_ui import render_demo_html

    monkeypatch.setenv("REQ2TEST_TASK_STORE", "memory")
    monkeypatch.setenv("REQ2TEST_EAGER_TASKS", "true")
    monkeypatch.setenv("REQ2TEST_EAGER_EVALUATIONS", "true")
    monkeypatch.setenv("PORT", "10000")
    html = render_demo_html()
    assert "http://127.0.0.1:10000" in html
    assert "http://api:8000" not in html
