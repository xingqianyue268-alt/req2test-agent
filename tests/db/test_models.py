from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from req2test.db.models import (
    ExecutionORM,
    KnowledgeDocumentORM,
    TaskORM,
    TestCaseORM as CaseORM,
    UserORM,
)


def _task(**overrides):
    values = {
        "title": "Login requirement",
        "requirement_text": "Users can log in.",
        "generation_config": {"max_cases": 12},
        "execution_config": {"enabled": True},
        "result_payload": {
            "requirements": [{"id": "REQ-001"}],
            "test_cases": [{"case_id": "TC-001"}],
            "review": {"score": 92},
        },
    }
    values.update(overrides)
    return TaskORM(**values)


def _case(task_id, **overrides):
    values = {
        "task_id": task_id,
        "case_id": "TC-001",
        "module": "Login",
        "title": "Login with valid credentials",
        "priority": "P1",
        "test_type": "positive",
        "source_requirement": "REQ-001",
        "preconditions": ["User exists"],
        "steps": [{"action": "Submit credentials", "expected": "Login succeeds"}],
    }
    values.update(overrides)
    return CaseORM(**values)


def test_uuid_jsonb_result_payload_and_timezone_timestamps(db_session):
    task = _task()
    db_session.add(task)
    db_session.flush()

    assert isinstance(task.id, uuid.UUID)
    assert task.result_payload["review"]["score"] == 92
    assert task.created_at.tzinfo is not None
    assert task.updated_at.tzinfo is not None


def test_progress_check_constraint(db_session):
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_task(progress=101))
        db_session.flush()


def test_required_unique_constraints(db_session):
    user_a = UserORM(email="team@example.com", password_hash="hash-a")
    user_b = UserORM(email="team@example.com", password_hash="hash-b")
    db_session.add(user_a)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(user_b)
        db_session.flush()

    task_a = _task(celery_task_id="celery-1")
    task_b = _task(title="Other", celery_task_id="celery-1")
    db_session.add(task_a)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(task_b)
        db_session.flush()

    case_a = _case(task_a.id)
    db_session.add(case_a)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_case(task_a.id, title="Duplicate"))
        db_session.flush()

    execution_a = ExecutionORM(
        task_id=task_a.id, kind="http", idempotency_key="run-1", passed=True
    )
    db_session.add(execution_a)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            ExecutionORM(
                task_id=task_a.id, kind="http", idempotency_key="run-1", passed=False
            )
        )
        db_session.flush()

    document_a = KnowledgeDocumentORM(
        title="API guide",
        source_name="api.md",
        kind="markdown",
        vector_collection="req2test",
        vector_document_id="doc-1",
        document_metadata={"section": "auth"},
    )
    db_session.add(document_a)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            KnowledgeDocumentORM(
                title="Duplicate",
                source_name="copy.md",
                kind="markdown",
                vector_collection="req2test",
                vector_document_id="doc-1",
            )
        )
        db_session.flush()


def test_foreign_key_delete_behaviour(db_session):
    user = UserORM(email="owner@example.com", password_hash="hash")
    task = _task(user=user)
    db_session.add(task)
    db_session.flush()

    case = _case(task.id)
    db_session.add(case)
    db_session.flush()
    execution = ExecutionORM(
        task_id=task.id,
        test_case_id=case.id,
        kind="http",
        idempotency_key="delete-behaviour",
        passed=False,
    )
    db_session.add(execution)
    db_session.flush()

    db_session.delete(user)
    db_session.flush()
    db_session.expire(task)
    assert task.user_id is None

    db_session.delete(case)
    db_session.flush()
    db_session.expire(execution)
    assert execution.test_case_id is None

    task_id = task.id
    db_session.execute(delete(TaskORM).where(TaskORM.id == task_id))
    db_session.flush()
    assert db_session.scalar(select(ExecutionORM).where(ExecutionORM.task_id == task_id)) is None
