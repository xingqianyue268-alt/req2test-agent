"""Celery worker entrypoint for asynchronous Req2Test generation and execution."""

from __future__ import annotations

import logging
import os

from celery import Celery
from sqlalchemy.exc import SQLAlchemyError

from .config import GenerationConfig, LLMSettings
from .db.services.result_persistence import (
    CeleryDeliveryConflict,
    ResultPersistenceService,
    bound_result_payload,
)
from .db.services.task_persistence import task_to_projection
from .db.session import session_scope
from .execution_models import ExecutionConfig, ExecutionReport
from .progress import run_workflow_with_progress
from .task_store import task_store
from .tool_calling import execute_with_tools

logger = logging.getLogger(__name__)
result_persistence = ResultPersistenceService()


class FinalPersistenceError(RuntimeError):
    """Retryable error raised after execution results have been cached in Redis."""


BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/1")
)

celery_app = Celery("req2test", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


@celery_app.task(
    bind=True,
    name="req2test.generate",
    autoretry_for=(Exception,),
    dont_autoretry_for=(CeleryDeliveryConflict,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def generate_test_cases(
    self,
    task_id: str,
    requirement_text: str,
    llm_settings: dict,
    generation_config: dict,
    execution_config: dict | None = None,
):
    delivery_id = str(self.request.id or task_id)
    failure_stage = "generation_failed"
    try:
        with session_scope() as session:
            durable_task, healed = result_persistence.bind_delivery(
                session, task_id, delivery_id
            )
    except CeleryDeliveryConflict:
        logger.error(
            "Rejected conflicting Celery delivery %s for business task %s",
            delivery_id,
            task_id,
        )
        raise
    if healed:
        logger.info("Self-healed celery_task_id for business task %s", task_id)

    if durable_task.status in {"completed", "failed"} and durable_task.result_payload:
        task_store.set(task_id, task_to_projection(durable_task))
        if durable_task.status == "failed":
            raise RuntimeError(durable_task.error or "Task previously failed")
        return durable_task.result_payload

    cached = task_store.get(task_id) or {}
    if cached.get("stage") == "persistence_pending" and cached.get("persistence_payload"):
        payload = cached["persistence_payload"]
        try:
            with session_scope() as session:
                durable_task = result_persistence.finalize_completed(session, task_id, payload)
        except SQLAlchemyError as exc:
            raise FinalPersistenceError("PostgreSQL final persistence retry failed") from exc
        task_store.set(task_id, task_to_projection(durable_task))
        return payload
    if cached.get("stage") == "failure_persistence_pending":
        partial = cached.get("persistence_payload") or {}
        cached_error = RuntimeError(cached.get("persistence_error") or "Worker failed")
        try:
            with session_scope() as session:
                durable_task = result_persistence.finalize_failed(
                    session,
                    task_id,
                    cached_error,
                    partial,
                    stage=cached.get("failure_stage") or "internal_error",
                )
        except SQLAlchemyError as exc:
            raise FinalPersistenceError("PostgreSQL failure persistence retry failed") from exc
        task_store.set(task_id, task_to_projection(durable_task))
        raise cached_error

    with session_scope() as session:
        durable_task = result_persistence.persist_milestone(
            session, task_id, status="running", stage="running", progress=5
        )
    task_store.update(
        task_id,
        status="running",
        stage="started",
        progress=5,
        state_version=durable_task.state_version,
        message="Worker 已接收任务",
        celery_task_id=delivery_id,
    )

    try:
        settings = LLMSettings.model_validate(llm_settings)
        generation = GenerationConfig.model_validate(generation_config)
        execution = ExecutionConfig.model_validate(execution_config or {})
    except Exception as exc:  # noqa: BLE001
        with session_scope() as session:
            durable_task = result_persistence.finalize_failed(
                session, task_id, exc, stage="generation_failed"
            )
        task_store.set(task_id, task_to_projection(durable_task))
        raise

    def on_progress(stage: str, progress: int, message: str) -> None:
        state_version = None
        if stage == "generation_completed":
            with session_scope() as session:
                milestone = result_persistence.persist_milestone(
                    session,
                    task_id,
                    status="running",
                    stage="generation_completed",
                    progress=progress,
                )
            state_version = milestone.state_version
        task_store.update(
            task_id,
            status="running",
            stage=stage,
            progress=progress,
            **({"state_version": state_version} if state_version is not None else {}),
            message=message,
        )

    try:
        result = run_workflow_with_progress(
            requirement_text=requirement_text,
            llm_settings=settings,
            generation_config=generation,
            on_progress=on_progress,
        )
        payload = result.model_dump()

        if execution.enabled:
            failure_stage = "execution_failed"
            with session_scope() as session:
                durable_task = result_persistence.persist_milestone(
                    session,
                    task_id,
                    status="running",
                    stage="execution_started",
                    progress=84,
                )
            task_store.update(
                task_id,
                status="running",
                stage="tool_planning",
                progress=84,
                state_version=durable_task.state_version,
                message="正在规划可执行 API 测试并准备 Tool Calling",
            )
            try:
                execution_report = execute_with_tools(
                    requirement_text=requirement_text,
                    workflow_result=result,
                    llm_settings=settings,
                    config=execution,
                )
                payload["execution"] = execution_report.model_dump()
                task_store.update(
                    task_id,
                    status="running",
                    stage="failure_analysis",
                    progress=98,
                    message="真实执行完成，失败归因与测试结果已汇总",
                )
            except Exception as execution_exc:  # noqa: BLE001
                fallback_report = ExecutionReport(
                    enabled=True,
                    summary={"status": "tool_error"},
                    warnings=[f"执行阶段发生工具级异常：{execution_exc}"],
                )
                payload["execution"] = fallback_report.model_dump()
                task_store.update(
                    task_id,
                    status="running",
                    stage="execution_warning",
                    progress=98,
                    message=(
                        "测试用例已生成，但自动执行阶段出现异常，已保留生成结果"
                    ),
                )
        else:
            payload["execution"] = ExecutionReport(
                enabled=False,
                summary={"status": "disabled"},
            ).model_dump()

        payload = bound_result_payload(payload)
        task_store.update(
            task_id,
            status="running",
            stage="persistence_pending",
            progress=99,
            message="执行完成，正在持久化最终结果",
            persistence_payload=payload,
        )
        try:
            with session_scope() as session:
                durable_task = result_persistence.finalize_completed(
                    session, task_id, payload
                )
        except SQLAlchemyError as exc:
            logger.exception("Final PostgreSQL transaction failed for task %s", task_id)
            raise FinalPersistenceError("PostgreSQL final persistence failed") from exc
        task_store.set(task_id, task_to_projection(durable_task))
        return payload
    except FinalPersistenceError:
        raise
    except CeleryDeliveryConflict:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            current = task_store.get(task_id) or {}
        except Exception:  # noqa: BLE001
            current = {}
        partial_payload = current.get("persistence_payload") or {}
        task_store.update(
            task_id,
            status="running",
            stage="failure_persistence_pending",
            progress=99,
            message="任务失败，正在持久化失败状态",
            persistence_payload=partial_payload,
            persistence_error=str(exc),
            failure_stage=failure_stage,
        )
        try:
            with session_scope() as session:
                durable_task = result_persistence.finalize_failed(
                    session, task_id, exc, partial_payload, stage=failure_stage
                )
        except SQLAlchemyError as persistence_exc:
            raise FinalPersistenceError(
                "PostgreSQL failure persistence failed"
            ) from persistence_exc
        task_store.set(task_id, task_to_projection(durable_task))
        raise
