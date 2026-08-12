"""Celery worker entrypoint for asynchronous Req2Test generation and execution."""

from __future__ import annotations

import os

from celery import Celery

from .config import GenerationConfig, LLMSettings
from .execution_models import ExecutionConfig, ExecutionReport
from .progress import run_workflow_with_progress
from .task_store import task_store
from .tool_calling import execute_with_tools

BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/1"))

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
    task_store.update(
        task_id,
        status="running",
        stage="started",
        progress=5,
        message="Worker 已接收任务",
        celery_task_id=self.request.id,
    )

    settings = LLMSettings.model_validate(llm_settings)
    generation = GenerationConfig.model_validate(generation_config)
    execution = ExecutionConfig.model_validate(execution_config or {})

    def on_progress(stage: str, progress: int, message: str) -> None:
        task_store.update(
            task_id,
            status="running",
            stage=stage,
            progress=progress,
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
            task_store.update(
                task_id,
                status="running",
                stage="tool_planning",
                progress=84,
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
                    message="测试用例已生成，但自动执行阶段出现异常，已保留生成结果",
                )
        else:
            payload["execution"] = ExecutionReport(
                enabled=False,
                summary={"status": "disabled"},
            ).model_dump()

        task_store.update(
            task_id,
            status="completed",
            stage="completed",
            progress=100,
            message="任务已完成",
            result=payload,
            error=None,
        )
        return payload
    except Exception as exc:  # noqa: BLE001
        task_store.update(
            task_id,
            status="failed",
            stage="failed",
            message="任务执行失败",
            error=str(exc),
        )
        raise
