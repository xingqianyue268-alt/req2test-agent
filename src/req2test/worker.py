"""Celery worker entrypoint for asynchronous Req2Test generation and execution."""

from __future__ import annotations

import logging
import os
import time

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
from .diagnostics.evidence import EvidenceCollector, TraceContext
from .progress import run_workflow_with_progress
from .task_store import TaskStoreUnavailable, task_store
from .tool_calling import execute_with_tools

logger = logging.getLogger(__name__)
result_persistence = ResultPersistenceService()


class FinalPersistenceError(RuntimeError):
    """Retryable error raised after execution results have been cached in Redis."""


class DuplicateDeliveryInFlight(RuntimeError):
    """A broker redelivery arrived while the same real attempt is still claimed."""


MAX_TASK_RETRIES = int(os.getenv("CELERY_TASK_MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE_SECONDS = int(os.getenv("CELERY_RETRY_BACKOFF_BASE_SECONDS", "2"))
RETRY_BACKOFF_MAX_SECONDS = int(os.getenv("CELERY_RETRY_BACKOFF_MAX_SECONDS", "30"))


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
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


def _generate_test_cases_once(
    self,
    task_id: str,
    requirement_text: str,
    llm_settings: dict,
    generation_config: dict,
    execution_config: dict | None = None,
):
    delivery_id = str(self.request.id or task_id)
    trace_context = TraceContext.for_task(task_id, delivery_id)
    evidence = EvidenceCollector(trace_context)
    evidence.collect_worker(
        event="started",
        stage="worker_start",
        retry_count=int(getattr(self.request, "retries", 0) or 0),
    )
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
        _set_terminal_projection_best_effort(task_id, durable_task)
        if durable_task.status == "failed":
            raise RuntimeError(durable_task.error or "Task previously failed")
        return durable_task.result_payload

    cached = task_store.get(task_id) or {}
    if cached.get("persistence_payload") and not cached.get("failure_stage"):
        payload = cached["persistence_payload"]
        try:
            with session_scope() as session:
                durable_task = result_persistence.finalize_completed(session, task_id, payload)
        except SQLAlchemyError as exc:
            raise FinalPersistenceError("PostgreSQL final persistence retry failed") from exc
        _set_terminal_projection_best_effort(task_id, durable_task)
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
        _set_terminal_projection_best_effort(task_id, durable_task)
        raise cached_error

    retry_count = int(getattr(self.request, "retries", 0) or 0)
    with session_scope() as session:
        durable_task, claimed = result_persistence.claim_attempt(
            session, task_id, delivery_id, retry_count
        )
    if not claimed:
        if bool((getattr(self.request, "delivery_info", None) or {}).get("redelivered")):
            raise DuplicateDeliveryInFlight(
                f"Delivery {delivery_id} attempt {retry_count} is already in progress"
            )
        logger.warning(
            "Ignored duplicate active delivery %s for business task %s attempt %s",
            delivery_id,
            task_id,
            retry_count,
        )
        return durable_task.result_payload or {
            "task_id": task_id,
            "status": durable_task.status,
            "stage": durable_task.stage,
            "duplicate_delivery": True,
        }

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
        partial = {
            "task_reliability": _reliability_metadata(
                retry_count, final_failure_reason=str(exc)
            )
        }
        with session_scope() as session:
            durable_task = result_persistence.finalize_failed(
                session, task_id, exc, partial, stage="generation_failed"
            )
        _set_terminal_projection_best_effort(task_id, durable_task)
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
        generation_started = time.perf_counter()
        result = run_workflow_with_progress(
            requirement_text=requirement_text,
            llm_settings=settings,
            generation_config=generation,
            on_progress=on_progress,
        )
        payload = result.model_dump()
        payload["trace_id"] = trace_context.trace_id
        evidence.collect_rag(
            query=requirement_text,
            top_k=4,
            contexts=result.retrieved_context,
        )
        evidence.collect_generation(
            provider=settings.mode,
            model=settings.model,
            duration_ms=round((time.perf_counter() - generation_started) * 1000, 2),
            parse_success=not bool(result.errors),
            generated_case_count=len(result.test_cases),
            validation_issues=result.errors,
            review_score=result.review.score,
        )
        evidence.collect_infrastructure(
            {
                "PostgreSQL": {"state": "healthy", "basis": "worker milestone committed"},
                "Redis": {"state": "healthy", "basis": "live progress update succeeded"},
                "RabbitMQ": {"state": "connected", "basis": "Celery delivery received"},
                "Knowledge/Chroma": {
                    "state": "observed" if result.retrieved_context else "unknown",
                    "basis": "RAG workflow output",
                },
            }
        )

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
                    trace_context=trace_context,
                    initial_evidence=evidence.dump(),
                )
                finish_evidence = EvidenceCollector(trace_context)
                finish_evidence.collect_worker(
                    event="finished",
                    stage="execution_completed",
                    retry_count=int(getattr(self.request, "retries", 0) or 0),
                )
                execution_report.diagnostic_evidence.extend(finish_evidence.dump())
                execution_report.evidence_collection_overhead_ms = round(
                    execution_report.evidence_collection_overhead_ms
                    + finish_evidence.overhead_ms(),
                    3,
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
                    trace_id=trace_context.trace_id,
                    summary={"status": "tool_error"},
                    warnings=[f"执行阶段发生工具级异常：{execution_exc}"],
                )
                evidence.collect_worker(
                    event="exception",
                    stage="execution_failed",
                    retry_count=int(getattr(self.request, "retries", 0) or 0),
                    exception=execution_exc,
                )
                fallback_report.diagnostic_evidence = evidence.dump()
                fallback_report.evidence_collection_overhead_ms = evidence.overhead_ms()
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
                trace_id=trace_context.trace_id,
                summary={"status": "disabled"},
                diagnostic_evidence=evidence.dump(),
                evidence_collection_overhead_ms=evidence.overhead_ms(),
            ).model_dump()

        payload["task_reliability"] = _reliability_metadata(retry_count)
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
        _set_terminal_projection_best_effort(task_id, durable_task)
        return payload
    except FinalPersistenceError:
        raise
    except CeleryDeliveryConflict:
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_transient_infrastructure_error(exc):
            raise
        evidence.collect_worker(
            event="exception",
            stage=failure_stage,
            retry_count=int(getattr(self.request, "retries", 0) or 0),
            exception=exc,
        )
        try:
            current = task_store.get(task_id) or {}
        except Exception:  # noqa: BLE001
            current = {}
        partial_payload = current.get("persistence_payload") or {
            "trace_id": trace_context.trace_id,
            "execution": {
                "enabled": False,
                "trace_id": trace_context.trace_id,
                "diagnostic_evidence": evidence.dump(),
                "evidence_collection_overhead_ms": evidence.overhead_ms(),
            },
        }
        partial_payload["task_reliability"] = _reliability_metadata(
            retry_count, final_failure_reason=str(exc)
        )
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
        _set_terminal_projection_best_effort(task_id, durable_task)
        raise


