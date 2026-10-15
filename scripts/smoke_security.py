"""Isolated real API -> RabbitMQ -> Celery -> HTTP/Pytest -> PostgreSQL/Redis smoke."""

import argparse
import base64
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit

import httpx
from sqlalchemy import create_engine, text

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-dir", type=pathlib.Path, required=True)
args = parser.parse_args()
out = args.output_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
source = pathlib.Path(__file__).resolve().parents[1]
env = os.environ.copy()
if env.get("REQ2TEST_ENV") != "test":
    raise SystemExit("This smoke requires REQ2TEST_ENV=test and disposable local services")
for key in ("DATABASE_URL", "REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
    if urlsplit(env.get(key, "")).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit(f"{key} must point at a disposable loopback service")
if urlsplit(env["DATABASE_URL"]).path != "/req2test_security_test":
    raise SystemExit("Only the dedicated req2test_security_test database is allowed")
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
origin = f"http://127.0.0.1:{port}"
env["REQ2TEST_TRUSTED_ORIGINS"] = origin
env["AUTH_COOKIE_SECURE"] = "false"
env["REQ2TEST_CHROMA_DIR"] = str(out / "smoke-chroma")
processes = []
handles = []
results = {}
started = time.perf_counter()


def command(name, args):
    with (out / f"{name}.log").open("w") as stream:
        subprocess.run(
            [sys.executable, *args],
            cwd=source,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=60,
        )


def launch(name, args):
    stream = (out / f"{name}.log").open("w")
    handles.append(stream)
    process = subprocess.Popen(
        [sys.executable, *args], cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT
    )
    processes.append(process)
    return process


def wait_for(check, label, timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError(f"Timed out: {label}")


try:
    command("smoke-migrate", ["-m", "alembic", "upgrade", "head"])
    command("smoke-seed", ["-m", "req2test.kb_cli", "seed"])
    api = launch(
        "smoke-api",
        ["-m", "uvicorn", "req2test.api:app", "--host", "127.0.0.1", "--port", str(port)],
    )
    worker = launch(
        "smoke-worker",
        [
            "-m",
            "celery",
            "-A",
            "req2test.worker.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=INFO",
        ],
    )
    with httpx.Client(
        base_url=origin, headers={"Origin": origin}, timeout=5, trust_env=False
    ) as client:

        def ready():
            try:
                response = client.get("/ready")
                return response.json() if response.status_code == 200 else None
            except httpx.RequestError:
                return None

        results["ready"] = wait_for(ready, "readiness")
        user = {
            "email": f"security-{uuid.uuid4().hex}@example.test",
            "password": "Synthetic-Local-Password-Only!",
        }
        registered = client.post("/api/v1/auth/register", json=user)
        assert registered.status_code == 201
        login = client.post("/api/v1/auth/login", json=user)
        assert login.status_code == 200 and login.json()["access_token"]
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.get("/workbench").status_code == 200
        results["browser_login"] = True
        rejected = client.post(
            "/api/v1/tasks",
            headers={"Origin": "https://untrusted.example.test"},
            json={"requirement_text": "synthetic"},
        )
        assert rejected.status_code == 403
        results["untrusted_cookie_mutation"] = rejected.status_code
        assert client.get("/api/v1/knowledge/documents").status_code == 200
        search = client.post("/api/v1/knowledge/search", json={"query": "401 token", "top_k": 3})
        assert search.status_code == 200
        results["knowledge_search"] = True

        # Promote only this newly generated account in the disposable test database.
        upload = {
            "filename": f"security-{uuid.uuid4().hex}.md",
            "content_base64": base64.b64encode(
                b"# Local rule\n\nValidate contract HTTP 422."
            ).decode(),
        }
        assert client.post("/api/v1/knowledge/documents", json=upload).status_code == 403
        engine = create_engine(env["DATABASE_URL"])
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET role='admin' WHERE id=:id"), {"id": registered.json()["id"]}
            )
        engine.dispose()
        assert client.get("/api/v1/admin/dashboard").status_code == 200
        created = client.post("/api/v1/knowledge/documents", json=upload)
        assert created.status_code == 201, created.text
        document_id = created.json()["id"]
        assert created.json()["index_status"] == "indexed"
        assert client.get(f"/api/v1/knowledge/documents/{document_id}").status_code == 200
        assert client.post(f"/api/v1/knowledge/documents/{document_id}/reindex").status_code == 200
        assert client.post("/api/v1/knowledge/rebuild").status_code == 200
        matches = client.post("/api/v1/knowledge/search", json={"query": "HTTP 422", "top_k": 20})
        assert matches.status_code == 200 and any(
            item["document_id"] == document_id for item in matches.json()["items"]
        )
        assert client.delete(f"/api/v1/knowledge/documents/{document_id}").status_code == 204
        assert client.get(f"/api/v1/knowledge/documents/{document_id}").status_code == 404
        results["knowledge_real_chroma_crud_reindex_rebuild"] = True
        results["admin_rbac"] = True

        def task_finished(task_id):
            data = client.get(f"/api/v1/tasks/{task_id}").json()
            if data.get("status") == "failed":
                raise AssertionError(data.get("error"))
            return data if data.get("status") == "completed" else None

        cases = {
            "pass": [
                {
                    "case_id": "GET",
                    "name": "health",
                    "path": "/demo-target/health",
                    "expected_json_contains": {"status": "ok"},
                },
                {
                    "case_id": "POST",
                    "name": "echo",
                    "method": "POST",
                    "path": "/demo-target/echo",
                    "headers": {"Authorization": "Bearer SYNTHETIC_EXECUTION_HEADER"},
                    "json_body": {"message": "hello", "token": "SYNTHETIC_EXECUTION_TOKEN"},
                    "expected_json_contains": {"received": {"token": "SYNTHETIC_EXECUTION_TOKEN"}},
                },
            ],
            "failure_422": [
                {
                    "case_id": "MISSING",
                    "name": "missing body",
                    "method": "POST",
                    "path": "/demo-target/echo",
                    "expected_status": 200,
                }
            ],
        }
        task_ids = []
        for label, specs in cases.items():
            response = client.post(
                "/api/v1/tasks",
                json={
                    "requirement_text": "GET /demo-target/health\nPOST /demo-target/echo",
                    "llm_settings": {"mode": "demo"},
                    "generation_config": {"max_cases": 4},
                    "execution_config": {"enabled": True, "base_url": origin, "api_specs": specs},
                },
            )
            assert response.status_code == 202, response.text
            task_id = response.json()["task_id"]
            task_ids.append(task_id)
            detail = wait_for(lambda task_id=task_id: task_finished(task_id), label)
            summary = detail["execution"]["summary"]
            assert summary["pytest_passed"] is (label == "pass"), summary
            assert summary["failed_http_cases"] == (0 if label == "pass" else 1), summary
            assert "SYNTHETIC_EXECUTION_TOKEN" not in json.dumps(detail)
            assert "SYNTHETIC_EXECUTION_HEADER" not in json.dumps(detail)
            diagnostics = client.get(f"/api/v1/tasks/{task_id}/diagnostics")
            assert diagnostics.status_code == 200
            assert "SYNTHETIC_EXECUTION_TOKEN" not in diagnostics.text
            results[label] = summary
            print("Completed", label, flush=True)

        from websockets.sync.client import connect

        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        with connect(
            origin.replace("http://", "ws://") + f"/ws/tasks/{task_ids[0]}",
            origin=origin,
            additional_headers={"Cookie": cookie},
        ) as ws:
            message = ws.recv(timeout=5)
            assert "completed" in message and "SYNTHETIC_EXECUTION_TOKEN" not in message
        results["websocket"] = True

        datasets = client.get("/api/v1/evaluations/datasets")
        assert datasets.status_code == 200
        evaluation = client.post(
            "/api/v1/evaluations/runs",
            json={
                "dataset_name": "golden_demo",
                "configuration": {
                    "llm_settings": {"mode": "demo"},
                    "generation_config": {"max_cases": 30},
                },
            },
        )
        assert evaluation.status_code == 202, evaluation.text
        evaluation_data = evaluation.json()
        run_id = evaluation_data["run"]["id"]

        def evaluation_finished():
            value = client.get(f"/api/v1/evaluations/runs/{run_id}").json()
            if value.get("status") == "failed":
                raise AssertionError(value.get("failure_reason"))
            return value if value.get("status") == "completed" else None

        evaluated = wait_for(evaluation_finished, "evaluation")
        results["evaluation"] = {"status": evaluated["status"], "score": evaluated["overall_score"]}
        assert evaluated["overall_score"] >= 80
        # Bearer clients work without a browser Origin or cookie.
        token = login.json()["access_token"]
        with httpx.Client(
            base_url=origin, headers={"Authorization": f"Bearer {token}"}, trust_env=False
        ) as bearer:
            response = bearer.post(
                "/api/v1/tasks", json={"requirement_text": "synthetic bearer task"}
            )
            assert response.status_code == 202
            wait_for(lambda: task_finished(response.json()["task_id"]), "bearer task")
        results["bearer_api"] = True
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
        results["logout"] = True

    engine = create_engine(env["DATABASE_URL"])
    with engine.connect() as connection:
        payloads = (
            connection.execute(
                text("SELECT result_payload FROM tasks WHERE result_payload IS NOT NULL")
            )
            .scalars()
            .all()
        )
        assert payloads and "SYNTHETIC_EXECUTION_TOKEN" not in json.dumps(payloads)
    engine.dispose()
    results["postgres_redaction"] = True
finally:
    for process in reversed(processes):
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    for stream in handles:
        stream.close()
    results["seconds"] = round(time.perf_counter() - started, 2)
    (out / "smoke-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

worker_log = (out / "smoke-worker.log").read_text()
for sentinel in (
    "SYNTHETIC_EXECUTION_HEADER",
    "SYNTHETIC_EXECUTION_TOKEN",
    "Synthetic-Local-Password-Only!",
):
    assert sentinel not in worker_log
results["worker_log_redaction"] = True
(out / "smoke-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(json.dumps(results, ensure_ascii=False, indent=2))
