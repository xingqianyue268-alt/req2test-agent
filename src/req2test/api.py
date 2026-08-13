"""FastAPI service for asynchronous Req2Test generation, execution and progress streaming."""

from __future__ import annotations

import asyncio
import base64
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import GenerationConfig, LLMSettings
from .auth_api import router as auth_router
from .auth_ui import render_auth_html
from .db.services.task_persistence import (
    DatabasePersistenceError,
    LiveProjectionUnavailable,
    TaskDispatchError,
    TaskPersistenceService,
)
from .db.session import database_is_ready, get_db
from .demo_ui import render_demo_html
from .document_loader import SUPPORTED_SUFFIXES, load_document_bytes
from .execution_models import ExecutionConfig
from .readiness import rabbitmq_is_ready, redis_is_ready
from .db.models import UserORM
from .db.repositories import users as user_repository
from .security.dependencies import get_optional_current_user
from .security.tokens import InvalidAccessToken, decode_access_token
from .settings import get_settings
from .task_store import task_store
from .worker import generate_test_cases

app = FastAPI(title="Req2Test Agent API", version="0.5.0")
app.include_router(auth_router)


def _publish_task(task_args: list[Any], eager: bool) -> str:
    result = (
        generate_test_cases.apply(args=task_args)
        if eager
        else generate_test_cases.delay(*task_args)
    )
    return str(result.id or task_args[0])


task_persistence = TaskPersistenceService(task_store, _publish_task)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    requirement_text: str = Field(min_length=1)
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
    execution_config: ExecutionConfig = Field(default_factory=ExecutionConfig)


class DocumentParseRequest(BaseModel):
    filename: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)


def task_actor(
    current_user: UserORM | None = Depends(get_optional_current_user),
) -> UserORM | None:
    if current_user is None and not get_settings().allow_anonymous_demo:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: report only whether the FastAPI process can respond."""

    return {"status": "ok", "task_store": task_store.backend}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Report whether every dependency required for new asynchronous tasks is ready."""

    checks = {
        "database": "ok" if database_is_ready() else "down",
        "redis": "ok" if redis_is_ready(task_store) else "down",
        "rabbitmq": "ok" if rabbitmq_is_ready() else "down",
    }
    payload = {"ready": all(value == "ok" for value in checks.values()), "checks": checks}
    if not payload["ready"]:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.get("/", include_in_schema=False)
def home_page() -> RedirectResponse:
    """Send the application root to the primary product route."""

    return RedirectResponse(url="/workbench", status_code=307)


@app.get("/workbench", response_class=HTMLResponse)
def workbench_page(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("req2test_access_token")
    if not token:
        return RedirectResponse(url="/login?next=/workbench", status_code=307)
    try:
        payload = decode_access_token(token)
        user = user_repository.get_user_by_id(db, uuid.UUID(payload["sub"]))
    except (InvalidAccessToken, ValueError, TypeError):
        user = None
    if user is None or not user.is_active:
        response = RedirectResponse(url="/login?next=/workbench", status_code=307)
        response.delete_cookie("req2test_access_token", path="/")
        return response
    return render_demo_html("workbench")


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return render_auth_html("login")


@app.get("/register", response_class=HTMLResponse)
def register_page() -> str:
    return render_auth_html("register")


@app.get("/workflow", response_class=HTMLResponse)
def workflow_page() -> str:
    return render_demo_html("workflow")


@app.get("/system", response_class=HTMLResponse)
def system_page() -> str:
    return render_demo_html("system")


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

    return render_demo_html("workbench")


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
def create_task(
    request: TaskCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserORM | None = Depends(task_actor),
) -> dict[str, str]:
    eager = os.getenv("REQ2TEST_EAGER_TASKS", "false").lower() in {"1", "true", "yes"}
    try:
        task = task_persistence.create_and_dispatch(
            db,
            requirement_text=request.requirement_text,
            title=request.title,
            llm_settings=request.llm_settings.model_dump(),
            generation_config=request.generation_config.model_dump(),
            execution_config=request.execution_config.model_dump(),
            eager=eager,
            user_id=current_user.id if current_user else None,
        )
    except (DatabasePersistenceError, LiveProjectionUnavailable, TaskDispatchError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = str(task.id)

    return {
        "task_id": task_id,
        "status_url": f"/api/v1/tasks/{task_id}",
        "ws_url": f"/ws/tasks/{task_id}",
    }


@app.get("/api/v1/tasks")
def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserORM | None = Depends(task_actor),
):
    if current_user is None:
        return {"items": [], "page": page, "page_size": page_size}
    return {
        "items": task_persistence.list_task_states(
            db,
            user_id=current_user.id,
            is_admin=current_user.role == "admin",
            page=page,
            page_size=page_size,
        ),
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/v1/tasks/{task_id}")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: UserORM | None = Depends(task_actor),
):
    try:
        state = task_persistence.get_task_state(
            db,
            task_id,
            user_id=current_user.id if current_user else None,
            is_admin=bool(current_user and current_user.role == "admin"),
            allow_anonymous=current_user is None and get_settings().allow_anonymous_demo,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL task lookup failed") from exc
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state


@app.websocket("/ws/tasks/{task_id}")
async def task_progress(
    websocket: WebSocket, task_id: str, db: Session = Depends(get_db)
) -> None:
    current_user = None
    token = websocket.cookies.get("req2test_access_token")
    if token:
        try:
            payload = decode_access_token(token)
            current_user = user_repository.get_user_by_id(db, uuid.UUID(payload["sub"]))
        except (InvalidAccessToken, ValueError, TypeError):
            current_user = None
        if current_user is None or not current_user.is_active:
            await websocket.close(code=4401, reason="Authentication required")
            return
    elif not get_settings().allow_anonymous_demo:
        await websocket.close(code=4401, reason="Authentication required")
        return

    authorized_state = task_persistence.get_task_state(
        db,
        task_id,
        user_id=current_user.id if current_user else None,
        is_admin=bool(current_user and current_user.role == "admin"),
        allow_anonymous=current_user is None and get_settings().allow_anonymous_demo,
    )
    if authorized_state is None:
        await websocket.close(code=4404, reason="Task not found")
        return
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
