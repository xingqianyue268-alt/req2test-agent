from __future__ import annotations

import uuid
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

import req2test.worker as worker_module
from req2test.db.models import ExecutionORM, TestCaseORM as CaseORM
from req2test.db.repositories import tasks
from req2test.execution_models import (
    ExecutionReport,
    HttpExecutionResult,
    HttpTestSpec,
    PytestExecutionResult,
)
from req2test.models import (
    RequirementItem,
    ReviewReport,
    TestCase as WorkflowTestCase,
    TestStep as WorkflowTestStep,
    WorkflowResult,
)
from req2test.task_store import TaskStore


def _workflow_result():
    return WorkflowResult(
        requirements=[
            RequirementItem(
                requirement_id="REQ-001",
                module="API",
                description="GET /health",
                acceptance_criteria=["200"],
            )
        ],
        test_cases=[
            WorkflowTestCase(
                case_id="API-001",
                module="API",
                title="Health check",
                priority="P1",
                test_type="正向",
                source_requirement="REQ-001",
                steps=[WorkflowTestStep(order=1, action="GET /health", expected="200")],
            )
        ],
        review=ReviewReport(score=95, coverage_rate=1.0),
        retrieved_context=["API test context"],
    )


def _execution_report(*, passed=True, status=200, failure=False):
    report = ExecutionReport(
        enabled=True,
        executable_cases=[
            HttpTestSpec(
                case_id="API-001",
                name="health",
                method="GET",
                path="/health",
                expected_status=200,
            )
        ],
        http_results=[
            HttpExecutionResult(
                case_id="API-001",
                name="health",
                method="GET",
                url="http://api:8000/health",
                passed=passed,
                status_code=status,
                expected_status=200,
                duration_ms=2.5,
                failures=[] if passed else ["status mismatch"],
            )
        ],
        pytest_result=PytestExecutionResult(
            passed=passed,
            exit_code=0 if passed else 1,
            duration_ms=4.0,
            passed_count=int(passed),
            failed_count=int(not passed),
        ),
        summary={
            "status": "completed",
            "total_http_cases": 1,
            "passed_http_cases": int(passed),
            "failed_http_cases": int(not passed),
            "http_pass_rate": float(passed),
            "pytest_passed": passed,
        },
    )
    if failure:
        from req2test.execution_models import FailureAnalysis

        report.failure_analysis = [
            FailureAnalysis(
                case_id="API-001",
                category="contract_mismatch",
                probable_cause="schema mismatch",
                evidence=["422"],
                suggestion="fix body",
            )
        ]
    return report


def _prepare_worker(monkeypatch, db_session, *, celery_id="delivery-1"):
    task = tasks.create_task(
        db_session,
        id=uuid.uuid4(),
        title="Worker task",
        requirement_text="GET /health",
        status="queued",
        stage="queued",
        progress=0,
        state_version=1,
        celery_task_id=celery_id,
        generation_config={},
        execution_config={"enabled": True},
    )
    db_session.commit()
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    store.create(str(task.id))
    store.update(str(task.id), celery_task_id=celery_id)

    @contextmanager
    def test_session_scope():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    monkeypatch.setattr(worker_module, "session_scope", test_session_scope)
    monkeypatch.setattr(worker_module, "task_store", store)
    return task, store


def test_worker_persists_lifecycle_and_terminal_db_before_redis(db_session, monkeypatch):
    task, store = _prepare_worker(monkeypatch, db_session)
    events = []

    def workflow(**kwargs):
        kwargs["on_progress"]("generation_completed", 80, "generated")
        return _workflow_result()

    original_finalize = worker_module.result_persistence.finalize_completed

    def finalize(*args, **kwargs):
        events.append("db_terminal")
        return original_finalize(*args, **kwargs)

    original_set = store.set

    def record_set(task_id, state):
        if state.get("status") == "completed":
            events.append("redis_terminal")
        return original_set(task_id, state)

    monkeypatch.setattr(worker_module, "run_workflow_with_progress", workflow)
    monkeypatch.setattr(worker_module, "execute_with_tools", lambda **kwargs: _execution_report())
    monkeypatch.setattr(worker_module.result_persistence, "finalize_completed", finalize)
    monkeypatch.setattr(store, "set", record_set)

    result = worker_module.generate_test_cases.apply(
        args=[
            str(task.id),
            "GET /health",
            {"mode": "demo"},
            {"max_cases": 4},
            {"enabled": True, "base_url": "http://api:8000"},
        ],
        task_id="delivery-1",
        throw=True,
    ).get()

    db_session.refresh(task)
    assert task.status == "completed"
    assert task.stage == "completed"
    assert task.progress == 100
    assert task.result_payload == result
    assert events[-2:] == ["db_terminal", "redis_terminal"]
    assert store.get(str(task.id))["state_version"] == task.state_version