def _is_transient_infrastructure_error(error: BaseException) -> bool:
    """Recognize retryable transport/storage failures without retrying business results."""

    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (
                FinalPersistenceError,
                DuplicateDeliveryInFlight,
                SQLAlchemyError,
                TaskStoreUnavailable,
                ConnectionError,
                TimeoutError,
            ),
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _retry_countdown(retry_count: int) -> int:
    return min(
        RETRY_BACKOFF_BASE_SECONDS * (2**retry_count), RETRY_BACKOFF_MAX_SECONDS
    )


def _reliability_metadata(
    retry_count: int, *, dead_lettered: bool = False, final_failure_reason: str | None = None
) -> dict:
    return {
        "retry_count": retry_count,
        "max_retries": MAX_TASK_RETRIES,
        "dead_lettered": dead_lettered,
        "final_failure_reason": final_failure_reason,
    }


def _set_terminal_projection_best_effort(task_id: str, durable_task) -> None:
    try:
        task_store.set(task_id, task_to_projection(durable_task))
    except TaskStoreUnavailable:
        logger.warning(
            "PostgreSQL terminal state is durable but Redis projection failed for task %s",
            task_id,
        )


def _cached_partial_payload(task_id: str) -> dict:
    try:
        state = task_store.get(task_id) or {}
    except Exception:  # noqa: BLE001
        return {}
    return state.get("persistence_payload") or {}


def _record_retry(
    task_id: str, error: BaseException, *, retry_count: int, countdown_seconds: int
) -> None:
    durable_task = None
    try:
        with session_scope() as session:
            durable_task = result_persistence.record_retry(
                session,
                task_id,
                error,
                retry_count=retry_count,
                max_retries=MAX_TASK_RETRIES,
                countdown_seconds=countdown_seconds,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist retry metadata for task %s", task_id)
    try:
        if durable_task is not None:
            projection = task_to_projection(durable_task)
            projection["message"] = f"瞬时基础设施异常，{countdown_seconds} 秒后重试"
            current = task_store.get(task_id) or {}
            task_store.set(task_id, {**current, **projection})
        else:
            task_store.update(
                task_id,
                status="running",
                stage="retrying",
                retry_count=retry_count,
                message=f"瞬时基础设施异常，{countdown_seconds} 秒后重试",
                error=str(error),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not update Redis retry projection for task %s", task_id)


def _record_dead_letter(task_id: str, error: BaseException, *, retry_count: int) -> None:
    durable_task = None
    partial_payload = _cached_partial_payload(task_id)
    try:
        with session_scope() as session:
            durable_task = result_persistence.finalize_dead_lettered(
                session,
                task_id,
                error,
                partial_payload,
                retry_count=retry_count,
                max_retries=MAX_TASK_RETRIES,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist dead-letter state for task %s", task_id)
    try:
        if durable_task is not None:
            task_store.set(task_id, task_to_projection(durable_task))
        else:
            task_store.update(
                task_id,
                status="failed",
                stage="dead_lettered",
                progress=100,
                retry_count=retry_count,
                dead_lettered=True,
                message="任务在有限重试后仍失败",
                error=str(error),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Could not update Redis dead-letter projection for task %s", task_id)


@celery_app.task(bind=True, name="req2test.generate", max_retries=MAX_TASK_RETRIES)
def generate_test_cases(
    self,
    task_id: str,
    requirement_text: str,
    llm_settings: dict,
    generation_config: dict,
    execution_config: dict | None = None,
):
    """Run once, retry only transient infrastructure failures, and finalize exhaustion."""

    try:
        return _generate_test_cases_once(
            self,
            task_id,
            requirement_text,
            llm_settings,
            generation_config,
            execution_config,
        )
    except CeleryDeliveryConflict:
        raise
    except Exception as exc:  # noqa: BLE001
        if not _is_transient_infrastructure_error(exc):
            raise
        current_retry = int(getattr(self.request, "retries", 0) or 0)
        if current_retry < MAX_TASK_RETRIES:
            countdown = _retry_countdown(current_retry)
            _record_retry(
                task_id,
                exc,
                retry_count=current_retry + 1,
                countdown_seconds=countdown,
            )
            raise self.retry(
                exc=exc,
                countdown=countdown,
                max_retries=MAX_TASK_RETRIES,
            )
        _record_dead_letter(task_id, exc, retry_count=current_retry)
        raise
