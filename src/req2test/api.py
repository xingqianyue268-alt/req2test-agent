"""FastAPI service for asynchronous Req2Test generation, execution and progress streaming."""

from __future__ import annotations

import asyncio
import base64
import os
import uuid
from datetime import datetime
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
from .task_ui import render_tasks_html
from .knowledge_ui import render_knowledge_html
from .admin_ui import render_admin_html, render_admin_forbidden_html
from .document_loader import SUPPORTED_SUFFIXES, load_document_bytes
from .execution_models import ExecutionConfig
from .readiness import rabbitmq_is_ready, redis_is_ready
from .db.models import UserORM
from .db.repositories import users as user_repository
from .security.dependencies import get_current_user, get_optional_current_user, require_roles
from .services.knowledge_service import (
    DuplicateKnowledgeDocument,
    KnowledgeDeleteError,
    KnowledgeIndexError,
    KnowledgeService,
    document_dto,
)
from .services.admin_service import AdminService, LastActiveAdminError, user_dto
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
knowledge_service = KnowledgeService()
admin_service = AdminService()


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


class KnowledgeUploadRequest(DocumentParseRequest):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    kind: str = Field(default="testing_rule", min_length=1, max_length=64)


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class AdminUserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class AdminUserRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(user|admin)$")


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


def _web_user(request: Request, db: Session) -> UserORM | None:
    token = request.cookies.get("req2test_access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user = user_repository.get_user_by_id(db, uuid.UUID(payload["sub"]))
    except (InvalidAccessToken, ValueError, TypeError):
        return None
    return user if user and user.is_active else None


def _login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=307)


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
    if _web_user(request, db) is None:
        response = _login_redirect(request)
        response.delete_cookie("req2test_access_token", path="/")
        return response
    return render_demo_html("workbench")


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session = Depends(get_db)):
    if _web_user(request, db) is None:
        return _login_redirect(request)
    return render_tasks_html()


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail_page(task_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    if _web_user(request, db) is None:
        return _login_redirect(request)
    return render_tasks_html(str(task_id))


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, db: Session = Depends(get_db)):
    if _web_user(request, db) is None:
        return _login_redirect(request)
    return render_knowledge_html()


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/{view}", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db), view: str = "overview"):
    if view not in {"overview", "users", "tasks", "knowledge", "system"}:
        raise HTTPException(status_code=404, detail="Admin view not found")
    current_user = _web_user(request, db)
    if current_user is None:
        return _login_redirect(request)
    if current_user.role != "admin":
        return HTMLResponse(render_admin_forbidden_html(), status_code=403)
    return render_admin_html(view)


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


@app.get("/demo-target/timeout")
async def demo_target_timeout(delay_seconds: float = Query(default=1.25, ge=0.6, le=3.0)):
    """Local-only deterministic latency fixture for Failure Analysis V2."""

    await asyncio.sleep(delay_seconds)
    return {"status": "late", "delay_seconds": delay_seconds}


@app.get("/demo-target/protected")
def demo_target_protected():
    """Credential-free 401 fixture; it never accepts or logs real credentials."""

    raise HTTPException(status_code=401, detail="Demo authentication required")


@app.get("/demo-target/upstream-error")
def demo_target_upstream_error():
    """Deterministic target-service 500 fixture, distinct from platform exceptions."""

    raise HTTPException(status_code=500, detail="Demo upstream service failure")


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


@app.get("/api/v1/knowledge/documents")
def list_knowledge_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: UserORM = Depends(get_current_user),
):
    return knowledge_service.list(db, page=page, page_size=page_size)


@app.get("/api/v1/knowledge/documents/{document_id}")
def get_knowledge_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_user: UserORM = Depends(get_current_user),
):
    document = knowledge_service.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return document_dto(document, include_content=True)


@app.post("/api/v1/knowledge/documents", status_code=201)
def upload_knowledge_document(
    request: KnowledgeUploadRequest,
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    try:
        document = knowledge_service.upload(
            db,
            filename=request.filename,
            content_base64=request.content_base64,
            title=request.title,
            kind=request.kind,
        )
    except DuplicateKnowledgeDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KnowledgeIndexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return document_dto(document, include_content=True)


@app.delete("/api/v1/knowledge/documents/{document_id}", status_code=204)
def delete_knowledge_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
) -> None:
    document = knowledge_service.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    try:
        knowledge_service.delete(db, document)
    except KnowledgeDeleteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/knowledge/documents/{document_id}/reindex")
