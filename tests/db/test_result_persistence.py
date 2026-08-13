from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from req2test.db.models import ExecutionORM, TestCaseORM as CaseORM
from req2test.db.repositories import tasks
from req2test.db.services.result_persistence import (
    CeleryDeliveryConflict,
    ResultPersistenceService,
    bound_result_payload,
    build_result_summary,
    sanitize_result,
)
import req2test.db.services.result_persistence as result_module
from req2test.db.services.task_persistence import TaskPersistenceService, task_to_projection
from req2test.task_store import TaskStore


def _business_task(session, *, celery_task_id=None):
    task = tasks.create_task(
        session,
        id=uuid.uuid4(),
        title="Persist result",
        requirement_text="GET /health",
        status="queued",
        stage="queued",
        progress=0,
        state_version=1,
        celery_task_id=celery_task_id,
        generation_config={},
        execution_config={"enabled": True},
    )
    session.commit()
    return task


def _payload(*, passed=True, status_code=200, category=None):
    failures = []
    analyses = []
    if not passed:
        failures = ["状态码不一致：期望 200，实际 422"]
        analyses = [
            {
                "case_id": "TC-001",
                "category": category or "contract_mismatch",
                "probable_cause": "契约校验失败",
                "evidence": failures,
                "suggestion": "核对请求体",
            }
        ]
    return {
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "module": "Health",
                "description": "Health endpoint",
                "acceptance_criteria": ["returns 200"],
            }
        ],
        "test_cases": [
            {
                "case_id": "TC-001",
                "module": "Health",
                "title": "Check health",
                "priority": "P1",
                "test_type": "正向",
                "source_requirement": "REQ-001",
                "preconditions": ["service running"],
                "steps": [{"order": 1, "action": "GET", "expected": "200"}],
            }
        ],
        "review": {"score": 92, "coverage_rate": 1.0, "issues": [], "suggestions": []},
        "retrieved_context": ["context"],
        "errors": [],
        "execution": {
            "enabled": True,
            "executable_cases": [
                {
                    "case_id": "TC-001",
                    "name": "health",
                    "method": "GET",
                    "path": "/health",
                    "headers": {"Authorization": "Bearer secret-token"},
                    "expected_status": 200,
                }
            ],
            "tool_calls": [{"tool_name": "http_api_test", "case_id": "TC-001"}],
            "http_results": [
                {
                    "case_id": "TC-001",
                    "name": "health",
                    "method": "GET",
                    "url": "http://api:8000/health",
                    "passed": passed,
                    "status_code": status_code,
                    "expected_status": 200,
                    "duration_ms": 12.5,
                    "failures": failures,
                    "response_excerpt": '{"status":"ok"}',
                    "error": None,
                }
            ],
            "pytest_result": {
                "passed": passed,
                "exit_code": 0 if passed else 1,
                "duration_ms": 22.5,
                "passed_count": 1 if passed else 0,
                "failed_count": 0 if passed else 1,
                "error_count": 0,
                "stdout": "one passed",
                "stderr": "",
                "generated_test_file": "/tmp/generated.py",
            },
            "failure_analysis": analyses,
            "summary": {
                "status": "completed",
                "total_http_cases": 1,
                "passed_http_cases": int(passed),
                "failed_http_cases": int(not passed),
                "http_pass_rate": 1.0 if passed else 0.0,
                "pytest_passed": passed,
            },
            "warnings": [],
        },
    }


def test_worker_self_heals_missing_celery_id_and_rejects_conflict(db_session):
    task = _business_task(db_session)
    service = ResultPersistenceService()
    healed, changed = service.bind_delivery(db_session, str(task.id), "delivery-1")
    db_session.commit()
    assert changed is True
    assert healed.celery_task_id == "delivery-1"

    same, changed = service.bind_delivery(db_session, str(task.id), "delivery-1")
    assert changed is False
    assert same.id == task.id
    with pytest.raises(CeleryDeliveryConflict):
        service.bind_delivery(db_session, str(task.id), "delivery-2")


