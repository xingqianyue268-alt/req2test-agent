from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import req2test.api as api_module
from req2test.db.models import TaskORM
from req2test.db.repositories import users
from req2test.db.services.task_persistence import TaskPersistenceService, task_to_projection
from req2test.db.session import get_db
from req2test.security.passwords import hash_password
from req2test.settings import Settings
from req2test.task_store import TaskStore
from req2test.task_ui import render_tasks_html


PASSWORD = "correct horse battery staple"


def test_task_ui_renders_javascript_newline_escapes_safely():
    html = render_tasks_html()
    assert "join('\\n')" in html
    assert "join('\\n\\n')" in html
    assert "join('\n')" not in html


def _settings():
    return Settings(
        database_url="postgresql+psycopg://unused",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout=1,
        environment="test",
        jwt_secret_key="task-product-test-secret-that-is-long-enough",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        allow_anonymous_demo=False,
        auth_cookie_secure=False,
    )


def _client(db_session, monkeypatch):
    def override_db():
        yield db_session

    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=True)
    service = TaskPersistenceService(store, lambda args, eager: f"celery-{args[0]}")
    api_module.app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(api_module, "task_persistence", service)
    monkeypatch.setattr(api_module, "task_store", store)
    monkeypatch.setattr(api_module, "get_settings", _settings)
    return TestClient(api_module.app), service, store


def _user(db_session, email, role="user"):
    record = users.create_user(
        db_session,
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    db_session.commit()
    return record


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200


def _payload(*, failed=False):
    http_result = {
        "case_id": "API-002" if failed else "API-001",
        "method": "POST" if failed else "GET",
        "url": "http://api:8000/demo-target/echo",
        "expected_status": 200,
        "status_code": 422 if failed else 200,
        "duration_ms": 12.4,
        "passed": not failed,
    }
    failure = (
        [
            {
                "case_id": "API-002",
                "category": "contract_mismatch",
                "probable_cause": "Schema validation rejected the request",
                "evidence": ["expected 200, actual 422"],
                "suggestion": "Send the required request body",
            }
        ]
        if failed
        else []
    )
    diagnosis_v2 = {
        "trace_id": "trace-product",
        "summary": {
            "failure_count": 1 if failed else 0,
            "category_distribution": {"contract_mismatch": 1} if failed else {},
            "primary_failure_category": "contract_mismatch" if failed else None,
        },
        "diagnoses": (
            [
                {
                    "case_id": "API-002",
                    "category": "contract_mismatch",
                    "confidence": "high",
                    "probable_cause": "Request validation failed with HTTP 422",
                    "evidence_refs": ["evidence-422"],
                    "evidence_summary": ["Request reached endpoint but failed validation"],
                    "suggestion": "Compare required fields and request types",
                    "diagnosis_source": "rule",
                }
            ]
            if failed
            else []
        ),
    }
    return {
        "trace_id": "trace-product",
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "module": "API",
                "description": "GET /demo-target/health",
                "acceptance_criteria": ["returns 200"],
            }
        ],
        "test_cases": [
            {
                "case_id": "TC-001",
                "module": "API",
                "title": "Health contract",
                "priority": "P1",
                "test_type": "positive",
                "source_requirement": "REQ-001",
                "preconditions": ["API is running"],
                "steps": [{"order": 1, "action": "Call API", "expected": "200"}],
            }
        ],
        "review": {"score": 94, "coverage_rate": 1.0, "issues": [], "suggestions": []},
        "retrieved_context": ["HTTP contract testing guidance"],
        "execution": {
            "enabled": True,
            "summary": {
                "total_http_cases": 1,
                "passed_http_cases": 0 if failed else 1,
                "failed_http_cases": 1 if failed else 0,
                "http_pass_rate": 0.0 if failed else 1.0,
                "pytest_passed": not failed,
            },
            "executable_cases": [],
            "http_results": [http_result],
            "pytest_result": {
                "passed": not failed,
                "failed_count": 1 if failed else 0,
                "duration_ms": 20,
                "exit_code": 1 if failed else 0,
            },
            "failure_analysis": failure,
            "failure_analysis_v2": diagnosis_v2,
            "diagnostic_evidence": (
                [
                    {
                        "evidence_id": "evidence-422",
                        "trace_id": "trace-product",
                        "task_id": "task-product",
                        "case_id": "API-002",
                        "execution_id": "API-002",
                        "stage": "http_validation",
                        "evidence_type": "validation",
                        "timestamp": "2026-08-13T00:00:00Z",
                        "summary": "Request reached endpoint but failed validation",
                        "details": {
                            "expected_status": 200,
                            "actual_status": 422,
                            "validation_error": "missing body.message",
                        },
                        "severity": "error",
                    }
                ]
                if failed
                else []
            ),
            "evidence_collection_overhead_ms": 0.7,
            "warnings": [],
        },
        "errors": [],
    }


