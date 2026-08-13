"""Idempotent persistence for generated test cases."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import TestCaseORM


def upsert_test_case(
    session: Session,
    *,
    task_id: uuid.UUID,
    case_id: str,
    version: int = 1,
    **values: Any,
) -> TestCaseORM:
    statement = insert(TestCaseORM).values(
        task_id=task_id, case_id=case_id, version=version, **values
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_test_cases_task_case_version",
        set_={
            "module": statement.excluded.module,
            "title": statement.excluded.title,
            "priority": statement.excluded.priority,
            "test_type": statement.excluded.test_type,
            "source_requirement": statement.excluded.source_requirement,
            "preconditions": statement.excluded.preconditions,
            "steps": statement.excluded.steps,
            "updated_at": func.now(),
        },
    ).returning(TestCaseORM)
    return session.scalars(statement, execution_options={"populate_existing": True}).one()


def get_test_case_by_business_id(
    session: Session, task_id: uuid.UUID, case_id: str, version: int = 1
) -> TestCaseORM | None:
    return session.scalar(
        select(TestCaseORM).where(
            TestCaseORM.task_id == task_id,
            TestCaseORM.case_id == case_id,
            TestCaseORM.version == version,
        )
    )


def list_test_cases(session: Session, task_id: uuid.UUID) -> list[TestCaseORM]:
    statement = (
        select(TestCaseORM)
        .where(TestCaseORM.task_id == task_id)
        .order_by(TestCaseORM.case_id, TestCaseORM.version)
    )
    return list(session.scalars(statement))
