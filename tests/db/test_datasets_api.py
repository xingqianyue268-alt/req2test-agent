"""Data import keeps Cookie/Bearer security, durable ownership and secret boundaries."""

import base64
import json
import uuid

from test_openapi_api import client as client  # noqa: PLC0414 - shared pytest fixture

from req2test.db.repositories.tasks import get_task


def plan():
    return {
        "base_url": "http://127.0.0.1:8081",
        "template": {
            "case_id": "login",
            "name": "login",
            "method": "POST",
            "path": "/login",
            "assertions": [
                {"path": "/access_token", "op": "eq", "expected": "private-synthetic-data"}
            ],
        },
        "dataset": {
            "filename": "rows.json",
            "content_base64": base64.b64encode(
                json.dumps(
                    [
                        {
                            "id": "ok",
                            "json_body": {"username": "demo", "password": "private-synthetic-data"},
                        }
                    ]
                ).encode()
            ).decode(),
        },
    }


def test_data_preview_dispatch_auth_and_no_encoding_leak(client, db_session):
    browser, captured, token = client
    assert browser.get("/datasets").status_code == 200
    preview = browser.post("/api/v1/datasets/preview", json=plan())
    assert preview.status_code == 200 and len(preview.json()["api_specs"]) == 1
    assert "private-synthetic-data" not in preview.text and not captured
    assert (
        browser.post(
            "/api/v1/datasets/preview", json=plan(), headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    created = browser.post(
        "/api/v1/tasks", json={"requirement_text": "data test", "data_driven": plan()}
    )
    assert created.status_code == 202
    task_id = created.json()["task_id"]
    assert get_task(db_session, uuid.UUID(task_id)).user_id is not None
    assert "private-synthetic-data" in json.dumps(captured)
    assert "content_base64" not in json.dumps(captured)
    assert browser.get(f"/api/v1/tasks/{task_id}/reports/junit.xml").status_code == 409
    browser.cookies.clear()
    assert browser.post("/api/v1/datasets/preview", json=plan()).status_code == 401
    assert browser.get(f"/api/v1/tasks/{task_id}/reports/junit.xml").status_code == 401
    assert (
        browser.post(
            "/api/v1/datasets/preview",
            json=plan(),
            headers={"Authorization": "Bearer " + token, "Origin": "https://api.invalid"},
        ).status_code
        == 200
    )


def test_data_invalid_input_never_echoes_credentials(client):
    browser, captured, _ = client
    body = plan()
    body["unexpected"] = "PRIVATE_UNTRUSTED_INPUT"
    result = browser.post("/api/v1/datasets/preview", json=body)
    assert result.status_code == 422 and "PRIVATE_UNTRUSTED_INPUT" not in result.text
    body = plan()
    body["base_url"] = "https://evil.invalid"
    assert browser.post("/api/v1/datasets/preview", json=body).status_code == 422
    assert not captured


def test_junit_completed_owned_task_and_cross_user_denial(client, db_session):
    import xml.etree.ElementTree as ET

    browser, _, _ = client
    created = browser.post(
        "/api/v1/tasks", json={"requirement_text": "data", "data_driven": plan()}
    )
    task_id = created.json()["task_id"]
    task = get_task(db_session, uuid.UUID(task_id))
    task.status = "completed"
    task.result_payload = {
        "execution": {
            "enabled": True,
            "summary": {"status": "completed"},
            "http_results": [
                {
                    "case_id": "row-1",
                    "data_id": "one",
                    "source": "data.json:1",
                    "passed": False,
                    "expected_status": 200,
                    "status_code": 422,
                    "failures": ["status mismatch"],
                    "request": {"json_body": {"password": "PRIVATE_EXPECTED"}},
                    "assertions": [
                        {
                            "path": "/access_token",
                            "kind": "eq",
                            "expected": "PRIVATE_EXPECTED",
                            "actual": "PRIVATE_ACTUAL",
                            "passed": False,
                        }
                    ],
                }
            ],
        }
    }
    db_session.flush()
    response = browser.get(f"/api/v1/tasks/{task_id}/reports/junit.xml")
    assert response.status_code == 200 and response.headers["content-type"].startswith(
        "application/xml"
    )
    assert ET.fromstring(response.text).attrib["failures"] == "1"
    assert "PRIVATE_" not in response.text
    browser.cookies.clear()
    other = {"email": "other-data@example.test", "password": "Synthetic-other-password!"}
    assert browser.post("/api/v1/auth/register", json=other).status_code == 201
    assert browser.post("/api/v1/auth/login", json=other).status_code == 200
    assert browser.get(f"/api/v1/tasks/{task_id}/reports/junit.xml").status_code == 404