def _task(db_session, owner, *, title, status="completed", created_at=None, failed=False):
    payload = _payload(failed=failed) if status in {"completed", "failed"} else None
    record = TaskORM(
        id=uuid.uuid4(),
        user_id=owner.id,
        title=title,
        requirement_text=f"Requirement text for {title}",
        status=status,
        stage=status,
        progress=100 if status in {"completed", "failed"} else 30,
        state_version=3,
        generation_config={},
        execution_config={"enabled": True},
        result_summary=(
            {
                "total_test_cases": 1,
                "review_score": 94,
                "http_pass_rate": 0.0 if failed else 1.0,
                "pytest_passed": not failed,
                "failure_analysis_count": 1 if failed else 0,
                "primary_failure_category": "contract_mismatch" if failed else None,
                "failure_category_counts": {"contract_mismatch": 1} if failed else {},
            }
            if payload
            else None
        ),
        result_payload=payload,
        completed_at=(created_at or datetime.now(timezone.utc)) if payload else None,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_task_list_scoping_filters_pagination_and_summary_dto(db_session, monkeypatch):
    client, _, _ = _client(db_session, monkeypatch)
    user_a = _user(db_session, "product-a@example.com")
    user_b = _user(db_session, "product-b@example.com")
    _user(db_session, "product-admin@example.com", role="admin")
    now = datetime.now(timezone.utc)
    old_a = _task(
        db_session,
        user_a,
        title="Legacy checkout",
        status="failed",
        failed=True,
        created_at=now - timedelta(days=10),
    )
    new_a = _task(db_session, user_a, title="Current checkout", created_at=now)
    task_b = _task(db_session, user_b, title="Other tenant checkout", created_at=now)
    try:
        _login(client, user_a.email)
        page = client.get("/api/v1/tasks?page=1&page_size=1").json()
        assert page["total"] == 2 and page["pages"] == 2
        assert page["items"][0]["id"] == str(new_a.id)
        assert "requirement_text" not in page["items"][0]
        assert "result_payload" not in page["items"][0]
        assert page["items"][0]["summary"]["review_score"] == 94

        failed = client.get("/api/v1/tasks?status=failed").json()
        assert [item["id"] for item in failed["items"]] == [str(old_a.id)]
        keyword = client.get("/api/v1/tasks?keyword=Current").json()
        assert [item["id"] for item in keyword["items"]] == [str(new_a.id)]
        cutoff = (now - timedelta(days=1)).isoformat()
        recent = client.get("/api/v1/tasks", params={"created_from": cutoff}).json()
        assert [item["id"] for item in recent["items"]] == [str(new_a.id)]
        client.post("/api/v1/auth/logout")

        _login(client, user_b.email)
        assert [item["id"] for item in client.get("/api/v1/tasks").json()["items"]] == [
            str(task_b.id)
        ]
        client.post("/api/v1/auth/logout")

        _login(client, "product-admin@example.com")
        admin_items = client.get("/api/v1/tasks?page_size=20").json()["items"]
        assert {str(old_a.id), str(new_a.id), str(task_b.id)} <= {
            item["id"] for item in admin_items
        }
        assert all("user_email" in item for item in admin_items)
    finally:
        api_module.app.dependency_overrides.clear()

def test_structured_detail_permissions_pass_failure_raw_and_postgres_priority(
    db_session, monkeypatch
):
    client, service, store = _client(db_session, monkeypatch)
    user_a = _user(db_session, "detail-a@example.com")
    user_b = _user(db_session, "detail-b@example.com")
    _user(db_session, "detail-admin@example.com", role="admin")
    passed = _task(db_session, user_a, title="PASS detail")
    failed = _task(db_session, user_a, title="FAIL detail", failed=True)
    store.set(
        str(passed.id),
        {
            **task_to_projection(passed),
            "status": "running",
            "stage": "http_execution",
            "progress": 80,
            "state_version": 99,
            "result": None,
        },
    )
    try:
        _login(client, user_a.email)
        pass_detail = client.get(f"/api/v1/tasks/{passed.id}")
        assert pass_detail.status_code == 200
        body = pass_detail.json()
        assert body["status"] == "completed"
        assert body["task"]["title"] == "PASS detail"
        assert body["requirements"] and body["test_cases"]
        assert body["review"]["score"] == 94
        assert body["rag"]["retrieved_context"]
        assert body["execution"]["http_results"][0]["passed"] is True
        assert body["failure_analysis"] == []
        assert body["raw_payload"]["test_cases"]

        store._memory.clear()
        failure_body = client.get(f"/api/v1/tasks/{failed.id}").json()
        assert failure_body["failure_analysis"][0]["category"] == "contract_mismatch"
        assert failure_body["failure_analysis_v2"]["diagnoses"][0]["confidence"] == "high"
        assert "diagnostic_evidence" not in failure_body["raw_payload"]["execution"]
        assert store.get(str(failed.id))["status"] == "completed"
        client.post("/api/v1/auth/logout")

        _login(client, user_b.email)
        assert client.get(f"/api/v1/tasks/{passed.id}").status_code == 404
        assert client.get(f"/api/v1/tasks/{failed.id}").status_code == 404
        client.post("/api/v1/auth/logout")

        _login(client, "detail-admin@example.com")
        assert client.get(f"/api/v1/tasks/{passed.id}").status_code == 200
        assert client.get(f"/api/v1/tasks/{failed.id}").status_code == 200
        assert service
    finally:
        api_module.app.dependency_overrides.clear()


def test_task_product_routes_are_protected_and_include_local_exports(db_session, monkeypatch):
    client, _, _ = _client(db_session, monkeypatch)
    user = _user(db_session, "routes@example.com")
    task = _task(db_session, user, title="Route task")
    try:
        assert client.get("/tasks", follow_redirects=False).status_code == 307
        assert client.get(f"/tasks/{task.id}", follow_redirects=False).status_code == 307
        _login(client, user.email)
        history = client.get("/tasks")
        detail = client.get(f"/tasks/{task.id}")
        assert history.status_code == detail.status_code == 200
        assert "TEST\nHISTORY." in history.text
        assert "TASK\nDETAIL." in detail.text
        assert "EXPORT MARKDOWN" in detail.text
        assert "EXPORT CSV" in detail.text
        assert "EXPORT JSON" in detail.text
        assert "/api/v1/tasks/" in detail.text
        assert "VIEW EVIDENCE / 查看详细证据" in detail.text
        assert "PRIMARY FAILURE" in history.text
    finally:
        api_module.app.dependency_overrides.clear()


def test_diagnostics_api_ownership_admin_access_and_redis_fallback(db_session, monkeypatch):
    client, _, store = _client(db_session, monkeypatch)
    user_a = _user(db_session, "diagnostics-a@example.com")
    user_b = _user(db_session, "diagnostics-b@example.com")
    _user(db_session, "diagnostics-admin@example.com", role="admin")
    failed = _task(db_session, user_a, title="Timeout-style diagnosis", failed=True)
    try:
        _login(client, user_a.email)
        store._memory.clear()
        response = client.get(f"/api/v1/tasks/{failed.id}/diagnostics")
        assert response.status_code == 200
        body = response.json()
        assert body["trace_id"] == "trace-product"
        assert body["summary"]["primary_failure_category"] == "contract_mismatch"
        assert body["diagnoses"][0]["evidence_refs"] == ["evidence-422"]
        assert body["evidence"][0]["details"]["actual_status"] == 422
        assert store.get(str(failed.id))["status"] == "completed"
        client.post("/api/v1/auth/logout")

        _login(client, user_b.email)
        assert client.get(f"/api/v1/tasks/{failed.id}/diagnostics").status_code == 404
        client.post("/api/v1/auth/logout")

        _login(client, "diagnostics-admin@example.com")
        assert client.get(f"/api/v1/tasks/{failed.id}/diagnostics").status_code == 200
    finally:
        api_module.app.dependency_overrides.clear()