def test_milestones_increment_version_and_terminal_cannot_regress(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    service = ResultPersistenceService()
    running = service.persist_milestone(
        db_session, str(task.id), status="running", stage="running", progress=5
    )
    running_version = running.state_version
    generated = service.persist_milestone(
        db_session,
        str(task.id),
        status="running",
        stage="generation_completed",
        progress=80,
    )
    generated_version = generated.state_version
    completed = service.finalize_completed(db_session, str(task.id), _payload())
    version = completed.state_version
    stale = service.persist_milestone(
        db_session, str(task.id), status="running", stage="running", progress=5
    )
    assert running_version < generated_version < version
    assert stale.status == "completed"
    assert stale.stage == "completed"
    assert stale.state_version == version


def test_atomic_finalization_persists_case_execution_summary_and_payload(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    service = ResultPersistenceService()
    completed = service.finalize_completed(db_session, str(task.id), _payload())
    db_session.commit()

    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert completed.result_summary == {
        "total_requirements": 1,
        "total_test_cases": 1,
        "review_score": 92,
        "coverage_rate": 1.0,
        "total_http_cases": 1,
        "passed_http_cases": 1,
        "failed_http_cases": 0,
        "http_pass_rate": 1.0,
        "pytest_passed": True,
        "failure_analysis_count": 0,
        "final_status": "completed",
    }
    assert completed.result_payload["execution"]["pytest_result"]["passed"] is True
    headers = completed.result_payload["execution"]["executable_cases"][0]["headers"]
    assert "Authorization" not in headers

    case = db_session.scalar(select(CaseORM).where(CaseORM.task_id == task.id))
    execution = db_session.scalar(
        select(ExecutionORM).where(ExecutionORM.task_id == task.id)
    )
    assert case.case_id == "TC-001"
    assert execution.test_case_id == case.id
    assert execution.method == "GET"
    assert execution.path == "/health"
    assert execution.passed is True


def test_terminal_projection_is_safe_after_transaction_session_closes(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    completed = ResultPersistenceService().finalize_completed(
        db_session, str(task.id), _payload()
    )
    db_session.commit()
    db_session.expunge(completed)

    projection = task_to_projection(completed)
    assert projection["status"] == "completed"
    assert projection["result"]["execution"]["pytest_result"]["passed"] is True


def test_duplicate_final_persistence_is_idempotent(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    service = ResultPersistenceService()
    service.finalize_completed(db_session, str(task.id), _payload())
    service.finalize_completed(db_session, str(task.id), _payload())
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(CaseORM).where(CaseORM.task_id == task.id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(ExecutionORM).where(ExecutionORM.task_id == task.id)
    ) == 1


def test_failure_category_and_full_analysis_are_persisted(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    payload = _payload(passed=False, status_code=422, category="contract_mismatch")
    completed = ResultPersistenceService().finalize_completed(db_session, str(task.id), payload)
    db_session.commit()
    execution = db_session.scalar(
        select(ExecutionORM).where(ExecutionORM.task_id == task.id)
    )
    assert execution.actual_status == 422
    assert execution.failure_category == "contract_mismatch"
    analysis = completed.result_payload["execution"]["failure_analysis"][0]
    assert analysis["category"] == "contract_mismatch"
    assert analysis["suggestion"] == "核对请求体"


def test_sanitizer_and_payload_size_limits():
    sanitized = sanitize_result(
        {
            "headers": {
                "authorization": "Bearer abc",
                "Cookie": "session=abc",
                "X-API-Key": "nested-key",
            },
            "nested": [
                {
                    "api_key": "secret",
                    "private_credential": "also-secret",
                    "safe": "Bearer hidden",
                }
            ],
            "error": "private_credential=raw-secret",
            "stdout": "x" * 9000,
        }
    )
    assert sanitized["headers"] == {}
    assert "nested-key" not in str(sanitized)
    assert "raw-secret" not in str(sanitized)
    assert sanitized["nested"] == [{"safe": "Bearer ***"}]
    assert sanitized["stdout"].endswith("…[truncated]")

    bounded = bound_result_payload(_payload() | {"retrieved_context": ["x" * 5000]}, 1400)
    assert bounded["truncated"] is True
    import json

    assert len(json.dumps(bounded, ensure_ascii=False).encode()) <= 1400


def test_terminal_transaction_failure_rolls_back_children(db_session, monkeypatch):
    task = _business_task(db_session, celery_task_id="delivery")

    def fail_terminal(*args, **kwargs):
        raise OperationalError("UPDATE", {}, RuntimeError("commit path failed"))

    monkeypatch.setattr(result_module.task_repository, "finalize_task", fail_terminal)
    with pytest.raises(OperationalError):
        ResultPersistenceService().finalize_completed(db_session, str(task.id), _payload())
    db_session.rollback()
    assert db_session.scalar(
        select(func.count()).select_from(CaseORM).where(CaseORM.task_id == task.id)
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(ExecutionORM).where(ExecutionORM.task_id == task.id)
    ) == 0
    db_session.refresh(task)
    assert task.status == "queued"


def test_failed_task_persists_partial_result(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    failed = ResultPersistenceService().finalize_failed(
        db_session,
        str(task.id),
        RuntimeError("token=private failure"),
        {"requirements": _payload()["requirements"], "test_cases": []},
        stage="generation_failed",
    )
    db_session.commit()
    assert failed.status == "failed"
    assert failed.stage == "generation_failed"
    assert failed.result_summary["total_requirements"] == 1
    assert "private" not in failed.error
    assert failed.result_payload["errors"]


def test_terminal_redis_miss_restores_full_postgres_payload(db_session):
    task = _business_task(db_session, celery_task_id="delivery")
    ResultPersistenceService().finalize_completed(db_session, str(task.id), _payload())
    db_session.commit()
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    read_service = TaskPersistenceService(store, lambda args, eager: "unused")
    state = read_service.get_task_state(db_session, str(task.id))
    assert state["status"] == "completed"
    assert state["result"]["test_cases"][0]["case_id"] == "TC-001"
    assert store.get(str(task.id))["result"] == state["result"]


def test_result_summary_stays_small():
    summary = build_result_summary(_payload(), "completed")
    assert "test_cases" not in summary
    assert set(summary) == {
        "total_requirements",
        "total_test_cases",
        "review_score",
        "coverage_rate",
        "total_http_cases",
        "passed_http_cases",
        "failed_http_cases",
        "http_pass_rate",
        "pytest_passed",
        "failure_analysis_count",
        "final_status",
    }
