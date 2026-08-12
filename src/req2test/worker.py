"""Celery worker entrypoint for asynchronous Req2Test generation."""

from __future__ import annotations

import os

from celery import Celery

from .config import GenerationConfig, LLMSettings
from .progress import run_workflow_with_progress
from .task_store import task_store

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


@celery_app.task(bind=True, name="req2test.generate", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def generate_test_cases(self, task_id: str, requirement_text: str, llm_settings: dict, generation_config: dict):
    task_store.update(
        task_id,
        status="running",
        stage="started",
        progress=5,
        message="Worker 已接收任务",
        celery_task_id=self.request.id,
    )

    def on_progress(stage: str, progress: int, message: str) -> None:
        task_store.update(
            task_id,
            status="running" if progress < 100 else "completed",
            stage=stage,
            progress=progress,
            message=message,
        )

    try:
        result = run_workflow_with_progress(
            requirement_text=requirement_text,
            llm_settings=LLMSettings.model_validate(llm_settings),
            generation_config=GenerationConfig.model_validate(generation_config),
            on_progress=on_progress,
        )
        payload = result.model_dump()
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
