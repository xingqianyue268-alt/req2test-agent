"""SQLAlchemy repository for the Task aggregate."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import TaskORM


def create_task(session: Session, **values: Any) -> TaskORM:
    task = TaskORM(**values)
    session.add(task)
    session.flush()
    return task


def get_task(session: Session, task_id: uuid.UUID) -> TaskORM | None:
    return session.get(TaskORM, task_id)


def get_task_for_update(session: Session, task_id: uuid.UUID) -> TaskORM | None:
    statement = select(TaskORM).where(TaskORM.id == task_id).with_for_update()
    return session.scalar(statement)


def set_celery_task_id(session: Session, task_id: uuid.UUID, celery_task_id: str) -> TaskORM:
    task = get_task_for_update(session, task_id)
    if task is None:
        raise LookupError(f"Task {task_id} does not exist")
    task.celery_task_id = celery_task_id
    task.state_version += 1
    session.flush()
    return task


def update_task_state(
    session: Session,
    task_id: uuid.UUID,
    *,
    status: str,
    stage: str,
    progress: int | None = None,
    error: str | None = None,
) -> TaskORM:
    task = get_task_for_update(session, task_id)
    if task is None:
        raise LookupError(f"Task {task_id} does not exist")
    task.status = status
    task.stage = stage
    if progress is not None:
        task.progress = progress
    task.error = error
    task.state_version += 1
    session.flush()
    return task


def list_tasks(session: Session, *, offset: int = 0, limit: int = 50) -> list[TaskORM]:
    statement: Select[tuple[TaskORM]] = (
        select(TaskORM).order_by(TaskORM.created_at.desc()).offset(offset).limit(limit)
    )
    return list(session.scalars(statement))
