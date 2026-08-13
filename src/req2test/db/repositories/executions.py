"""Idempotent persistence for tool execution results."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import ExecutionORM


def upsert_execution(
    session: Session, *, idempotency_key: str, task_id: uuid.UUID, **values: Any
) -> ExecutionORM:
    statement = insert(ExecutionORM).values(
        idempotency_key=idempotency_key, task_id=task_id, **values
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_executions_idempotency_key",
        set_={
            "test_case_id": statement.excluded.test_case_id,
            "kind": statement.excluded.kind,
            "attempt": statement.excluded.attempt,
            "method": statement.excluded.method,
            "path": statement.excluded.path,
            "expected_status": statement.excluded.expected_status,
            "actual_status": statement.excluded.actual_status,
            "passed": statement.excluded.passed,
            "duration_ms": statement.excluded.duration_ms,
            "response_excerpt": statement.excluded.response_excerpt,
            "error": statement.excluded.error,
            "failure_category": statement.excluded.failure_category,
        },
    ).returning(ExecutionORM)
    return session.scalars(statement, execution_options={"populate_existing": True}).one()


def list_executions(session: Session, task_id: uuid.UUID) -> list[ExecutionORM]:
    statement = (
        select(ExecutionORM)
        .where(ExecutionORM.task_id == task_id)
        .order_by(ExecutionORM.created_at, ExecutionORM.id)
    )
    return list(session.scalars(statement))