def reindex_knowledge_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    document = knowledge_service.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    try:
        return document_dto(knowledge_service.reindex(db, document), include_content=True)
    except KnowledgeIndexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/knowledge/rebuild")
def rebuild_knowledge(
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    try:
        return knowledge_service.rebuild(db)
    except KnowledgeIndexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/knowledge/search")
def search_knowledge(
    request: KnowledgeSearchRequest,
    _current_user: UserORM = Depends(get_current_user),
):
    return {"items": knowledge_service.search(request.query, top_k=request.top_k)}


@app.get("/api/v1/admin/dashboard")
def admin_dashboard(
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    return admin_service.dashboard(db)


@app.get("/api/v1/admin/users")
def admin_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    return admin_service.list_users(db, page=page, page_size=page_size)


@app.patch("/api/v1/admin/users/{user_id}/status")
def admin_update_user_status(
    user_id: uuid.UUID,
    request: AdminUserStatusRequest,
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    try:
        user = admin_service.set_status(db, user_id=user_id, is_active=request.is_active)
    except LastActiveAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_dto(user)


@app.patch("/api/v1/admin/users/{user_id}/role")
def admin_update_user_role(
    user_id: uuid.UUID,
    request: AdminUserRoleRequest,
    db: Session = Depends(get_db),
    _admin: UserORM = Depends(require_roles("admin")),
):
    try:
        user = admin_service.set_role(db, user_id=user_id, role=request.role)
    except LastActiveAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_dto(user)


@app.get("/api/v1/admin/tasks")
def admin_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(queued|running|completed|failed)$"),
    keyword: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    admin: UserORM = Depends(require_roles("admin")),
):
    return task_persistence.list_task_states(
        db,
        user_id=admin.id,
        is_admin=True,
        page=page,
        page_size=page_size,
        status=status,
        keyword=keyword,
    )


@app.get("/api/v1/admin/system")
def admin_system(_admin: UserORM = Depends(require_roles("admin"))):
    try:
        knowledge_count = knowledge_service._kb().count()
        knowledge_state = "HEALTHY"
    except Exception:  # noqa: BLE001 - status endpoint translates backend failures
        knowledge_count = None
        knowledge_state = "UNAVAILABLE"
    return {
        "services": [
            {"name": "PostgreSQL", "state": "HEALTHY" if database_is_ready() else "UNAVAILABLE", "basis": "probe"},
            {"name": "Redis", "state": "HEALTHY" if redis_is_ready(task_store) else "UNAVAILABLE", "basis": "probe"},
            {"name": "RabbitMQ", "state": "HEALTHY" if rabbitmq_is_ready() else "UNAVAILABLE", "basis": "probe"},
            {"name": "Celery Worker", "state": "CONFIGURED", "basis": "configuration"},
            {"name": "Chroma / Knowledge", "state": knowledge_state, "basis": "probe", "documents": knowledge_count},
            {"name": "Task Store", "state": "CONFIGURED", "basis": task_store.backend},
            {"name": "WebSocket", "state": "CONFIGURED", "basis": "application"},
            {"name": "Pytest", "state": "CONFIGURED", "basis": "capability"},
            {"name": "Failure Analysis", "state": "CONFIGURED", "basis": "capability"},
        ]
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
    status: str | None = Query(default=None, pattern="^(queued|running|completed|failed)$"),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    keyword: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    current_user: UserORM | None = Depends(task_actor),
):
    if current_user is None:
        return {"items": [], "page": page, "page_size": page_size, "total": 0, "pages": 0}
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=422, detail="created_from must not exceed created_to")
    return task_persistence.list_task_states(
        db,
        user_id=current_user.id,
        is_admin=current_user.role == "admin",
        page=page,
        page_size=page_size,
        status=status,
        created_from=created_from,
        created_to=created_to,
        keyword=keyword,
    )


@app.get("/api/v1/tasks/{task_id}")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: UserORM | None = Depends(task_actor),
):
    try:
        state = task_persistence.get_task_detail(
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


@app.get("/api/v1/tasks/{task_id}/diagnostics")
def get_task_diagnostics(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: UserORM | None = Depends(task_actor),
):
    try:
        diagnostics = task_persistence.get_task_diagnostics(
            db,
            task_id,
            user_id=current_user.id if current_user else None,
            is_admin=bool(current_user and current_user.role == "admin"),
            allow_anonymous=current_user is None and get_settings().allow_anonymous_demo,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL diagnostics lookup failed") from exc
    if diagnostics is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return diagnostics


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
