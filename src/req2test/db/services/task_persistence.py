"""Task creation and live-projection orchestration."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...task_store import TaskStore, TaskStoreUnavailable
from ..models import TaskORM
from ..repositories import tasks as task_repository


TERMINAL_STATUSES = {"completed", "failed"}
SENSITIVE_KEY_PARTS = {
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
}


class TaskPersistenceError(RuntimeError):
    """Base error translated to a service-unavailable API response."""


class DatabasePersistenceError(TaskPersistenceError):
    pass


class LiveProjectionUnavailable(TaskPersistenceError):
    pass


class TaskDispatchError(TaskPersistenceError):
    pass


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    if normalized in SENSITIVE_KEY_PARTS:
        return True
    if "api_key" in normalized or "private_key" in normalized:
        return True
    parts = set(normalized.split("_"))
    return bool(
        parts & {"authorization", "cookie", "credential", "password", "secret", "token"}
    )


def sanitize_config(value: Any) -> Any:
    """Recursively omit credential-bearing keys before PostgreSQL persistence."""

    if isinstance(value, Mapping):
        return {
            str(key): sanitize_config(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_config(item) for item in value]
    return value


def generate_task_title(requirement_text: str, explicit_title: str | None = None) -> str:
    """Generate a backward-compatible, database-safe Task title."""

    candidate = (explicit_title or "").strip()
    if not candidate:
        candidate = next(
            (line.strip() for line in requirement_text.splitlines() if line.strip()), ""
        )
    return (candidate or "Untitled Test Task")[:255]


def safe_error_summary(error: BaseException) -> str:
    summary = str(error).replace("\n", " ").strip() or error.__class__.__name__
    summary = re.sub(r"://[^/@\s]+:[^/@\s]+@", "://***:***@", summary)
    summary = re.sub(
        r"(?i)(api[_-]?key|authorization|cookie|credential|password|"
        r"private[_-]?(?:credential|key)|secret|token)\s*[=:]\s*[^\s,;]+",
        r"\1=***",
        summary,
    )
    return summary[:500]


def task_to_projection(task: TaskORM) -> dict[str, Any]:
    """Map ORM state to the existing JSON-compatible TaskStore contract."""

    messages = {
        "queued": "任务已提交，等待处理",
        "failed": "任务提交失败",
        "completed": "任务已完成",
    }
    return {
        "task_id": str(task.id),
        "status": task.status,
        "stage": task.stage,
        "progress": task.progress,
        "state_version": task.state_version,
        "celery_task_id": task.celery_task_id,
        "message": messages.get(task.status, "任务处理中"),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "result": task.result_payload,
        "error": task.error,
        "payload": {
            "source": "api",
            "execution_enabled": bool(task.execution_config.get("enabled", False)),
        },
    }


Publisher = Callable[[list[Any], bool], str]


class TaskPersistenceService:
    def __init__(self, task_store: TaskStore, publisher: Publisher) -> None:
        self.task_store = task_store
        self.publisher = publisher

    def create_and_dispatch(
        self,
        session: Session,
        *,
        requirement_text: str,
        title: str | None,
        llm_settings: dict[str, Any],
        generation_config: dict[str, Any],
        execution_config: dict[str, Any],
        eager: bool,
    ) -> TaskORM:
        task_id = uuid.uuid4()
        try:
            task = task_repository.create_task(
                session,
                id=task_id,
                title=generate_task_title(requirement_text, title),
                requirement_text=requirement_text,
                status="queued",
                stage="queued",
                progress=0,
                state_version=1,
                generation_config=sanitize_config(generation_config),
                execution_config=sanitize_config(execution_config),
            )
            session.commit()
            session.refresh(task)
        except SQLAlchemyError as exc:
            session.rollback()
            raise DatabasePersistenceError("PostgreSQL task creation failed") from exc

        try:
            self.task_store.set(str(task.id), task_to_projection(task))
        except TaskStoreUnavailable as exc:
            self._compensate_failure(
                session, task.id, stage="infrastructure_unavailable", error=exc
            )
            raise LiveProjectionUnavailable("Redis is required to create a task") from exc

        task_args = [
            str(task.id),
            requirement_text,
            llm_settings,
            generation_config,
            execution_config,
        ]
        try:
            celery_task_id = self.publisher(task_args, eager)
        except Exception as exc:  # Celery/Kombu expose multiple transport exception types.
            self._compensate_failure(session, task.id, stage="dispatch_failed", error=exc)
            raise TaskDispatchError("Task dispatch failed") from exc

        try:
            task = task_repository.set_celery_task_id(session, task.id, celery_task_id)
            session.commit()
            session.refresh(task)
        except SQLAlchemyError as exc:
            session.rollback()
            # Publish already succeeded. Phase 4A-3 will let the Worker repair this field
            # from request.id rather than dispatching a duplicate task.
            raise DatabasePersistenceError(
                "Task dispatched but Celery id persistence failed"
            ) from exc

        try:
            current = self.task_store.get(str(task.id))
            if current and (
                current.get("status") != "queued" or int(current.get("progress") or 0) > 0
            ):
                current["celery_task_id"] = task.celery_task_id
                current["state_version"] = task.state_version
                self.task_store.set(str(task.id), current)
            else:
                self.task_store.set(str(task.id), task_to_projection(task))
        except TaskStoreUnavailable:
            # A race can take Redis down after a successful publish. The durable Task and
            # celery_task_id remain intact; returning the accepted Task avoids duplicate dispatch.
            pass
        return task

    def get_task_state(self, session: Session, task_id: str) -> dict[str, Any] | None:
        try:
            parsed_id = uuid.UUID(task_id)
        except ValueError:
            return None

        try:
            live_state = self.task_store.get(task_id)
        except TaskStoreUnavailable:
            live_state = None

        task = task_repository.get_task(session, parsed_id)
        if task is None:
            return None

        durable_state = task_to_projection(task)
        if live_state is None:
            self._best_effort_rebuild(task_id, durable_state)
            return durable_state

        durable_version = int(task.state_version or 0)
        live_version = int(live_state.get("state_version") or 0)
        if task.status in TERMINAL_STATUSES or live_version < durable_version:
            self._best_effort_rebuild(task_id, durable_state)
            return durable_state
        return live_state

    def _compensate_failure(
        self, session: Session, task_id: uuid.UUID, *, stage: str, error: BaseException
    ) -> None:
        summary = safe_error_summary(error)
        try:
            task = task_repository.update_task_state(
                session,
                task_id,
                status="failed",
                stage=stage,
                progress=0,
                error=summary,
            )
            session.commit()
            session.refresh(task)
        except SQLAlchemyError:
            session.rollback()
            return
        self._best_effort_rebuild(str(task.id), task_to_projection(task))

    def _best_effort_rebuild(self, task_id: str, state: dict[str, Any]) -> None:
        try:
            self.task_store.set(task_id, state)
        except TaskStoreUnavailable:
            pass