def test_worker_duplicate_delivery_reuses_terminal_rows(db_session, monkeypatch):
    task, _ = _prepare_worker(monkeypatch, db_session)
    calls = {"workflow": 0}

    def workflow(**kwargs):
        calls["workflow"] += 1
        kwargs["on_progress"]("generation_completed", 80, "generated")
        return _workflow_result()

    monkeypatch.setattr(worker_module, "run_workflow_with_progress", workflow)
    monkeypatch.setattr(worker_module, "execute_with_tools", lambda **kwargs: _execution_report())
    args = [
        str(task.id),
        "GET /health",
        {"mode": "demo"},
        {"max_cases": 4},
        {"enabled": True, "base_url": "http://api:8000"},
    ]
    worker_module.generate_test_cases.apply(args=args, task_id="delivery-1", throw=True).get()
    worker_module.generate_test_cases.apply(args=args, task_id="delivery-1", throw=True).get()
    assert calls["workflow"] == 1
    assert db_session.scalar(
        select(func.count()).select_from(CaseORM).where(CaseORM.task_id == task.id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(ExecutionORM).where(ExecutionORM.task_id == task.id)
    ) == 1


def test_worker_rejects_conflicting_celery_delivery(db_session, monkeypatch):
    task, _ = _prepare_worker(monkeypatch, db_session, celery_id="owner-delivery")
    called = []
    monkeypatch.setattr(
        worker_module, "run_workflow_with_progress", lambda **kwargs: called.append(True)
    )
    result = worker_module.generate_test_cases.apply(
        args=[str(task.id), "GET /health", {"mode": "demo"}, {}, {}],
        task_id="other-delivery",
        throw=False,
    )
    assert result.failed()
    assert called == []
    db_session.refresh(task)
    assert task.celery_task_id == "owner-delivery"


def test_final_commit_failure_does_not_mark_redis_completed_or_rerun_http(
    db_session, monkeypatch
):
    task, store = _prepare_worker(monkeypatch, db_session)
    calls = {"workflow": 0, "tools": 0}

    def workflow(**kwargs):
        calls["workflow"] += 1
        kwargs["on_progress"]("generation_completed", 80, "generated")
        return _workflow_result()

    def tools(**kwargs):
        calls["tools"] += 1
        return _execution_report()

    def fail_final(*args, **kwargs):
        raise OperationalError("UPDATE", {}, RuntimeError("db unavailable"))

    monkeypatch.setattr(worker_module, "run_workflow_with_progress", workflow)
    monkeypatch.setattr(worker_module, "execute_with_tools", tools)
    monkeypatch.setattr(worker_module.result_persistence, "finalize_completed", fail_final)
    result = worker_module.generate_test_cases.apply(
        args=[
            str(task.id),
            "GET /health",
            {"mode": "demo"},
            {"max_cases": 4},
            {"enabled": True, "base_url": "http://api:8000"},
        ],
        task_id="delivery-1",
        throw=False,
    )
    assert result.failed()
    assert calls == {"workflow": 1, "tools": 1}
    state = store.get(str(task.id))
    assert state["status"] == "running"
    assert state["stage"] == "persistence_pending"
    db_session.refresh(task)
    assert task.status == "running"


def test_worker_business_failure_persists_failed_terminal(db_session, monkeypatch):
    task, store = _prepare_worker(monkeypatch, db_session)

    def fail_workflow(**kwargs):
        raise RuntimeError("authorization=Bearer-private generation exploded")

    monkeypatch.setattr(worker_module, "run_workflow_with_progress", fail_workflow)
    result = worker_module.generate_test_cases.apply(
        args=[str(task.id), "bad", {"mode": "demo"}, {}, {"enabled": False}],
        task_id="delivery-1",
        throw=False,
    )
    assert result.failed()
    db_session.refresh(task)
    assert task.status == "failed"
    assert task.stage == "generation_failed"
    assert task.completed_at is not None
    assert "Bearer-private" not in task.error
    assert store.get(str(task.id))["status"] == "failed"
