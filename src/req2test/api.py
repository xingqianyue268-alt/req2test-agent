"""FastAPI service for asynchronous Req2Test generation, execution and progress streaming."""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import GenerationConfig, LLMSettings
from .demo_ui import DEMO_HTML
from .document_loader import SUPPORTED_SUFFIXES, load_document_bytes
from .execution_models import ExecutionConfig
from .task_store import task_store
from .worker import generate_test_cases

app = FastAPI(title="Req2Test Agent API", version="0.4.0")


class TaskCreateRequest(BaseModel):
    requirement_text: str = Field(min_length=1)
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
    execution_config: ExecutionConfig = Field(default_factory=ExecutionConfig)


class DocumentParseRequest(BaseModel):
    filename: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "task_store": task_store.backend}


@app.get("/", response_class=HTMLResponse)
def home_page() -> str:
    """Primary unified workbench entrypoint."""

    return DEMO_HTML


@app.get("/demo-target/health")
def demo_target_health() -> dict[str, str]:
    """Deterministic GET endpoint used by the built-in execution demo."""

    return {"status": "ok", "service": "req2test-demo-target"}


@app.post("/demo-target/echo")
def demo_target_echo(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic POST endpoint that requires a JSON request body."""

    return {"status": "ok", "received": payload}


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    """Backward-compatible alias for the unified browser workbench."""

    return DEMO_HTML


@app.post("/api/v1/documents/parse")
def parse_document(request: DocumentParseRequest) -> dict[str, Any]:
    """Parse a supported requirement file without introducing multipart dependencies."""

    suffix = Path(request.filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise HTTPException(status_code=400, detail=f"暂不支持该文件类型，可使用：{supported}")
    try:
        content = base64.b64decode(request.content_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="文件内容编码无效") from exc
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="单个需求文档不能超过 10 MB")
    try:
        text = load_document_bytes(content, suffix)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "filename": request.filename,
        "suffix": suffix,
        "characters": len(text),
        "text": text,
    }


@app.post("/api/v1/tasks", status_code=202)
def create_task(request: TaskCreateRequest) -> dict[str, str]:
    task_id = str(uuid4())
    task_store.create(
        task_id,
        payload={
            "source": "api",
            "execution_enabled": request.execution_config.enabled,
        },
    )

    task_args = [
        task_id,
        request.requirement_text,
        request.llm_settings.model_dump(),
        request.generation_config.model_dump(),
        request.execution_config.model_dump(),
    ]
    eager = os.getenv("REQ2TEST_EAGER_TASKS", "false").lower() in {"1", "true", "yes"}
    if eager:
        generate_test_cases.apply(args=task_args)
    else:
        async_result = generate_test_cases.delay(*task_args)
        task_store.update(task_id, celery_task_id=async_result.id)

    return {
        "task_id": task_id,
        "status_url": f"/api/v1/tasks/{task_id}",
        "ws_url": f"/ws/tasks/{task_id}",
    }


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
