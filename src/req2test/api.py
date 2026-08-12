"""FastAPI service for asynchronous Req2Test task submission and progress streaming."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .config import GenerationConfig, LLMSettings
from .task_store import task_store
from .worker import generate_test_cases

app = FastAPI(title="Req2Test Agent API", version="0.2.0")


class TaskCreateRequest(BaseModel):
    requirement_text: str = Field(min_length=1)
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "task_store": task_store.backend}


@app.post("/api/v1/tasks", status_code=202)
def create_task(request: TaskCreateRequest) -> dict[str, str]:
    task_id = str(uuid4())
    task_store.create(task_id, payload={"source": "api"})

    eager = os.getenv("REQ2TEST_EAGER_TASKS", "false").lower() in {"1", "true", "yes"}
    if eager:
        generate_test_cases.apply(
            args=[
                task_id,
                request.requirement_text,
                request.llm_settings.model_dump(),
                request.generation_config.model_dump(),
            ]
        )
    else:
        async_result = generate_test_cases.delay(
            task_id,
            request.requirement_text,
            request.llm_settings.model_dump(),
            request.generation_config.model_dump(),
        )
        task_store.update(task_id, celery_task_id=async_result.id)

    return {"task_id": task_id, "status_url": f"/api/v1/tasks/{task_id}", "ws_url": f"/ws/tasks/{task_id}"}


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str):
    state = task_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state


@app.websocket("/ws/tasks/{task_id}")
async def task_progress(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    last_updated = None
    try:
        while True:
            state = task_store.get(task_id)
            if state is None:
                await websocket.send_json({"task_id": task_id, "status": "missing"})
                return
            if state.get("updated_at") != last_updated:
                await websocket.send_json(state)
                last_updated = state.get("updated_at")
            if state.get("status") in {"completed", "failed"}:
                return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
