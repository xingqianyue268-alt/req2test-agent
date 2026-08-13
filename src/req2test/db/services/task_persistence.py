"""Task creation and live-projection orchestration."""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from collections.abc import Callable, Mapping
from datetime import datetime
from math import ceil
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
        "trace_id": str(task.id),
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


def task_to_list_item(task: TaskORM, *, include_user: bool = False) -> dict[str, Any]:
    summary = task.result_summary or {}
    item = {
        "id": str(task.id),
        "task_id": str(task.id),
        "title": task.title,
        "status": task.status,
        "stage": task.stage,
        "progress": task.progress,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "summary": {
            "total_test_cases": int(summary.get("total_test_cases") or 0),
            "review_score": summary.get("review_score"),
            "http_pass_rate": summary.get("http_pass_rate"),
            "pytest_passed": summary.get("pytest_passed"),
            "failure_analysis_count": int(
                summary.get("failure_analysis_count") or 0
            ),
            "primary_failure_category": summary.get("primary_failure_category"),
            "failure_category_counts": summary.get("failure_category_counts") or {},
        },
    }
    if include_user:
        item["user_id"] = str(task.user_id) if task.user_id else None
        item["user_email"] = task.user.email if task.user else None
    return item


def task_to_detail(task: TaskORM, state: dict[str, Any]) -> dict[str, Any]:
    payload = task.result_payload or state.get("result") or {}
    execution = payload.get("execution") or {}
    public_payload = deepcopy(payload)
    public_execution = public_payload.get("execution") or {}
    public_execution.pop("diagnostic_evidence", None)
    detail = {
        **state,
        "trace_id": payload.get("trace_id") or str(task.id),
        "task": {
            "id": str(task.id),
            "title": task.title,
            "requirement_text": task.requirement_text,
            "status": task.status,
            "stage": task.stage,
            "progress": task.progress,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error": task.error,
        },
        "requirements": payload.get("requirements") or [],
        "test_cases": payload.get("test_cases") or [],
        "review": payload.get("review") or {},
        "rag": {"retrieved_context": payload.get("retrieved_context") or []},
        "execution": {
            "enabled": execution.get("enabled", False),
            "summary": execution.get("summary") or {},
            "executable_cases": execution.get("executable_cases") or [],
            "http_results": execution.get("http_results") or [],
            "pytest_result": execution.get("pytest_result"),
        },
        "failure_analysis": execution.get("failure_analysis") or [],
        "failure_analysis_v2": execution.get("failure_analysis_v2") or {
            "trace_id": payload.get("trace_id") or str(task.id),
            "summary": {
                "failure_count": 0,
                "category_distribution": {},
                "primary_failure_category": None,
            },
            "diagnoses": [],
        },
        "warnings": [
            *(payload.get("warnings") or []),
            *(execution.get("warnings") or []),
        ],
        "errors": payload.get("errors") or [],
        "raw_payload": public_payload,
    }
    # Preserve the Phase 4B response for existing polling and Workbench clients.
    detail["result"] = public_payload or None
    return detail


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
        user_id: uuid.UUID | None = None,
    ) -> TaskORM:
        task_id = uuid.uuid4()
        try:
            task = task_repository.create_task(
                session,
                id=task_id,
                user_id=user_id,
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

        # The immutable business Task UUID is also the task-wide trace root.
        # Keeping these identifiers equal avoids an extra nullable schema field
        # while still providing explicit structured correlation everywhere.
        self.task_store.update(str(task.id), trace_id=str(task.id))

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

    def get_task_state(
        self,
        session: Session,
        task_id: str,
        *,
        user_id: uuid.UUID | None = None,
        is_admin: bool = False,
        allow_anonymous: bool = False,
    ) -> dict[str, Any] | None:
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
        owns_task = user_id is not None and task.user_id == user_id
        anonymous_task = allow_anonymous and user_id is None and task.user_id is None
        if not (is_admin or owns_task or anonymous_task):
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

    def get_task_detail(
        self,
        session: Session,
        task_id: str,
        *,
        user_id: uuid.UUID | None = None,
        is_admin: bool = False,
        allow_anonymous: bool = False,
    ) -> dict[str, Any] | None:
        state = self.get_task_state(
            session,
            task_id,
            user_id=user_id,
            is_admin=is_admin,
            allow_anonymous=allow_anonymous,
        )
        if state is None:
            return None
        task = task_repository.get_task(session, uuid.UUID(task_id))
        return task_to_detail(task, state) if task else None

    def get_task_diagnostics(
        self,
        session: Session,
        task_id: str,
        *,
        user_id: uuid.UUID | None = None,
        is_admin: bool = False,
        allow_anonymous: bool = False,
    ) -> dict[str, Any] | None:
        state = self.get_task_state(
            session,
            task_id,
            user_id=user_id,
            is_admin=is_admin,
            allow_anonymous=allow_anonymous,
        )
        if state is None:
            return None
        try:
            task = task_repository.get_task(session, uuid.UUID(task_id))
        except ValueError:
            return None
        if task is None:
            return None
        payload = task.result_payload or state.get("result") or {}
        execution = payload.get("execution") or {}
        analysis = execution.get("failure_analysis_v2") or {}
        return {
            "trace_id": payload.get("trace_id") or str(task.id),
            "summary": analysis.get("summary") or {},
            "diagnoses": analysis.get("diagnoses") or [],
            "evidence": execution.get("diagnostic_evidence") or [],
            "evidence_collection_overhead_ms": execution.get(
                "evidence_collection_overhead_ms", 0.0
            ),
        }

    def list_task_states(
        self,
        session: Session,
        *,
        user_id: uuid.UUID,
        is_admin: bool,
        page: int,
        page_size: int,
        status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        records, total = task_repository.search_tasks(
            session,
            user_id=user_id,
            include_all=is_admin,
            offset=(page - 1) * page_size,
            limit=page_size,
            status=status,
            created_from=created_from,
            created_to=created_to,
            keyword=keyword,
        )
        return {
            "items": [
                task_to_list_item(task, include_user=is_admin) for task in records
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": ceil(total / page_size) if total else 0,
        }

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
